-- ============================================================
-- AutoWork AI 콘텐츠 자동화 파이프라인 DB 스키마
-- Migration: 001_content_pipeline_schema
-- ============================================================

-- ---- 트렌드 & 주제 ----

-- 일별 콘텐츠 주제 큐 (Phase 2: 트렌드 수집 결과)
CREATE TABLE IF NOT EXISTS content_topics (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    topic           TEXT NOT NULL,
    keywords        TEXT[] NOT NULL DEFAULT '{}',
    source          TEXT NOT NULL,               -- 'google_trends' | 'youtube_trending' | 'naver_datalab'
    trend_score     FLOAT,                        -- 트렌드 점수 (높을수록 핫)
    content_types   TEXT[] NOT NULL DEFAULT '{}', -- ['blog', 'youtube', 'reels']
    scheduled_date  DATE NOT NULL,                -- 콘텐츠 발행 예정일
    status          TEXT NOT NULL DEFAULT 'pending', -- pending | in_progress | done | skipped
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_content_topics_date ON content_topics(scheduled_date);
CREATE INDEX IF NOT EXISTS idx_content_topics_status ON content_topics(status);

-- ---- 생성된 콘텐츠 ----

-- 블로그 포스트 (Phase 3: AI 생성 결과)
CREATE TABLE IF NOT EXISTS blog_posts (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    topic_id        UUID REFERENCES content_topics(id) ON DELETE SET NULL,
    title           TEXT NOT NULL,
    content         TEXT NOT NULL,               -- 마크다운 원본
    meta_description TEXT,
    tags            TEXT[] NOT NULL DEFAULT '{}',
    seo_score       FLOAT,                       -- SEO 점수 (0~100)
    status          TEXT NOT NULL DEFAULT 'draft', -- draft | scheduled | published | failed
    -- 발행 정보
    tistory_post_id TEXT,
    tistory_url     TEXT,
    published_at    TIMESTAMPTZ,
    -- 메타
    ai_model        TEXT DEFAULT 'claude-sonnet-4-6',
    generation_ms   INTEGER,                     -- 생성 소요시간 (ms)
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_blog_posts_status ON blog_posts(status);
CREATE INDEX IF NOT EXISTS idx_blog_posts_published ON blog_posts(published_at);

-- 유튜브 영상 (Phase 3: AI 생성 결과)
CREATE TABLE IF NOT EXISTS youtube_videos (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    topic_id        UUID REFERENCES content_topics(id) ON DELETE SET NULL,
    title           TEXT NOT NULL,
    description     TEXT NOT NULL,
    script          TEXT NOT NULL,               -- 영상 스크립트 원문
    tags            TEXT[] NOT NULL DEFAULT '{}',
    thumbnail_concept TEXT,
    status          TEXT NOT NULL DEFAULT 'draft', -- draft | rendering | scheduled | published | failed
    -- 파일
    video_file_path TEXT,                        -- 로컬 또는 스토리지 경로
    -- 발행 정보
    youtube_video_id TEXT,
    youtube_url     TEXT,
    published_at    TIMESTAMPTZ,
    -- 메타
    ai_model        TEXT DEFAULT 'claude-sonnet-4-6',
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_youtube_videos_status ON youtube_videos(status);

-- 인스타그램 릴스 (Phase 3: AI 생성 결과)
CREATE TABLE IF NOT EXISTS instagram_reels (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    topic_id        UUID REFERENCES content_topics(id) ON DELETE SET NULL,
    caption         TEXT NOT NULL,
    hashtags        TEXT[] NOT NULL DEFAULT '{}',
    video_concept   TEXT,                        -- 영상 컨셉 설명
    status          TEXT NOT NULL DEFAULT 'draft', -- draft | scheduled | published | failed
    -- 파일
    video_url       TEXT,                        -- 업로드용 공개 URL
    -- 발행 정보
    instagram_media_id TEXT,
    instagram_permalink TEXT,
    published_at    TIMESTAMPTZ,
    -- 메타
    ai_model        TEXT DEFAULT 'claude-sonnet-4-6',
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_instagram_reels_status ON instagram_reels(status);

-- ---- 쿠팡 파트너스 ----

-- 삽입된 제휴 링크 (Phase 5)
CREATE TABLE IF NOT EXISTS affiliate_links (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    content_type    TEXT NOT NULL,               -- 'blog' | 'youtube' | 'reels'
    content_id      UUID NOT NULL,               -- 각 콘텐츠 테이블의 id
    product_id      TEXT NOT NULL,               -- 쿠팡 상품 ID
    product_name    TEXT NOT NULL,
    product_url     TEXT NOT NULL,               -- 원본 상품 URL
    affiliate_url   TEXT NOT NULL,               -- 파트너스 추적 URL
    keyword         TEXT,                        -- 어떤 키워드로 찾은 상품인지
    position        INTEGER,                     -- 콘텐츠 내 삽입 위치 (1-based)
    click_count     INTEGER DEFAULT 0,           -- 클릭 수 (추적 시스템 연동 시)
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_affiliate_links_content ON affiliate_links(content_type, content_id);

-- ---- 파이프라인 실행 로그 ----

-- 워크플로우 실행 이력 (Phase 6: 모니터링)
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    workflow_name   TEXT NOT NULL,               -- n8n 워크플로우 이름
    n8n_execution_id TEXT,                       -- n8n 실행 ID
    status          TEXT NOT NULL,               -- success | failed | partial
    content_type    TEXT,                        -- 'blog' | 'youtube' | 'reels' | 'all'
    items_created   INTEGER DEFAULT 0,
    items_published INTEGER DEFAULT 0,
    error_message   TEXT,
    started_at      TIMESTAMPTZ DEFAULT now(),
    completed_at    TIMESTAMPTZ,
    duration_ms     INTEGER
);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_status ON pipeline_runs(status);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_started ON pipeline_runs(started_at);

-- ---- updated_at 자동 업데이트 트리거 ----

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_content_topics_updated_at
    BEFORE UPDATE ON content_topics
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_blog_posts_updated_at
    BEFORE UPDATE ON blog_posts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_youtube_videos_updated_at
    BEFORE UPDATE ON youtube_videos
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_instagram_reels_updated_at
    BEFORE UPDATE ON instagram_reels
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ---- Row Level Security ----

ALTER TABLE content_topics ENABLE ROW LEVEL SECURITY;
ALTER TABLE blog_posts ENABLE ROW LEVEL SECURITY;
ALTER TABLE youtube_videos ENABLE ROW LEVEL SECURITY;
ALTER TABLE instagram_reels ENABLE ROW LEVEL SECURITY;
ALTER TABLE affiliate_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE pipeline_runs ENABLE ROW LEVEL SECURITY;

-- Service role은 모든 행 접근 허용
CREATE POLICY "service_role_all" ON content_topics FOR ALL TO service_role USING (true);
CREATE POLICY "service_role_all" ON blog_posts FOR ALL TO service_role USING (true);
CREATE POLICY "service_role_all" ON youtube_videos FOR ALL TO service_role USING (true);
CREATE POLICY "service_role_all" ON instagram_reels FOR ALL TO service_role USING (true);
CREATE POLICY "service_role_all" ON affiliate_links FOR ALL TO service_role USING (true);
CREATE POLICY "service_role_all" ON pipeline_runs FOR ALL TO service_role USING (true);
