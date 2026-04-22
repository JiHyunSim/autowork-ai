-- Phase 6: 파이프라인 모니터링 — 실행 로그 테이블

-- ------------------------------------------------------------------ --
-- 파이프라인 런 기록
-- ------------------------------------------------------------------ --
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    target_date     DATE NOT NULL,
    status          TEXT NOT NULL DEFAULT 'running'
                        CHECK (status IN ('running','success','partial','failed')),
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    duration_sec    NUMERIC(10,2),
    -- 콘텐츠 생성 집계
    blog_generated  INTEGER DEFAULT 0,
    blog_published  INTEGER DEFAULT 0,
    youtube_generated INTEGER DEFAULT 0,
    youtube_published INTEGER DEFAULT 0,
    reels_generated  INTEGER DEFAULT 0,
    reels_published  INTEGER DEFAULT 0,
    affiliate_inserted INTEGER DEFAULT 0,
    error_count     INTEGER DEFAULT 0,
    errors_json     JSONB DEFAULT '[]',
    stats           JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_target_date ON pipeline_runs(target_date DESC);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_status ON pipeline_runs(status);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_started_at ON pipeline_runs(started_at DESC);

-- ------------------------------------------------------------------ --
-- 단계별 실행 기록 (재시도 로그 포함)
-- ------------------------------------------------------------------ --
CREATE TABLE IF NOT EXISTS pipeline_run_steps (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          UUID NOT NULL REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    step_name       TEXT NOT NULL,
    success         BOOLEAN NOT NULL DEFAULT FALSE,
    result_summary  JSONB DEFAULT '{}',
    error           TEXT,
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pipeline_run_steps_run_id ON pipeline_run_steps(run_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_run_steps_step_name ON pipeline_run_steps(step_name);
