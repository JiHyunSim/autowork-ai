"""24시간 자동 발행 스케줄러 — APScheduler 기반

스케줄:
  - 매일 06:00 KST: 트렌드 수집 → 큐 생성 → 블로그 5개 생성/발행 → 릴스 1개
  - 매주 월/수/금 07:00 KST: 유튜브 스크립트 생성 (주 3개)
  - 매일 23:50 KST: 일별 요약 Slack 알림
"""
from __future__ import annotations

import os
from datetime import datetime, date
from typing import Optional

import structlog

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    HAS_APSCHEDULER = True
except ImportError:
    HAS_APSCHEDULER = False

from src.config import settings

logger = structlog.get_logger(__name__)

# KST = UTC+9
KST_TIMEZONE = "Asia/Seoul"


class ContentScheduler:
    """콘텐츠 파이프라인 24시간 자동 발행 스케줄러"""

    def __init__(self) -> None:
        if not HAS_APSCHEDULER:
            raise ImportError(
                "APScheduler가 설치되지 않았습니다. "
                "pip install apscheduler 를 실행하세요."
            )
        self._scheduler = BackgroundScheduler(timezone=KST_TIMEZONE)
        self._jobs: dict[str, str] = {}  # job_name → job_id
        self._pipeline_api_url = os.getenv(
            "PIPELINE_API_URL", "http://localhost:8000"
        )
        self._api_token = os.getenv("PIPELINE_API_TOKEN", "")

    # ------------------------------------------------------------------ #
    # 스케줄 등록
    # ------------------------------------------------------------------ #

    def setup_jobs(self) -> None:
        """전체 스케줄 잡 등록"""
        # 1. 매일 06:00 KST — 블로그 + 릴스 발행 파이프라인
        job_daily = self._scheduler.add_job(
            func=self._run_daily_pipeline,
            trigger=CronTrigger(hour=6, minute=0, timezone=KST_TIMEZONE),
            id="daily_content_pipeline",
            name="Daily Blog & Reels Pipeline",
            replace_existing=True,
            misfire_grace_time=600,
        )
        self._jobs["daily_content_pipeline"] = job_daily.id

        # 2. 매주 월/수/금 07:00 KST — 유튜브 스크립트 발행
        job_youtube = self._scheduler.add_job(
            func=self._run_youtube_pipeline,
            trigger=CronTrigger(
                day_of_week="mon,wed,fri",
                hour=7,
                minute=0,
                timezone=KST_TIMEZONE,
            ),
            id="youtube_pipeline",
            name="YouTube Script Pipeline (Mon/Wed/Fri)",
            replace_existing=True,
            misfire_grace_time=600,
        )
        self._jobs["youtube_pipeline"] = job_youtube.id

        # 3. 매일 23:50 KST — 일별 요약 알림
        job_summary = self._scheduler.add_job(
            func=self._send_daily_summary,
            trigger=CronTrigger(hour=23, minute=50, timezone=KST_TIMEZONE),
            id="daily_summary",
            name="Daily Summary Notification",
            replace_existing=True,
        )
        self._jobs["daily_summary"] = job_summary.id

        logger.info(
            "scheduler.jobs_registered",
            jobs=list(self._jobs.keys()),
        )

    # ------------------------------------------------------------------ #
    # 잡 구현
    # ------------------------------------------------------------------ #

    def _run_daily_pipeline(self) -> None:
        """매일 실행: 트렌드 수집 → 블로그 + 릴스 생성/발행 + 제휴 링크"""
        import httpx

        today = date.today().isoformat()
        logger.info("scheduler.daily_pipeline_start", date=today)

        headers = {}
        if self._api_token:
            headers["Authorization"] = f"Bearer {self._api_token}"

        base = self._pipeline_api_url

        try:
            with httpx.Client(timeout=300.0) as client:
                # 1. 트렌드 수집
                resp = client.post(
                    f"{base}/api/pipeline/trends/collect",
                    json={"sources": ["google_trends", "naver_datalab", "rss"], "limit": 20},
                    headers=headers,
                )
                resp.raise_for_status()
                trends_data = resp.json()
                logger.info("scheduler.trends_collected", count=trends_data.get("count"))

                # 2. 큐 생성
                resp = client.post(
                    f"{base}/api/pipeline/topics/generate-queue",
                    json={
                        "trends": trends_data.get("trends", []),
                        "blog_count": settings.daily_blog_target,
                        "reels_count": settings.daily_reels_target,
                        "target_date": today,
                    },
                    headers=headers,
                )
                resp.raise_for_status()
                logger.info("scheduler.queue_generated", date=today)

                # 3. 블로그 생성
                resp = client.post(
                    f"{base}/api/pipeline/content/generate-blog",
                    json={"target_date": today, "limit": settings.daily_blog_target},
                    headers=headers,
                )
                resp.raise_for_status()
                blog_result = resp.json()
                logger.info(
                    "scheduler.blog_generated",
                    generated=blog_result.get("generated"),
                )

                # 4. 블로그 발행
                resp = client.post(
                    f"{base}/api/pipeline/upload/blog",
                    json={"target_date": today, "limit": settings.daily_blog_target},
                    headers=headers,
                )
                resp.raise_for_status()
                upload_result = resp.json()
                logger.info(
                    "scheduler.blog_uploaded",
                    uploaded=upload_result.get("uploaded"),
                )

                # 5. 릴스 생성
                resp = client.post(
                    f"{base}/api/pipeline/content/generate-reels",
                    json={"target_date": today, "limit": settings.daily_reels_target},
                    headers=headers,
                )
                resp.raise_for_status()
                logger.info("scheduler.reels_generated", date=today)

                # 6. 릴스 발행
                resp = client.post(
                    f"{base}/api/pipeline/upload/reels",
                    json={"target_date": today, "limit": settings.daily_reels_target},
                    headers=headers,
                )
                resp.raise_for_status()
                logger.info("scheduler.reels_uploaded", date=today)

        except Exception as exc:
            logger.error("scheduler.daily_pipeline_failed", error=str(exc), date=today)
            # 오류 알림은 PipelineMonitor에서 발송됨

    def _run_youtube_pipeline(self) -> None:
        """월/수/금 실행: 유튜브 스크립트 생성 + 발행"""
        import httpx

        today = date.today().isoformat()
        logger.info("scheduler.youtube_pipeline_start", date=today)

        headers = {}
        if self._api_token:
            headers["Authorization"] = f"Bearer {self._api_token}"

        base = self._pipeline_api_url

        try:
            with httpx.Client(timeout=300.0) as client:
                # 유튜브 스크립트 생성 (주 3개 목표 중 1개/실행)
                resp = client.post(
                    f"{base}/api/pipeline/content/generate-youtube",
                    json={"target_date": today, "limit": 1},
                    headers=headers,
                )
                resp.raise_for_status()
                yt_result = resp.json()
                logger.info(
                    "scheduler.youtube_generated",
                    generated=yt_result.get("generated"),
                )

                # 유튜브 업로드 (메타데이터만 — 영상 파일은 별도 처리)
                resp = client.post(
                    f"{base}/api/pipeline/upload/youtube",
                    json={"target_date": today, "limit": 1},
                    headers=headers,
                )
                resp.raise_for_status()
                logger.info("scheduler.youtube_uploaded", date=today)

        except Exception as exc:
            logger.error("scheduler.youtube_pipeline_failed", error=str(exc), date=today)

    def _send_daily_summary(self) -> None:
        """23:50 실행: 일별 통계 수집 후 Slack 요약 알림"""
        import httpx

        from src.monitoring.slack_notifier import SlackNotifier

        today = date.today().isoformat()
        logger.info("scheduler.daily_summary_start", date=today)

        try:
            with httpx.Client(timeout=30.0) as client:
                headers = {}
                if self._api_token:
                    headers["Authorization"] = f"Bearer {self._api_token}"

                resp = client.get(
                    f"{self._pipeline_api_url}/api/pipeline/monitor/daily-stats",
                    params={"target_date": today},
                    headers=headers,
                )
                resp.raise_for_status()
                stats = resp.json()

            notifier = SlackNotifier()
            notifier.notify_daily_summary(stats)
            notifier.close()
            logger.info("scheduler.daily_summary_sent", date=today)

        except Exception as exc:
            logger.error("scheduler.daily_summary_failed", error=str(exc))

    # ------------------------------------------------------------------ #
    # 라이프사이클
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        self.setup_jobs()
        self._scheduler.start()
        logger.info(
            "scheduler.started",
            job_count=len(self._jobs),
            next_runs={
                j.id: str(j.next_run_time)
                for j in self._scheduler.get_jobs()
            },
        )

    def stop(self) -> None:
        self._scheduler.shutdown(wait=False)
        logger.info("scheduler.stopped")

    def get_status(self) -> dict:
        """스케줄러 상태 & 잡 목록 반환"""
        jobs = []
        for job in self._scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run_time": str(job.next_run_time) if job.next_run_time else None,
                "trigger": str(job.trigger),
            })
        return {
            "running": self._scheduler.running,
            "timezone": KST_TIMEZONE,
            "jobs": jobs,
        }

    def trigger_now(self, job_id: str) -> bool:
        """잡을 즉시 수동 실행 (테스트/운영 용도)"""
        try:
            self._scheduler.get_job(job_id).modify(next_run_time=datetime.now())
            logger.info("scheduler.manual_trigger", job_id=job_id)
            return True
        except Exception as exc:
            logger.error("scheduler.trigger_failed", job_id=job_id, error=str(exc))
            return False
