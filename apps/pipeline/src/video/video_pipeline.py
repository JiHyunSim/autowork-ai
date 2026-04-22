"""영상 생성 파이프라인 E2E 조율자 (CMP-74)

Script(DB) → TTS Generator → audio.mp3
Script(DB) → Slide Generator → PNG frames
FFmpeg(audio + frames) → video.mp4
DB 업데이트 (video_file_path, status=draft)
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional

import structlog

from src.video.tts_generator import TTSGenerator
from src.video.slide_generator import SlideGenerator
from src.video.video_synthesizer import VideoSynthesizer

logger = structlog.get_logger(__name__)

# 생성된 MP4가 저장될 기본 위치
_DEFAULT_OUTPUT_DIR = "/tmp/youtube_videos"


class VideoPipeline:
    """youtube_videos 테이블의 스크립트 → MP4 변환 파이프라인"""

    def __init__(
        self,
        output_dir: str = _DEFAULT_OUTPUT_DIR,
        tts: Optional[TTSGenerator] = None,
        slides: Optional[SlideGenerator] = None,
        synthesizer: Optional[VideoSynthesizer] = None,
    ) -> None:
        self._output_dir = Path(output_dir)
        self._tts = tts or TTSGenerator()
        self._slides = slides or SlideGenerator()
        self._synthesizer = synthesizer or VideoSynthesizer()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def render(self, video_id: str, title: str, script: str) -> Path:
        """스크립트 → MP4 파일 생성.

        Args:
            video_id: youtube_videos.id (파일명에 사용)
            title: 영상 제목
            script: 유튜브 스크립트 텍스트

        Returns:
            생성된 MP4 파일 Path
        """
        work_dir = Path(tempfile.mkdtemp(prefix=f"yt_{video_id[:8]}_"))
        try:
            return self._render_impl(video_id, title, script, work_dir)
        except Exception:
            shutil.rmtree(work_dir, ignore_errors=True)
            raise

    def render_pending(self, limit: int = 1) -> list[dict]:
        """youtube_videos.status='draft', video_file_path=null 항목 일괄 렌더링.

        Returns:
            렌더링 결과 목록 [{video_id, success, path|error}]
        """
        from src.config import settings
        from supabase import create_client

        db = create_client(settings.supabase_url, settings.supabase_service_role_key)
        rows = (
            db.table("youtube_videos")
            .select("id, title, script")
            .eq("status", "draft")
            .is_("video_file_path", "null")
            .limit(limit)
            .execute()
        ).data

        if not rows:
            logger.info("video_pipeline.no_pending_videos")
            return []

        results = []
        for row in rows:
            video_id = row["id"]
            try:
                # DB 상태를 'rendering'으로 먼저 업데이트 (타임아웃 감지용 시각 기록)
                from datetime import timezone
                import datetime as _dt
                db.table("youtube_videos").update({
                    "status": "rendering",
                    "rendering_started_at": _dt.datetime.now(timezone.utc).isoformat(),
                }).eq("id", video_id).execute()

                mp4_path = self.render(video_id, row["title"], row["script"])

                # 완료: DB에 경로 저장, status=draft로 복원 (YouTubeUploader가 처리)
                db.table("youtube_videos").update({
                    "video_file_path": str(mp4_path),
                    "status": "draft",
                }).eq("id", video_id).execute()

                logger.info("video_pipeline.rendered", video_id=video_id, path=str(mp4_path))
                results.append({"video_id": video_id, "success": True, "path": str(mp4_path)})

            except Exception as exc:
                logger.error("video_pipeline.render_failed", video_id=video_id, error=str(exc))
                # 실패 시 draft로 되돌림
                db.table("youtube_videos").update({"status": "draft"}).eq("id", video_id).execute()
                results.append({"video_id": video_id, "success": False, "error": str(exc)})

        return results

    def estimate_cost(self, script: str) -> dict:
        """영상 1편 생성 비용 예측"""
        return self._tts.estimate_cost(script)

    # ------------------------------------------------------------------ #
    # Internal
    # ------------------------------------------------------------------ #

    def _render_impl(self, video_id: str, title: str, script: str, work_dir: Path) -> Path:
        logger.info("video_pipeline.render_start", video_id=video_id[:8], title=title[:40])

        # 1단계: TTS
        audio_path = work_dir / "audio.mp3"
        self._tts.generate(script, audio_path)

        # 2단계: 슬라이드 생성
        slides_dir = work_dir / "slides"
        slide_seq = self._slides.generate(script, slides_dir)

        # 3단계: FFmpeg 합성
        self._output_dir.mkdir(parents=True, exist_ok=True)
        safe_title = "".join(c for c in title[:40] if c.isalnum() or c in " -_").strip().replace(" ", "_")
        output_path = self._output_dir / f"{safe_title}_{video_id[:8]}.mp4"

        self._synthesizer.synthesize(audio_path, slide_seq, output_path)

        logger.info("video_pipeline.render_done", video_id=video_id[:8], path=str(output_path))
        return output_path
