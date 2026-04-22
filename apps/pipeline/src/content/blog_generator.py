"""블로그 포스트 생성기 (Claude API + Supabase 저장)"""
from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Optional
from uuid import UUID

import structlog
from supabase import create_client, Client

from src.config import settings
from src.connectors.claude import ClaudeConnector
from src.trend.content_queue import ContentQueue

logger = structlog.get_logger(__name__)

BLOG_SYSTEM_PROMPT = """당신은 한국 독자를 위한 SEO 최적화 블로그 포스트를 작성하는 전문 작가입니다.

작성 원칙:
- 자연스럽고 읽기 쉬운 한국어 사용
- SEO를 위해 주요 키워드를 제목·소제목·본문에 자연스럽게 배치
- 독자에게 실질적인 가치를 제공하는 정보성 콘텐츠
- 마크다운 형식: H1 제목, H2/H3 소제목, 단락, 목록 구조 활용
- 구매 결정을 돕는 CTA(Call-to-Action) 포함

출력 형식은 반드시 유효한 JSON이어야 합니다."""


def _get_supabase() -> Client:
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


class BlogGenerator:
    """Claude API 기반 블로그 포스트 생성기"""

    def __init__(self, claude: Optional[ClaudeConnector] = None) -> None:
        self._claude = claude or ClaudeConnector()
        self._queue = ContentQueue()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def generate_from_queue(
        self,
        target_date: Optional[str] = None,
        limit: int = 5,
    ) -> list[dict]:
        """content_queue에서 pending 블로그 주제를 꺼내 콘텐츠 생성

        Args:
            target_date: ISO date string (없으면 오늘)
            limit: 최대 생성 수

        Returns:
            생성된 블로그 포스트 목록 (각 항목은 Supabase 저장 결과)
        """
        from datetime import date
        parsed_date = date.fromisoformat(target_date) if target_date else date.today()

        pending = self._queue.get_pending_topics(
            target_date=parsed_date,
            content_type="blog",
        )[:limit]

        if not pending:
            logger.info("blog_generator.no_pending_topics", date=str(parsed_date))
            return []

        results: list[dict] = []
        for topic_row in pending:
            queue_id = topic_row.get("id", "")
            try:
                self._queue.mark_generating(queue_id)
                post = self.generate_single(
                    title=topic_row.get("title", ""),
                    primary_keyword=topic_row.get("primary_keyword", ""),
                    seo_keywords=json.loads(topic_row.get("seo_keywords", "[]")),
                    angle=topic_row.get("angle", ""),
                    target_audience=topic_row.get("target_audience", ""),
                    queue_id=queue_id,
                )
                results.append(post)
                logger.info("blog_generator.post_done", queue_id=queue_id, title=post["title"])
            except Exception as exc:
                logger.error("blog_generator.error", queue_id=queue_id, error=str(exc))
                results.append({"queue_id": queue_id, "error": str(exc), "status": "failed"})

        return results

    def generate_single(
        self,
        title: str,
        primary_keyword: str,
        seo_keywords: list[str],
        angle: str = "",
        target_audience: str = "",
        queue_id: str = "",
    ) -> dict:
        """단일 블로그 포스트 생성 & Supabase 저장"""
        t0 = time.time()

        all_keywords = [primary_keyword] + [k for k in seo_keywords if k != primary_keyword]

        user_prompt = self._build_prompt(
            title=title,
            primary_keyword=primary_keyword,
            keywords=all_keywords[:8],
            angle=angle,
            target_audience=target_audience,
        )

        logger.info("blog_generator.claude_call", title=title)
        raw = self._claude.generate(
            system_prompt=BLOG_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            max_tokens=4000,
            temperature=0.75,
        )
        generation_ms = int((time.time() - t0) * 1000)

        raw = raw.strip().removeprefix("```json").removesuffix("```").strip()
        data = json.loads(raw)

        post_row = self._save_to_supabase(
            data=data,
            queue_id=queue_id,
            generation_ms=generation_ms,
        )

        if queue_id:
            self._queue.mark_published(queue_id, publish_url="")  # URL은 업로드 시 채움

        return post_row

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _build_prompt(
        self,
        title: str,
        primary_keyword: str,
        keywords: list[str],
        angle: str,
        target_audience: str,
    ) -> str:
        angle_hint = f"\n콘텐츠 각도: {angle}" if angle else ""
        audience_hint = f"\n타겟 독자: {target_audience}" if target_audience else ""
        return (
            f"주제 제목: {title}\n"
            f"메인 키워드: {primary_keyword}\n"
            f"SEO 키워드: {', '.join(keywords)}"
            f"{angle_hint}{audience_hint}\n\n"
            "위 주제로 SEO 최적화 블로그 포스트를 작성하세요.\n\n"
            "반환 형식 (유효한 JSON):\n"
            "{\n"
            '  "title": "SEO 최적화 제목 (60자 이내, 메인 키워드 포함)",\n'
            '  "meta_description": "검색 결과에 표시될 설명 (120~160자, 행동 유도 포함)",\n'
            '  "content": "마크다운 본문 (H1 제목, H2/H3 소제목, 1800~2500자, 결론+CTA 포함)",\n'
            '  "tags": ["태그1", "태그2", "태그3", "태그4", "태그5"],\n'
            '  "seo_score_estimate": 85\n'
            "}"
        )

    def _save_to_supabase(self, data: dict, queue_id: str, generation_ms: int) -> dict:
        """생성된 블로그 포스트를 Supabase blog_posts 테이블에 저장"""
        row = {
            "queue_id": queue_id or None,
            "title": data.get("title", ""),
            "meta_description": data.get("meta_description", ""),
            "content": data.get("content", ""),
            "tags": data.get("tags", []),
            "seo_score": data.get("seo_score_estimate"),
            "status": "draft",
            "ai_model": settings.claude_model,
            "generation_ms": generation_ms,
            "created_at": datetime.now().isoformat(),
        }
        try:
            supabase = _get_supabase()
            resp = supabase.table("blog_posts").insert(row).execute()
            saved = resp.data[0] if resp.data else row
            logger.info("blog_generator.supabase_saved", id=saved.get("id"))
            return saved
        except Exception as exc:
            logger.error("blog_generator.supabase_error", error=str(exc))
            return {**row, "error": str(exc)}
