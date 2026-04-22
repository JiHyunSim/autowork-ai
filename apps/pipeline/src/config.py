"""콘텐츠 파이프라인 설정"""
from pydantic_settings import BaseSettings
from pydantic import Field


class PipelineSettings(BaseSettings):
    # ---- Anthropic (Claude Sonnet 4.6) ----
    anthropic_api_key: str = Field(alias="ANTHROPIC_API_KEY")
    claude_model: str = "claude-sonnet-4-6"

    # ---- YouTube Data API v3 ----
    youtube_api_key: str = Field(default="", alias="YOUTUBE_API_KEY")
    youtube_client_id: str = Field(default="", alias="YOUTUBE_CLIENT_ID")
    youtube_client_secret: str = Field(default="", alias="YOUTUBE_CLIENT_SECRET")
    youtube_refresh_token: str = Field(default="", alias="YOUTUBE_REFRESH_TOKEN")
    youtube_channel_id: str = Field(default="", alias="YOUTUBE_CHANNEL_ID")

    # ---- 티스토리 API ----
    tistory_app_id: str = Field(default="", alias="TISTORY_APP_ID")
    tistory_secret_key: str = Field(default="", alias="TISTORY_SECRET_KEY")
    tistory_access_token: str = Field(default="", alias="TISTORY_ACCESS_TOKEN")
    tistory_blog_name: str = Field(default="", alias="TISTORY_BLOG_NAME")

    # ---- Instagram Graph API ----
    instagram_access_token: str = Field(default="", alias="INSTAGRAM_ACCESS_TOKEN")
    instagram_business_account_id: str = Field(
        default="", alias="INSTAGRAM_BUSINESS_ACCOUNT_ID"
    )
    facebook_app_id: str = Field(default="", alias="FACEBOOK_APP_ID")
    facebook_app_secret: str = Field(default="", alias="FACEBOOK_APP_SECRET")

    # ---- 쿠팡 파트너스 API ----
    coupang_access_key: str = Field(default="", alias="COUPANG_ACCESS_KEY")
    coupang_secret_key: str = Field(default="", alias="COUPANG_SECRET_KEY")

    # ---- 네이버 DataLab ----
    naver_client_id: str = Field(default="", alias="NAVER_CLIENT_ID")
    naver_client_secret: str = Field(default="", alias="NAVER_CLIENT_SECRET")

    # ---- Supabase ----
    supabase_url: str = Field(alias="SUPABASE_URL")
    supabase_service_role_key: str = Field(alias="SUPABASE_SERVICE_ROLE_KEY")

    # ---- Slack (알림) ----
    slack_webhook_url: str = Field(default="", alias="SLACK_WEBHOOK_URL")

    # ---- 파이프라인 설정 ----
    # 일별 블로그 포스트 목표 수
    daily_blog_target: int = 5
    # 주별 유튜브 영상 목표 수
    weekly_youtube_target: int = 3
    # 일별 릴스 목표 수
    daily_reels_target: int = 1
    # Claude API 최대 재시도 횟수
    claude_max_retries: int = 3
    # 타임존
    timezone: str = "Asia/Seoul"

    class Config:
        env_file = "../../.env.local"
        env_file_encoding = "utf-8"
        populate_by_name = True


settings = PipelineSettings()
