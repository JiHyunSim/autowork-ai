from pydantic_settings import BaseSettings
from typing import list


class Settings(BaseSettings):
    # App
    ENVIRONMENT: str = "development"
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Supabase
    SUPABASE_URL: str
    SUPABASE_SERVICE_ROLE_KEY: str

    # Anthropic (Claude Sonnet 4.6)
    ANTHROPIC_API_KEY: str
    CLAUDE_MODEL: str = "claude-sonnet-4-6"

    # OpenAI (Whisper + Embeddings)
    OPENAI_API_KEY: str
    WHISPER_MODEL: str = "whisper-1"
    EMBEDDING_MODEL: str = "text-embedding-3-small"

    # Redis
    REDIS_URL: str = "redis://localhost:6379"

    # Toss Payments
    TOSS_CLIENT_KEY: str = ""
    TOSS_SECRET_KEY: str = ""

    # Slack
    SLACK_BOT_TOKEN: str = ""

    # CORS
    ALLOWED_ORIGINS: list[str] = [
        "http://localhost:3000",
        "https://autowork.ai",
    ]

    class Config:
        env_file = "../../.env.local"
        env_file_encoding = "utf-8"


settings = Settings()
