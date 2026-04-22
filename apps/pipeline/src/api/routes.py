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
from src.upload import WordPressUploader, YouTubeUploader, InstagramUploader
from src.affiliate import AffiliateLinkInserter
from src.monitoring import PipelineMonitor
from src.scheduler import PipelineScheduler

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
    """블로그 포스트 WordPress 발행 — n8n 업로드 워크플로우

    blog_posts.status = 'draft' 항목을 읽어 WordPress REST API로 발행.
    성공 시 wordpress_post_id, wordpress_url 업데이트.
    """
    logger.info("api.upload.blog", limit=req.limit)
    uploader = WordPressUploader()
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


# ------------------------------------------------------------------ #
# Phase 5: 쿠팡 파트너스 제휴 링크 자동 삽입 엔드포인트
# ------------------------------------------------------------------ #


class AffiliateInsertRequest(BaseModel):
    blog_post_id: str
    content: str
    title: str


class AffiliateClickRequest(BaseModel):
    affiliate_link_id: str


@router.post("/affiliate/insert")
def insert_affiliate_links(
    req: AffiliateInsertRequest,
    _token: str = Depends(_verify_token),
) -> dict:
    """블로그 포스트에 쿠팡 파트너스 제휴 링크 자동 삽입 — n8n 워크플로우 5단계

    1. Claude로 상품 키워드 추출
    2. 쿠팡 파트너스 API로 관련 상품 검색
    3. 마크다운 콘텐츠에 추천 상품 섹션 삽입
    4. Supabase affiliate_links 테이블 저장
    5. blog_posts.content 업데이트
    """
    logger.info("api.affiliate.insert", blog_post_id=req.blog_post_id)
    inserter = AffiliateLinkInserter()
    try:
        result = inserter.process_blog_post(
            blog_post_id=req.blog_post_id,
            content=req.content,
            title=req.title,
        )
        return result
    finally:
        inserter.close()


@router.post("/affiliate/click")
def track_affiliate_click(
    req: AffiliateClickRequest,
    _token: str = Depends(_verify_token),
) -> dict:
    """제휴 링크 클릭 추적 — click_count 증가"""
    logger.info("api.affiliate.click", affiliate_link_id=req.affiliate_link_id)
    inserter = AffiliateLinkInserter()
    try:
        return inserter.track_click(req.affiliate_link_id)
    finally:
        inserter.close()


@router.get("/affiliate/stats/{blog_post_id}")
def get_affiliate_stats(
    blog_post_id: str,
    _token: str = Depends(_verify_token),
) -> dict:
    """블로그 포스트의 제휴 링크 클릭 통계 조회"""
    logger.info("api.affiliate.stats", blog_post_id=blog_post_id)
    inserter = AffiliateLinkInserter()
    try:
        return inserter.get_post_stats(blog_post_id)
    finally:
        inserter.close()


# ------------------------------------------------------------------ #
# Phase 6: 모니터링, 스케줄링 & E2E 검증 엔드포인트
# ------------------------------------------------------------------ #


class PipelineRunRequest(BaseModel):
    target_date: Optional[str] = None  # ISO date string, 없으면 오늘


@router.post("/monitor/run-daily")
def run_daily_pipeline(
    req: PipelineRunRequest,
    _token: str = Depends(_verify_token),
) -> dict:
    """전체 일일 파이프라인 1회 실행 — n8n 마스터 스케줄러가 호출

    트렌드 수집 → 주제 선정 → 콘텐츠 생성 → 업로드 → 제휴 링크 삽입 → Slack 알림.
    pipeline_runs 테이블에 실행 결과 기록.
    """
    logger.info("api.monitor.run_daily", date=req.target_date)
    monitor = PipelineMonitor()
    run_id = monitor.start_run(target_date=req.target_date)

    errors: list[str] = []
    stats: dict = {
        "date": req.target_date or date.today().isoformat(),
        "blog_generated": 0,
        "blog_published": 0,
        "youtube_generated": 0,
        "youtube_published": 0,
        "reels_generated": 0,
        "reels_published": 0,
        "affiliate_inserted": 0,
        "errors": [],
    }

    # 콘텐츠 생성
    try:
        blog_results = monitor.run_step_with_retry(
            "blog_generate",
            lambda: BlogGenerator().generate_from_queue(
                target_date=req.target_date, limit=5
            ),
        )
        ok = [r for r in blog_results if "error" not in r]
        stats["blog_generated"] = len(ok)
        monitor.record_step(run_id, "blog_generate", success=True, result={"count": len(ok)})
    except Exception as exc:
        errors.append(f"blog_generate: {exc}")
        monitor.record_step(run_id, "blog_generate", success=False, error=str(exc))

    try:
        yt_results = monitor.run_step_with_retry(
            "youtube_generate",
            lambda: YouTubeGenerator().generate_from_queue(
                target_date=req.target_date, limit=1
            ),
        )
        ok = [r for r in yt_results if "error" not in r]
        stats["youtube_generated"] = len(ok)
        monitor.record_step(run_id, "youtube_generate", success=True, result={"count": len(ok)})
    except Exception as exc:
        errors.append(f"youtube_generate: {exc}")
        monitor.record_step(run_id, "youtube_generate", success=False, error=str(exc))

    try:
        reels_results = monitor.run_step_with_retry(
            "reels_generate",
            lambda: ReelsGenerator().generate_from_queue(
                target_date=req.target_date, limit=1
            ),
        )
        ok = [r for r in reels_results if "error" not in r]
        stats["reels_generated"] = len(ok)
        monitor.record_step(run_id, "reels_generate", success=True, result={"count": len(ok)})
    except Exception as exc:
        errors.append(f"reels_generate: {exc}")
        monitor.record_step(run_id, "reels_generate", success=False, error=str(exc))

    stats["errors"] = errors
    monitor.finish_run(run_id, stats)
    monitor.close()

    return {"run_id": run_id, "status": "success" if not errors else "partial", **stats}


@router.get("/monitor/stats")
def get_daily_stats(
    target_date: Optional[str] = None,
    _token: str = Depends(_verify_token),
) -> dict:
    """일별 파이프라인 실행 통계 조회"""
    monitor = PipelineMonitor()
    return monitor.get_daily_stats(target_date=target_date)


@router.get("/monitor/health")
def pipeline_health(
    _token: str = Depends(_verify_token),
) -> dict:
    """파이프라인 헬스 체크 — Supabase 연결 & 최근 콘텐츠 생성 여부"""
    monitor = PipelineMonitor()
    return monitor.get_pipeline_health()


# ------------------------------------------------------------------ #
# Phase 7: TTS + 영상 생성 엔드포인트 (CMP-74)
# ------------------------------------------------------------------ #


class VideoRenderRequest(BaseModel):
    limit: Optional[int] = 1  # 렌더링할 최대 영상 수


@router.post("/video/render")
def render_videos(
    req: VideoRenderRequest,
    _token: str = Depends(_verify_token),
) -> dict:
    """youtube_videos.status='draft', video_file_path=null 항목을 MP4로 렌더링 (CMP-74)

    스크립트 → Google Cloud TTS 음성 → Pillow 슬라이드 → FFmpeg MP4 합성.
    완료 시 video_file_path 저장, status=draft 유지 (YouTubeUploader가 업로드).
    환경 요구사항: GOOGLE_APPLICATION_CREDENTIALS, ffmpeg 설치됨.
    """
    logger.info("api.video.render", limit=req.limit)
    from src.video import VideoPipeline

    pipeline = VideoPipeline(output_dir=settings.video_output_dir)
    results = pipeline.render_pending(limit=req.limit or 1)
    success = [r for r in results if r.get("success")]
    failed = [r for r in results if not r.get("success")]
    return {
        "rendered": len(success),
        "failed": len(failed),
        "results": results,
    }


class VideoEstimateCostRequest(BaseModel):
    script: str


@router.post("/video/estimate-cost")
def estimate_video_cost(
    req: VideoEstimateCostRequest,
    _token: str = Depends(_verify_token),
) -> dict:
    """스크립트 기준 영상 생성 예상 비용 반환 (Google TTS Neural2 기준, API 호출 없음)"""
    logger.info("api.video.estimate_cost")
    from src.video.tts_generator import TTSGenerator

    gen = TTSGenerator.__new__(TTSGenerator)
    gen._voice_name = settings.google_tts_voice
    return gen.estimate_cost(req.script)


@router.get("/schedule")
def get_schedule(
    _token: str = Depends(_verify_token),
) -> dict:
    """24시간 자동 발행 스케줄 목록 반환 (KST 기준)"""
    scheduler = PipelineScheduler(
        pipeline_base_url=os.getenv("PIPELINE_BASE_URL", "http://localhost:8000"),
        api_token=PIPELINE_API_TOKEN,
    )
    schedule = scheduler.get_schedule()
    return {"schedule": schedule, "count": len(schedule)}


class TriggerJobRequest(BaseModel):
    job_id: str


@router.post("/schedule/trigger")
def schedule_trigger_job(
    req: TriggerJobRequest,
    _token: str = Depends(_verify_token),
) -> dict:
    """특정 스케줄 job 즉시 수동 실행 (디버깅/테스트용)"""
    logger.info("api.schedule.trigger", job_id=req.job_id)
    scheduler = PipelineScheduler(
        pipeline_base_url=os.getenv("PIPELINE_BASE_URL", "http://localhost:8000"),
        api_token=PIPELINE_API_TOKEN,
    )
    return scheduler.trigger_job(req.job_id)


class E2ERunRequest(BaseModel):
    target_date: Optional[str] = None


@router.post("/e2e/run")
def e2e_run_pipeline(
    req: E2ERunRequest,
    _token: str = Depends(_verify_token),
) -> dict:
    """E2E 전체 파이프라인 검증 — 트렌드 수집 → 콘텐츠 생성 → 업로드 순서 실행.

    사람 개입 없이 완전 자동화 흐름을 검증한다.
    각 단계 결과를 모니터링에 기록하고 최종 Slack 요약 발송.
    """
    logger.info("api.e2e.run", target_date=req.target_date)
    monitor = PipelineMonitor()
    scheduler = PipelineScheduler(
        pipeline_base_url=os.getenv("PIPELINE_BASE_URL", "http://localhost:8000"),
        api_token=PIPELINE_API_TOKEN,
    )
    run_id = monitor.start_run(target_date=req.target_date)

    steps = [
        ("trend_collect", "/api/pipeline/trends/collect",
         {"sources": ["google_trends", "naver_datalab", "rss"], "limit": 20}),
        ("blog_generate", "/api/pipeline/content/generate-blog",
         {"limit": 5, **({"target_date": req.target_date} if req.target_date else {})}),
        ("youtube_generate", "/api/pipeline/content/generate-youtube",
         {"limit": 1, **({"target_date": req.target_date} if req.target_date else {})}),
        ("reels_generate", "/api/pipeline/content/generate-reels",
         {"limit": 1, **({"target_date": req.target_date} if req.target_date else {})}),
        ("blog_upload", "/api/pipeline/upload/blog", {"limit": 5}),
        ("youtube_upload", "/api/pipeline/upload/youtube", {"limit": 1}),
        ("reels_upload", "/api/pipeline/upload/reels", {"limit": 1}),
    ]

    step_results: dict[str, dict] = {}
    errors: list[str] = []

    for step_id, path, payload in steps:
        try:
            result = monitor.run_step_with_retry(step_id, scheduler._call, path, payload)
            step_results[step_id] = result
            monitor.record_step(run_id, step_id, success=True, result=result)
        except Exception as exc:
            errors.append(f"{step_id}: {exc}")
            step_results[step_id] = {"error": str(exc)}
            monitor.record_step(run_id, step_id, success=False, error=str(exc))
            logger.error("api.e2e.step_failed", step=step_id, error=str(exc))

    blog_r = step_results.get("blog_generate", {})
    yt_r = step_results.get("youtube_generate", {})
    reels_r = step_results.get("reels_generate", {})

    stats = {
        "date": req.target_date or date.today().isoformat(),
        "run_id": run_id,
        "blog_generated": blog_r.get("generated", 0),
        "blog_published": step_results.get("blog_upload", {}).get("uploaded", 0),
        "blog_failed": blog_r.get("failed", 0),
        "youtube_generated": yt_r.get("generated", 0),
        "youtube_published": step_results.get("youtube_upload", {}).get("uploaded", 0),
        "reels_generated": reels_r.get("generated", 0),
        "reels_published": step_results.get("reels_upload", {}).get("uploaded", 0),
        "errors": errors,
    }

    monitor.finish_run(run_id=run_id, stats=stats)
    monitor.close()

    return {
        "run_id": run_id,
        "success": len(errors) == 0,
        "stats": stats,
        "step_results": step_results,
    }
