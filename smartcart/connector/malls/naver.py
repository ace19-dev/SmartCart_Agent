"""네이버쇼핑 검색 API 어댑터 — 실 API 연동 (GS프레시몰/이마트/마켓컬리는 공개 검색
API가 없어 당분간 Mock 유지, 네이버쇼핑만 우선 실연동. 자세한 조사 내용은
docs/implementation-plan.md Step 7 참고).

알려진 한계 (네이버 검색 API가 제공하지 않는 정보):
- rating/review_count: 미제공 → 0으로 채움. ranking_priority의 popularity/rating
  정렬에서 항상 후순위가 되어, 실제 평점 데이터가 있는 다른 몰이 우선 선택됨.
- volume_ml: 미제공 → None 유지. "우유 2L 이상" 같은 용량 조건이 있으면 optimizer가
  volume_ml=None인 상품을 자동으로 제외함(연동 정보 부족, 신뢰 불가).
- delivery_date: 미제공 → 요청 배송 희망일을 그대로 가정(미확정). 실제 배송 가능
  여부는 사용자가 딥링크를 클릭해 직접 확인해야 함(Phase 1 범위: 링크 제공까지).
"""
from __future__ import annotations

import html
import json
import logging
import re
from datetime import date

from mcp.http import get_http_mcp

from smartcart.config import NAVER_CLIENT_ID, NAVER_CLIENT_SECRET
from smartcart.connector.malls.base import MallAdapter, SearchFilters
from smartcart.models import Product

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://openapi.naver.com/v1/search/shop.json"
_DISPLAY = 10  # 품목당 후보 수 (다른 어댑터와 비슷한 규모로 제한)
_EXCLUDE = "used:rental:cbshop"  # 중고/렌탈/해외직구 제외 (식료품 검색 품질 향상)


def _clean_title(raw: str) -> str:
    """검색어 강조용 <b> 태그 제거 + HTML 엔티티 디코딩."""
    return html.unescape(re.sub(r"</?b>", "", raw))


class NaverShoppingAdapter(MallAdapter):
    mall_id = "naver"

    def __init__(self) -> None:
        if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
            raise RuntimeError(
                "NAVER_CLIENT_ID / NAVER_CLIENT_SECRET이 설정되지 않았습니다. "
                "https://developers.naver.com 에서 발급한 키를 .env에 추가하세요."
            )

    def search_products(self, query: str, filters: SearchFilters) -> list[Product]:
        result = get_http_mcp().get(
            _SEARCH_URL,
            headers={
                "X-Naver-Client-Id": NAVER_CLIENT_ID,
                "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
            },
            params={"query": query, "display": _DISPLAY, "sort": "sim", "exclude": _EXCLUDE},
            max_body=20_000,
        )
        if not result.success or result.data.get("status_code") != 200:
            logger.warning(
                "네이버쇼핑 검색 실패(query=%r): %s",
                query, result.error or result.data.get("body"),
            )
            return []

        body = json.loads(result.data["body"])
        assumed_delivery = filters.delivery_date or date.today().isoformat()

        products = [
            Product(
                id=item["link"],  # router/deeplink.py가 그대로 사용 (실 구매 링크)
                name=_clean_title(item["title"]),
                mall=self.mall_id,
                price=int(item["lprice"]),
                rating=0.0,
                review_count=0,
                delivery_date=assumed_delivery,
                url=item["link"],
                image_url=item.get("image", ""),
            )
            for item in body.get("items", [])
            if item.get("lprice")
        ]

        if filters.max_price is not None:
            products = [p for p in products if p.price <= filters.max_price]

        return products
