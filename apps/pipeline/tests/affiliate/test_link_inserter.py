"""AffiliateLinkInserter 단위 테스트"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.affiliate.link_inserter import AffiliateLinkInserter


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #

SAMPLE_CONTENT = """# 에어프라이어 추천 TOP 5 (2026년 최신)

에어프라이어는 현대인의 필수 주방 기기가 되었습니다.

## 에어프라이어 선택 기준

- 용량: 3~5L가 적당
- 온도 범위: 80~200℃
- 자동 셧오프 기능

## 추천 모델

필립스, 코스오리, 닌자 에어프라이어를 추천합니다.

## 결론

올바른 에어프라이어를 선택해 건강한 요리를 즐겨보세요!
"""

SAMPLE_TITLE = "에어프라이어 추천 TOP 5 (2026년 최신)"

MOCK_PRODUCTS = [
    {
        "productId": "12345",
        "productName": "필립스 에어프라이어 HD9200",
        "price": 129000,
        "affiliate_url": "https://www.coupang.com/vp/products/12345?subId=TESTKEY",
        "image_url": "https://thumbnail6.coupangcdn.com/12345.jpg",
        "rating": 4.7,
        "keyword": "에어프라이어",
    },
    {
        "productId": "67890",
        "productName": "코스오리 에어프라이어 5.5L",
        "price": 89000,
        "affiliate_url": "https://www.coupang.com/vp/products/67890?subId=TESTKEY",
        "image_url": None,
        "rating": 4.5,
        "keyword": "에어프라이어",
    },
]


def _make_inserter(mock_claude_resp: str = '["에어프라이어"]') -> tuple[AffiliateLinkInserter, MagicMock, MagicMock]:
    """테스트용 AffiliateLinkInserter (외부 의존성 모두 Mock)"""
    claude = MagicMock()
    claude.generate.return_value = mock_claude_resp

    coupang = MagicMock()
    coupang.search_products.return_value = MOCK_PRODUCTS
    coupang.generate_deep_link.side_effect = lambda url: url  # 그대로 반환

    inserter = AffiliateLinkInserter(claude=claude, coupang=coupang)
    return inserter, claude, coupang


# ------------------------------------------------------------------ #
# extract_product_keywords
# ------------------------------------------------------------------ #

class TestExtractProductKeywords:
    def test_returns_keywords_from_claude(self):
        inserter, claude, _ = _make_inserter('["에어프라이어", "요리도구"]')
        keywords = inserter.extract_product_keywords(SAMPLE_TITLE, SAMPLE_CONTENT)
        assert keywords == ["에어프라이어", "요리도구"]
        claude.generate.assert_called_once()

    def test_returns_empty_on_invalid_json(self):
        inserter, claude, _ = _make_inserter("이것은 JSON이 아닙니다")
        keywords = inserter.extract_product_keywords(SAMPLE_TITLE, SAMPLE_CONTENT)
        assert keywords == []

    def test_limits_to_max_keywords(self):
        inserter, _, _ = _make_inserter('["A", "B", "C", "D", "E"]')
        keywords = inserter.extract_product_keywords(SAMPLE_TITLE, SAMPLE_CONTENT)
        # MAX_KEYWORDS = 3
        assert len(keywords) <= 3

    def test_truncates_long_content(self):
        inserter, claude, _ = _make_inserter('["에어프라이어"]')
        long_content = "x" * 5000
        inserter.extract_product_keywords(SAMPLE_TITLE, long_content)
        # generate가 호출되어야 함 (내용 길이와 무관)
        claude.generate.assert_called_once()


# ------------------------------------------------------------------ #
# _select_top_products
# ------------------------------------------------------------------ #

class TestSelectTopProducts:
    def test_selects_products_for_keyword(self):
        inserter, _, coupang = _make_inserter()
        products = inserter._select_top_products(["에어프라이어"])
        assert len(products) > 0
        coupang.search_products.assert_called_once_with("에어프라이어", limit=5)

    def test_deduplicates_same_product_id(self):
        inserter, _, coupang = _make_inserter()
        # 두 키워드 모두 동일 상품 반환
        coupang.search_products.return_value = MOCK_PRODUCTS
        products = inserter._select_top_products(["에어프라이어", "프라이어"])
        ids = [p["productId"] for p in products]
        assert len(ids) == len(set(ids))

    def test_max_products_per_post(self):
        inserter, _, coupang = _make_inserter()
        # 6개 상품 반환 Mock
        many_products = [
            {"productId": str(i), "productName": f"상품{i}", "price": 10000,
             "affiliate_url": f"https://coupang.com/{i}", "image_url": None, "rating": 4.0}
            for i in range(6)
        ]
        coupang.search_products.return_value = many_products
        products = inserter._select_top_products(["키워드1", "키워드2"])
        # MAX_PRODUCTS_PER_POST = 3
        assert len(products) <= 3

    def test_handles_coupang_error_gracefully(self):
        inserter, _, coupang = _make_inserter()
        coupang.search_products.side_effect = Exception("API 오류")
        products = inserter._select_top_products(["에어프라이어"])
        assert products == []


# ------------------------------------------------------------------ #
# _insert_product_section
# ------------------------------------------------------------------ #

class TestInsertProductSection:
    def test_appends_product_section(self):
        inserter, _, _ = _make_inserter()
        result = inserter._insert_product_section(SAMPLE_CONTENT, MOCK_PRODUCTS)
        assert "## 🛒 추천 상품" in result
        assert "필립스 에어프라이어 HD9200" in result

    def test_includes_disclaimer(self):
        inserter, _, _ = _make_inserter()
        result = inserter._insert_product_section(SAMPLE_CONTENT, MOCK_PRODUCTS)
        assert "쿠팡 파트너스" in result

    def test_replaces_existing_section(self):
        inserter, _, _ = _make_inserter()
        content_with_section = SAMPLE_CONTENT + "\n## 🛒 추천 상품\n\n기존 섹션"
        result = inserter._insert_product_section(content_with_section, MOCK_PRODUCTS)
        # "## 🛒 추천 상품"이 딱 한 번만 나와야 함
        assert result.count("## 🛒 추천 상품") == 1

    def test_shows_price_formatted(self):
        inserter, _, _ = _make_inserter()
        result = inserter._insert_product_section(SAMPLE_CONTENT, MOCK_PRODUCTS)
        assert "129,000원" in result

    def test_no_image_url_omits_img_tag(self):
        inserter, _, _ = _make_inserter()
        no_img_products = [{**MOCK_PRODUCTS[1], "image_url": None}]
        result = inserter._insert_product_section(SAMPLE_CONTENT, no_img_products)
        assert "![" not in result


# ------------------------------------------------------------------ #
# process_blog_post (통합)
# ------------------------------------------------------------------ #

class TestProcessBlogPost:
    @patch("src.affiliate.link_inserter._get_supabase")
    def test_full_flow_returns_updated_content(self, mock_supabase_fn):
        mock_sb = MagicMock()
        mock_supabase_fn.return_value = mock_sb
        mock_sb.table.return_value.insert.return_value.execute.return_value.data = [
            {"id": "link-1", "product_name": "필립스 에어프라이어 HD9200"}
        ]
        mock_sb.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()

        inserter, _, _ = _make_inserter('["에어프라이어"]')
        result = inserter.process_blog_post(
            blog_post_id="post-abc",
            content=SAMPLE_CONTENT,
            title=SAMPLE_TITLE,
        )

        assert result["blog_post_id"] == "post-abc"
        assert result["inserted_count"] > 0
        assert "## 🛒 추천 상품" in result["updated_content"]

    @patch("src.affiliate.link_inserter._get_supabase")
    def test_no_keywords_returns_original_content(self, mock_supabase_fn):
        inserter, claude, _ = _make_inserter("[]")
        result = inserter.process_blog_post(
            blog_post_id="post-xyz",
            content=SAMPLE_CONTENT,
            title=SAMPLE_TITLE,
        )

        assert result["inserted_count"] == 0
        assert result["updated_content"] == SAMPLE_CONTENT
        # Supabase 저장 호출 없음
        mock_supabase_fn.assert_not_called()
