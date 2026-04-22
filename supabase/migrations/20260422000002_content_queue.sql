-- CMP-21: 콘텐츠 큐 & 트렌드 수집 테이블
-- Phase 2: 트렌드 수집 & 주제 선정 모듈

-- =============================================
-- content_queue (일별 콘텐츠 주제 큐)
-- =============================================
CREATE TYPE public.content_type AS ENUM ('blog', 'youtube', 'reels');
CREATE TYPE public.queue_status AS ENUM ('pending', 'generating', 'published', 'failed', 'skipped');
CREATE TYPE public.volume_level AS ENUM ('high', 'medium', 'low');

CREATE TABLE IF NOT EXISTS public.content_queue (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  scheduled_date DATE NOT NULL,
  content_type content_type NOT NULL,
  title TEXT NOT NULL,
  primary_keyword TEXT NOT NULL,
  seo_keywords JSONB DEFAULT '[]',           -- ["키워드1", "키워드2", ...]
  related_products JSONB DEFAULT '[]',       -- 쿠팡 연계 상품 힌트
  angle TEXT,
  target_audience TEXT,
  estimated_search_volume volume_level DEFAULT 'medium',
  affiliate_potential volume_level DEFAULT 'medium',
  status queue_status DEFAULT 'pending' NOT NULL,
  publish_url TEXT,                          -- 발행 후 URL
  published_at TIMESTAMPTZ,
  error_message TEXT,                        -- 실패 시 에러 메시지
  created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

-- =============================================
-- trend_snapshots (트렌드 수집 이력)
-- =============================================
CREATE TABLE IF NOT EXISTS public.trend_snapshots (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  snapshot_date DATE NOT NULL,
  source TEXT NOT NULL,                      -- "google_trends" | "naver_datalab" | "rss"
  keyword TEXT NOT NULL,
  score NUMERIC(5, 4) DEFAULT 0,
  related_keywords JSONB DEFAULT '[]',
  raw_data JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

-- =============================================
-- Indexes
-- =============================================
CREATE INDEX idx_content_queue_date ON public.content_queue(scheduled_date);
CREATE INDEX idx_content_queue_status ON public.content_queue(status);
CREATE INDEX idx_content_queue_type ON public.content_queue(content_type);
CREATE INDEX idx_trend_snapshots_date ON public.trend_snapshots(snapshot_date);
CREATE INDEX idx_trend_snapshots_source ON public.trend_snapshots(source);
CREATE INDEX idx_trend_snapshots_keyword ON public.trend_snapshots(keyword);

-- =============================================
-- Triggers
-- =============================================
CREATE TRIGGER update_content_queue_updated_at
  BEFORE UPDATE ON public.content_queue
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- =============================================
-- RLS (파이프라인 서비스 역할은 service_role로 접근)
-- =============================================
ALTER TABLE public.content_queue ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.trend_snapshots ENABLE ROW LEVEL SECURITY;

-- service_role은 RLS 우회 (Supabase 기본 동작)
-- 일반 사용자는 자신의 팀 데이터만 접근 (content_queue는 팀 귀속 없음 → 관리자만)
CREATE POLICY "content_queue_service_only" ON public.content_queue
  USING (auth.role() = 'service_role');

CREATE POLICY "trend_snapshots_service_only" ON public.trend_snapshots
  USING (auth.role() = 'service_role');
