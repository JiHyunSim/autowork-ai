"""TrendCollector 단위 테스트"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.trend.trend_collector import TrendCollector, TrendKeyword


def _make_kw(keyword: str, source: str, score: float) -> TrendKeyword:
    return TrendKeyword(keyword=keyword, source=source, score=score, timestamp=datetime.now())


class TestMergeAndScore:
    def test_merge_same_keyword_different_sources(self):
        trends = [
            _make_kw("챗GPT", "google_trends", 0.9),
            _make_kw("챗gpt", "naver_datalab", 0.5),  # 소문자 동일 키워드
        ]
        result = TrendCollector._merge_and_score(trends)
        # 동일 키워드 병합 → 1개
        assert len(result) == 1
        # 소스 다양성 보너스로 점수 상승 (0.9 + 0.5*0.3 = 1.05 → cap 1.0)
        assert result[0].score == 1.0

    def test_merge_different_keywords(self):
        trends = [
            _make_kw("인공지능", "google_trends", 0.8),
            _make_kw("주식", "naver_datalab", 0.6),
        ]
        result = TrendCollector._merge_and_score(trends)
        assert len(result) == 2
        assert result[0].score >= result[1].score  # 내림차순 정렬 확인

    def test_empty_trends(self):
        assert TrendCollector._merge_and_score([]) == []


class TestExtractTitlesFromXml:
    def test_basic_rss(self):
        xml = """<rss>
<channel><title>채널 제목</title>
<item><title>첫 번째 뉴스</title></item>
<item><title>두 번째 뉴스</title></item>
</channel>
</rss>"""
        result = TrendCollector._extract_titles_from_xml(xml)
        assert "첫 번째 뉴스" in result
        assert "두 번째 뉴스" in result

    def test_cdata_title(self):
        xml = """<item><title><![CDATA[CDATA 제목 & 특수문자]]></title></item>"""
        result = TrendCollector._extract_titles_from_xml(xml)
        assert any("CDATA" in t for t in result)

    def test_empty_xml(self):
        result = TrendCollector._extract_titles_from_xml("")
        assert result == []


class TestFetchNaverDatalab:
    def test_skip_when_no_credentials(self, monkeypatch):
        from src import config
        monkeypatch.setattr(config.settings, "naver_client_id", "")
        monkeypatch.setattr(config.settings, "naver_client_secret", "")

        collector = TrendCollector()
        result = collector.fetch_naver_datalab(
            keyword_groups=[{"groupName": "AI", "keywords": ["인공지능"]}]
        )
        assert result == []

    def test_skip_when_empty_groups(self, monkeypatch):
        from src import config
        monkeypatch.setattr(config.settings, "naver_client_id", "test-id")
        monkeypatch.setattr(config.settings, "naver_client_secret", "test-secret")

        collector = TrendCollector()
        result = collector.fetch_naver_datalab(keyword_groups=[])
        assert result == []

    def test_parse_response(self, monkeypatch):
        from src import config
        monkeypatch.setattr(config.settings, "naver_client_id", "test-id")
        monkeypatch.setattr(config.settings, "naver_client_secret", "test-secret")

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": [
                {
                    "title": "AI/ChatGPT",
                    "data": [{"ratio": 80.0}, {"ratio": 90.0}, {"ratio": 70.0}],
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()

        collector = TrendCollector()
        with patch.object(collector._http, "post", return_value=mock_response):
            result = collector.fetch_naver_datalab(
                keyword_groups=[{"groupName": "AI/ChatGPT", "keywords": ["챗GPT", "인공지능"]}]
            )

        assert len(result) == 1
        assert result[0].source == "naver_datalab"
        assert result[0].keyword == "챗GPT"
        assert result[0].related == ["인공지능"]
        # avg ratio = (80+90+70)/3 / 100 ≈ 0.8
        assert abs(result[0].score - 0.8) < 0.01
