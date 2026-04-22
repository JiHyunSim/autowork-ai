"""TopicSelector 단위 테스트"""
from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from src.trend.topic_selector import TopicSelector
from src.trend.trend_collector import TrendKeyword


def _make_kw(keyword: str, score: float) -> TrendKeyword:
    return TrendKeyword(keyword=keyword, source="google_trends", score=score, timestamp=datetime.now())


class TestSelectDailyTopics:
    def test_returns_empty_on_no_trends(self):
        selector = TopicSelector()
        result = selector.select_daily_topics(trends=[])
        assert result == []

    def test_parses_claude_response(self):
        mock_claude = MagicMock()
        mock_response = {
            "topics": [
                {
                    "title": "챗GPT로 부업하는 법 2026",
                    "content_type": "blog",
                    "primary_keyword": "챗GPT 부업",
                    "seo_keywords": ["챗GPT", "부업", "AI", "수익"],
                    "related_products": ["ChatGPT Plus"],
                    "angle": "실제 수익 사례 중심",
                    "target_audience": "직장인 20-40대",
                    "estimated_search_volume": "high",
                    "affiliate_potential": "medium",
                }
            ]
        }
        mock_claude.generate.return_value = json.dumps(mock_response)

        selector = TopicSelector(claude=mock_claude)
        trends = [_make_kw("챗GPT", 0.9), _make_kw("부업", 0.7)]
        result = selector.select_daily_topics(trends=trends, blog_count=1, youtube_count=0, reels_count=0)

        assert len(result) == 1
        assert result[0].title == "챗GPT로 부업하는 법 2026"
        assert result[0].content_type == "blog"
        assert result[0].primary_keyword == "챗GPT 부업"
        assert result[0].estimated_search_volume == "high"

    def test_handles_json_parse_error(self):
        mock_claude = MagicMock()
        mock_claude.generate.return_value = "invalid json response"

        selector = TopicSelector(claude=mock_claude)
        trends = [_make_kw("테스트", 0.5)]
        result = selector.select_daily_topics(trends=trends)
        assert result == []

    def test_handles_claude_exception(self):
        mock_claude = MagicMock()
        mock_claude.generate.side_effect = Exception("API 오류")

        selector = TopicSelector(claude=mock_claude)
        trends = [_make_kw("테스트", 0.5)]
        result = selector.select_daily_topics(trends=trends)
        assert result == []

    def test_limits_trends_to_top_30(self):
        mock_claude = MagicMock()
        mock_claude.generate.return_value = json.dumps({"topics": []})

        selector = TopicSelector(claude=mock_claude)
        trends = [_make_kw(f"키워드{i}", 1.0 - i * 0.01) for i in range(50)]
        selector.select_daily_topics(trends=trends)

        call_args = mock_claude.generate.call_args
        user_prompt = call_args[1].get("user_prompt") or call_args[0][1]
        # 상위 30개만 포함되어야 함
        assert "키워드29" in user_prompt
        assert "키워드30" not in user_prompt
