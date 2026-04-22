"""YouTubeGenerator 단위 테스트"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from src.content.youtube_generator import YouTubeGenerator


MOCK_YOUTUBE_RESPONSE = {
    "title": "챗GPT로 월 100만원 버는 법 (직장인 부업 실전편)",
    "description": "챗GPT를 활용한 실전 부업 방법을 공개합니다. 블로그 대행, 번역, 콘텐츠 제작으로 월 100만원 수익 달성 로드맵.\n\n⏰ 타임스탬프\n00:00 인트로\n01:30 부업 방법 1: 블로그 대행\n04:00 부업 방법 2: 번역·교정\n06:30 수익 현황 공개",
    "tags": ["챗GPT", "부업", "AI", "수익", "직장인부업", "자동화"],
    "thumbnail_concept": "임팩트 있는 숫자 '월 100만원'을 크게 배치, 노트북 앞에 앉은 직장인 이미지, 배경은 밝은 오렌지 계열",
    "script": "[훅] 챗GPT 하나로 월 100만원이 가능할까요?\n저는 실제로 지난 3개월간 검증했습니다.\n\n[본론1] 첫 번째 방법은 블로그 콘텐츠 대행입니다...\n\n[CTA] 구독과 좋아요 부탁드립니다!",
}


class TestYouTubeGeneratorSingle:
    def _make_generator(self, mock_response: dict) -> YouTubeGenerator:
        mock_claude = MagicMock()
        mock_claude.generate.return_value = json.dumps(mock_response)
        gen = YouTubeGenerator(claude=mock_claude)
        gen._queue = MagicMock()
        gen._queue.get_pending_topics.return_value = []
        return gen

    def test_generate_single_saves_to_supabase(self):
        gen = self._make_generator(MOCK_YOUTUBE_RESPONSE)
        with patch("src.content.youtube_generator._get_supabase") as mock_sb:
            mock_client = MagicMock()
            mock_client.table.return_value.insert.return_value.execute.return_value.data = [
                {**MOCK_YOUTUBE_RESPONSE, "id": "yt-uuid", "status": "draft"}
            ]
            mock_sb.return_value = mock_client

            result = gen.generate_single(
                title="챗GPT로 부업하는 법",
                primary_keyword="챗GPT 부업",
                seo_keywords=["챗GPT", "부업"],
            )

        assert result["title"] == MOCK_YOUTUBE_RESPONSE["title"]
        mock_client.table.assert_called_with("youtube_videos")

    def test_generate_single_strips_markdown_codeblock(self):
        mock_claude = MagicMock()
        mock_claude.generate.return_value = f"```json\n{json.dumps(MOCK_YOUTUBE_RESPONSE)}\n```"
        gen = YouTubeGenerator(claude=mock_claude)
        gen._queue = MagicMock()

        with patch("src.content.youtube_generator._get_supabase") as mock_sb:
            mock_client = MagicMock()
            mock_client.table.return_value.insert.return_value.execute.return_value.data = [
                {**MOCK_YOUTUBE_RESPONSE, "id": "uuid", "status": "draft"}
            ]
            mock_sb.return_value = mock_client
            result = gen.generate_single(
                title="테스트",
                primary_keyword="테스트",
                seo_keywords=[],
            )

        assert result["script"] == MOCK_YOUTUBE_RESPONSE["script"]


class TestYouTubeGeneratorFromQueue:
    def test_returns_empty_when_no_pending(self):
        gen = YouTubeGenerator(claude=MagicMock())
        gen._queue = MagicMock()
        gen._queue.get_pending_topics.return_value = []

        result = gen.generate_from_queue(target_date="2026-04-22", limit=1)
        assert result == []

    def test_records_error_on_failure(self):
        mock_claude = MagicMock()
        mock_claude.generate.side_effect = Exception("API 오류")

        gen = YouTubeGenerator(claude=mock_claude)
        gen._queue = MagicMock()
        gen._queue.get_pending_topics.return_value = [
            {
                "id": "q1",
                "title": "테스트",
                "primary_keyword": "k",
                "seo_keywords": "[]",
                "angle": "",
                "target_audience": "",
            }
        ]

        results = gen.generate_from_queue(target_date="2026-04-22", limit=1)
        assert results[0]["status"] == "failed"
        assert "error" in results[0]
