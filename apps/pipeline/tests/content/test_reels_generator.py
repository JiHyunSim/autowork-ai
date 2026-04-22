"""ReelsGenerator 단위 테스트"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from src.content.reels_generator import ReelsGenerator


MOCK_REELS_RESPONSE = {
    "title": "챗GPT 부업 꿀팁 🔥",
    "caption": "챗GPT로 하루 1시간, 월 50만원 부업 성공! 💰 당신도 가능합니다. 방법이 궁금하다면 저장해두세요! #챗GPT #부업 #AI수익",
    "hashtags": [
        "#챗GPT",
        "#AI부업",
        "#수익창출",
        "#직장인부업",
        "#자동화",
        "#콘텐츠제작",
        "#블로그",
        "#유튜브부업",
    ],
    "video_concept": "첫 화면: '월 50만원 부업 실화?' 텍스트 + 노트북 화면. 전개: 챗GPT 사용 화면 캡처. 마지막: 수익 인증 + CTA",
    "script": "[0s] 월 50만원 부업이 가능할까요?\n[5s] 네, 가능합니다. 저도 했으니까요.\n[10s] 챗GPT 하나로 이걸 해냈어요.\n[25s] 저장하고 나중에 꼭 해보세요!",
}


class TestReelsGeneratorSingle:
    def _make_generator(self, mock_response: dict) -> ReelsGenerator:
        mock_claude = MagicMock()
        mock_claude.generate.return_value = json.dumps(mock_response)
        gen = ReelsGenerator(claude=mock_claude)
        gen._queue = MagicMock()
        gen._queue.get_pending_topics.return_value = []
        return gen

    def test_generate_single_saves_to_supabase(self):
        gen = self._make_generator(MOCK_REELS_RESPONSE)
        with patch("src.content.reels_generator._get_supabase") as mock_sb:
            mock_client = MagicMock()
            mock_client.table.return_value.insert.return_value.execute.return_value.data = [
                {**MOCK_REELS_RESPONSE, "id": "reels-uuid", "status": "draft"}
            ]
            mock_sb.return_value = mock_client

            result = gen.generate_single(
                title="챗GPT 부업 꿀팁",
                primary_keyword="챗GPT 부업",
                seo_keywords=["챗GPT", "AI", "부업"],
            )

        assert result["caption"] == MOCK_REELS_RESPONSE["caption"]
        mock_client.table.assert_called_with("reels_scripts")

    def test_generate_single_strips_markdown_codeblock(self):
        mock_claude = MagicMock()
        mock_claude.generate.return_value = f"```json\n{json.dumps(MOCK_REELS_RESPONSE)}\n```"
        gen = ReelsGenerator(claude=mock_claude)
        gen._queue = MagicMock()

        with patch("src.content.reels_generator._get_supabase") as mock_sb:
            mock_client = MagicMock()
            mock_client.table.return_value.insert.return_value.execute.return_value.data = [
                {**MOCK_REELS_RESPONSE, "id": "uuid", "status": "draft"}
            ]
            mock_sb.return_value = mock_client
            result = gen.generate_single(
                title="테스트",
                primary_keyword="테스트",
                seo_keywords=[],
            )

        assert result["hashtags"] == MOCK_REELS_RESPONSE["hashtags"]

    def test_generate_single_handles_supabase_error(self):
        gen = self._make_generator(MOCK_REELS_RESPONSE)
        with patch("src.content.reels_generator._get_supabase") as mock_sb:
            mock_client = MagicMock()
            mock_client.table.return_value.insert.return_value.execute.side_effect = Exception(
                "Supabase 연결 오류"
            )
            mock_sb.return_value = mock_client

            result = gen.generate_single(
                title="오류 테스트",
                primary_keyword="오류",
                seo_keywords=[],
            )

        assert "error" in result
        assert result["caption"] == MOCK_REELS_RESPONSE["caption"]


class TestReelsGeneratorFromQueue:
    def test_returns_empty_when_no_pending(self):
        gen = ReelsGenerator(claude=MagicMock())
        gen._queue = MagicMock()
        gen._queue.get_pending_topics.return_value = []

        result = gen.generate_from_queue(target_date="2026-04-22", limit=1)
        assert result == []

    def test_generates_for_pending_topic(self):
        mock_claude = MagicMock()
        mock_claude.generate.return_value = json.dumps(MOCK_REELS_RESPONSE)

        gen = ReelsGenerator(claude=mock_claude)
        gen._queue = MagicMock()
        gen._queue.get_pending_topics.return_value = [
            {
                "id": "reel-q1",
                "title": "챗GPT 릴스",
                "primary_keyword": "챗GPT",
                "seo_keywords": '["챗GPT", "AI"]',
                "angle": "실제 사례",
                "target_audience": "20-30대 직장인",
            }
        ]

        with patch("src.content.reels_generator._get_supabase") as mock_sb:
            mock_client = MagicMock()
            mock_client.table.return_value.insert.return_value.execute.return_value.data = [
                {**MOCK_REELS_RESPONSE, "id": "uuid", "status": "draft"}
            ]
            mock_sb.return_value = mock_client
            results = gen.generate_from_queue(target_date="2026-04-22", limit=1)

        assert len(results) == 1
        gen._queue.mark_generating.assert_called_once_with("reel-q1")

    def test_records_error_on_failure(self):
        mock_claude = MagicMock()
        mock_claude.generate.side_effect = Exception("Claude API 오류")

        gen = ReelsGenerator(claude=mock_claude)
        gen._queue = MagicMock()
        gen._queue.get_pending_topics.return_value = [
            {
                "id": "reel-err",
                "title": "오류 릴스",
                "primary_keyword": "오류",
                "seo_keywords": "[]",
                "angle": "",
                "target_audience": "",
            }
        ]

        results = gen.generate_from_queue(target_date="2026-04-22", limit=1)
        assert len(results) == 1
        assert results[0]["status"] == "failed"
        assert "error" in results[0]
