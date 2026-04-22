"""TTS 음성 생성기 — Google Cloud TTS API (CMP-74)

스크립트 텍스트를 MP3 음성 파일로 변환.
한국어 Neural2 음성 사용 (비용: ~$0.016/1K 자, 6분 영상 약 $0.08).
"""
from __future__ import annotations

import os
import textwrap
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

# Google Cloud TTS 최대 입력 길이 (바이트). 5000 bytes 안전 마진
_MAX_BYTES = 4800
# 기본 한국어 Neural2 음성
_DEFAULT_VOICE = "ko-KR-Neural2-C"
_DEFAULT_LANG = "ko-KR"


class TTSGenerator:
    """Google Cloud TTS를 사용해 스크립트 텍스트 → MP3 파일 변환"""

    def __init__(self, voice_name: str = _DEFAULT_VOICE) -> None:
        self._voice_name = voice_name
        self._client = self._build_client()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def generate(self, script: str, output_path: str | Path) -> Path:
        """스크립트를 MP3 파일로 변환.

        Args:
            script: 변환할 텍스트 (한국어)
            output_path: 저장할 MP3 파일 경로

        Returns:
            생성된 MP3 파일의 Path
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        cleaned = self._clean_script(script)
        chunks = self._split_into_chunks(cleaned)

        logger.info(
            "tts_generator.generating",
            chunks=len(chunks),
            total_chars=len(cleaned),
            output=str(output_path),
        )

        if len(chunks) == 1:
            audio_data = self._synthesize_chunk(chunks[0])
        else:
            audio_data = self._synthesize_and_merge(chunks)

        output_path.write_bytes(audio_data)
        logger.info("tts_generator.done", path=str(output_path), size_kb=len(audio_data) // 1024)
        return output_path

    def estimate_cost(self, script: str) -> dict:
        """비용 예측 (Neural2 기준 $0.016/1K 자)"""
        char_count = len(self._clean_script(script))
        cost_usd = (char_count / 1000) * 0.016
        return {
            "char_count": char_count,
            "cost_usd": round(cost_usd, 4),
            "voice": self._voice_name,
        }

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _build_client(self):
        try:
            from google.cloud import texttospeech  # type: ignore
            return texttospeech.TextToSpeechClient()
        except ImportError as e:
            raise ImportError(
                "google-cloud-texttospeech 패키지가 필요합니다. "
                "pip install google-cloud-texttospeech"
            ) from e

    def _clean_script(self, script: str) -> str:
        """YouTube 스크립트에서 TTS에 불필요한 마크다운/메타 태그 제거"""
        import re
        # 마크다운 헤딩/기호 제거
        text = re.sub(r"#+\s*", "", script)
        # 대괄호 지시어 제거 ([인트로], [아웃트로] 등)
        text = re.sub(r"\[.*?\]", "", text)
        # 이중 공백/빈 줄 정리
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r" {2,}", " ", text)
        return text.strip()

    def _split_into_chunks(self, text: str) -> list[str]:
        """텍스트를 Google TTS 입력 한계(_MAX_BYTES bytes) 이하 청크로 분할"""
        if len(text.encode("utf-8")) <= _MAX_BYTES:
            return [text]

        chunks: list[str] = []
        paragraphs = text.split("\n\n")
        current = ""

        for para in paragraphs:
            candidate = (current + "\n\n" + para).strip() if current else para
            if len(candidate.encode("utf-8")) > _MAX_BYTES:
                if current:
                    chunks.append(current)
                # 단락 자체가 너무 크면 문장 단위로 더 분할
                if len(para.encode("utf-8")) > _MAX_BYTES:
                    chunks.extend(self._split_by_sentences(para))
                    current = ""
                else:
                    current = para
            else:
                current = candidate

        if current:
            chunks.append(current)
        return chunks

    def _split_by_sentences(self, text: str) -> list[str]:
        """문장 단위로 분할 (문단 분할로도 부족할 때)"""
        import re
        sentences = re.split(r"(?<=[.!?。])\s+", text)
        chunks: list[str] = []
        current = ""
        for sent in sentences:
            candidate = (current + " " + sent).strip() if current else sent
            if len(candidate.encode("utf-8")) > _MAX_BYTES:
                if current:
                    chunks.append(current)
                current = sent
            else:
                current = candidate
        if current:
            chunks.append(current)
        return chunks

    def _synthesize_chunk(self, text: str) -> bytes:
        """단일 텍스트 청크를 MP3 bytes로 변환"""
        from google.cloud import texttospeech  # type: ignore

        synthesis_input = texttospeech.SynthesisInput(text=text)
        voice = texttospeech.VoiceSelectionParams(
            language_code=_DEFAULT_LANG,
            name=self._voice_name,
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=1.0,
            pitch=0.0,
        )
        response = self._client.synthesize_speech(
            input=synthesis_input,
            voice=voice,
            audio_config=audio_config,
        )
        return response.audio_content

    def _synthesize_and_merge(self, chunks: list[str]) -> bytes:
        """여러 청크를 순서대로 합성 후 MP3 bytes 연결"""
        parts = [self._synthesize_chunk(chunk) for chunk in chunks]
        return b"".join(parts)
