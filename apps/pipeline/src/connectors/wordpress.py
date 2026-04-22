"""WordPress REST API 커넥터"""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.config import settings

logger = structlog.get_logger(__name__)


class WordPressConnector:
    """WordPress Application Password 인증 기반 발행 커넥터"""

    def __init__(self) -> None:
        if not settings.wordpress_url:
            raise ValueError("WORDPRESS_URL is required")
        if not settings.wordpress_user:
            raise ValueError("WORDPRESS_USER is required")
        if not settings.wordpress_app_password:
            raise ValueError("WORDPRESS_APP_PASSWORD is required")

        self.base_url = settings.wordpress_url.rstrip("/")
        self._client = httpx.Client(timeout=30.0, headers=self._build_headers())

    def _build_headers(self) -> dict[str, str]:
        token = f"{settings.wordpress_user}:{settings.wordpress_app_password}"
        encoded = base64.b64encode(token.encode("utf-8")).decode("ascii")
        return {
            "Authorization": f"Basic {encoded}",
            "Accept": "application/json",
            "User-Agent": "autowork-pipeline/0.1",
        }

    def _is_retryable(self, exc: Exception) -> bool:
        if not isinstance(exc, httpx.HTTPStatusError):
            return False
        code = exc.response.status_code
        return code == 429 or code >= 500

    def _should_retry_post(self, exc: Exception) -> bool:
        if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)):
            return True
        return self._is_retryable(exc)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=8),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        reraise=True,
    )
    def verify_connectivity(self) -> dict[str, Any]:
        """인증/연결 상태 확인"""
        base_resp = self._client.get(f"{self.base_url}/wp-json/wp/v2")
        base_resp.raise_for_status()

        me_resp = self._client.get(f"{self.base_url}/wp-json/wp/v2/users/me")
        me_resp.raise_for_status()
        data = me_resp.json()

        return {
            "site": self.base_url,
            "user_id": data.get("id"),
            "username": data.get("slug") or data.get("name"),
        }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=8),
        retry=retry_if_exception(lambda exc: self._should_retry_post(exc)),
        reraise=True,
    )
    def create_post(
        self,
        *,
        title: str,
        content: str,
        slug: str,
        status: str = "publish",
        featured_media: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "title": title,
            "content": content,
            "slug": slug,
            "status": status,
        }
        if featured_media is not None:
            payload["featured_media"] = featured_media

        logger.info("wordpress.create_post", slug=slug, status=status)
        resp = self._client.post(
            f"{self.base_url}/wp-json/wp/v2/posts",
            json=payload,
            headers={"Content-Type": "application/json", **self._build_headers()},
        )
        resp.raise_for_status()

        data = resp.json()
        logger.info("wordpress.create_post.done", post_id=data.get("id"), slug=data.get("slug"))
        return {
            "post_id": str(data.get("id", "")),
            "url": data.get("link", ""),
            "status": data.get("status", ""),
            "slug": data.get("slug", slug),
        }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=8),
        retry=retry_if_exception(lambda exc: self._should_retry_post(exc)),
        reraise=True,
    )
    def upload_media(self, file_path: str, title: str = "") -> dict[str, Any]:
        """선택적 대표 이미지 업로드"""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"file not found: {file_path}")

        mime = "image/jpeg"
        if path.suffix.lower() == ".png":
            mime = "image/png"
        elif path.suffix.lower() == ".webp":
            mime = "image/webp"

        with path.open("rb") as fh:
            files = {"file": (path.name, fh, mime)}
            headers = {
                **self._build_headers(),
                "Content-Disposition": f'attachment; filename="{path.name}"',
            }
            resp = self._client.post(
                f"{self.base_url}/wp-json/wp/v2/media",
                files=files,
                data={"title": title} if title else None,
                headers=headers,
            )

        resp.raise_for_status()

        data = resp.json()
        return {
            "media_id": int(data.get("id", 0)),
            "url": data.get("source_url", ""),
        }

    def close(self) -> None:
        self._client.close()
