"""WordPress 자동 업로드 모듈 (Phase 4)"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

import structlog
from supabase import Client, create_client

from src.config import settings
from src.connectors.wordpress import WordPressConnector

logger = structlog.get_logger(__name__)


def _get_supabase() -> Client:
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def _markdown_to_html(content: str) -> str:
    """간단한 마크다운 -> HTML 변환"""
    html = content
    html = re.sub(r"^### (.+)$", r"<h3>\1</h3>", html, flags=re.MULTILINE)
    html = re.sub(r"^## (.+)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
    html = re.sub(r"^# (.+)$", r"<h1>\1</h1>", html, flags=re.MULTILINE)
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    html = re.sub(r"\*(.+?)\*", r"<em>\1</em>", html)
    html = re.sub(r"\[(.+?)\]\((.+?)\)", r"<a href=\"\2\">\1</a>", html)
    html = re.sub(r"^- (.+)$", r"<li>\1</li>", html, flags=re.MULTILINE)

    paragraphs = []
    for line in html.split("\n"):
        stripped = line.strip()
        if stripped and not stripped.startswith("<"):
            paragraphs.append(f"<p>{stripped}</p>")
        else:
            paragraphs.append(stripped)
    return "\n".join(paragraphs)


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9\s-]", "", text).strip().lower()
    slug = re.sub(r"[\s_-]+", "-", slug)
    return slug[:80] or f"post-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"


class WordPressUploader:
    """blog_posts 테이블 draft 항목을 WordPress에 발행"""

    def __init__(self, connector: Optional[WordPressConnector] = None) -> None:
        self._wordpress = connector or WordPressConnector()

    def upload_pending(self, limit: int = 5) -> list[dict]:
        db = _get_supabase()
        rows = (
            db.table("blog_posts")
            .select("id, title, content, tags, meta_description")
            .eq("status", "draft")
            .limit(limit)
            .execute()
        ).data

        if not rows:
            logger.info("wordpress_uploader.no_draft_posts")
            return []

        results = []
        for row in rows:
            try:
                result = self.upload_single(row)
                results.append({"post_id": row["id"], "success": True, **result})
            except Exception as exc:
                logger.error("wordpress_uploader.error", post_id=row["id"], error=str(exc))
                self._mark_failed(row["id"], str(exc))
                results.append({"post_id": row["id"], "success": False, "error": str(exc)})

        return results

    def upload_single(self, post: dict) -> dict:
        logger.info("wordpress_uploader.upload", post_id=post.get("id"), title=post.get("title"))

        html_content = _markdown_to_html(post.get("content", ""))
        slug = _slugify(post.get("title", ""))
        response = self._wordpress.create_post(
            title=post["title"],
            content=html_content,
            slug=slug,
            status="publish",
        )

        wordpress_post_id = response.get("post_id", "")
        wordpress_url = response.get("url", "")

        self._mark_published(
            post_id=post["id"],
            wordpress_post_id=wordpress_post_id,
            wordpress_url=wordpress_url,
        )

        return {
            "wordpress_post_id": wordpress_post_id,
            "wordpress_url": wordpress_url,
            "status": response.get("status", ""),
            "slug": response.get("slug", slug),
        }

    def _mark_published(self, post_id: str, wordpress_post_id: str, wordpress_url: str) -> None:
        db = _get_supabase()
        now = datetime.utcnow().isoformat()
        db.table("blog_posts").update(
            {
                "status": "published",
                "wordpress_post_id": wordpress_post_id,
                "wordpress_url": wordpress_url,
                "published_at": now,
                "updated_at": now,
            }
        ).eq("id", post_id).execute()

    def _mark_failed(self, post_id: str, error: str) -> None:
        db = _get_supabase()
        db.table("blog_posts").update(
            {
                "status": "failed",
                "error_message": error,
                "updated_at": datetime.utcnow().isoformat(),
            }
        ).eq("id", post_id).execute()

    def close(self) -> None:
        self._wordpress.close()
