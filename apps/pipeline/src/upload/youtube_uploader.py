"""유튜브 자동 업로드 모듈 (Phase 4)"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

import structlog
from supabase import create_client, Client

from src.config import settings
from src.connectors.youtube import YouTubeConnector

logger = structlog.get_logger(__name__)


def _get_supabase() -> Client:
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


class YouTubeUploader:
    """youtube_videos 테이블의 draft 항목을 YouTube에 발행"""

    def __init__(self, connector: Optional[YouTubeConnector] = None) -> None:
        self._youtube = connector or YouTubeConnector()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def upload_pending(self, limit: int = 1) -> list[dict]:
        """youtube_videos.status = 'draft' 항목을 일괄 업로드 (기본 1개)

        영상 파일이 없는 경우 'scheduled' 상태로 표시하고 스크립트만 보존.

        Returns:
            업로드 결과 목록
        """
        db = _get_supabase()
        rows = (
            db.table("youtube_videos")
            .select("id, title, description, tags, script, video_file_path")
            .eq("status", "draft")
            .limit(limit)
            .execute()
        ).data

        if not rows:
            logger.info("youtube_uploader.no_draft_videos")
            return []

        results = []
        for row in rows:
            video_path = row.get("video_file_path") or ""
            try:
                if video_path and os.path.exists(video_path):
                    result = self.upload_video_file(row)
                    results.append({"video_id": row["id"], "success": True, "action": "uploaded", **result})
                else:
                    # 영상 파일 없음 → 예약(scheduled) 상태로 표시
                    self._mark_scheduled(row["id"])
                    results.append({
                        "video_id": row["id"],
                        "success": True,
                        "action": "scheduled",
                        "note": "영상 파일 없음 — 스크립트 저장 완료, 렌더링 후 재시도 필요",
                    })
            except Exception as exc:
                logger.error("youtube_uploader.error", video_id=row["id"], error=str(exc))
                self._mark_failed(row["id"], str(exc))
                results.append({"video_id": row["id"], "success": False, "error": str(exc)})

        return results

    def upload_video_file(self, video: dict) -> dict:
        """단일 유튜브 영상 업로드

        Args:
            video: youtube_videos 테이블 행

        Returns:
            {"youtube_video_id": "...", "youtube_url": "..."}
        """
        logger.info("youtube_uploader.upload", video_id=video.get("id"), title=video.get("title"))

        tags = video.get("tags") or []

        response = self._youtube.upload_video(
            video_path=video["video_file_path"],
            title=video["title"],
            description=video.get("description", ""),
            tags=tags if isinstance(tags, list) else [],
        )

        youtube_video_id = response.get("id", "")
        youtube_url = f"https://www.youtube.com/watch?v={youtube_video_id}"

        self._mark_published(
            video_id=video["id"],
            youtube_video_id=youtube_video_id,
        )

        return {"youtube_video_id": youtube_video_id, "youtube_url": youtube_url}

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    def _mark_published(self, video_id: str, youtube_video_id: str) -> None:
        db = _get_supabase()
        db.table("youtube_videos").update({
            "status": "published",
            "youtube_video_id": youtube_video_id,
            "published_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("id", video_id).execute()

    def _mark_scheduled(self, video_id: str) -> None:
        db = _get_supabase()
        db.table("youtube_videos").update({
            "status": "scheduled",
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("id", video_id).execute()

    def _mark_failed(self, video_id: str, error: str) -> None:
        db = _get_supabase()
        db.table("youtube_videos").update({
            "status": "failed",
            "error_message": error,
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("id", video_id).execute()
