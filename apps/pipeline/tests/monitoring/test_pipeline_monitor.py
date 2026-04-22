"""PipelineMonitor 단위 테스트 (Phase 6)"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch, call
import pytest

from src.monitoring.pipeline_monitor import PipelineMonitor, MAX_RETRIES


# ------------------------------------------------------------------ #
# 픽스처
# ------------------------------------------------------------------ #


@pytest.fixture
def mock_supabase():
    """Supabase 클라이언트 목(mock)"""
    client = MagicMock()
    # table().insert().execute() 체인 설정
    table_mock = MagicMock()
    client.table.return_value = table_mock
    table_mock.insert.return_value = table_mock
    table_mock.update.return_value = table_mock
    table_mock.select.return_value = table_mock
    table_mock.eq.return_value = table_mock
    table_mock.order.return_value = table_mock
    table_mock.limit.return_value = table_mock
    table_mock.single.return_value = table_mock
    table_mock.execute.return_value = MagicMock(data=[])
    return client


@pytest.fixture
def monitor(mock_supabase):
    m = PipelineMonitor(supabase=mock_supabase)
    # Slack 알림 비활성화
    m._notifier = MagicMock()
    return m


# ------------------------------------------------------------------ #
# start_run
# ------------------------------------------------------------------ #


def test_start_run_returns_uuid(monitor):
    run_id = monitor.start_run(target_date="2026-04-22")
    assert run_id
    assert len(run_id) == 36  # UUID 포맷


def test_start_run_calls_supabase_insert(monitor, mock_supabase):
    monitor.start_run(target_date="2026-04-22")
    mock_supabase.table.assert_any_call("pipeline_runs")


def test_start_run_notifies_slack(monitor):
    monitor.start_run(target_date="2026-04-22")
    monitor._notifier.notify_pipeline_start.assert_called_once_with("2026-04-22")


# ------------------------------------------------------------------ #
# finish_run
# ------------------------------------------------------------------ #


def test_finish_run_success(monitor):
    run_id = monitor.start_run()
    stats = {
        "date": "2026-04-22",
        "blog_generated": 5,
        "blog_published": 5,
        "youtube_published": 1,
        "reels_published": 1,
        "affiliate_inserted": 4,
        "errors": [],
    }
    monitor.finish_run(run_id, stats)
    monitor._notifier.notify_daily_summary.assert_called_once_with(stats)
    monitor._notifier.notify_pipeline_complete.assert_called_once()


def test_finish_run_with_errors_notifies_summary(monitor):
    run_id = monitor.start_run()
    stats = {"date": "2026-04-22", "errors": ["blog_generate: timeout"]}
    monitor.finish_run(run_id, stats)
    monitor._notifier.notify_daily_summary.assert_called_once()


# ------------------------------------------------------------------ #
# record_step
# ------------------------------------------------------------------ #


def test_record_step_success(monitor):
    run_id = monitor.start_run()
    monitor.record_step(run_id, "blog_generate", success=True, result={"count": 5})
    # 성공이면 오류 알림 없음
    monitor._notifier.notify_error.assert_not_called()


def test_record_step_failure_sends_slack_error(monitor):
    run_id = monitor.start_run()
    monitor.record_step(
        run_id, "blog_upload", success=False, error="Connection timeout"
    )
    monitor._notifier.notify_error.assert_called_once()
    args = monitor._notifier.notify_error.call_args
    assert args.kwargs["phase"] == "blog_upload" or args.args[0] == "blog_upload"


# ------------------------------------------------------------------ #
# run_step_with_retry
# ------------------------------------------------------------------ #


def test_retry_succeeds_on_first_try(monitor):
    fn = MagicMock(return_value={"ok": True})
    result = monitor.run_step_with_retry("test_step", fn)
    assert result == {"ok": True}
    fn.assert_called_once()


def test_retry_succeeds_on_second_try(monitor):
    fn = MagicMock(side_effect=[ValueError("transient"), {"ok": True}])
    result = monitor.run_step_with_retry("test_step", fn, max_retries=3)
    assert result == {"ok": True}
    assert fn.call_count == 2


def test_retry_raises_after_max_retries(monitor):
    fn = MagicMock(side_effect=RuntimeError("persistent error"))
    with pytest.raises(RuntimeError, match="persistent error"):
        monitor.run_step_with_retry("test_step", fn, max_retries=3)
    assert fn.call_count == 3


def test_retry_passes_args_and_kwargs(monitor):
    fn = MagicMock(return_value="done")
    monitor.run_step_with_retry("test", fn, "arg1", key="val")
    fn.assert_called_with("arg1", key="val")


def test_retry_backoff_timing(monitor):
    """재시도 사이에 백오프가 실제로 일어나는지 확인 (sleep mock)"""
    fn = MagicMock(side_effect=[Exception("fail"), {"ok": True}])
    with patch("src.monitoring.pipeline_monitor.time.sleep") as mock_sleep:
        monitor.run_step_with_retry("test", fn, max_retries=2)
    mock_sleep.assert_called_once_with(1.0)  # BASE_BACKOFF_SEC * 2^0


# ------------------------------------------------------------------ #
# get_daily_stats
# ------------------------------------------------------------------ #


def test_get_daily_stats_returns_dict(monitor, mock_supabase):
    mock_supabase.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
        data=[
            {"id": "abc", "status": "success", "target_date": "2026-04-22"},
        ]
    )
    stats = monitor.get_daily_stats("2026-04-22")
    assert stats["date"] == "2026-04-22"
    assert "total_runs" in stats


def test_get_daily_stats_handles_db_error(monitor, mock_supabase):
    mock_supabase.table.return_value.select.return_value.eq.return_value.order.return_value.execute.side_effect = Exception(
        "DB error"
    )
    stats = monitor.get_daily_stats("2026-04-22")
    assert "error" in stats


# ------------------------------------------------------------------ #
# PipelineScheduler
# ------------------------------------------------------------------ #


def test_scheduler_get_schedule():
    from src.scheduler.pipeline_scheduler import PipelineScheduler

    scheduler = PipelineScheduler()
    schedule = scheduler.get_schedule()
    assert len(schedule) > 0
    for item in schedule:
        assert "job_id" in item
        assert "cron" in item
        assert "endpoint" in item


def test_scheduler_trigger_unknown_job():
    from src.scheduler.pipeline_scheduler import PipelineScheduler

    scheduler = PipelineScheduler()
    result = scheduler.trigger_job("nonexistent_job")
    assert "error" in result
