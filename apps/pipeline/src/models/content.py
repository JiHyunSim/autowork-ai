"""콘텐츠 파이프라인 데이터 모델 (Pydantic v2)"""
from __future__ import annotations
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ContentTopic(BaseModel):
    """트렌드 기반 콘텐츠 주제"""
    id: UUID | None = None
    topic: str
    keywords: list[str] = Field(default_factory=list)
    source: Literal["google_trends", "naver_datalab", "youtube_trending", "manual"]
    trend_score: float | None = None
    content_types: list[Literal["blog", "youtube", "reels"]] = Field(default_factory=list)
    scheduled_date: date
    status: Literal["pending", "in_progress", "done", "skipped"] = "pending"


class BlogPost(BaseModel):
    """블로그 포스트"""
    id: UUID | None = None
    topic_id: UUID | None = None
    title: str
    content: str  # 마크다운 원본
    meta_description: str | None = None
    tags: list[str] = Field(default_factory=list)
    seo_score: float | None = None
    status: Literal["draft", "scheduled", "published", "failed"] = "draft"
    wordpress_post_id: str | None = None
    wordpress_url: str | None = None
    published_at: datetime | None = None
    ai_model: str = "claude-sonnet-4-6"
    generation_ms: int | None = None


class YouTubeVideo(BaseModel):
    """유튜브 영상"""
    id: UUID | None = None
    topic_id: UUID | None = None
    title: str
    description: str
    script: str
    tags: list[str] = Field(default_factory=list)
    thumbnail_concept: str | None = None
    status: Literal["draft", "rendering", "scheduled", "published", "failed"] = "draft"
    video_file_path: str | None = None
    youtube_video_id: str | None = None
    youtube_url: str | None = None
    published_at: datetime | None = None
    ai_model: str = "claude-sonnet-4-6"


class InstagramReel(BaseModel):
    """인스타그램 릴스"""
    id: UUID | None = None
    topic_id: UUID | None = None
    caption: str
    hashtags: list[str] = Field(default_factory=list)
    video_concept: str | None = None
    status: Literal["draft", "scheduled", "published", "failed"] = "draft"
    video_url: str | None = None
    instagram_media_id: str | None = None
    instagram_permalink: str | None = None
    published_at: datetime | None = None
    ai_model: str = "claude-sonnet-4-6"


class AffiliateLink(BaseModel):
    """쿠팡 파트너스 제휴 링크"""
    id: UUID | None = None
    content_type: Literal["blog", "youtube", "reels"]
    content_id: UUID
    product_id: str
    product_name: str
    product_url: str
    affiliate_url: str
    keyword: str | None = None
    position: int | None = None
    click_count: int = 0
