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
