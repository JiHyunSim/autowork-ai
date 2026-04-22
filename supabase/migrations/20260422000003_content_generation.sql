-- Phase 3: AI 콘텐츠 생성 모듈 — 생성된 콘텐츠 저장 테이블

-- ------------------------------------------------------------------ --
-- 블로그 포스트
-- ------------------------------------------------------------------ --
CREATE TABLE IF NOT EXISTS blog_posts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    queue_id        UUID REFERENCES content_queue(id) ON DELETE SET NULL,
    title           TEXT NOT NULL,
    meta_description TEXT,
    content         TEXT NOT NULL,           -- 마크다운 본문
    tags            TEXT[] DEFAULT '{}',
    seo_score       NUMERIC(5,2),
    status          TEXT NOT NULL DEFAULT 'draft'
                        CHECK (status IN ('draft','scheduled','published','failed')),
    tistory_post_id TEXT,
    tistory_url     TEXT,
    ai_model        TEXT NOT NULL DEFAULT 'claude-sonnet-4-6',
    generation_ms   INTEGER,
    published_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_blog_posts_status ON blog_posts(status);
CREATE INDEX IF NOT EXISTS idx_blog_posts_created_at ON blog_posts(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_blog_posts_queue_id ON blog_posts(queue_id);

-- ------------------------------------------------------------------ --
-- 유튜브 영상 스크립트 + 메타데이터
-- ------------------------------------------------------------------ --
CREATE TABLE IF NOT EXISTS youtube_videos (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    queue_id            UUID REFERENCES content_queue(id) ON DELETE SET NULL,
    title               TEXT NOT NULL,
    description         TEXT NOT NULL,       -- 영상 설명란
    tags                TEXT[] DEFAULT '{}',
    thumbnail_concept   TEXT,
    script              TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'draft'
                            CHECK (status IN ('draft','rendering','scheduled','published','failed')),
    video_file_path     TEXT,
    youtube_video_id    TEXT,
    youtube_url         TEXT,
    ai_model            TEXT NOT NULL DEFAULT 'claude-sonnet-4-6',
    generation_ms       INTEGER,
    published_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_youtube_videos_status ON youtube_videos(status);
CREATE INDEX IF NOT EXISTS idx_youtube_videos_created_at ON youtube_videos(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_youtube_videos_queue_id ON youtube_videos(queue_id);

-- ------------------------------------------------------------------ --
-- 릴스 스크립트 + 캡션
-- ------------------------------------------------------------------ --
CREATE TABLE IF NOT EXISTS reels_scripts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    queue_id            UUID REFERENCES content_queue(id) ON DELETE SET NULL,
    title               TEXT,                -- 훅 문구 / 릴스 제목
    script              TEXT NOT NULL,       -- 영상 자막 스크립트
    caption             TEXT NOT NULL,       -- 인스타그램 캡션
    hashtags            TEXT[] DEFAULT '{}',
    video_concept       TEXT,
    status              TEXT NOT NULL DEFAULT 'draft'
                            CHECK (status IN ('draft','scheduled','published','failed')),
    instagram_media_id  TEXT,
    instagram_permalink TEXT,
    ai_model            TEXT NOT NULL DEFAULT 'claude-sonnet-4-6',
    generation_ms       INTEGER,
    published_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reels_scripts_status ON reels_scripts(status);
CREATE INDEX IF NOT EXISTS idx_reels_scripts_created_at ON reels_scripts(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_reels_scripts_queue_id ON reels_scripts(queue_id);

-- ------------------------------------------------------------------ --
-- updated_at 자동 갱신 트리거
-- ------------------------------------------------------------------ --
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER blog_posts_updated_at
    BEFORE UPDATE ON blog_posts
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER youtube_videos_updated_at
    BEFORE UPDATE ON youtube_videos
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER reels_scripts_updated_at
    BEFORE UPDATE ON reels_scripts
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
