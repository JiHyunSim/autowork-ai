"""TTS + 자동 영상 생성 모듈 (CMP-74)

스크립트 텍스트 → MP4 영상 변환 파이프라인:
  1. TTS Generator: 스크립트 → 음성 파일 (Google Cloud TTS)
  2. Slide Generator: 스크립트 → 키프레임 이미지 (Pillow)
  3. Video Synthesizer: 음성 + 이미지 → MP4 (FFmpeg)
  4. Video Pipeline: 위 단계를 조율하는 E2E 실행자
"""
from src.video.video_pipeline import VideoPipeline

__all__ = ["VideoPipeline"]
