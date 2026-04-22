"""파이프라인 FastAPI 라우터 — n8n이 호출하는 엔드포인트"""
from __future__ import annotations

import os
from datetime import date
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from src.trend import TrendCollector, TopicSelector, ContentQueue
from src.content import BlogGenerator, YouTubeGenerator, ReelsGenerator
from src.upload import TistoryUploader, YouTubeUploader, InstagramUploader
from src.affiliate import AffiliateLinkInserter

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/pipeline")
security = HTTPBearer()

PIPELINE_API_TOKEN = os.getenv("PIPELINE_API_TOKEN", "")


def _verify_token(credentials: HTTPAuthorizationCredentials = Security(security)) -> str:
    if PIPELINE_API_TOKEN and credentials.credentials != PIPELINE_API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid token")
    return credentials.credentials


# ------------------------------------------------------------------ #
# Request / Response Models
# ------------------------------------------------------------------ #


class TrendCollectRequest(BaseModel):
    sources: list[str] = ["google_trends", "naver_datalab", "rss"]
    limit: int = 20
    naver_keyword_groups: Optional[list[dict]] = None
    google_seed_keywords: Optional[list[str]] = None


class TopicQueueRequest(BaseModel):
    trends: list[dict]            # TrendKeyword 직렬화 목록
    blog_count: int = 5
    youtube_count: int = 1
    reels_count: int = 1
    target_date: Optional[str] = None  # ISO date string


class ContentGenerateRequest(BaseModel):
    target_date: Optional[str] = None  # ISO date string, 없으면 오늘
    limit: Optional[int] = None        # 최대 생성 수 (없으면 기본값 사용)


class ContentGenerateSingleRequest(BaseModel):
    title: str
    primary_keyword: str
    seo_keywords: list[str] = []
    angle: str = ""
    target_audience: str = ""
    queue_id: str = ""


# ------------------------------------------------------------------ #
# Endpoints
# ------------------------------------------------------------------ #


@router.post("/trends/collect")
def collect_trends(
    req: TrendCollectRequest,
    _token: str = Depends(_verify_token),
) -> dict:
    """트렌드 수집 — n8n 워크플로우 1단계"""
    logger.info("api.trends.collect", sources=req.sources)

    collector = TrendCollector()
    trends = collector.collect_all(
        naver_keyword_groups=req.naver_keyword_groups,
        google_seed_keywords=req.google_seed_keywords,
    )

    # 상위 N개만 반환
    limited = trends[: req.limit]
    return {
        "count": len(limited),
        "trends": [
            {
                "keyword": t.keyword,
                "source": t.source,
                "score": round(t.score, 4),
                "related": t.related[:5],
            }
            for t in limited
        ],
        "top_keywords": [t.keyword for t in limited[:10]],
    }


@router.post("/topics/generate-queue")
def generate_queue(
    req: TopicQueueRequest,
    _token: str = Depends(_verify_token),
) -> dict:
    """트렌드 → 주제 선정 & 큐 저장 — n8n 워크플로우 2단계"""
    from src.trend.trend_collector import TrendKeyword

    logger.info("api.topics.generate_queue", trend_count=len(req.trends))

    # dict → TrendKeyword 역직렬화
    trend_objects = [
        TrendKeyword(
            keyword=t["keyword"],
            source=t["source"],
            score=t["score"],
            related=t.get("related", []),
        )
        for t in req.trends
    ]

    target_date = date.fromisoformat(req.target_date) if req.target_date else date.today()

    queue = ContentQueue()
    result = queue.build_daily_queue(
        target_date=target_date,
    )

    # trends를 직접 selector에 전달 (DB 저장 없이 빠른 선정만 원할 경우)
    if not result.get("topics"):
        selector = TopicSelector()
        topics = selector.select_daily_topics(
            trends=trend_objects,
            blog_count=req.blog_count,
            youtube_count=req.youtube_count,
            reels_count=req.reels_count,
        )
        result = {
            "date": str(target_date),
            "topics": [ContentQueue._topic_to_dict(t) for t in topics],
            "saved_count": 0,
        }

    return {
        **result,
        "blog_count": sum(1 for t in result["topics"] if t["content_type"] == "blog"),
        "youtube_count": sum(1 for t in result["topics"] if t["content_type"] == "youtube"),
        "reels_count": sum(1 for t in result["topics"] if t["content_type"] == "reels"),
        "top_keywords": [t["primary_keyword"] for t in result["topics"][:5]],
    }


@router.get("/queue/pending")
def get_pending_queue(
    target_date: Optional[str] = None,
    content_type: Optional[str] = None,
    _token: str = Depends(_verify_token),
) -> dict:
    """pending 콘텐츠 큐 조회 — Phase 3 콘텐츠 생성에서 활용"""
    queue = ContentQueue()
    parsed_date = date.fromisoformat(target_date) if target_date else date.today()
    items = queue.get_pending_topics(target_date=parsed_date, content_type=content_type)
    return {"date": str(parsed_date), "count": len(items), "items": items}


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "autowork-pipeline"}


# ------------------------------------------------------------------ #
# Phase 3: AI 콘텐츠 생성 엔드포인트 (n8n 워크플로우 3단계)
# ------------------------------------------------------------------ #


@router.post("/content/generate-blog")
def generate_blog(
    req: ContentGenerateRequest,
    _token: str = Depends(_verify_token),
) -> dict:
    """블로그 포스트 자동 생성 — n8n 콘텐츠 생성 워크플로우

    content_queue 테이블의 pending blog 항목을 읽어 Claude API로 생성 후 blog_posts에 저장.
    """
    logger.info("api.content.generate_blog", date=req.target_date, limit=req.limit)
    generator = BlogGenerator()
    posts = generator.generate_from_queue(
        target_date=req.target_date,
        limit=req.limit or 5,
    )
    success = [p for p in posts if "error" not in p]
    failed = [p for p in posts if "error" in p]
    return {
        "generated": len(success),
        "failed": len(failed),
        "posts": success,
        "errors": failed,
    }


@router.post("/content/generate-blog/single")
def generate_blog_single(
    req: ContentGenerateSingleRequest,
    _token: str = Depends(_verify_token),
) -> dict:
    """단일 블로그 포스트 생성 (큐 없이 직접 호출)"""
    logger.info("api.content.generate_blog_single", title=req.title)
    generator = BlogGenerator()
    post = generator.generate_single(
        title=req.title,
        primary_keyword=req.primary_keyword,
        seo_keywords=req.seo_keywords,
        angle=req.angle,
        target_audience=req.target_audience,
        queue_id=req.queue_id,
    )
    return post


@router.post("/content/generate-youtube")
def generate_youtube(
    req: ContentGenerateRequest,
    _token: str = Depends(_verify_token),
) -> dict:
    """유튜브 스크립트 + 메타데이터 자동 생성 — n8n 콘텐츠 생성 워크플로우

    content_queue 테이블의 pending youtube 항목을 읽어 Claude API로 생성 후 youtube_videos에 저장.
    """
    logger.info("api.content.generate_youtube", date=req.target_date, limit=req.limit)
    generator = YouTubeGenerator()
    videos = generator.generate_from_queue(
        target_date=req.target_date,
        limit=req.limit or 1,
    )
    success = [v for v in videos if "error" not in v]
    failed = [v for v in videos if "error" in v]
    return {
        "generated": len(success),
        "failed": len(failed),
        "videos": success,
        "errors": failed,
    }


@router.post("/content/generate-youtube/single")
def generate_youtube_single(
    req: ContentGenerateSingleRequest,
    _token: str = Depends(_verify_token),
) -> dict:
    """단일 유튜브 스크립트 생성 (큐 없이 직접 호출)"""
    logger.info("api.content.generate_youtube_single", title=req.title)
    generator = YouTubeGenerator()
    video = generator.generate_single(
        title=req.title,
        primary_keyword=req.primary_keyword,
        seo_keywords=req.seo_keywords,
        angle=req.angle,
        target_audience=req.target_audience,
        queue_id=req.queue_id,
    )
    return video


@router.post("/content/generate-reels")
def generate_reels(
    req: ContentGenerateRequest,
    _token: str = Depends(_verify_token),
) -> dict:
    """릴스 캡션 + 대본 자동 생성 — n8n 콘텐츠 생성 워크플로우

    content_queue 테이블의 pending reels 항목을 읽어 Claude API로 생성 후 instagram_reels에 저장.
    """
    logger.info("api.content.generate_reels", date=req.target_date, limit=req.limit)
    generator = ReelsGenerator()
    reels = generator.generate_from_queue(
        target_date=req.target_date,
        limit=req.limit or 1,
    )
    success = [r for r in reels if "error" not in r]
    failed = [r for r in reels if "error" in r]
    return {
        "generated": len(success),
        "failed": len(failed),
        "reels": success,
        "errors": failed,
    }


@router.post("/content/generate-reels/single")
def generate_reels_single(
    req: ContentGenerateSingleRequest,
    _token: str = Depends(_verify_token),
) -> dict:
    """단일 릴스 캡션 + 대본 생성 (큐 없이 직접 호출)"""
    logger.info("api.content.generate_reels_single", title=req.title)
    generator = ReelsGenerator()
    reel = generator.generate_single(
        title=req.title,
        primary_keyword=req.primary_keyword,
        seo_keywords=req.seo_keywords,
        angle=req.angle,
        target_audience=req.target_audience,
        queue_id=req.queue_id,
    )
    return reel


# ------------------------------------------------------------------ #
# Phase 4: 멀티 플랫폼 자동 업로드 엔드포인트 (n8n 워크플로우 4단계)
# ------------------------------------------------------------------ #


class UploadRequest(BaseModel):
    limit: Optional[int] = None  # 최대 업로드 수 (없으면 기본값 사용)


@router.post("/upload/blog")
def upload_blog(
    req: UploadRequest,
    _token: str = Depends(_verify_token),
) -> dict:
    """블로그 포스트 티스토리 발행 — n8n 업로드 워크플로우

    blog_posts.status = 'draft' 항목을 읽어 티스토리 API로 발행.
    성공 시 tistory_post_id, tistory_url 업데이트.
    """
    logger.info("api.upload.blog", limit=req.limit)
    uploader = TistoryUploader()
    results = uploader.upload_pending(limit=req.limit or 5)
    success = [r for r in results if r.get("success")]
    failed = [r for r in results if not r.get("success")]
    return {"uploaded": len(success), "failed": len(failed), "results": results}


@router.post("/upload/youtube")
def upload_youtube(
    req: UploadRequest,
    _token: str = Depends(_verify_token),
) -> dict:
    """유튜브 영상 업로드 — n8n 업로드 워크플로우

    youtube_videos.status = 'draft' 항목을 읽어 YouTube Data API로 업로드.
    영상 파일 없으면 'scheduled' 상태로 표시.
    """
    logger.info("api.upload.youtube", limit=req.limit)
    uploader = YouTubeUploader()
    results = uploader.upload_pending(limit=req.limit or 1)
    success = [r for r in results if r.get("success")]
    failed = [r for r in results if not r.get("success")]
    return {"uploaded": len(success), "failed": len(failed), "results": results}


@router.post("/upload/reels")
def upload_reels(
    req: UploadRequest,
    _token: str = Depends(_verify_token),
) -> dict:
    """릴스 인스타그램 발행 — n8n 업로드 워크플로우

    reels_scripts.status = 'draft' 항목을 읽어 Instagram Graph API로 릴스 발행.
    영상 URL 없으면 'scheduled' 상태로 표시.
    """
    logger.info("api.upload.reels", limit=req.limit)
    uploader = InstagramUploader()
    results = uploader.upload_pending(limit=req.limit or 1)
    success = [r for r in results if r.get("success")]
    failed = [r for r in results if not r.get("success")]
    return {"uploaded": len(success), "failed": len(failed), "results": results}
