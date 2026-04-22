"""인스타그램 릴스 자동 업로드 모듈 (Phase 4)"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

import structlog
from supabase import create_client, Client

from src.config import settings
from src.connectors.instagram import InstagramConnector

logger = structlog.get_logger(__name__)


def _get_supabase() -> Client:
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def _build_caption(caption: str, hashtags: list[str]) -> str:
    """캡션 + 해시태그 결합"""
    tags_str = " ".join(hashtags) if hashtags else ""
    if tags_str:
        return f"{caption}\n\n{tags_str}"
    return caption


class InstagramUploader:
    """reels_scripts 테이블의 draft 항목을 Instagram에 발행"""

    def __init__(self, connector: Optional[InstagramConnector] = None) -> None:
        self._instagram = connector or InstagramConnector()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def upload_pending(self, limit: int = 1) -> list[dict]:
        """reels_scripts.status = 'draft' 항목을 일괄 업로드 (기본 1개)

        영상 파일이 없는 경우 'scheduled' 상태로 표시하고 스크립트만 보존.

        Returns:
            업로드 결과 목록
        """
        db = _get_supabase()
        rows = (
            db.table("reels_scripts")
            .select("id, title, script, caption, hashtags, video_url")
            .eq("status", "draft")
            .limit(limit)
            .execute()
        ).data

        if not rows:
            logger.info("instagram_uploader.no_draft_reels")
            return []

        results = []
        for row in rows:
            video_url = row.get("video_url") or ""
            try:
                if video_url:
                    result = self.upload_reel(row)
                    results.append({"reel_id": row["id"], "success": True, "action": "uploaded", **result})
                else:
                    self._mark_scheduled(row["id"])
                    results.append({
                        "reel_id": row["id"],
                        "success": True,
                        "action": "scheduled",
                        "note": "영상 URL 없음 — 스크립트 저장 완료, 영상 준비 후 재시도 필요",
                    })
            except Exception as exc:
                logger.error("instagram_uploader.error", reel_id=row["id"], error=str(exc))
                self._mark_failed(row["id"], str(exc))
                results.append({"reel_id": row["id"], "success": False, "error": str(exc)})

        return results

    def upload_reel(self, reel: dict) -> dict:
        """단일 릴스 Instagram Graph API로 업로드

        Args:
            reel: reels_scripts 테이블 행

        Returns:
            {"instagram_media_id": "...", "instagram_url": "..."}
        """
        logger.info("instagram_uploader.upload", reel_id=reel.get("id"), title=reel.get("title"))

        hashtags = reel.get("hashtags") or []
        full_caption = _build_caption(
            caption=reel.get("caption", ""),
            hashtags=hashtags if isinstance(hashtags, list) else [],
        )

        response = self._instagram.upload_reel(
            video_url=reel["video_url"],
            caption=full_caption,
        )

        media_id = response.get("mediaId", "")
        permalink = response.get("permalink", "")

        self._mark_published(
            reel_id=reel["id"],
            media_id=media_id,
            instagram_url=permalink,
        )

        return {"instagram_media_id": media_id, "instagram_url": permalink}

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    def _mark_published(self, reel_id: str, media_id: str, instagram_url: str) -> None:
        db = _get_supabase()
        db.table("reels_scripts").update({
            "status": "published",
            "instagram_media_id": media_id,
            "instagram_url": instagram_url,
            "published_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("id", reel_id).execute()

    def _mark_scheduled(self, reel_id: str) -> None:
        db = _get_supabase()
        db.table("reels_scripts").update({
            "status": "scheduled",
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("id", reel_id).execute()

    def _mark_failed(self, reel_id: str, error: str) -> None:
        db = _get_supabase()
        db.table("reels_scripts").update({
            "status": "failed",
            "error_message": error,
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("id", reel_id).execute()
