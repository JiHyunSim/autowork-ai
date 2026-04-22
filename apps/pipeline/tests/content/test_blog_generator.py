"""BlogGenerator 단위 테스트"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from src.content.blog_generator import BlogGenerator


MOCK_BLOG_RESPONSE = {
    "title": "챗GPT로 부업하는 법 2026 — 월 100만원 실전 가이드",
    "meta_description": "챗GPT를 활용해 부업으로 월 100만원을 버는 실전 방법을 단계별로 안내합니다. 직장인도 하루 1시간으로 가능한 AI 부업 노하우.",
    "content": "# 챗GPT로 부업하는 법 2026\n\n## 시작하기 전에\n\n챗GPT는 이제 단순한 도구가 아닙니다...\n\n## 실전 부업 방법 5가지\n\n### 1. 블로그 콘텐츠 대행\n...\n\n## 결론\n\n지금 바로 시작하세요.",
    "tags": ["챗GPT", "부업", "AI", "수익", "직장인"],
    "seo_score_estimate": 82,
}


class TestBlogGeneratorSingle:
    def _make_generator(self, mock_response: dict) -> BlogGenerator:
        mock_claude = MagicMock()
        mock_claude.generate.return_value = json.dumps(mock_response)
        mock_queue = MagicMock()
        mock_queue.get_pending_topics.return_value = []
        gen = BlogGenerator(claude=mock_claude)
        gen._queue = mock_queue
        return gen

    def test_generate_single_saves_to_supabase(self):
        gen = self._make_generator(MOCK_BLOG_RESPONSE)
        with patch("src.content.blog_generator._get_supabase") as mock_sb:
            mock_client = MagicMock()
            mock_client.table.return_value.insert.return_value.execute.return_value.data = [
                {**MOCK_BLOG_RESPONSE, "id": "test-uuid-1234", "status": "draft"}
            ]
            mock_sb.return_value = mock_client

            result = gen.generate_single(
                title="챗GPT로 부업하는 법",
                primary_keyword="챗GPT 부업",
                seo_keywords=["챗GPT", "부업", "AI"],
            )

        assert result["title"] == MOCK_BLOG_RESPONSE["title"]
        assert result["status"] == "draft"
        mock_client.table.assert_called_with("blog_posts")

    def test_generate_single_handles_json_parse_error(self):
        mock_claude = MagicMock()
        mock_claude.generate.return_value = "이것은 유효하지 않은 JSON입니다"
        gen = BlogGenerator(claude=mock_claude)

        with pytest.raises(json.JSONDecodeError):
            gen.generate_single(
                title="테스트",
                primary_keyword="테스트",
                seo_keywords=[],
            )

    def test_generate_single_strips_markdown_codeblock(self):
        mock_claude = MagicMock()
        mock_claude.generate.return_value = f"```json\n{json.dumps(MOCK_BLOG_RESPONSE)}\n```"
        gen = BlogGenerator(claude=mock_claude)

        with patch("src.content.blog_generator._get_supabase") as mock_sb:
            mock_client = MagicMock()
            mock_client.table.return_value.insert.return_value.execute.return_value.data = [
                {**MOCK_BLOG_RESPONSE, "id": "uuid", "status": "draft"}
            ]
            mock_sb.return_value = mock_client
            result = gen.generate_single(
                title="테스트",
                primary_keyword="테스트",
                seo_keywords=[],
            )

        assert result["title"] == MOCK_BLOG_RESPONSE["title"]


class TestBlogGeneratorFromQueue:
    def test_returns_empty_when_no_pending(self):
        mock_claude = MagicMock()
        gen = BlogGenerator(claude=mock_claude)
        mock_queue = MagicMock()
        mock_queue.get_pending_topics.return_value = []
        gen._queue = mock_queue

        result = gen.generate_from_queue(target_date="2026-04-22", limit=5)
        assert result == []

    def test_generates_for_each_pending_topic(self):
        mock_claude = MagicMock()
        mock_claude.generate.return_value = json.dumps(MOCK_BLOG_RESPONSE)

        pending = [
            {
                "id": f"queue-{i}",
                "title": f"주제 {i}",
                "primary_keyword": "키워드",
                "seo_keywords": '["키워드1", "키워드2"]',
                "angle": "",
                "target_audience": "",
            }
            for i in range(3)
        ]
        gen = BlogGenerator(claude=mock_claude)
        mock_queue = MagicMock()
        mock_queue.get_pending_topics.return_value = pending
        gen._queue = mock_queue

        with patch("src.content.blog_generator._get_supabase") as mock_sb:
            mock_client = MagicMock()
            mock_client.table.return_value.insert.return_value.execute.return_value.data = [
                {**MOCK_BLOG_RESPONSE, "id": "uuid", "status": "draft"}
            ]
            mock_sb.return_value = mock_client
            results = gen.generate_from_queue(target_date="2026-04-22", limit=5)

        assert len(results) == 3
        assert mock_queue.mark_generating.call_count == 3

    def test_records_error_on_claude_failure(self):
        mock_claude = MagicMock()
        mock_claude.generate.side_effect = Exception("Claude API 오류")

        gen = BlogGenerator(claude=mock_claude)
        mock_queue = MagicMock()
        mock_queue.get_pending_topics.return_value = [
            {
                "id": "queue-err",
                "title": "오류 테스트",
                "primary_keyword": "키워드",
                "seo_keywords": "[]",
                "angle": "",
                "target_audience": "",
            }
        ]
        gen._queue = mock_queue

        results = gen.generate_from_queue(target_date="2026-04-22", limit=1)
        assert len(results) == 1
        assert "error" in results[0]
        assert results[0]["status"] == "failed"
