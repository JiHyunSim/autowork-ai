"""E2E 파이프라인 통합 테스트 (Phase 6)

사람 개입 없는 완전 자동화 검증:
- 블로그 일 5개 × 연속 발행
- 유튜브 주 3개 (1회 실행당 1개)
- 릴스 일 1개

실제 외부 API(Claude, Supabase, 티스토리 등) 호출 없이 httpx mock으로 시뮬레이션.
FastAPI TestClient를 통해 /api/pipeline/e2e/run 엔드포인트를 검증.
"""
from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.main import app


# ------------------------------------------------------------------ #
# 픽스처
# ------------------------------------------------------------------ #


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def disable_pipeline_token(monkeypatch):
    """테스트 중 토큰 검증 비활성화"""
    monkeypatch.setenv("PIPELINE_API_TOKEN", "")


def _make_supabase_mock():
    """Supabase 전체 체인을 무해하게 목(mock)"""
    client = MagicMock()
    table = MagicMock()
    client.table.return_value = table
    table.insert.return_value = table
    table.update.return_value = table
    table.select.return_value = table
    table.eq.return_value = table
    table.order.return_value = table
    table.limit.return_value = table
    table.single.return_value = table
    table.execute.return_value = MagicMock(data=[])
    return client


# ------------------------------------------------------------------ #
# /health 엔드포인트 (사전 검증)
# ------------------------------------------------------------------ #


def test_health_endpoint(client):
    resp = client.get(
        "/api/pipeline/health",
        headers={"Authorization": "Bearer test-token"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ------------------------------------------------------------------ #
# /monitor/health 엔드포인트
# ------------------------------------------------------------------ #


def test_pipeline_health_endpoint(client):
    with patch(
        "src.monitoring.pipeline_monitor._get_supabase",
        return_value=_make_supabase_mock(),
    ):
        resp = client.get(
            "/api/pipeline/monitor/health",
            headers={"Authorization": "Bearer test-token"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert "status" in body
    assert body["status"] in ("healthy", "degraded", "unhealthy")


# ------------------------------------------------------------------ #
# /schedule 엔드포인트
# ------------------------------------------------------------------ #


def test_get_schedule_returns_list(client):
    resp = client.get(
        "/api/pipeline/schedule",
        headers={"Authorization": "Bearer test-token"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "schedule" in body
    assert body["count"] > 0
    # 7:00 트렌드 수집 포함 확인
    job_ids = [s["job_id"] for s in body["schedule"]]
    assert "trend_collect" in job_ids


def test_schedule_covers_full_day(client):
    """스케줄이 블로그 5개, 유튜브 1개, 릴스 1개를 커버하는지 확인"""
    resp = client.get(
        "/api/pipeline/schedule",
        headers={"Authorization": "Bearer test-token"},
    )
    body = resp.json()
    schedule = body["schedule"]

    blog_gen_jobs = [s for s in schedule if "blog_generate" in s["job_id"]]
    youtube_gen_jobs = [s for s in schedule if "youtube_generate" in s["job_id"]]
    reels_gen_jobs = [s for s in schedule if "reels_generate" in s["job_id"]]

    # 블로그 생성 job이 여러 번 나눠서 합산 5개 이상
    total_blog_limit = sum(
        s["payload"].get("limit", 0) for s in blog_gen_jobs
    )
    assert total_blog_limit >= 5

    assert len(youtube_gen_jobs) >= 1
    assert len(reels_gen_jobs) >= 1


# ------------------------------------------------------------------ #
# /e2e/run 엔드포인트 — 전체 파이프라인 E2E 검증
# ------------------------------------------------------------------ #


def _mock_httpx_response(data: dict, status_code: int = 200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = data
    resp.raise_for_status = MagicMock()
    return resp


def test_e2e_run_all_steps_succeed(client):
    """모든 단계 성공 시 success=True 반환"""
    step_responses = {
        "/api/pipeline/trends/collect": {"count": 10, "trends": [], "top_keywords": []},
        "/api/pipeline/content/generate-blog": {"generated": 5, "failed": 0, "posts": [], "errors": []},
        "/api/pipeline/content/generate-youtube": {"generated": 1, "failed": 0, "videos": [], "errors": []},
        "/api/pipeline/content/generate-reels": {"generated": 1, "failed": 0, "reels": [], "errors": []},
        "/api/pipeline/upload/blog": {"uploaded": 5, "failed": 0, "results": []},
        "/api/pipeline/upload/youtube": {"uploaded": 1, "failed": 0, "results": []},
        "/api/pipeline/upload/reels": {"uploaded": 1, "failed": 0, "results": []},
    }

    def _fake_call(path: str, payload: dict) -> dict:
        return step_responses.get(path, {"ok": True})

    with patch(
        "src.monitoring.pipeline_monitor._get_supabase",
        return_value=_make_supabase_mock(),
    ), patch(
        "src.scheduler.pipeline_scheduler.PipelineScheduler._call",
        side_effect=_fake_call,
    ):
        resp = client.post(
            "/api/pipeline/e2e/run",
            json={"target_date": "2026-04-22"},
            headers={"Authorization": "Bearer test-token"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["stats"]["blog_generated"] == 5
    assert body["stats"]["blog_published"] == 5
    assert body["stats"]["youtube_generated"] == 1
    assert body["stats"]["reels_generated"] == 1
    assert body["stats"]["errors"] == []


def test_e2e_run_partial_failure_recorded(client):
    """일부 단계 실패 시 success=False, errors 목록에 기록"""
    call_count = {"n": 0}

    def _fake_call(path: str, payload: dict) -> dict:
        call_count["n"] += 1
        if "generate-blog" in path:
            raise ConnectionError("Claude API timeout")
        return {"generated": 1, "uploaded": 1, "failed": 0, "count": 5,
                "trends": [], "top_keywords": []}

    with patch(
        "src.monitoring.pipeline_monitor._get_supabase",
        return_value=_make_supabase_mock(),
    ), patch(
        "src.scheduler.pipeline_scheduler.PipelineScheduler._call",
        side_effect=_fake_call,
    ):
        resp = client.post(
            "/api/pipeline/e2e/run",
            json={"target_date": "2026-04-22"},
            headers={"Authorization": "Bearer test-token"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert any("blog_generate" in e for e in body["stats"]["errors"])


def test_e2e_run_returns_run_id(client):
    """E2E 실행 결과에 run_id가 포함되는지 확인"""
    def _fake_call(path: str, payload: dict) -> dict:
        return {"generated": 0, "uploaded": 0, "failed": 0, "count": 0,
                "trends": [], "top_keywords": []}

    with patch(
        "src.monitoring.pipeline_monitor._get_supabase",
        return_value=_make_supabase_mock(),
    ), patch(
        "src.scheduler.pipeline_scheduler.PipelineScheduler._call",
        side_effect=_fake_call,
    ):
        resp = client.post(
            "/api/pipeline/e2e/run",
            json={},
            headers={"Authorization": "Bearer test-token"},
        )

    body = resp.json()
    assert "run_id" in body
    assert len(body["run_id"]) == 36  # UUID 포맷


# ------------------------------------------------------------------ #
# /monitor/run-daily 엔드포인트 E2E
# ------------------------------------------------------------------ #


def test_run_daily_pipeline(client):
    """일별 파이프라인 실행 엔드포인트 검증"""
    mock_gen = MagicMock(return_value=[{"title": "post", "content": "...", "id": "1"}])

    with patch(
        "src.monitoring.pipeline_monitor._get_supabase",
        return_value=_make_supabase_mock(),
    ), patch("src.content.BlogGenerator.generate_from_queue", mock_gen), patch(
        "src.content.YouTubeGenerator.generate_from_queue",
        MagicMock(return_value=[{"title": "yt", "id": "2"}]),
    ), patch(
        "src.content.ReelsGenerator.generate_from_queue",
        MagicMock(return_value=[{"caption": "reel", "id": "3"}]),
    ):
        resp = client.post(
            "/api/pipeline/monitor/run-daily",
            json={"target_date": "2026-04-22"},
            headers={"Authorization": "Bearer test-token"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert "run_id" in body
    assert body["status"] in ("success", "partial")
