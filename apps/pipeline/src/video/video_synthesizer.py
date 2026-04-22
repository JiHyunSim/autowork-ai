"""영상 합성기 — FFmpeg 기반 (CMP-74)

슬라이드 PNG + 음성 MP3 → MP4 영상 합성.
각 슬라이드의 표시 시간은 SlideSequence.durations를 따름.
최종 영상은 오디오 길이에 맞춰 트리밍.
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import structlog

from src.video.slide_generator import SlideSequence

logger = structlog.get_logger(__name__)

# 출력 영상 설정
_VIDEO_CRF = 23       # 화질 (낮을수록 고화질, 18-28 권장)
_VIDEO_PRESET = "medium"
_FPS = 25
_AUDIO_BITRATE = "192k"


class VideoSynthesizer:
    """PNG 슬라이드 시퀀스 + MP3 오디오 → MP4 영상 합성"""

    def __init__(self, ffmpeg_bin: str = "ffmpeg") -> None:
        self._ffmpeg = ffmpeg_bin
        self._verify_ffmpeg()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def synthesize(
        self,
        audio_path: str | Path,
        slides: SlideSequence,
        output_path: str | Path,
    ) -> Path:
        """오디오 + 슬라이드 → MP4 합성.

        Args:
            audio_path: TTS 생성 MP3 파일
            slides: SlideGenerator가 반환한 SlideSequence
            output_path: 출력 MP4 파일 경로

        Returns:
            생성된 MP4 파일 Path
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        concat_file = self._write_concat_file(slides)
        logger.info(
            "video_synthesizer.synthesizing",
            slide_count=len(slides.slide_paths),
            audio=str(audio_path),
            output=str(output_path),
        )

        self._run_ffmpeg(
            concat_file=concat_file,
            audio_path=Path(audio_path),
            output_path=output_path,
        )

        # 임시 concat 파일 정리
        Path(concat_file).unlink(missing_ok=True)

        logger.info("video_synthesizer.done", path=str(output_path))
        return output_path

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _write_concat_file(self, slides: SlideSequence) -> str:
        """FFmpeg concat demuxer 형식 파일 작성"""
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        )
        for path, duration in zip(slides.slide_paths, slides.durations):
            # FFmpeg concat 형식: file 경로와 duration
            tmp.write(f"file '{path.resolve()}'\n")
            tmp.write(f"duration {duration:.3f}\n")
        # 마지막 프레임을 1프레임 추가 (concat demuxer 버그 방지)
        if slides.slide_paths:
            tmp.write(f"file '{slides.slide_paths[-1].resolve()}'\n")
        tmp.close()
        return tmp.name

    def _run_ffmpeg(
        self,
        concat_file: str,
        audio_path: Path,
        output_path: Path,
    ) -> None:
        """FFmpeg 실행: 슬라이드 concat + 오디오 믹싱 → MP4"""
        cmd = [
            self._ffmpeg,
            "-y",                          # 덮어쓰기
            # 슬라이드 비디오 스트림 (concat demuxer)
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file,
            # 오디오 스트림
            "-i", str(audio_path),
            # 비디오 인코딩
            "-vf", f"fps={_FPS},format=yuv420p",
            "-c:v", "libx264",
            "-crf", str(_VIDEO_CRF),
            "-preset", _VIDEO_PRESET,
            # 오디오 인코딩
            "-c:a", "aac",
            "-b:a", _AUDIO_BITRATE,
            # 오디오 길이에 맞춰 최단 스트림 사용 (슬라이드가 길어도 오디오 끝에서 종료)
            "-shortest",
            str(output_path),
        ]
        logger.debug("video_synthesizer.ffmpeg_cmd", cmd=" ".join(cmd))

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10분 최대
        )
        if result.returncode != 0:
            logger.error(
                "video_synthesizer.ffmpeg_failed",
                returncode=result.returncode,
                stderr=result.stderr[-2000:],  # 마지막 2000자만 로그
            )
            raise RuntimeError(
                f"FFmpeg 실패 (code {result.returncode}): {result.stderr[-500:]}"
            )

    def _verify_ffmpeg(self) -> None:
        """FFmpeg 바이너리 존재 여부 확인"""
        result = subprocess.run(
            [self._ffmpeg, "-version"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"FFmpeg를 찾을 수 없습니다. '{self._ffmpeg}' 설치가 필요합니다."
            )
