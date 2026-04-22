-- CMP-74: TTS + 자동 영상 생성 파이프라인 지원을 위한 youtube_videos 테이블 확장
-- rendering 상태 + video_file_path 컬럼이 없을 경우 추가
-- 이미 존재하는 경우 NO-OP (idempotent)

BEGIN;

-- video_file_path 컬럼 추가 (MP4 파일 절대 경로)
ALTER TABLE youtube_videos
  ADD COLUMN IF NOT EXISTS video_file_path TEXT DEFAULT NULL;

-- status enum에 'rendering' 추가
-- Supabase는 CHECK 제약조건 또는 enum 타입으로 status를 관리함.
-- 기존 status 값: 'draft', 'scheduled', 'published', 'failed'
-- 신규 추가: 'rendering' (TTS + FFmpeg 처리 중 표시용)

-- CHECK 제약조건을 사용하는 경우:
DO $$
BEGIN
  -- 기존 CHECK 제약이 있으면 이름으로 찾아 업데이트
  IF EXISTS (
    SELECT 1 FROM information_schema.table_constraints
    WHERE table_name = 'youtube_videos'
      AND constraint_type = 'CHECK'
      AND constraint_name LIKE '%status%'
  ) THEN
    -- 기존 제약 삭제 후 확장된 제약으로 교체
    EXECUTE (
      SELECT 'ALTER TABLE youtube_videos DROP CONSTRAINT ' || constraint_name
      FROM information_schema.table_constraints
      WHERE table_name = 'youtube_videos'
        AND constraint_type = 'CHECK'
        AND constraint_name LIKE '%status%'
      LIMIT 1
    );
  END IF;
END
$$;

ALTER TABLE youtube_videos
  ADD CONSTRAINT youtube_videos_status_check
  CHECK (status IN ('draft', 'rendering', 'scheduled', 'published', 'failed'));

-- rendering_started_at: 렌더링 시작 시각 (타임아웃 감지용)
ALTER TABLE youtube_videos
  ADD COLUMN IF NOT EXISTS rendering_started_at TIMESTAMPTZ DEFAULT NULL;

COMMIT;
