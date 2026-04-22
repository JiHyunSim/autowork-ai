"""E2E 파이프라인 검증 테스트 (Phase 6)

사람 개입 없이 완전 자동화 흐름이 동작하는지 검증.
dry_run=True 모드로 실제 API 호출 없이 구조적 정확성만 검증한다.

커버리지:
  - PipelineMonitor: run lifecycle (start → record_step → finish)
  - PipelineMonitor: run_step_with_retry 재시도 메커니즘
  - PipelineRunner: 전체 E2E 흐름 (dry_run)
  - PipelineScheduler: schedule 정의 & trigger_job 라우팅
  - SlackNotifier: Webhook 없이 graceful skip
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch, call
import pytest

from src.monitoring.pipeline_monitor import PipelineMonitor
from src.monitoring.pipeline_runner import PipelineRunner
from src.monitoring.slack_notifier import SlackNotifier
from src.scheduler.pipeline_scheduler import PipelineScheduler, PIPELINE_SCHEDULE


# ================================================================== #
# PipelineMonitor tests
# ================================================================== #


@pytest.fixture()
def mock_supabase():
    sb = MagicMock()
    table = MagicMock()
    sb.table.return_value = table
    table.insert.return_value = table
    table.update.return_value = table
    table.select.return_value = table
    table.eq.return_value = table
    table.order.return_value = table
    table.limit.return_value = table
    table.single.return_value = table
    table.execute.return_value = MagicMock(data=[])
    return sb


@pytest.fixture()
def monitor(mock_supabase):
    m = PipelineMonitor(supabase=mock_supabase)
    # Slack 알림 비활성화
    m._notifier = MagicMock(spec=SlackNotifier)
    return m


class TestPipelineMonitorLifecycle:
    def test_start_run_returns_uuid(self, monitor, mock_supabase):
        run_id = monitor.start_run("2026-04-22")
        assert len(run_id) == 36  # UUID 형식
        # pipeline_runs 테이블에 insert 호출 확인
        mock_supabase.table.assert_any_call("pipeline_runs")

    def test_finish_run_calls_slack(self, monitor):
        run_id = monitor.start_run("2026-04-22")
        stats = {
            "date": "2026-04-22",
            "blog_generated": 5,
            "blog_published": 5,
            "errors": [],
        }
        monitor.finish_run(run_id, stats)
        monitor._notifier.notify_daily_summary.assert_called_once_with(stats)
        monitor._notifier.notify_pipeline_complete.assert_called_once()

    def test_record_step_success(self, monitor, mock_supabase):
        run_id = monitor.start_run("2026-04-22")
        monitor.record_step(run_id, "blog_generate", success=True, result={"count": 5})
        mock_supabase.table.assert_any_call("pipeline_run_steps")
        # 성공 시 오류 알림 미발송
        monitor._notifier.notify_error.assert_not_called()

    def test_record_step_failure_sends_alert(self, monitor):
        run_id = monitor.start_run("2026-04-22")
        monitor.record_step(
            run_id, "blog_upload", success=False, error="Tistory API error"
        )
        monitor._notifier.notify_error.assert_called_once()
        args = monitor._notifier.notify_error.call_args
        assert args.kwargs["phase"] == "blog_upload"
        assert "Tistory API error" in args.kwargs["error"]


class TestRunStepWithRetry:
    def test_success_on_first_attempt(self, monitor):
        fn = MagicMock(return_value={"ok": True})
        result = monitor.run_step_with_retry("step", fn)
        assert result == {"ok": True}
        fn.assert_called_once()

    def test_retries_on_failure_then_success(self, monitor):
        fn = MagicMock(side_effect=[ValueError("fail1"), ValueError("fail2"), {"ok": True}])
        result = monitor.run_step_with_retry("step", fn, max_retries=3)
        assert result == {"ok": True}
        assert fn.call_count == 3

    def test_raises_after_max_retries(self, monitor):
        fn = MagicMock(side_effect=RuntimeError("always fails"))
        with pytest.raises(RuntimeError, match="always fails"):
            monitor.run_step_with_retry("step", fn, max_retries=2)
        assert fn.call_count == 2

    def test_no_sleep_on_single_attempt(self, monitor):
        """성공 시 sleep 없이 즉시 반환 — 테스트가 느려지지 않는지 확인"""
        import time
        fn = MagicMock(return_value={"ok": True})
        start = time.monotonic()
        monitor.run_step_with_retry("step", fn, max_retries=3)
        elapsed = time.monotonic() - start
        assert elapsed < 0.5  # 성공 시 sleep 없음


class TestGetDailyStats:
    def test_returns_date_key(self, monitor, mock_supabase):
        result = monitor.get_daily_stats("2026-04-22")
        assert result["date"] == "2026-04-22"

    def test_handles_db_error(self, monitor, mock_supabase):
        mock_supabase.table.return_value.select.return_value.eq.return_value.order.return_value.execute.side_effect = Exception(
            "DB down"
        )
        result = monitor.get_daily_stats("2026-04-22")
        assert "error" in result


class TestPipelineHealth:
    def test_healthy_when_no_runs(self, monitor):
        health = monitor.get_pipeline_health()
        assert health["status"] in ("healthy", "unhealthy")

    def test_degraded_when_last_run_failed(self, monitor, mock_supabase):
        mock_supabase.table.return_value.select.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"id": "abc", "status": "failed", "started_at": "2026-04-22T06:00:00"}]
        )
        health = monitor.get_pipeline_health()
        assert health["status"] == "degraded"


# ================================================================== #
# PipelineRunner (dry_run) tests
# ================================================================== #


class TestPipelineRunner:
    @pytest.fixture()
    def runner(self, monitor):
        return PipelineRunner(monitor=monitor, dry_run=True)

    def test_run_returns_stats_dict(self, runner):
        stats = runner.run("2026-04-22")
        assert "date" in stats
        assert stats["date"] == "2026-04-22"
        assert "blog_generated" in stats
        assert "reels_generated" in stats

    def test_dry_run_generates_expected_counts(self, runner):
        stats = runner.run("2026-04-22")
        # dry_run은 하드코딩된 결과 반환
        assert stats["blog_generated"] == 5
        assert stats["blog_published"] == 5
        assert stats["reels_generated"] == 1
        assert stats["reels_published"] == 1

    def test_youtube_runs_on_monday(self, runner):
        # 2026-04-20 = 월요일 (weekday=0)
        stats = runner.run("2026-04-20")
        assert stats["youtube_generated"] == 1

    def test_youtube_skipped_on_tuesday(self, runner):
        # 2026-04-21 = 화요일 (weekday=1) — YouTube 안함
        stats = runner.run("2026-04-21")
        assert stats["youtube_generated"] == 0

    def test_monitor_called_with_run_start(self, runner, monitor):
        monitor.start_run = MagicMock(return_value="test-run-id")
        runner.run("2026-04-22")
        monitor.start_run.assert_called_once_with("2026-04-22")


# ================================================================== #
# SlackNotifier tests
# ================================================================== #


class TestSlackNotifier:
    def test_returns_false_when_no_webhook(self):
        notifier = SlackNotifier(webhook_url="")
        assert notifier.notify_pipeline_start("2026-04-22") is False

    def test_sends_with_webhook(self):
        notifier = SlackNotifier(webhook_url="http://example.com/hook")
        with patch.object(notifier._client, "post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_post.return_value = mock_resp
            result = notifier.notify_pipeline_start("2026-04-22")
        assert result is True
        mock_post.assert_called_once()

    def test_error_notification_includes_phase(self):
        notifier = SlackNotifier(webhook_url="http://example.com/hook")
        with patch.object(notifier._client, "post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_post.return_value = mock_resp
            notifier.notify_error(phase="blog_upload", error="timeout")
        call_args = mock_post.call_args
        body = call_args.kwargs.get("content", "")
        assert "blog_upload" in body

    def test_daily_summary_includes_counts(self):
        notifier = SlackNotifier(webhook_url="http://example.com/hook")
        stats = {
            "date": "2026-04-22",
            "blog_generated": 5,
            "blog_published": 5,
            "youtube_published": 1,
            "reels_published": 1,
            "affiliate_inserted": 4,
            "errors": [],
        }
        with patch.object(notifier._client, "post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_post.return_value = mock_resp
            notifier.notify_daily_summary(stats)
        body = mock_post.call_args.kwargs.get("content", "")
        assert "5" in body  # 블로그 카운트
        assert "2026-04-22" in body


# ================================================================== #
# PipelineScheduler tests
# ================================================================== #


class TestPipelineScheduler:
    def test_get_schedule_returns_all_jobs(self):
        scheduler = PipelineScheduler()
        schedule = scheduler.get_schedule()
        assert len(schedule) == len(PIPELINE_SCHEDULE)
        for item in schedule:
            assert "job_id" in item
            assert "cron" in item
            assert "endpoint" in item

    def test_trigger_job_calls_correct_endpoint(self):
        scheduler = PipelineScheduler()
        with patch.object(scheduler, "_call") as mock_call:
            mock_call.return_value = {"ok": True}
            result = scheduler.trigger_job("trend_collect")
        assert result == {"ok": True}
        path_called = mock_call.call_args.args[0]
        assert "trends" in path_called

    def test_trigger_unknown_job_returns_error(self):
        scheduler = PipelineScheduler()
        result = scheduler.trigger_job("nonexistent_job")
        assert "error" in result

    def test_schedule_covers_required_steps(self):
        """필수 단계 — 트렌드/블로그/릴스/유튜브 — 스케줄에 포함 확인"""
        scheduler = PipelineScheduler()
        job_ids = {item["job_id"] for item in scheduler.get_schedule()}
        required = {"trend_collect", "blog_generate_1", "reels_generate", "youtube_generate"}
        assert required.issubset(job_ids)
