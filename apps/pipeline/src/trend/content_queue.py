"""일별 콘텐츠 큐 — 생성 & Supabase 저장"""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Optional

import structlog
from supabase import create_client, Client

from src.config import settings
from src.trend.trend_collector import TrendCollector, TrendKeyword
from src.trend.topic_selector import TopicSelector, ContentTopic

logger = structlog.get_logger(__name__)


def _get_supabase() -> Client:
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


class ContentQueue:
    """일별 콘텐츠 큐 관리 클래스"""

    def __init__(
        self,
        collector: Optional[TrendCollector] = None,
        selector: Optional[TopicSelector] = None,
    ) -> None:
        self._collector = collector or TrendCollector()
        self._selector = selector or TopicSelector()

    # ------------------------------------------------------------------ #
    # 큐 생성 (매일 오전 6시 실행 대상)
    # ------------------------------------------------------------------ #

    def build_daily_queue(
        self,
        target_date: Optional[date] = None,
        naver_keyword_groups: Optional[list[dict]] = None,
    ) -> dict:
        """일별 콘텐츠 큐 생성 & DB 저장

        Returns:
            {
                "date": "2026-04-22",
                "topics": [...],
                "saved_count": 8,
                "run_id": "..."
            }
        """
        target_date = target_date or date.today()
        logger.info("content_queue.build", date=str(target_date))

        # 1. 트렌드 수집
        trends: list[TrendKeyword] = self._collector.collect_all(
            naver_keyword_groups=naver_keyword_groups
        )

        if not trends:
            logger.warning("content_queue.no_trends")
            return {"date": str(target_date), "topics": [], "saved_count": 0}

        # 2. 주제 선정
        topics: list[ContentTopic] = self._selector.select_daily_topics(
            trends=trends,
            blog_count=settings.daily_blog_target,
            youtube_count=1,
            reels_count=settings.daily_reels_target,
        )

        # 3. Supabase 저장
        saved_count = self._save_to_supabase(topics, target_date)

        result = {
            "date": str(target_date),
            "topics": [self._topic_to_dict(t) for t in topics],
            "saved_count": saved_count,
        }

        logger.info("content_queue.build.done", saved=saved_count)
        return result

    # ------------------------------------------------------------------ #
    # Supabase CRUD
    # ------------------------------------------------------------------ #

    def _save_to_supabase(self, topics: list[ContentTopic], target_date: date) -> int:
        """콘텐츠 큐를 Supabase content_queue 테이블에 저장"""
        if not topics:
            return 0

        try:
            supabase = _get_supabase()
            rows = [
                {
                    "scheduled_date": str(target_date),
                    "content_type": t.content_type,
                    "title": t.title,
                    "primary_keyword": t.primary_keyword,
                    "seo_keywords": json.dumps(t.seo_keywords, ensure_ascii=False),
                    "related_products": json.dumps(t.related_products, ensure_ascii=False),
                    "angle": t.angle,
                    "target_audience": t.target_audience,
                    "estimated_search_volume": t.estimated_search_volume,
                    "affiliate_potential": t.affiliate_potential,
                    "status": "pending",  # pending → generating → published
                    "created_at": datetime.now().isoformat(),
                }
                for t in topics
            ]

            resp = supabase.table("content_queue").insert(rows).execute()
            count = len(resp.data) if resp.data else 0
            logger.info("content_queue.supabase_saved", count=count)
            return count

        except Exception as exc:
            logger.error("content_queue.supabase_error", error=str(exc))
            return 0

    def get_pending_topics(
        self,
        target_date: Optional[date] = None,
        content_type: Optional[str] = None,
    ) -> list[dict]:
        """pending 상태 주제 목록 조회"""
        target_date = target_date or date.today()
        try:
            supabase = _get_supabase()
            query = (
                supabase.table("content_queue")
                .select("*")
                .eq("scheduled_date", str(target_date))
                .eq("status", "pending")
            )
            if content_type:
                query = query.eq("content_type", content_type)

            resp = query.order("created_at").execute()
            return resp.data or []
        except Exception as exc:
            logger.error("content_queue.get_pending.error", error=str(exc))
            return []

    def mark_generating(self, queue_id: str) -> bool:
        """주제를 generating 상태로 변경"""
        try:
            supabase = _get_supabase()
            supabase.table("content_queue").update(
                {"status": "generating", "updated_at": datetime.now().isoformat()}
            ).eq("id", queue_id).execute()
            return True
        except Exception as exc:
            logger.error("content_queue.mark_generating.error", error=str(exc))
            return False

    def mark_published(self, queue_id: str, publish_url: str) -> bool:
        """주제를 published 상태로 변경 (발행 URL 저장)"""
        try:
            supabase = _get_supabase()
            supabase.table("content_queue").update(
                {
                    "status": "published",
                    "publish_url": publish_url,
                    "published_at": datetime.now().isoformat(),
                }
            ).eq("id", queue_id).execute()
            return True
        except Exception as exc:
            logger.error("content_queue.mark_published.error", error=str(exc))
            return False

    # ------------------------------------------------------------------ #
    # 헬퍼
    # ------------------------------------------------------------------ #

    @staticmethod
    def _topic_to_dict(t: ContentTopic) -> dict:
        return {
            "title": t.title,
            "content_type": t.content_type,
            "primary_keyword": t.primary_keyword,
            "seo_keywords": t.seo_keywords,
            "related_products": t.related_products,
            "angle": t.angle,
            "target_audience": t.target_audience,
            "estimated_search_volume": t.estimated_search_volume,
            "affiliate_potential": t.affiliate_potential,
        }
