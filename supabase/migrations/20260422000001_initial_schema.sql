-- AutoWork AI 초기 DB 스키마
-- Supabase (PostgreSQL) 마이그레이션

-- =============================================
-- Extensions
-- =============================================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";  -- pgvector for embeddings

-- =============================================
-- Users (Supabase Auth와 연동)
-- =============================================
CREATE TABLE IF NOT EXISTS public.users (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  email TEXT NOT NULL UNIQUE,
  name TEXT,
  avatar_url TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

-- =============================================
-- Teams
-- =============================================
CREATE TYPE public.team_plan AS ENUM ('starter', 'pro', 'enterprise');

CREATE TABLE IF NOT EXISTS public.teams (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name TEXT NOT NULL,
  plan team_plan DEFAULT 'starter' NOT NULL,
  owner_id UUID REFERENCES public.users(id) ON DELETE CASCADE NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

-- =============================================
-- Team Members
-- =============================================
CREATE TYPE public.member_role AS ENUM ('owner', 'admin', 'member');

CREATE TABLE IF NOT EXISTS public.team_members (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  team_id UUID REFERENCES public.teams(id) ON DELETE CASCADE NOT NULL,
  user_id UUID REFERENCES public.users(id) ON DELETE CASCADE NOT NULL,
  role member_role DEFAULT 'member' NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
  UNIQUE(team_id, user_id)
);

-- =============================================
-- Subscriptions (토스페이먼츠 연동)
-- =============================================
CREATE TYPE public.subscription_status AS ENUM ('trialing', 'active', 'past_due', 'cancelled');

CREATE TABLE IF NOT EXISTS public.subscriptions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  team_id UUID REFERENCES public.teams(id) ON DELETE CASCADE NOT NULL UNIQUE,
  plan team_plan NOT NULL,
  status subscription_status DEFAULT 'trialing' NOT NULL,
  toss_customer_key TEXT,    -- 토스페이먼츠 고객 키
  toss_billing_key TEXT,     -- 토스페이먼츠 빌링 키 (정기결제)
  current_period_start TIMESTAMPTZ,
  current_period_end TIMESTAMPTZ,
  trial_end TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

-- =============================================
-- Meeting Summaries (핵심 기능 1)
-- =============================================
CREATE TYPE public.meeting_status AS ENUM ('uploading', 'transcribing', 'summarizing', 'done', 'failed');

CREATE TABLE IF NOT EXISTS public.meeting_summaries (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  team_id UUID REFERENCES public.teams(id) ON DELETE CASCADE NOT NULL,
  created_by UUID REFERENCES public.users(id) ON DELETE CASCADE NOT NULL,
  title TEXT NOT NULL,
  original_file_path TEXT,  -- Supabase Storage 경로
  transcript TEXT,           -- Whisper 변환 텍스트
  summary TEXT,              -- Claude 요약
  action_items JSONB,        -- [{assignee, task, deadline}]
  decisions JSONB,           -- [decision_text]
  next_agenda JSONB,         -- [agenda_item]
  status meeting_status DEFAULT 'uploading' NOT NULL,
  duration_seconds INT,      -- 녹취 길이 (초)
  created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

-- =============================================
-- Reports (핵심 기능 2)
-- =============================================
CREATE TYPE public.report_type AS ENUM ('weekly', 'daily', 'custom');
CREATE TYPE public.report_status AS ENUM ('draft', 'generating', 'done');

CREATE TABLE IF NOT EXISTS public.reports (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  team_id UUID REFERENCES public.teams(id) ON DELETE CASCADE NOT NULL,
  created_by UUID REFERENCES public.users(id) ON DELETE CASCADE NOT NULL,
  title TEXT NOT NULL,
  report_type report_type DEFAULT 'weekly' NOT NULL,
  period_start DATE,
  period_end DATE,
  team_inputs JSONB,   -- 팀원 업무 입력 원본
  content TEXT,        -- Claude 생성 보고서 (마크다운)
  status report_status DEFAULT 'draft' NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

-- =============================================
-- Company Contexts (RAG용 — 이메일/제안서 기능)
-- =============================================
CREATE TABLE IF NOT EXISTS public.company_contexts (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  team_id UUID REFERENCES public.teams(id) ON DELETE CASCADE NOT NULL,
  content_type TEXT NOT NULL,   -- product_info | case_study | style_guide
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  embedding vector(1536),       -- text-embedding-3-small
  created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

-- =============================================
-- Row Level Security (RLS)
-- =============================================
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.teams ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.team_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.meeting_summaries ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.company_contexts ENABLE ROW LEVEL SECURITY;

-- Users: 자신의 정보만
CREATE POLICY "users_own" ON public.users
  FOR ALL USING (auth.uid() = id);

-- Teams: 팀 멤버만
CREATE POLICY "teams_member" ON public.teams
  FOR ALL USING (
    id IN (SELECT team_id FROM public.team_members WHERE user_id = auth.uid())
  );

-- Team Members: 팀 멤버만
CREATE POLICY "team_members_member" ON public.team_members
  FOR ALL USING (
    team_id IN (SELECT team_id FROM public.team_members WHERE user_id = auth.uid())
  );

-- Subscriptions: 팀 멤버만
CREATE POLICY "subscriptions_member" ON public.subscriptions
  FOR ALL USING (
    team_id IN (SELECT team_id FROM public.team_members WHERE user_id = auth.uid())
  );

-- Meeting Summaries: 팀 멤버만
CREATE POLICY "meetings_member" ON public.meeting_summaries
  FOR ALL USING (
    team_id IN (SELECT team_id FROM public.team_members WHERE user_id = auth.uid())
  );

-- Reports: 팀 멤버만
CREATE POLICY "reports_member" ON public.reports
  FOR ALL USING (
    team_id IN (SELECT team_id FROM public.team_members WHERE user_id = auth.uid())
  );

-- Company Contexts: 팀 멤버만
CREATE POLICY "contexts_member" ON public.company_contexts
  FOR ALL USING (
    team_id IN (SELECT team_id FROM public.team_members WHERE user_id = auth.uid())
  );

-- =============================================
-- Indexes
-- =============================================
CREATE INDEX idx_team_members_user ON public.team_members(user_id);
CREATE INDEX idx_team_members_team ON public.team_members(team_id);
CREATE INDEX idx_meetings_team ON public.meeting_summaries(team_id);
CREATE INDEX idx_meetings_created_by ON public.meeting_summaries(created_by);
CREATE INDEX idx_reports_team ON public.reports(team_id);
CREATE INDEX idx_company_contexts_team ON public.company_contexts(team_id);
-- pgvector HNSW index for fast similarity search
CREATE INDEX idx_contexts_embedding ON public.company_contexts USING hnsw (embedding vector_cosine_ops);

-- =============================================
-- Triggers: updated_at 자동 갱신
-- =============================================
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON public.users FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER update_teams_updated_at BEFORE UPDATE ON public.teams FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER update_subscriptions_updated_at BEFORE UPDATE ON public.subscriptions FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER update_meetings_updated_at BEFORE UPDATE ON public.meeting_summaries FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER update_reports_updated_at BEFORE UPDATE ON public.reports FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- =============================================
-- Function: 사용자 자동 생성 (Auth 트리거)
-- =============================================
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public.users (id, email, name, avatar_url)
  VALUES (
    NEW.id,
    NEW.email,
    NEW.raw_user_meta_data->>'name',
    NEW.raw_user_meta_data->>'avatar_url'
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();
