"""네이버 DataLab & 검색 API 커넥터"""
import httpx
import structlog
from datetime import date, timedelta
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import settings

logger = structlog.get_logger(__name__)

NAVER_DATALAB_BASE = "https://openapi.naver.com/v1/datalab"
NAVER_SEARCH_BASE = "https://openapi.naver.com/v1/search"


class NaverConnector:
    """네이버 DataLab 트렌드 수집 커넥터"""

    def __init__(self) -> None:
        self.headers = {
            "X-Naver-Client-Id": settings.naver_client_id,
            "X-Naver-Client-Secret": settings.naver_client_secret,
            "Content-Type": "application/json",
        }
        self.client = httpx.Client(timeout=30.0)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=5))
    def get_search_trends(
        self,
        keywords: list[str],
        start_date: str | None = None,
        end_date: str | None = None,
        time_unit: str = "date",
    ) -> list[dict]:
        """네이버 DataLab 검색어 트렌드 조회

        Args:
            keywords: 키워드 리스트 (최대 5개 그룹, 그룹당 5개 키워드)
            start_date: 시작일 (YYYY-MM-DD, 기본: 30일 전)
            end_date: 종료일 (YYYY-MM-DD, 기본: 오늘)
            time_unit: 시간 단위 (date/week/month)

        Returns:
            트렌드 데이터 리스트
        """
        if not start_date:
            start_date = (date.today() - timedelta(days=30)).isoformat()
        if not end_date:
            end_date = date.today().isoformat()

        # 키워드를 그룹으로 분할 (최대 5개 그룹)
        keyword_groups = [
            {
                "groupName": kw,
                "keywords": [kw],
            }
            for kw in keywords[:5]
        ]

        body = {
            "startDate": start_date,
            "endDate": end_date,
            "timeUnit": time_unit,
            "keywordGroups": keyword_groups,
        }

        resp = self.client.post(
            f"{NAVER_DATALAB_BASE}/search",
            json=body,
            headers=self.headers,
        )
        resp.raise_for_status()
        data = resp.json()

        logger.info(
            "naver.get_search_trends.done",
            keywords=keywords,
            period=f"{start_date}~{end_date}",
        )
        return data.get("results", [])

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=5))
    def search_blog(self, query: str, display: int = 10) -> list[dict]:
        """네이버 블로그 검색 (경쟁 포스트 분석용)

        Args:
            query: 검색 쿼리
            display: 결과 수 (최대 100)

        Returns:
            블로그 포스트 목록
        """
        resp = self.client.get(
            f"{NAVER_SEARCH_BASE}/blog",
            params={"query": query, "display": display, "sort": "sim"},
            headers=self.headers,
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
        logger.info("naver.search_blog.done", query=query, count=len(items))
        return items

    def close(self) -> None:
        self.client.close()
