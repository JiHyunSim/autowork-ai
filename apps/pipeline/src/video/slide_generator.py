"""슬라이드 키프레임 생성기 — Pillow 기반 (CMP-74)

YouTube 스크립트를 1920×1080 PNG 슬라이드 시퀀스로 변환.
각 슬라이드는 자막 단락에 대응하며, FFmpeg 영상 합성 입력으로 사용.
"""
from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)

# 출력 해상도 (YouTube 16:9 Full HD)
WIDTH = 1920
HEIGHT = 1080

# 색상 팔레트 (다크 테마)
BG_COLOR = (18, 18, 28)         # 진한 남색 배경
TEXT_COLOR = (240, 240, 240)     # 흰색 본문
ACCENT_COLOR = (99, 179, 237)    # 밝은 파란색 (제목 강조)
DIVIDER_COLOR = (50, 50, 80)     # 구분선

# 폰트 경로 (시스템 폰트 fallback 포함)
_FONT_PATHS = [
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/Library/Fonts/AppleGothic.ttf",
]


@dataclass
class SlideSpec:
    """슬라이드 한 장의 명세"""
    text: str
    is_title: bool = False
    duration_secs: float = 5.0
    index: int = 0


@dataclass
class SlideSequence:
    """생성된 슬라이드 시퀀스 정보"""
    slide_paths: list[Path] = field(default_factory=list)
    durations: list[float] = field(default_factory=list)
    total_duration: float = 0.0


class SlideGenerator:
    """스크립트 텍스트 → PNG 슬라이드 시퀀스 생성"""

    # 대략 1초당 읽히는 한국어 음절 수 (분당 400자 기준)
    _CHARS_PER_SECOND = 6.5

    def __init__(self, font_size_body: int = 52, font_size_title: int = 72) -> None:
        self._font_size_body = font_size_body
        self._font_size_title = font_size_title
        self._font = self._load_font()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def generate(self, script: str, output_dir: str | Path) -> SlideSequence:
        """스크립트를 PNG 슬라이드 시퀀스로 변환.

        Args:
            script: YouTube 스크립트 텍스트
            output_dir: 슬라이드 PNG를 저장할 폴더

        Returns:
            SlideSequence: 슬라이드 경로 목록과 각 지속 시간
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        specs = self._parse_script(script)
        logger.info("slide_generator.generating", slide_count=len(specs), output_dir=str(output_dir))

        sequence = SlideSequence()
        for spec in specs:
            path = output_dir / f"slide_{spec.index:04d}.png"
            self._render_slide(spec, path)
            sequence.slide_paths.append(path)
            sequence.durations.append(spec.duration_secs)
            sequence.total_duration += spec.duration_secs

        logger.info(
            "slide_generator.done",
            count=len(sequence.slide_paths),
            total_secs=round(sequence.total_duration, 1),
        )
        return sequence

    # ------------------------------------------------------------------ #
    # Script parsing
    # ------------------------------------------------------------------ #

    def _parse_script(self, script: str) -> list[SlideSpec]:
        """스크립트를 슬라이드 명세 목록으로 파싱"""
        specs: list[SlideSpec] = []
        idx = 0

        # 마크다운 헤딩을 제목 슬라이드로 처리
        # 일반 단락을 자막 슬라이드로 처리
        lines = script.split("\n")
        current_paragraphs: list[str] = []

        def flush_paragraphs() -> None:
            nonlocal idx
            combined = "\n".join(current_paragraphs).strip()
            if combined:
                chunks = self._split_text_for_slide(combined)
                for chunk in chunks:
                    duration = max(3.0, len(chunk) / self._CHARS_PER_SECOND)
                    specs.append(SlideSpec(text=chunk, is_title=False, duration_secs=duration, index=idx))
                    idx += 1
            current_paragraphs.clear()

        for line in lines:
            heading_match = re.match(r"^#{1,3}\s+(.+)$", line)
            if heading_match:
                flush_paragraphs()
                title_text = heading_match.group(1).strip()
                specs.append(SlideSpec(text=title_text, is_title=True, duration_secs=4.0, index=idx))
                idx += 1
            elif line.strip() == "":
                if current_paragraphs:
                    flush_paragraphs()
            else:
                stripped = re.sub(r"\[.*?\]", "", line).strip()
                if stripped:
                    current_paragraphs.append(stripped)

        flush_paragraphs()
        return specs

    def _split_text_for_slide(self, text: str, max_chars: int = 120) -> list[str]:
        """긴 텍스트를 슬라이드 1장 분량으로 분할 (최대 ~120자)"""
        if len(text) <= max_chars:
            return [text]
        chunks: list[str] = []
        sentences = re.split(r"(?<=[.!?。])\s+", text)
        current = ""
        for sent in sentences:
            candidate = (current + " " + sent).strip() if current else sent
            if len(candidate) > max_chars and current:
                chunks.append(current)
                current = sent
            else:
                current = candidate
        if current:
            chunks.append(current)
        return chunks if chunks else [text[:max_chars]]

    # ------------------------------------------------------------------ #
    # Rendering
    # ------------------------------------------------------------------ #

    def _render_slide(self, spec: SlideSpec, output_path: Path) -> None:
        """슬라이드 한 장을 PNG로 렌더링"""
        try:
            from PIL import Image, ImageDraw, ImageFont  # type: ignore
        except ImportError as e:
            raise ImportError("Pillow 패키지가 필요합니다. pip install Pillow") from e

        img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
        draw = ImageDraw.Draw(img)

        if spec.is_title:
            self._draw_title_slide(draw, spec.text)
        else:
            self._draw_body_slide(draw, spec.text)

        img.save(str(output_path), "PNG", optimize=True)

    def _draw_title_slide(self, draw, text: str) -> None:
        from PIL import ImageFont  # type: ignore

        font = self._get_font(self._font_size_title, bold=True)
        # 수평선 (상단 장식)
        draw.rectangle([(120, 200), (WIDTH - 120, 205)], fill=ACCENT_COLOR)
        # 텍스트 (중앙 정렬)
        wrapped = textwrap.fill(text, width=28)
        draw.text(
            (WIDTH // 2, HEIGHT // 2),
            wrapped,
            font=font,
            fill=ACCENT_COLOR,
            anchor="mm",
            align="center",
        )
        # 수평선 (하단 장식)
        draw.rectangle([(120, HEIGHT - 205), (WIDTH - 120, HEIGHT - 200)], fill=ACCENT_COLOR)

    def _draw_body_slide(self, draw, text: str) -> None:
        from PIL import ImageFont  # type: ignore

        font = self._get_font(self._font_size_body)
        # 좌측 강조 바
        draw.rectangle([(80, 200), (88, HEIGHT - 200)], fill=ACCENT_COLOR)
        # 본문 텍스트 (중앙 수직 정렬, 좌측 여백)
        wrapped = textwrap.fill(text, width=40)
        draw.text(
            (WIDTH // 2, HEIGHT // 2),
            wrapped,
            font=font,
            fill=TEXT_COLOR,
            anchor="mm",
            align="left",
        )

    def _load_font(self):
        """시스템 폰트 로드 (없으면 None)"""
        try:
            from PIL import ImageFont  # type: ignore
            for path in _FONT_PATHS:
                if Path(path).exists():
                    return path
        except ImportError:
            pass
        return None

    def _get_font(self, size: int, bold: bool = False):
        """크기별 폰트 객체 반환"""
        from PIL import ImageFont  # type: ignore
        if self._font:
            try:
                return ImageFont.truetype(self._font, size)
            except OSError:
                pass
        return ImageFont.load_default()
