"""24시간 자동 발행 스케줄러 (Phase 6)

APScheduler를 사용해 KST 기준 아래 스케줄을 유지한다:

  07:00  트렌드 수집 + 주제 선정 큐 생성
  08:00  블로그 생성 (1차 — 2개)
  09:00  블로그 발행 (1차)
  10:00  블로그 생성 (2차 — 2개) + 유튜브 스크립트 생성
  11:00  블로그 발행 (2차) + 유튜브 메타데이터 등록
  14:00  블로그 생성 (3차 — 1개) + 릴스 생성
  15:00  블로그 발행 (3차) + 릴스 발행
  16:00  제휴 링크 삽입 (당일 블로그 전체)
  23:30  일별 리포트 생성 + Slack 요약 발송
"""
from __future__ import annotations

import httpx
import structlog
from typing import Optional

logger = structlog.get_logger(__name__)

# 스케줄 정의 — (job_id, cron_표현식, 엔드포인트_경로, payload_dict)
PIPELINE_SCHEDULE: list[tuple[str, str, str, dict]] = [
    (
        "trend_collect",
        "0 7 * * *",
        "/api/pipeline/trends/collect",
        {"sources": ["google_trends", "naver_datalab", "rss"], "limit": 20},
    ),
    (
        "blog_generate_1",
        "0 8 * * *",
        "/api/pipeline/content/generate-blog",
        {"limit": 2},
    ),
    (
        "blog_upload_1",
        "0 9 * * *",
        "/api/pipeline/upload/blog",
        {"limit": 2},
    ),
    (
        "blog_generate_2",
        "0 10 * * *",
        "/api/pipeline/content/generate-blog",
        {"limit": 2},
    ),
    (
        "youtube_generate",
        "0 10 * * *",
        "/api/pipeline/content/generate-youtube",
        {"limit": 1},
    ),
    (
        "blog_upload_2",
        "0 11 * * *",
        "/api/pipeline/upload/blog",
        {"limit": 2},
    ),
    (
        "youtube_upload",
        "0 11 * * *",
        "/api/pipeline/upload/youtube",
        {"limit": 1},
    ),
    (
        "blog_generate_3",
        "0 14 * * *",
        "/api/pipeline/content/generate-blog",
        {"limit": 1},
    ),
    (
        "reels_generate",
        "0 14 * * *",
        "/api/pipeline/content/generate-reels",
        {"limit": 1},
    ),
    (
        "blog_upload_3",
        "0 15 * * *",
        "/api/pipeline/upload/blog",
        {"limit": 1},
    ),
    (
        "reels_upload",
        "0 15 * * *",
        "/api/pipeline/upload/reels",
        {"limit": 1},
    ),
]


class PipelineScheduler:
    """파이프라인 스케줄 관리자

    n8n 스케줄러 워크플로우가 없는 경우를 대비한 Python-native 스케줄러.
    APScheduler(BackgroundScheduler)를 사용해 FastAPI 서버와 함께 실행된다.
    실제 프로덕션 환경에서는 n8n 워크플로우 스케줄 트리거가 이 역할을 대체한다.
    """

    def __init__(
        self,
        pipeline_base_url: str = "http://localhost:8000",
        api_token: str = "",
        timezone: str = "Asia/Seoul",
    ) -> None:
        self._base_url = pipeline_base_url.rstrip("/")
        self._token = api_token
        self._timezone = timezone
        self._scheduler = None
        self._client = httpx.Client(timeout=120.0)

    def get_schedule(self) -> list[dict]:
        """현재 스케줄 정의 목록 반환 (API 응답용)"""
        return [
            {
                "job_id": job_id,
                "cron": cron,
                "endpoint": path,
                "payload": payload,
                "timezone": self._timezone,
            }
            for job_id, cron, path, payload in PIPELINE_SCHEDULE
        ]

    def trigger_job(self, job_id: str) -> dict:
        """특정 job을 즉시 수동 실행 (테스트/디버깅용)"""
        for jid, _, path, payload in PIPELINE_SCHEDULE:
            if jid == job_id:
                return self._call(path, payload)
        return {"error": f"job_id '{job_id}' not found"}

    def trigger_full_pipeline(self, target_date: Optional[str] = None) -> dict:
        """전체 파이프라인을 순서대로 동기 실행 (E2E 검증용)

        실제 발행 대신 dry_run=True를 사용하면 API 호출 없이 시뮬레이션만 수행.
        """
        results: dict[str, dict] = {}
        steps = [
            ("trend_collect", "/api/pipeline/trends/collect",
             {"sources": ["google_trends", "naver_datalab", "rss"], "limit": 20}),
            ("topic_queue", "/api/pipeline/topics/generate-queue",
             {"trends": [], "blog_count": 5, "youtube_count": 1, "reels_count": 1,
              **({"target_date": target_date} if target_date else {})}),
            ("blog_generate", "/api/pipeline/content/generate-blog",
             {"limit": 5, **({"target_date": target_date} if target_date else {})}),
            ("youtube_generate", "/api/pipeline/content/generate-youtube",
             {"limit": 1, **({"target_date": target_date} if target_date else {})}),
            ("reels_generate", "/api/pipeline/content/generate-reels",
             {"limit": 1, **({"target_date": target_date} if target_date else {})}),
            ("blog_upload", "/api/pipeline/upload/blog", {"limit": 5}),
            ("youtube_upload", "/api/pipeline/upload/youtube", {"limit": 1}),
            ("reels_upload", "/api/pipeline/upload/reels", {"limit": 1}),
        ]
        for step_id, path, payload in steps:
            logger.info("pipeline_scheduler.trigger_step", step=step_id)
            try:
                results[step_id] = self._call(path, payload)
            except Exception as exc:
                results[step_id] = {"error": str(exc)}
                logger.error(
                    "pipeline_scheduler.step_failed", step=step_id, error=str(exc)
                )
        return {"steps": results, "total": len(steps)}

    def _call(self, path: str, payload: dict) -> dict:
        headers = {}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        resp = self._client.post(
            f"{self._base_url}{path}",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json()

    def start(self) -> None:
        """APScheduler BackgroundScheduler 시작"""
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.triggers.cron import CronTrigger

            self._scheduler = BackgroundScheduler(timezone=self._timezone)
            for job_id, cron_expr, path, payload in PIPELINE_SCHEDULE:
                parts = cron_expr.split()
                minute, hour, day, month, day_of_week = parts
                self._scheduler.add_job(
                    func=self._call,
                    trigger=CronTrigger(
                        minute=minute,
                        hour=hour,
                        day=day,
                        month=month,
                        day_of_week=day_of_week,
                        timezone=self._timezone,
                    ),
                    args=[path, payload],
                    id=job_id,
                    replace_existing=True,
                )
                logger.info(
                    "pipeline_scheduler.job_registered",
                    job_id=job_id,
                    cron=cron_expr,
                )
            self._scheduler.start()
            logger.info("pipeline_scheduler.started", timezone=self._timezone)
        except ImportError:
            logger.warning(
                "pipeline_scheduler.apscheduler_not_installed",
                hint="pip install apscheduler>=3.10",
            )

    def stop(self) -> None:
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown()
            logger.info("pipeline_scheduler.stopped")
        self._client.close()
