-- CMP-24: 쿠팡 파트너스 제휴 링크 추적 테이블 (Phase 5)

CREATE TABLE IF NOT EXISTS public.affiliate_links (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  content_type TEXT NOT NULL CHECK (content_type IN ('blog', 'youtube', 'reels')),
  content_id UUID NOT NULL,              -- blog_posts.id or youtube_videos.id etc.
  product_id TEXT NOT NULL,              -- 쿠팡 productId
  product_name TEXT NOT NULL,
  product_url TEXT NOT NULL,             -- 원본 상품 URL
  affiliate_url TEXT NOT NULL,           -- 파트너스 딥링크
  keyword TEXT,                          -- 추출된 키워드
  position INT DEFAULT 1,               -- 포스트 내 삽입 순서
  click_count INT DEFAULT 0 NOT NULL,
  last_clicked_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

-- blog_posts에 제휴 링크 삽입 여부 컬럼 추가
ALTER TABLE public.blog_posts
  ADD COLUMN IF NOT EXISTS has_affiliate_links BOOLEAN DEFAULT FALSE;

CREATE INDEX idx_affiliate_links_content ON public.affiliate_links(content_type, content_id);
CREATE INDEX idx_affiliate_links_product ON public.affiliate_links(product_id);
CREATE INDEX idx_affiliate_links_created ON public.affiliate_links(created_at DESC);

ALTER TABLE public.affiliate_links ENABLE ROW LEVEL SECURITY;
CREATE POLICY "affiliate_links_service_only" ON public.affiliate_links
  USING (auth.role() = 'service_role');
