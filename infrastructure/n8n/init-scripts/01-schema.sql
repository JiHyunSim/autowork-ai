-- ============================================================
-- AutoWork AI 콘텐츠 파이프라인 (CMP) PostgreSQL 스키마
-- Phase 1: n8n 인프라 & API 연동 기반
-- ============================================================

-- 트렌드 수집 결과
CREATE TABLE IF NOT EXISTS cmp_trends (
    id          BIGSERIAL PRIMARY KEY,
    keyword     TEXT NOT NULL,
    source      TEXT NOT NULL,           -- 'google_trends' | 'naver_datalab' | 'youtube'
    score       NUMERIC(5,2),
    category    TEXT,
    collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    raw_data    JSONB
);

-- 콘텐츠 생성 큐
CREATE TABLE IF NOT EXISTS cmp_content_queue (
    id              BIGSERIAL PRIMARY KEY,
    trend_id        BIGINT REFERENCES cmp_trends(id),
    topic           TEXT NOT NULL,
    content_type    TEXT NOT NULL,      -- 'blog' | 'youtube' | 'reels'
    status          TEXT NOT NULL DEFAULT 'pending',
                                        -- 'pending' | 'generating' | 'done' | 'failed'
    priority        INTEGER DEFAULT 5,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at    TIMESTAMPTZ
);

-- 생성된 콘텐츠
CREATE TABLE IF NOT EXISTS cmp_contents (
    id              BIGSERIAL PRIMARY KEY,
    queue_id        BIGINT REFERENCES cmp_content_queue(id),
    content_type    TEXT NOT NULL,
    title           TEXT NOT NULL,
    body            TEXT,
    thumbnail_url   TEXT,
    tags            TEXT[],
    seo_keywords    TEXT[],
    affiliate_links JSONB,              -- 쿠팡 파트너스 링크 목록
    status          TEXT NOT NULL DEFAULT 'draft',
                                        -- 'draft' | 'ready' | 'published' | 'failed'
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at    TIMESTAMPTZ,
    metadata        JSONB
);

-- 게시 결과
CREATE TABLE IF NOT EXISTS cmp_publish_logs (
    id              BIGSERIAL PRIMARY KEY,
    content_id      BIGINT REFERENCES cmp_contents(id),
    platform        TEXT NOT NULL,      -- 'tistory' | 'youtube' | 'instagram'
    platform_post_id TEXT,
    platform_url    TEXT,
    status          TEXT NOT NULL,      -- 'success' | 'failed'
    error_message   TEXT,
    published_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 파이프라인 실행 이력
CREATE TABLE IF NOT EXISTS cmp_pipeline_runs (
    id              BIGSERIAL PRIMARY KEY,
    run_date        DATE NOT NULL DEFAULT CURRENT_DATE,
    workflow_name   TEXT NOT NULL,
    blog_count      INTEGER DEFAULT 0,
    youtube_count   INTEGER DEFAULT 0,
    reels_count     INTEGER DEFAULT 0,
    success_count   INTEGER DEFAULT 0,
    fail_count      INTEGER DEFAULT 0,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    metadata        JSONB
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_trends_collected_at  ON cmp_trends(collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_queue_status         ON cmp_content_queue(status, created_at);
CREATE INDEX IF NOT EXISTS idx_contents_status      ON cmp_contents(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_publish_platform     ON cmp_publish_logs(platform, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_pipeline_run_date    ON cmp_pipeline_runs(run_date DESC);
