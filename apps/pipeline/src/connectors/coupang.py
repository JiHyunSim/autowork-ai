"""쿠팡 파트너스 API 커넥터"""
import hashlib
import hmac
import time
import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import settings

logger = structlog.get_logger(__name__)

COUPANG_API_BASE = "https://api-gateway.coupang.com"


class CoupangConnector:
    """쿠팡 파트너스 제휴 링크 생성 커넥터"""

    def __init__(self) -> None:
        self.access_key = settings.coupang_access_key
        self.secret_key = settings.coupang_secret_key
        self.client = httpx.Client(timeout=30.0)

    def _generate_hmac(self, method: str, path: str, query: str) -> str:
        """쿠팡 API HMAC 서명 생성"""
        datetime_str = time.strftime("%y%m%dT%H%M%SZ", time.gmtime())
        message = f"{datetime_str}{method}{path}{query}"
        signature = hmac.new(
            self.secret_key.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return f"CEA algorithm=HmacSHA256, access-key={self.access_key}, signed-date={datetime_str}, signature={signature}"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=5))
    def search_products(self, keyword: str, limit: int = 5) -> list[dict]:
        """키워드로 쿠팡 상품 검색

        Args:
            keyword: 검색 키워드
            limit: 반환 상품 수 (최대 100)

        Returns:
            [{"productId": ..., "productName": ..., "price": ..., "affiliate_url": ...}, ...]
        """
        logger.info("coupang.search_products", keyword=keyword, limit=limit)

        path = "/v2/providers/affiliate_open_api/apis/openapi/products/search"
        query = f"keyword={keyword}&limit={limit}"

        authorization = self._generate_hmac("GET", path, query)
        resp = self.client.get(
            f"{COUPANG_API_BASE}{path}",
            params={"keyword": keyword, "limit": limit},
            headers={"Authorization": authorization},
        )
        resp.raise_for_status()
        data = resp.json()

        products = []
        for item in data.get("data", {}).get("productData", []):
            products.append(
                {
                    "productId": item.get("productId"),
                    "productName": item.get("productName"),
                    "price": item.get("price"),
                    "affiliate_url": item.get("productUrl"),
                    "image_url": item.get("productImage"),
                    "rating": item.get("rating"),
                }
            )

        logger.info("coupang.search_products.done", count=len(products))
        return products

    def generate_deep_link(self, product_url: str) -> str:
        """쿠팡 상품 URL을 파트너스 딥링크로 변환

        쿠팡 파트너스 API가 없는 경우 URL 파라미터 방식 사용
        """
        if "coupang.com" not in product_url:
            return product_url

        # 파트너스 트래킹 파라미터 추가
        separator = "&" if "?" in product_url else "?"
        return f"{product_url}{separator}subId={self.access_key[:8]}"

    def close(self) -> None:
        self.client.close()
