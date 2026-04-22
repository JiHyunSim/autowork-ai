"""Instagram Graph API 커넥터"""
import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import settings

logger = structlog.get_logger(__name__)

GRAPH_API_BASE = "https://graph.facebook.com/v20.0"


class InstagramConnector:
    """Instagram 릴스 자동 업로드 커넥터 (Graph API)"""

    def __init__(self) -> None:
        self.access_token = settings.instagram_access_token
        self.account_id = settings.instagram_business_account_id
        self.client = httpx.Client(timeout=60.0)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    def upload_reel(
        self,
        video_url: str,
        caption: str,
        cover_url: str | None = None,
        share_to_feed: bool = True,
    ) -> dict:
        """릴스 업로드 (2단계: 컨테이너 생성 → 발행)

        Args:
            video_url: 공개 접근 가능한 영상 URL (CDN 또는 공개 스토리지)
            caption: 캡션 + 해시태그
            cover_url: 커버 이미지 URL (선택)
            share_to_feed: 피드에도 공유 여부

        Returns:
            {"mediaId": "...", "permalink": "..."}
        """
        logger.info("instagram.upload_reel", account=self.account_id)

        # Step 1: 미디어 컨테이너 생성
        container_data = {
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "share_to_feed": str(share_to_feed).lower(),
            "access_token": self.access_token,
        }
        if cover_url:
            container_data["cover_url"] = cover_url

        resp = self.client.post(
            f"{GRAPH_API_BASE}/{self.account_id}/media",
            data=container_data,
        )
        resp.raise_for_status()
        container_id = resp.json()["id"]
        logger.info("instagram.container_created", container_id=container_id)

        # Step 2: 컨테이너 상태 확인 (처리 완료 대기)
        self._wait_for_container(container_id)

        # Step 3: 미디어 발행
        publish_resp = self.client.post(
            f"{GRAPH_API_BASE}/{self.account_id}/media_publish",
            data={
                "creation_id": container_id,
                "access_token": self.access_token,
            },
        )
        publish_resp.raise_for_status()
        media_id = publish_resp.json()["id"]

        # Step 4: 퍼마링크 조회
        permalink = self._get_permalink(media_id)
        logger.info("instagram.upload_reel.done", media_id=media_id, url=permalink)
        return {"mediaId": media_id, "permalink": permalink}

    def _wait_for_container(self, container_id: str, max_retries: int = 20) -> None:
        """컨테이너 처리 완료 대기 (폴링)"""
        import time
        for i in range(max_retries):
            resp = self.client.get(
                f"{GRAPH_API_BASE}/{container_id}",
                params={
                    "fields": "status_code,status",
                    "access_token": self.access_token,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            status = data.get("status_code")

            if status == "FINISHED":
                return
            elif status == "ERROR":
                raise RuntimeError(f"Instagram 컨테이너 처리 실패: {data}")
            elif status in ("IN_PROGRESS", "PUBLISHED"):
                logger.info("instagram.container_status", status=status, attempt=i + 1)
                time.sleep(15)
            else:
                time.sleep(10)

        raise TimeoutError("Instagram 컨테이너 처리 시간 초과")

    def _get_permalink(self, media_id: str) -> str:
        """미디어 퍼마링크 조회"""
        resp = self.client.get(
            f"{GRAPH_API_BASE}/{media_id}",
            params={"fields": "permalink", "access_token": self.access_token},
        )
        resp.raise_for_status()
        return resp.json().get("permalink", "")

    def close(self) -> None:
        self.client.close()
