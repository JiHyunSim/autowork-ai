"""YouTube Data API v3 커넥터"""
import os
import structlog
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from src.config import settings

logger = structlog.get_logger(__name__)

YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]


class YouTubeConnector:
    """YouTube 자동 업로드 커넥터"""

    def __init__(self) -> None:
        self._service = None

    def _get_service(self):
        """YouTube API 서비스 인스턴스 반환 (Lazy init)"""
        if self._service is not None:
            return self._service

        creds = Credentials(
            token=None,
            refresh_token=settings.youtube_refresh_token,
            client_id=settings.youtube_client_id,
            client_secret=settings.youtube_client_secret,
            token_uri="https://oauth2.googleapis.com/token",
            scopes=YOUTUBE_SCOPES,
        )

        if creds.expired:
            creds.refresh(Request())

        self._service = build("youtube", "v3", credentials=creds)
        return self._service

    def upload_video(
        self,
        video_path: str,
        title: str,
        description: str,
        tags: list[str] | None = None,
        category_id: str = "22",  # 22 = 사람 및 블로그
        privacy_status: str = "public",
    ) -> dict:
        """유튜브 영상 업로드

        Args:
            video_path: 로컬 영상 파일 경로
            title: 영상 제목
            description: 영상 설명
            tags: 태그 리스트
            category_id: 카테고리 ID (22=사람/블로그, 28=과학기술)
            privacy_status: 공개 여부 (public/private/unlisted)

        Returns:
            {"videoId": "...", "url": "..."}
        """
        logger.info("youtube.upload_video", title=title, path=video_path)

        if not os.path.exists(video_path):
            raise FileNotFoundError(f"영상 파일을 찾을 수 없습니다: {video_path}")

        service = self._get_service()

        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags or [],
                "categoryId": category_id,
                "defaultLanguage": "ko",
                "defaultAudioLanguage": "ko",
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": False,
            },
        }

        media = MediaFileUpload(
            video_path,
            mimetype="video/*",
            resumable=True,
            chunksize=50 * 1024 * 1024,  # 50MB 청크
        )

        request = service.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media,
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                logger.info("youtube.upload_progress", percent=int(status.progress() * 100))

        video_id = response["id"]
        url = f"https://www.youtube.com/watch?v={video_id}"
        logger.info("youtube.upload_video.done", video_id=video_id, url=url)
        return {"videoId": video_id, "url": url}

    def set_thumbnail(self, video_id: str, thumbnail_path: str) -> bool:
        """영상 썸네일 설정"""
        service = self._get_service()
        media = MediaFileUpload(thumbnail_path, mimetype="image/jpeg")
        service.thumbnails().set(videoId=video_id, media_body=media).execute()
        logger.info("youtube.set_thumbnail.done", video_id=video_id)
        return True
