"""유튜브 스크립트 + 메타데이터 생성기 (Claude API + Supabase 저장)"""
from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Optional

import structlog
from supabase import create_client, Client

from src.config import settings
from src.connectors.claude import ClaudeConnector
from src.trend.content_queue import ContentQueue

logger = structlog.get_logger(__name__)

YOUTUBE_SYSTEM_PROMPT = """당신은 한국 유튜브 채널을 위한 영상 스크립트와 메타데이터를 작성하는 전문가입니다.

작성 원칙:
- 첫 5초 안에 시청자의 관심을 사로잡는 강력한 훅(Hook)
- 훅 → 본론(문제/해결/사례) → 결론(CTA) 구조
- 자연스럽게 말할 수 있는 구어체 스크립트
- SEO를 위한 제목·설명란 키워드 배치
- 쿠팡 파트너스 링크 삽입이 자연스러운 제품 언급 포함
- 구독·좋아요 유도 문구 포함

출력 형식은 반드시 유효한 JSON이어야 합니다."""


def _get_supabase() -> Client:
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


class YouTubeGenerator:
    """Claude API 기반 유튜브 스크립트 + 메타데이터 생성기"""

    def __init__(self, claude: Optional[ClaudeConnector] = None) -> None:
        self._claude = claude or ClaudeConnector()
        self._queue = ContentQueue()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def generate_from_queue(
        self,
        target_date: Optional[str] = None,
        limit: int = 1,
    ) -> list[dict]:
        """content_queue에서 pending 유튜브 주제를 꺼내 스크립트 생성

        Args:
            target_date: ISO date string (없으면 오늘)
            limit: 최대 생성 수 (기본 1 — 일별 1편 생성)

        Returns:
            생성된 유튜브 영상 메타데이터 + 스크립트 목록
        """
        from datetime import date
        parsed_date = date.fromisoformat(target_date) if target_date else date.today()

        pending = self._queue.get_pending_topics(
            target_date=parsed_date,
            content_type="youtube",
        )[:limit]

        if not pending:
            logger.info("youtube_generator.no_pending_topics", date=str(parsed_date))
            return []

        results: list[dict] = []
        for topic_row in pending:
            queue_id = topic_row.get("id", "")
            try:
                self._queue.mark_generating(queue_id)
                video = self.generate_single(
                    title=topic_row.get("title", ""),
                    primary_keyword=topic_row.get("primary_keyword", ""),
                    seo_keywords=json.loads(topic_row.get("seo_keywords", "[]")),
                    angle=topic_row.get("angle", ""),
                    target_audience=topic_row.get("target_audience", ""),
                    queue_id=queue_id,
                )
                results.append(video)
                logger.info("youtube_generator.video_done", queue_id=queue_id, title=video["title"])
            except Exception as exc:
                logger.error("youtube_generator.error", queue_id=queue_id, error=str(exc))
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
        """단일 유튜브 스크립트 + 메타데이터 생성 & Supabase 저장"""
        t0 = time.time()

        all_keywords = [primary_keyword] + [k for k in seo_keywords if k != primary_keyword]

        user_prompt = self._build_prompt(
            title=title,
            primary_keyword=primary_keyword,
            keywords=all_keywords[:8],
            angle=angle,
            target_audience=target_audience,
        )

        logger.info("youtube_generator.claude_call", title=title)
        raw = self._claude.generate(
            system_prompt=YOUTUBE_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            max_tokens=5000,
            temperature=0.8,
        )
        generation_ms = int((time.time() - t0) * 1000)

        raw = raw.strip().removeprefix("```json").removesuffix("```").strip()
        data = json.loads(raw)

        video_row = self._save_to_supabase(
            data=data,
            queue_id=queue_id,
            generation_ms=generation_ms,
        )

        if queue_id:
            self._queue.mark_published(queue_id, publish_url="")

        return video_row

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
        audience_hint = f"\n타겟 시청자: {target_audience}" if target_audience else ""
        return (
            f"주제: {title}\n"
            f"메인 키워드: {primary_keyword}\n"
            f"SEO 키워드: {', '.join(keywords)}"
            f"{angle_hint}{audience_hint}\n\n"
            "위 주제로 유튜브 영상 스크립트와 메타데이터를 작성하세요.\n"
            "스크립트는 7~10분 분량(약 1400~2000 단어)으로 작성합니다.\n\n"
            "반환 형식 (유효한 JSON):\n"
            "{\n"
            '  "title": "유튜브 제목 (60자 이내, 클릭 유도, 메인 키워드 포함)",\n'
            '  "description": "영상 설명란 (첫 2줄에 핵심 키워드, 총 500자, 타임스탬프·링크 자리 표시 포함)",\n'
            '  "tags": ["태그1", "태그2", ...],\n'
            '  "thumbnail_concept": "썸네일 텍스트·이미지 컨셉 설명 (2~3문장)",\n'
            '  "script": "영상 스크립트 (훅 → 본론 → CTA, 구어체, 자막 형식)"\n'
            "}"
        )

    def _save_to_supabase(self, data: dict, queue_id: str, generation_ms: int) -> dict:
        """생성된 유튜브 메타데이터+스크립트를 Supabase youtube_videos 테이블에 저장"""
        row = {
            "queue_id": queue_id or None,
            "title": data.get("title", ""),
            "description": data.get("description", ""),
            "tags": data.get("tags", []),
            "thumbnail_concept": data.get("thumbnail_concept", ""),
            "script": data.get("script", ""),
            "status": "draft",
            "ai_model": settings.claude_model,
            "generation_ms": generation_ms,
            "created_at": datetime.now().isoformat(),
        }
        try:
            supabase = _get_supabase()
            resp = supabase.table("youtube_videos").insert(row).execute()
            saved = resp.data[0] if resp.data else row
            logger.info("youtube_generator.supabase_saved", id=saved.get("id"))
            return saved
        except Exception as exc:
            logger.error("youtube_generator.supabase_error", error=str(exc))
            return {**row, "error": str(exc)}
