"""티스토리 API 커넥터"""
import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import settings

logger = structlog.get_logger(__name__)

TISTORY_API_BASE = "https://www.tistory.com/apis"


class TistoryConnector:
    """티스토리 블로그 자동 포스팅 커넥터"""

    def __init__(self) -> None:
        self.access_token = settings.tistory_access_token
        self.blog_name = settings.tistory_blog_name
        self.client = httpx.Client(timeout=30.0)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=5))
    def post_article(
        self,
        title: str,
        content: str,
        tags: list[str] | None = None,
        category: int = 0,
        visibility: int = 3,  # 3=공개, 0=비공개
    ) -> dict:
        """블로그 포스트 작성

        Args:
            title: 포스트 제목
            content: HTML 또는 마크다운 내용
            tags: 태그 리스트
            category: 카테고리 ID (0=미분류)
            visibility: 공개 여부 (3=공개, 15=보호, 0=비공개)

        Returns:
            {"postId": "...", "url": "..."}
        """
        logger.info("tistory.post_article", title=title, blog=self.blog_name)

        params = {
            "access_token": self.access_token,
            "output": "json",
            "blogName": self.blog_name,
            "title": title,
            "content": content,
            "visibility": str(visibility),
            "category": str(category),
        }

        if tags:
            params["tag"] = ",".join(tags)

        resp = self.client.post(f"{TISTORY_API_BASE}/post/write", data=params)
        resp.raise_for_status()
        data = resp.json()

        if data.get("tistory", {}).get("status") != "200":
            raise RuntimeError(f"티스토리 API 오류: {data}")

        post_id = data["tistory"]["postId"]
        post_url = data["tistory"]["url"]
        logger.info("tistory.post_article.done", post_id=post_id, url=post_url)
        return {"postId": post_id, "url": post_url}

    def get_categories(self) -> list[dict]:
        """카테고리 목록 조회"""
        resp = self.client.get(
            f"{TISTORY_API_BASE}/category/list",
            params={
                "access_token": self.access_token,
                "output": "json",
                "blogName": self.blog_name,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("tistory", {}).get("item", {}).get("categories", [])

    def close(self) -> None:
        self.client.close()
