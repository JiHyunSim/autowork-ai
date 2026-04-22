"""트렌드 수집기 — Google Trends + 네이버 DataLab + RSS"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

import httpx
import structlog
from pytrends.request import TrendReq

from src.config import settings

logger = structlog.get_logger(__name__)

# 한국 트렌드 대상 RSS 피드 목록
RSS_FEEDS = [
    # 네이버 뉴스 - IT/과학
    "https://news.naver.com/rss/main.xml",
    # 한경 경제
    "https://www.hankyung.com/feed/all-news",
    # ZDNet Korea
    "https://zdnet.co.kr/rss/news.xml",
]

# 네이버 DataLab Trending API endpoint
NAVER_DATALAB_URL = "https://openapi.naver.com/v1/datalab/search"


@dataclass
class TrendKeyword:
    """트렌드 키워드 단위"""
    keyword: str
    source: str          # "google_trends" | "naver_datalab" | "rss"
    score: float         # 정규화 점수 0.0~1.0
    related: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)


class TrendCollector:
    """멀티 소스 트렌드 수집 클래스"""

    def __init__(self) -> None:
        self._http = httpx.Client(timeout=20.0)

    # ------------------------------------------------------------------ #
    # Google Trends
    # ------------------------------------------------------------------ #

    def fetch_google_trends(
        self,
        keywords: Optional[list[str]] = None,
        geo: str = "KR",
        timeframe: str = "now 1-d",
    ) -> list[TrendKeyword]:
        """Google Trends 실시간 급상승 키워드 수집"""
        logger.info("google_trends.fetch", geo=geo)
        results: list[TrendKeyword] = []

        try:
            pytrends = TrendReq(hl="ko", tz=540, timeout=(10, 25))

            # 실시간 트렌딩 검색어 (한국)
            trending = pytrends.trending_searches(pn="south_korea")
            trending_list = trending[0].tolist()[:20]

            for rank, kw in enumerate(trending_list):
                score = 1.0 - (rank / len(trending_list))
                results.append(
                    TrendKeyword(keyword=kw, source="google_trends", score=score)
                )

            # 키워드가 주어진 경우 관련 쿼리도 수집
            if keywords:
                # pytrends는 한 번에 최대 5개 키워드 처리
                for chunk_start in range(0, len(keywords), 5):
                    chunk = keywords[chunk_start : chunk_start + 5]
                    pytrends.build_payload(chunk, timeframe=timeframe, geo=geo)
                    related = pytrends.related_queries()
                    for kw in chunk:
                        top_df = related.get(kw, {}).get("top")
                        if top_df is not None and not top_df.empty:
                            related_kws = top_df["query"].tolist()[:5]
                            # 기존 결과에 related 추가
                            for item in results:
                                if item.keyword == kw:
                                    item.related = related_kws
                    time.sleep(1)  # rate-limit 방지

        except Exception as exc:
            logger.warning("google_trends.error", error=str(exc))

        logger.info("google_trends.done", count=len(results))
        return results

    # ------------------------------------------------------------------ #
    # 네이버 DataLab
    # ------------------------------------------------------------------ #

    def fetch_naver_datalab(
        self,
        keyword_groups: list[dict],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> list[TrendKeyword]:
        """네이버 DataLab 검색어 트렌드 수집

        keyword_groups 형식:
          [{"groupName": "AI", "keywords": ["인공지능", "챗GPT"]}, ...]
        """
        if not settings.naver_client_id or not settings.naver_client_secret:
            logger.warning("naver_datalab.skip", reason="credentials_missing")
            return []

        if not keyword_groups:
            return []

        today = datetime.now()
        end_date = end_date or today.strftime("%Y-%m-%d")
        start_date = start_date or (today - timedelta(days=7)).strftime("%Y-%m-%d")

        payload = {
            "startDate": start_date,
            "endDate": end_date,
            "timeUnit": "date",
            "keywordGroups": keyword_groups,
        }

        logger.info("naver_datalab.fetch", groups=len(keyword_groups))
        results: list[TrendKeyword] = []

        try:
            resp = self._http.post(
                NAVER_DATALAB_URL,
                json=payload,
                headers={
                    "X-Naver-Client-Id": settings.naver_client_id,
                    "X-Naver-Client-Secret": settings.naver_client_secret,
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()

            for result in data.get("results", []):
                group_name = result["title"]
                # 최근 7일 평균 ratio를 점수로 활용
                ratios = [p["ratio"] for p in result.get("data", []) if "ratio" in p]
                avg_score = (sum(ratios) / len(ratios) / 100.0) if ratios else 0.0
                # 대표 키워드는 그룹의 첫 번째 키워드 사용
                keywords_list = next(
                    (g["keywords"] for g in keyword_groups if g["groupName"] == group_name),
                    [group_name],
                )
                results.append(
                    TrendKeyword(
                        keyword=keywords_list[0],
                        source="naver_datalab",
                        score=avg_score,
                        related=keywords_list[1:],
                    )
                )

        except Exception as exc:
            logger.warning("naver_datalab.error", error=str(exc))

        logger.info("naver_datalab.done", count=len(results))
        return results

    # ------------------------------------------------------------------ #
    # RSS 피드
    # ------------------------------------------------------------------ #

    def fetch_rss_keywords(self, feeds: Optional[list[str]] = None) -> list[TrendKeyword]:
        """RSS 피드에서 최근 기사 제목 키워드 추출"""
        feeds = feeds or RSS_FEEDS
        results: list[TrendKeyword] = []

        for feed_url in feeds:
            try:
                resp = self._http.get(feed_url, follow_redirects=True)
                resp.raise_for_status()
                titles = self._extract_titles_from_xml(resp.text)

                for i, title in enumerate(titles[:10]):
                    score = 1.0 - (i / max(len(titles[:10]), 1))
                    results.append(
                        TrendKeyword(keyword=title, source="rss", score=score * 0.6)
                    )
            except Exception as exc:
                logger.warning("rss.error", url=feed_url, error=str(exc))

        logger.info("rss.done", count=len(results))
        return results

    @staticmethod
    def _extract_titles_from_xml(xml_text: str) -> list[str]:
        """RSS XML에서 <title> 태그 내용 추출 (간단 파싱)"""
        import re
        # <title> 내용 추출 (채널 제목 제외를 위해 <item> 이후만 처리)
        item_section = xml_text.split("<item>", 1)[-1] if "<item>" in xml_text else xml_text
        titles = re.findall(r"<title>(?:<!\[CDATA\[)?(.+?)(?:\]\]>)?</title>", item_section)
        # HTML 엔티티 기본 정리
        cleaned = [t.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").strip() for t in titles]
        return [t for t in cleaned if t]

    # ------------------------------------------------------------------ #
    # 통합 수집
    # ------------------------------------------------------------------ #

    def collect_all(
        self,
        naver_keyword_groups: Optional[list[dict]] = None,
        google_seed_keywords: Optional[list[str]] = None,
    ) -> list[TrendKeyword]:
        """모든 소스에서 트렌드 수집 후 병합 & 정렬"""
        logger.info("trend_collector.collect_all.start")

        # 기본 네이버 DataLab 키워드 그룹
        if naver_keyword_groups is None:
            naver_keyword_groups = [
                {"groupName": "AI/ChatGPT", "keywords": ["챗GPT", "인공지능", "AI"]},
                {"groupName": "재테크", "keywords": ["주식", "부동산", "코인", "재테크"]},
                {"groupName": "건강", "keywords": ["다이어트", "건강", "영양제"]},
                {"groupName": "여행", "keywords": ["국내여행", "해외여행", "호텔"]},
                {"groupName": "쿠팡", "keywords": ["쿠팡", "쿠팡파트너스", "직구"]},
            ]

        all_trends: list[TrendKeyword] = []
        all_trends.extend(self.fetch_google_trends(keywords=google_seed_keywords))
        all_trends.extend(self.fetch_naver_datalab(keyword_groups=naver_keyword_groups))
        all_trends.extend(self.fetch_rss_keywords())

        # 중복 키워드 병합 (소스 다양성 보너스 점수 부여)
        merged = self._merge_and_score(all_trends)

        logger.info("trend_collector.collect_all.done", total=len(merged))
        return merged

    @staticmethod
    def _merge_and_score(trends: list[TrendKeyword]) -> list[TrendKeyword]:
        """동일 키워드 병합 및 종합 점수 계산"""
        keyword_map: dict[str, TrendKeyword] = {}

        for item in trends:
            key = item.keyword.lower().strip()
            if key in keyword_map:
                existing = keyword_map[key]
                # 소스 다양성 보너스 (다른 소스에서도 나타나면 점수 상승)
                if item.source != existing.source:
                    existing.score = min(1.0, existing.score + item.score * 0.3)
                existing.related = list(set(existing.related + item.related))
            else:
                keyword_map[key] = item

        return sorted(keyword_map.values(), key=lambda x: x.score, reverse=True)
