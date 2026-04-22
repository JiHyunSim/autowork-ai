"""쿠팡 파트너스 제휴 링크 자동 삽입 모듈 (Phase 5)

흐름:
1. 블로그 포스트 콘텐츠에서 상품 관련 키워드를 Claude로 추출
2. 키워드별 쿠팡 파트너스 상품 검색
3. 마크다운 콘텐츠에 제휴 링크 자동 삽입 (상품 카드 블록)
4. 삽입 결과를 Supabase affiliate_links 테이블에 저장
5. 클릭 추적용 서브ID 파라미터 적용
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Optional
from uuid import UUID

import structlog
from supabase import create_client, Client

from src.config import settings
from src.connectors.claude import ClaudeConnector
from src.connectors.coupang import CoupangConnector

logger = structlog.get_logger(__name__)

# 포스트당 삽입할 최대 상품 수
MAX_PRODUCTS_PER_POST = 3
# 키워드당 검색 상품 수
PRODUCTS_PER_KEYWORD = 5
# 추출할 최대 상품 키워드 수
MAX_KEYWORDS = 3

KEYWORD_EXTRACT_SYSTEM = """당신은 쇼핑 콘텐츠 전문가입니다.
블로그 포스트를 분석하여 쿠팡에서 판매 가능한 실제 상품 키워드를 추출합니다.

규칙:
- 구체적인 상품명/카테고리로 추출 (예: "에어프라이어", "블루투스 이어폰", "단백질 파우더")
- 추상적 개념이나 서비스는 제외 (예: "성공", "자기계발", "여행")
- 반드시 쿠팡에서 검색 가능한 상품이어야 함
- JSON 배열로만 반환 (설명 없이)"""


def _get_supabase() -> Client:
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


class AffiliateLinkInserter:
    """쿠팡 파트너스 제휴 링크를 블로그 포스트에 자동 삽입하는 클래스"""

    def __init__(
        self,
        claude: Optional[ClaudeConnector] = None,
        coupang: Optional[CoupangConnector] = None,
    ) -> None:
        self._claude = claude or ClaudeConnector()
        self._coupang = coupang or CoupangConnector()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def process_blog_post(self, blog_post_id: str, content: str, title: str) -> dict:
        """블로그 포스트에 쿠팡 파트너스 제휴 링크 삽입

        Args:
            blog_post_id: Supabase blog_posts.id
            content: 마크다운 원본 콘텐츠
            title: 포스트 제목

        Returns:
            {
              "blog_post_id": ...,
              "updated_content": ...,  # 링크가 삽입된 마크다운
              "inserted_count": ...,
              "affiliate_links": [...]
            }
        """
        logger.info("affiliate.process_start", blog_post_id=blog_post_id, title=title)

        # 1. 상품 키워드 추출
        keywords = self.extract_product_keywords(title, content)
        if not keywords:
            logger.info("affiliate.no_keywords", blog_post_id=blog_post_id)
            return {
                "blog_post_id": blog_post_id,
                "updated_content": content,
                "inserted_count": 0,
                "affiliate_links": [],
            }

        # 2. 키워드별 쿠팡 상품 검색 → 최고 평점 상품 선정
        products = self._select_top_products(keywords)
        if not products:
            logger.info("affiliate.no_products", blog_post_id=blog_post_id, keywords=keywords)
            return {
                "blog_post_id": blog_post_id,
                "updated_content": content,
                "inserted_count": 0,
                "affiliate_links": [],
            }

        # 3. 마크다운에 제품 카드 삽입
        updated_content = self._insert_product_section(content, products)

        # 4. Supabase에 저장
        saved_links = self._save_affiliate_links(
            blog_post_id=blog_post_id,
            products=products,
        )

        # 5. blog_posts 테이블 content 업데이트
        self._update_blog_post_content(blog_post_id, updated_content)

        logger.info(
            "affiliate.process_done",
            blog_post_id=blog_post_id,
            inserted=len(products),
        )
        return {
            "blog_post_id": blog_post_id,
            "updated_content": updated_content,
            "inserted_count": len(products),
            "affiliate_links": saved_links,
        }

    def extract_product_keywords(self, title: str, content: str) -> list[str]:
        """Claude로 콘텐츠에서 상품 키워드 추출

        Returns:
            추출된 키워드 목록 (최대 MAX_KEYWORDS 개)
        """
        # 콘텐츠가 너무 길면 앞부분만 사용 (토큰 절약)
        excerpt = content[:2000] if len(content) > 2000 else content

        user_prompt = (
            f"다음 블로그 포스트에서 쿠팡에서 구매 가능한 상품 키워드를 최대 {MAX_KEYWORDS}개 추출하세요.\n\n"
            f"제목: {title}\n\n"
            f"본문 일부:\n{excerpt}\n\n"
            f"JSON 배열로만 반환 (예: [\"에어프라이어\", \"단백질 파우더\"])"
        )

        try:
            raw = self._claude.generate(
                system_prompt=KEYWORD_EXTRACT_SYSTEM,
                user_prompt=user_prompt,
                max_tokens=200,
                temperature=0.3,
            )
            raw = raw.strip().removeprefix("```json").removesuffix("```").strip()
            keywords = json.loads(raw)
            if isinstance(keywords, list):
                return [str(k) for k in keywords[:MAX_KEYWORDS]]
        except Exception as exc:
            logger.warning("affiliate.keyword_extract_error", error=str(exc))

        return []

    def track_click(self, affiliate_link_id: str) -> dict:
        """제휴 링크 클릭 수 증가

        Args:
            affiliate_link_id: Supabase affiliate_links.id

        Returns:
            업데이트된 링크 레코드
        """
        try:
            supabase = _get_supabase()
            # 현재 클릭 수 조회
            resp = supabase.table("affiliate_links").select("click_count").eq("id", affiliate_link_id).single().execute()
            current_count = resp.data.get("click_count", 0) if resp.data else 0

            # 클릭 수 +1
            update_resp = (
                supabase.table("affiliate_links")
                .update({"click_count": current_count + 1, "last_clicked_at": datetime.now().isoformat()})
                .eq("id", affiliate_link_id)
                .execute()
            )
            updated = update_resp.data[0] if update_resp.data else {}
            logger.info("affiliate.click_tracked", id=affiliate_link_id, count=current_count + 1)
            return updated
        except Exception as exc:
            logger.error("affiliate.click_track_error", id=affiliate_link_id, error=str(exc))
            return {"error": str(exc)}

    def get_post_stats(self, blog_post_id: str) -> dict:
        """블로그 포스트의 제휴 링크 클릭 통계 조회

        Returns:
            {"total_clicks": ..., "links": [...]}
        """
        try:
            supabase = _get_supabase()
            resp = (
                supabase.table("affiliate_links")
                .select("*")
                .eq("content_id", blog_post_id)
                .eq("content_type", "blog")
                .execute()
            )
            links = resp.data or []
            total_clicks = sum(lnk.get("click_count", 0) for lnk in links)
            return {"blog_post_id": blog_post_id, "total_clicks": total_clicks, "links": links}
        except Exception as exc:
            logger.error("affiliate.stats_error", blog_post_id=blog_post_id, error=str(exc))
            return {"error": str(exc)}

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _select_top_products(self, keywords: list[str]) -> list[dict]:
        """키워드별 쿠팡 상품 검색 후 상위 상품 선정

        중복 제거 후 최대 MAX_PRODUCTS_PER_POST 개 반환.
        """
        seen_ids: set[str] = set()
        selected: list[dict] = []

        for keyword in keywords:
            if len(selected) >= MAX_PRODUCTS_PER_POST:
                break
            try:
                products = self._coupang.search_products(keyword, limit=PRODUCTS_PER_KEYWORD)
            except Exception as exc:
                logger.warning("affiliate.coupang_search_error", keyword=keyword, error=str(exc))
                continue

            for p in products:
                if len(selected) >= MAX_PRODUCTS_PER_POST:
                    break
                pid = str(p.get("productId", ""))
                if not pid or pid in seen_ids:
                    continue
                # 파트너스 딥링크 생성
                raw_url = p.get("affiliate_url") or p.get("product_url", "")
                affiliate_url = self._coupang.generate_deep_link(raw_url)
                selected.append({
                    **p,
                    "affiliate_url": affiliate_url,
                    "keyword": keyword,
                })
                seen_ids.add(pid)

        return selected

    def _insert_product_section(self, content: str, products: list[dict]) -> str:
        """마크다운 콘텐츠 끝에 추천 상품 섹션 삽입

        ## 추천 상품 섹션을 콘텐츠 맨 아래 CTA 직전에 삽입.
        이미 섹션이 있으면 교체.
        """
        product_section = self._build_product_section(products)

        # 기존 추천 상품 섹션 제거 (재삽입 방지)
        content = re.sub(
            r"\n## 🛒 추천 상품.*$",
            "",
            content,
            flags=re.DOTALL,
        ).rstrip()

        return f"{content}\n\n{product_section}"

    def _build_product_section(self, products: list[dict]) -> str:
        """추천 상품 마크다운 섹션 생성"""
        lines = ["## 🛒 추천 상품", ""]
        for idx, p in enumerate(products, start=1):
            name = p.get("productName", "상품")
            price = p.get("price")
            url = p.get("affiliate_url", "#")
            image_url = p.get("image_url", "")
            rating = p.get("rating")

            price_str = f"{int(price):,}원" if price else "가격 확인"
            rating_str = f" ⭐ {rating}" if rating else ""

            if image_url:
                lines.append(f"### {idx}. {name}")
                lines.append(f"![{name}]({image_url})")
            else:
                lines.append(f"### {idx}. {name}")

            lines.append(f"- 가격: **{price_str}**{rating_str}")
            lines.append(f"- [쿠팡에서 구매하기 →]({url}){{rel=\"nofollow\" target=\"_blank\"}}")
            lines.append("")

        lines.append("> ※ 이 포스트는 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.")
        return "\n".join(lines)

    def _save_affiliate_links(self, blog_post_id: str, products: list[dict]) -> list[dict]:
        """affiliate_links 테이블에 삽입된 링크 저장"""
        rows = []
        for idx, p in enumerate(products):
            rows.append({
                "content_type": "blog",
                "content_id": blog_post_id,
                "product_id": str(p.get("productId", "")),
                "product_name": p.get("productName", ""),
                "product_url": p.get("affiliate_url", ""),
                "affiliate_url": p.get("affiliate_url", ""),
                "keyword": p.get("keyword"),
                "position": idx + 1,
                "click_count": 0,
                "created_at": datetime.now().isoformat(),
            })

        try:
            supabase = _get_supabase()
            resp = supabase.table("affiliate_links").insert(rows).execute()
            saved = resp.data or rows
            logger.info("affiliate.links_saved", count=len(saved))
            return saved
        except Exception as exc:
            logger.error("affiliate.save_error", error=str(exc))
            return [{**r, "error": str(exc)} for r in rows]

    def _update_blog_post_content(self, blog_post_id: str, updated_content: str) -> None:
        """blog_posts 테이블의 content 필드 업데이트"""
        try:
            supabase = _get_supabase()
            supabase.table("blog_posts").update(
                {"content": updated_content, "has_affiliate_links": True}
            ).eq("id", blog_post_id).execute()
            logger.info("affiliate.blog_post_updated", blog_post_id=blog_post_id)
        except Exception as exc:
            logger.error("affiliate.blog_post_update_error", blog_post_id=blog_post_id, error=str(exc))

    def close(self) -> None:
        self._coupang.close()
