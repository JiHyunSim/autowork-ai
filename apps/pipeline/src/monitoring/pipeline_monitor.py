"""파이프라인 모니터링 & 오류 추적 (Phase 6)

파이프라인 각 단계의 실행 결과를 Supabase pipeline_runs 테이블에 기록하고
Slack 알림을 통해 성공/실패를 보고한다.

재시도 메커니즘:
- 단계별 실패 시 최대 MAX_RETRIES 회 재시도
- 지수 백오프 (1초, 2초, 4초)
- 최종 실패 시 Slack 오류 알림 발송
"""
from __future__ import annotations

import time
from datetime import datetime, date
from typing import Optional, Callable, Any
from uuid import uuid4

import structlog
from supabase import create_client, Client

from src.config import settings
from src.monitoring.slack_notifier import SlackNotifier

logger = structlog.get_logger(__name__)

MAX_RETRIES = 3
BASE_BACKOFF_SEC = 1.0


def _get_supabase() -> Client:
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


class PipelineMonitor:
    """파이프라인 실행 모니터링 및 상태 추적

    사용 예시:
        monitor = PipelineMonitor()
        run_id = monitor.start_run(target_date="2026-04-22")
        try:
            result = monitor.run_step_with_retry("blog_generate", fn, **kwargs)
            monitor.record_step(run_id, "blog_generate", success=True, result=result)
        except Exception as e:
            monitor.record_step(run_id, "blog_generate", success=False, error=str(e))
        finally:
            monitor.finish_run(run_id, stats)
    """

    def __init__(self, supabase: Optional[Client] = None) -> None:
        self._db: Optional[Client] = supabase
        self._notifier = SlackNotifier()
        self._run_cache: dict[str, dict] = {}  # run_id → 런타임 메타데이터

    @property
    def db(self) -> Client:
        if self._db is None:
            self._db = _get_supabase()
        return self._db

    # ------------------------------------------------------------------ #
    # 런 생명주기
    # ------------------------------------------------------------------ #

    def start_run(self, target_date: Optional[str] = None) -> str:
        """파이프라인 런 시작 — pipeline_runs 레코드 생성 후 run_id 반환"""
        run_id = str(uuid4())
        now = datetime.utcnow().isoformat()
        target = target_date or date.today().isoformat()

        self._run_cache[run_id] = {
            "run_id": run_id,
            "target_date": target,
            "started_at": now,
            "steps": [],
        }

        try:
            self.db.table("pipeline_runs").insert({
                "id": run_id,
                "target_date": target,
                "status": "running",
                "started_at": now,
            }).execute()
        except Exception as exc:
            logger.warning("pipeline_monitor.start_run.db_error", error=str(exc))

        self._notifier.notify_pipeline_start(target)
        logger.info("pipeline_monitor.run_started", run_id=run_id, target_date=target)
        return run_id

    def finish_run(self, run_id: str, stats: dict) -> None:
        """파이프라인 런 완료 — DB 업데이트 + Slack 일별 요약 알림"""
        cache = self._run_cache.get(run_id, {})
        started_at_str = cache.get("started_at", datetime.utcnow().isoformat())
        try:
            started_at = datetime.fromisoformat(started_at_str)
            duration_sec = (datetime.utcnow() - started_at).total_seconds()
        except Exception:
            duration_sec = 0.0

        errors = stats.get("errors", [])
        status = "failed" if errors else "success"

        try:
            self.db.table("pipeline_runs").update({
                "status": status,
                "completed_at": datetime.utcnow().isoformat(),
                "duration_sec": duration_sec,
                "stats": stats,
            }).eq("id", run_id).execute()
        except Exception as exc:
            logger.warning("pipeline_monitor.finish_run.db_error", error=str(exc))

        # Slack 알림
        self._notifier.notify_daily_summary(stats)
        target = cache.get("target_date", stats.get("date", ""))
        self._notifier.notify_pipeline_complete(target, duration_sec)

        logger.info(
            "pipeline_monitor.run_finished",
            run_id=run_id,
            status=status,
            duration_sec=duration_sec,
        )

    # ------------------------------------------------------------------ #
    # 단계별 기록
    # ------------------------------------------------------------------ #

    def record_step(
        self,
        run_id: str,
        step_name: str,
        success: bool,
        result: Optional[dict] = None,
        error: Optional[str] = None,
    ) -> None:
        """단계 실행 결과를 DB에 기록"""
        step_data = {
            "run_id": run_id,
            "step_name": step_name,
            "success": success,
            "result_summary": result or {},
            "error": error,
            "recorded_at": datetime.utcnow().isoformat(),
        }

        if run_id in self._run_cache:
            self._run_cache[run_id]["steps"].append(step_data)

        try:
            self.db.table("pipeline_run_steps").insert(step_data).execute()
        except Exception as exc:
            logger.warning("pipeline_monitor.record_step.db_error", error=str(exc))

        if not success and error:
            self._notifier.notify_error(
                phase=step_name,
                error=error,
                context={"run_id": run_id},
            )

        logger.info(
            "pipeline_monitor.step_recorded",
            run_id=run_id,
            step=step_name,
            success=success,
        )

    # ------------------------------------------------------------------ #
    # 재시도 메커니즘
    # ------------------------------------------------------------------ #

    def run_step_with_retry(
        self,
        step_name: str,
        fn: Callable[..., Any],
        *args: Any,
        max_retries: int = MAX_RETRIES,
        **kwargs: Any,
    ) -> Any:
        """fn을 최대 max_retries 회 재시도하며 실행한다 (지수 백오프).

        성공 시 결과 반환, 모든 시도 실패 시 마지막 예외를 re-raise.
        """
        last_exc: Optional[Exception] = None
        for attempt in range(1, max_retries + 1):
            try:
                result = fn(*args, **kwargs)
                if attempt > 1:
                    logger.info(
                        "pipeline_monitor.retry_succeeded",
                        step=step_name,
                        attempt=attempt,
                    )
                return result
            except Exception as exc:
                last_exc = exc
                backoff = BASE_BACKOFF_SEC * (2 ** (attempt - 1))
                logger.warning(
                    "pipeline_monitor.retry",
                    step=step_name,
                    attempt=attempt,
                    max_retries=max_retries,
                    backoff_sec=backoff,
                    error=str(exc),
                )
                if attempt < max_retries:
                    time.sleep(backoff)

        raise last_exc  # type: ignore[misc]

    # ------------------------------------------------------------------ #
    # 메트릭 조회
    # ------------------------------------------------------------------ #

    def get_run_stats(self, run_id: str) -> dict:
        """특정 런의 집계 메트릭 조회"""
        try:
            resp = (
                self.db.table("pipeline_runs")
                .select("*")
                .eq("id", run_id)
                .single()
                .execute()
            )
            return resp.data or {}
        except Exception as exc:
            logger.warning("pipeline_monitor.get_run_stats.error", error=str(exc))
            return {}

    def get_daily_stats(self, target_date: Optional[str] = None) -> dict:
        """일별 파이프라인 실행 통계 요약 조회"""
        target = target_date or date.today().isoformat()
        try:
            resp = (
                self.db.table("pipeline_runs")
                .select("*")
                .eq("target_date", target)
                .order("started_at", desc=True)
                .execute()
            )
            runs = resp.data or []
            total = len(runs)
            success_count = sum(1 for r in runs if r.get("status") == "success")
            failed_count = sum(1 for r in runs if r.get("status") == "failed")
            return {
                "date": target,
                "total_runs": total,
                "success": success_count,
                "failed": failed_count,
                "runs": runs,
            }
        except Exception as exc:
            logger.warning("pipeline_monitor.get_daily_stats.error", error=str(exc))
            return {"date": target, "total_runs": 0, "error": str(exc)}

    def get_pipeline_health(self) -> dict:
        """파이프라인 헬스 체크 — Supabase 연결 & 최근 런 상태"""
        health: dict = {"supabase": "ok", "last_run": None, "status": "healthy"}
        try:
            resp = (
                self.db.table("pipeline_runs")
                .select("id, status, started_at, target_date")
                .order("started_at", desc=True)
                .limit(1)
                .execute()
            )
            runs = resp.data or []
            if runs:
                health["last_run"] = runs[0]
                if runs[0].get("status") == "failed":
                    health["status"] = "degraded"
        except Exception as exc:
            health["supabase"] = f"error: {exc}"
            health["status"] = "unhealthy"
        return health

    def close(self) -> None:
        self._notifier.close()
