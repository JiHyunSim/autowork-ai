"""인스타그램 릴스 스크립트 + 캡션 생성기 (Claude API + Supabase 저장)"""
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

REELS_SYSTEM_PROMPT = """당신은 한국 인스타그램 릴스를 위한 스크립트와 캡션을 작성하는 숏폼 콘텐츠 전문가입니다.

작성 원칙:
- 첫 1초에 스크롤을 멈추게 하는 강력한 오프닝 훅
- 30~60초 분량의 간결하고 임팩트 있는 스크립트
- 감정을 자극하거나 호기심을 유발하는 훅 문구
- 영상 자막 형식으로 읽기 쉬운 짧은 문장
- 트렌디한 해시태그 (인기 태그 + 니치 태그 조합)
- 쿠팡 링크 유도 문구 ("링크 바이오" 등) 자연스럽게 포함

출력 형식은 반드시 유효한 JSON이어야 합니다."""


def _get_supabase() -> Client:
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


class ReelsGenerator:
    """Claude API 기반 릴스 스크립트 + 캡션 생성기"""

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
        """content_queue에서 pending 릴스 주제를 꺼내 스크립트 생성

        Args:
            target_date: ISO date string (없으면 오늘)
            limit: 최대 생성 수 (기본 1 — 일별 1편)

        Returns:
            생성된 릴스 스크립트 + 캡션 목록
        """
        from datetime import date

        parsed_date = date.fromisoformat(target_date) if target_date else date.today()

        pending = self._queue.get_pending_topics(
            target_date=parsed_date,
            content_type="reels",
        )[:limit]

        if not pending:
            logger.info("reels_generator.no_pending_topics", date=str(parsed_date))
            return []

        results: list[dict] = []
        for topic_row in pending:
            queue_id = topic_row.get("id", "")
            try:
                self._queue.mark_generating(queue_id)
                reel = self.generate_single(
                    title=topic_row.get("title", ""),
                    primary_keyword=topic_row.get("primary_keyword", ""),
                    seo_keywords=json.loads(topic_row.get("seo_keywords", "[]")),
                    angle=topic_row.get("angle", ""),
                    target_audience=topic_row.get("target_audience", ""),
                    queue_id=queue_id,
                )
                results.append(reel)
                logger.info("reels_generator.reel_done", queue_id=queue_id, title=reel.get("title"))
            except Exception as exc:
                logger.error("reels_generator.error", queue_id=queue_id, error=str(exc))
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
        """단일 릴스 스크립트 + 캡션 생성 & Supabase 저장"""
        t0 = time.time()

        all_keywords = [primary_keyword] + [k for k in seo_keywords if k != primary_keyword]

        user_prompt = self._build_prompt(
            title=title,
            primary_keyword=primary_keyword,
            keywords=all_keywords[:6],
            angle=angle,
            target_audience=target_audience,
        )

        logger.info("reels_generator.claude_call", title=title)
        raw = self._claude.generate(
            system_prompt=REELS_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            max_tokens=1500,
            temperature=0.85,
        )
        generation_ms = int((time.time() - t0) * 1000)

        raw = raw.strip().removeprefix("```json").removesuffix("```").strip()
        data = json.loads(raw)

        reel_row = self._save_to_supabase(
            data=data,
            queue_id=queue_id,
            generation_ms=generation_ms,
        )

        if queue_id:
            self._queue.mark_published(queue_id, publish_url="")

        return reel_row

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
        audience_hint = f"\n타겟 팔로워: {target_audience}" if target_audience else ""
        return (
            f"주제: {title}\n"
            f"메인 키워드: {primary_keyword}\n"
            f"관련 키워드: {', '.join(keywords)}"
            f"{angle_hint}{audience_hint}\n\n"
            "위 주제로 인스타그램 릴스 콘텐츠를 작성하세요.\n"
            "영상은 30~60초 분량입니다.\n\n"
            "반환 형식 (유효한 JSON):\n"
            "{\n"
            '  "title": "릴스 제목/훅 문구 (15자 이내, 강력한 임팩트)",\n'
            '  "script": "영상 자막 스크립트 (오프닝훅→본론→CTA, 줄바꿈으로 구분, 30~60초 분량)",\n'
            '  "caption": "인스타그램 캡션 (150자 이내, 이모지 포함, 행동 유도)",\n'
            '  "hashtags": ["#태그1", "#태그2", "#태그3", ...],\n'
            '  "video_concept": "영상 촬영 컨셉 설명 (배경·구도·분위기, 2~3문장)"\n'
            "}"
        )

    def _save_to_supabase(self, data: dict, queue_id: str, generation_ms: int) -> dict:
        """생성된 릴스 데이터를 Supabase reels_scripts 테이블에 저장"""
        row = {
            "queue_id": queue_id or None,
            "title": data.get("title", ""),
            "script": data.get("script", ""),
            "caption": data.get("caption", ""),
            "hashtags": data.get("hashtags", []),
            "video_concept": data.get("video_concept", ""),
            "status": "draft",
            "ai_model": settings.claude_model,
            "generation_ms": generation_ms,
            "created_at": datetime.now().isoformat(),
        }
        try:
            supabase = _get_supabase()
            resp = supabase.table("reels_scripts").insert(row).execute()
            saved = resp.data[0] if resp.data else row
            logger.info("reels_generator.supabase_saved", id=saved.get("id"))
            return saved
        except Exception as exc:
            logger.error("reels_generator.supabase_error", error=str(exc))
            return {**row, "error": str(exc)}
