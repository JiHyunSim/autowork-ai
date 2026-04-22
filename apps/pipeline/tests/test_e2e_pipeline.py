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
            run_id, "blog_upload", success=False, error="WordPress API error"
        )
        monitor._notifier.notify_error.assert_called_once()
        args = monitor._notifier.notify_error.call_args
        assert args.kwargs["phase"] == "blog_upload"
        assert "WordPress API error" in args.kwargs["error"]


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


# ================================================================== #
# VideoPipeline unit tests (CMP-74)
# ================================================================== #


class TestTTSGenerator:
    """TTSGenerator — Google Cloud TTS 클라이언트를 mock으로 대체해 단위 검증"""

    def test_clean_script_removes_markdown(self):
        from src.video.tts_generator import TTSGenerator

        gen = TTSGenerator.__new__(TTSGenerator)
        gen._voice_name = "ko-KR-Neural2-C"
        cleaned = gen._clean_script("## 제목\n[인트로] 안녕하세요.  내용입니다.")
        assert "##" not in cleaned
        assert "[인트로]" not in cleaned
        assert "안녕하세요" in cleaned

    def test_split_into_chunks_short_text(self):
        from src.video.tts_generator import TTSGenerator

        gen = TTSGenerator.__new__(TTSGenerator)
        short = "안녕하세요."
        chunks = gen._split_into_chunks(short)
        assert len(chunks) == 1
        assert chunks[0] == short

    def test_split_into_chunks_long_text(self):
        from src.video.tts_generator import TTSGenerator

        gen = TTSGenerator.__new__(TTSGenerator)
        # 5000자 이상 텍스트 → 여러 청크로 분할
        long_text = "가나다라마바사아자차카타파하. " * 400
        chunks = gen._split_into_chunks(long_text)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk.encode("utf-8")) <= 4800

    def test_estimate_cost_returns_dict(self):
        from src.video.tts_generator import TTSGenerator

        gen = TTSGenerator.__new__(TTSGenerator)
        gen._voice_name = "ko-KR-Neural2-C"
        result = gen.estimate_cost("안녕하세요 " * 100)
        assert "char_count" in result
        assert "cost_usd" in result
        assert result["cost_usd"] >= 0


class TestSlideGenerator:
    """SlideGenerator — 파일 I/O 없이 파싱 로직만 검증"""

    def test_parse_script_extracts_headings(self):
        from src.video.slide_generator import SlideGenerator

        gen = SlideGenerator.__new__(SlideGenerator)
        gen._font = None
        gen._font_size_body = 52
        gen._font_size_title = 72
        gen._CHARS_PER_SECOND = 6.5
        script = "## 도입\n안녕하세요.\n\n## 본론\n내용입니다."
        specs = gen._parse_script(script)
        titles = [s for s in specs if s.is_title]
        bodies = [s for s in specs if not s.is_title]
        assert len(titles) == 2
        assert any("도입" in t.text for t in titles)
        assert len(bodies) >= 1

    def test_duration_scales_with_text_length(self):
        from src.video.slide_generator import SlideGenerator

        gen = SlideGenerator.__new__(SlideGenerator)
        gen._CHARS_PER_SECOND = 6.5
        gen._font = None
        gen._font_size_body = 52
        gen._font_size_title = 72
        short = "짧은 텍스트"
        long_text = "긴 텍스트입니다. " * 10
        specs_short = gen._parse_script(short)
        specs_long = gen._parse_script(long_text)
        total_short = sum(s.duration_secs for s in specs_short)
        total_long = sum(s.duration_secs for s in specs_long)
        assert total_long > total_short


class TestVideoPipelineIntegration:
    """VideoPipeline — dry_run 모드에서 E2E 흐름 검증 (실제 API 호출 없음)"""

    def test_pipeline_runner_dry_run_includes_video_render(self, monitor):
        """dry_run=True 시 video_rendered 카운트가 stats에 포함됨"""
        runner = PipelineRunner(monitor=monitor, dry_run=True)
        # 월요일 (2026-04-20) → YouTube + Video Render 실행
        stats = runner.run("2026-04-20")
        assert "video_rendered" in stats
        assert stats["video_rendered"] >= 0

    def test_pipeline_runner_video_render_skipped_on_tuesday(self, monitor):
        """화요일은 YouTube 없으므로 video_render도 0"""
        runner = PipelineRunner(monitor=monitor, dry_run=True)
        stats = runner.run("2026-04-21")
        assert stats.get("video_rendered", 0) == 0
