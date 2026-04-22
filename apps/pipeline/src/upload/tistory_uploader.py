"""티스토리 자동 업로드 모듈 (Phase 4)"""
from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Optional

import structlog
from supabase import create_client, Client

from src.config import settings
from src.connectors.tistory import TistoryConnector

logger = structlog.get_logger(__name__)


def _get_supabase() -> Client:
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def _markdown_to_html(content: str) -> str:
    """간단한 마크다운 → HTML 변환 (티스토리 API용)"""
    html = content
    # 제목 변환
    html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
    html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
    html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)
    # 굵게/기울임
    html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
    html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)
    # 링크
    html = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2">\1</a>', html)
    # 목록
    html = re.sub(r'^- (.+)$', r'<li>\1</li>', html, flags=re.MULTILINE)
    # 단락
    paragraphs = []
    for line in html.split('\n'):
        stripped = line.strip()
        if stripped and not stripped.startswith('<'):
            paragraphs.append(f'<p>{stripped}</p>')
        else:
            paragraphs.append(stripped)
    return '\n'.join(paragraphs)


class TistoryUploader:
    """blog_posts 테이블의 draft 항목을 티스토리에 발행"""

    def __init__(self, connector: Optional[TistoryConnector] = None) -> None:
        self._tistory = connector or TistoryConnector()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def upload_pending(self, limit: int = 5) -> list[dict]:
        """blog_posts.status = 'draft' 항목을 일괄 업로드

        Returns:
            업로드 결과 목록 (성공/실패 포함)
        """
        db = _get_supabase()
        rows = (
            db.table("blog_posts")
            .select("id, title, content, tags, meta_description")
            .eq("status", "draft")
            .limit(limit)
            .execute()
        ).data

        if not rows:
            logger.info("tistory_uploader.no_draft_posts")
            return []

        results = []
        for row in rows:
            try:
                result = self.upload_single(row)
                results.append({"post_id": row["id"], "success": True, **result})
            except Exception as exc:
                logger.error("tistory_uploader.error", post_id=row["id"], error=str(exc))
                self._mark_failed(row["id"], str(exc))
                results.append({"post_id": row["id"], "success": False, "error": str(exc)})

        return results

    def upload_single(self, post: dict) -> dict:
        """단일 블로그 포스트를 티스토리에 발행

        Args:
            post: blog_posts 테이블 행 (id, title, content, tags)

        Returns:
            {"tistory_post_id": "...", "tistory_url": "..."}
        """
        logger.info("tistory_uploader.upload", post_id=post.get("id"), title=post.get("title"))

        html_content = _markdown_to_html(post.get("content", ""))
        tags = post.get("tags") or []

        response = self._tistory.post_article(
            title=post["title"],
            content=html_content,
            tags=tags if isinstance(tags, list) else [],
        )

        tistory_post_id = str(response.get("postId", ""))
        tistory_url = response.get("url", "")

        self._mark_published(
            post_id=post["id"],
            tistory_post_id=tistory_post_id,
            tistory_url=tistory_url,
        )

        return {"tistory_post_id": tistory_post_id, "tistory_url": tistory_url}

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    def _mark_published(self, post_id: str, tistory_post_id: str, tistory_url: str) -> None:
        db = _get_supabase()
        db.table("blog_posts").update({
            "status": "published",
            "tistory_post_id": tistory_post_id,
            "tistory_url": tistory_url,
            "published_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("id", post_id).execute()

    def _mark_failed(self, post_id: str, error: str) -> None:
        db = _get_supabase()
        db.table("blog_posts").update({
            "status": "failed",
            "error_message": error,
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("id", post_id).execute()
