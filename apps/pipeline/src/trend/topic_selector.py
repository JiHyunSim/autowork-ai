"""주제 선정 & SEO 키워드 분석 모듈 (Claude API)"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

import structlog

from src.connectors.claude import ClaudeConnector
from src.trend.trend_collector import TrendKeyword

logger = structlog.get_logger(__name__)

SYSTEM_PROMPT = """당신은 한국어 콘텐츠 전략가이자 SEO 전문가입니다.
트렌드 데이터를 분석하여 최적의 블로그/유튜브/릴스 주제를 선정하고,
각 주제에 대한 SEO 키워드와 콘텐츠 전략을 제안합니다.

다음 기준으로 주제를 평가합니다:
1. 검색 볼륨 및 트렌드 상승세
2. 광고 수익 잠재력 (쿠팡 제휴 연계 가능성)
3. 콘텐츠 제작 용이성 및 차별화 가능성
4. 한국 독자/시청자 관심도"""


@dataclass
class ContentTopic:
    """선정된 콘텐츠 주제"""
    title: str
    content_type: str          # "blog" | "youtube" | "reels"
    primary_keyword: str
    seo_keywords: list[str] = field(default_factory=list)
    related_products: list[str] = field(default_factory=list)  # 쿠팡 연계 상품 힌트
    angle: str = ""            # 콘텐츠 각도/접근 방식
    target_audience: str = ""
    estimated_search_volume: str = ""  # "high" | "medium" | "low"
    affiliate_potential: str = ""      # "high" | "medium" | "low"


class TopicSelector:
    """Claude API 기반 주제 선정 클래스"""

    def __init__(self, claude: Optional[ClaudeConnector] = None) -> None:
        self._claude = claude or ClaudeConnector()

    def select_daily_topics(
        self,
        trends: list[TrendKeyword],
        blog_count: int = 5,
        youtube_count: int = 1,  # 일별 (주 3회 → 하루 1회 실행으로 계산)
        reels_count: int = 1,
    ) -> list[ContentTopic]:
        """일별 콘텐츠 주제 선정

        Returns:
            총 (blog_count + youtube_count + reels_count)개의 ContentTopic 목록
        """
        if not trends:
            logger.warning("topic_selector.empty_trends")
            return []

        # 상위 30개 트렌드만 사용 (컨텍스트 최적화)
        top_trends = trends[:30]
        trends_text = "\n".join(
            f"- {t.keyword} (점수: {t.score:.2f}, 출처: {t.source})"
            + (f", 연관: {', '.join(t.related[:3])}" if t.related else "")
            for t in top_trends
        )

        user_prompt = f"""오늘의 트렌드 데이터:
{trends_text}

위 트렌드를 바탕으로 다음 콘텐츠 주제를 선정해 주세요:
- 블로그 포스트: {blog_count}개
- 유튜브 영상: {youtube_count}개
- 인스타그램 릴스: {reels_count}개

각 주제는 쿠팡 파트너스 제휴 링크 삽입이 자연스럽게 가능한 주제를 우선 선정해 주세요.

다음 JSON 형식으로 반환하세요:
{{
  "topics": [
    {{
      "title": "콘텐츠 제목 (구체적으로)",
      "content_type": "blog",
      "primary_keyword": "메인 SEO 키워드",
      "seo_keywords": ["키워드1", "키워드2", "키워드3", "키워드4", "키워드5"],
      "related_products": ["연관 상품1", "연관 상품2"],
      "angle": "콘텐츠 각도/차별화 포인트",
      "target_audience": "타겟 독자층",
      "estimated_search_volume": "high",
      "affiliate_potential": "high"
    }}
  ]
}}"""

        logger.info("topic_selector.claude_request", trend_count=len(top_trends))

        try:
            raw = self._claude.generate(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
                max_tokens=4000,
                temperature=0.8,
            )
            raw = raw.strip().removeprefix("```json").removesuffix("```").strip()
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.error("topic_selector.json_parse_error", error=str(exc))
            return []
        except Exception as exc:
            logger.error("topic_selector.claude_error", error=str(exc))
            return []

        topics: list[ContentTopic] = []
        for item in data.get("topics", []):
            topics.append(
                ContentTopic(
                    title=item.get("title", ""),
                    content_type=item.get("content_type", "blog"),
                    primary_keyword=item.get("primary_keyword", ""),
                    seo_keywords=item.get("seo_keywords", []),
                    related_products=item.get("related_products", []),
                    angle=item.get("angle", ""),
                    target_audience=item.get("target_audience", ""),
                    estimated_search_volume=item.get("estimated_search_volume", "medium"),
                    affiliate_potential=item.get("affiliate_potential", "medium"),
                )
            )

        logger.info("topic_selector.done", total=len(topics))
        return topics

    def analyze_keyword_seo(self, keyword: str) -> dict:
        """단일 키워드 SEO 분석"""
        user_prompt = f"""키워드 "{keyword}"에 대한 SEO 분석을 수행하세요.

다음 JSON 형식으로 반환:
{{
  "keyword": "{keyword}",
  "search_intent": "informational|commercial|navigational|transactional",
  "competition_level": "high|medium|low",
  "recommended_title_patterns": ["패턴1", "패턴2", "패턴3"],
  "lsi_keywords": ["LSI 키워드1", "LSI 키워드2", "LSI 키워드3"],
  "content_length_recommendation": "short|medium|long",
  "monetization_tips": "수익화 팁"
}}"""

        try:
            raw = self._claude.generate(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
                max_tokens=1000,
                temperature=0.5,
            )
            raw = raw.strip().removeprefix("```json").removesuffix("```").strip()
            return json.loads(raw)
        except Exception as exc:
            logger.error("seo_analysis.error", keyword=keyword, error=str(exc))
            return {"keyword": keyword, "error": str(exc)}
