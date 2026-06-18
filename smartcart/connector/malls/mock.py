"""Mock 어댑터 — PoC용 더미 데이터. 실 API 연동 전 전체 파이프라인 검증에 사용."""
from __future__ import annotations

from datetime import date, timedelta

from smartcart.connector.malls.base import MallAdapter, SearchFilters
from smartcart.models import Product

_TODAY = date.today().isoformat()
_TOMORROW = (date.today() + timedelta(days=1)).isoformat()
_DAY2 = (date.today() + timedelta(days=2)).isoformat()

# 쿠팡 제외: GS프레시, 이마트, 마켓컬리
_PRODUCTS: list[Product] = [
    # ── 사과 ────────────────────────────────────────────────────────────────
    Product(id="gs-apple-001", name="경북 홍로 사과 4입 (특)", mall="gs_fresh",
            price=8900, rating=4.7, review_count=2341, delivery_date=_TOMORROW,
            url="https://www.gsfresh.com/product/gs-apple-001"),
    Product(id="em-apple-001", name="충주 사과 6개입 (대)", mall="emart",
            price=9800, rating=4.5, review_count=1892, delivery_date=_TOMORROW,
            url="https://emart.ssg.com/item/itemView.ssg?itemId=em-apple-001"),
    Product(id="ku-apple-001", name="정품 부사 사과 1kg", mall="kurly",
            price=7500, rating=4.8, review_count=3201, delivery_date=_TOMORROW,
            url="https://www.kurly.com/goods/ku-apple-001"),

    # ── 배 ──────────────────────────────────────────────────────────────────
    Product(id="gs-pear-001", name="신고 배 2입 (대과)", mall="gs_fresh",
            price=11900, rating=4.6, review_count=987, delivery_date=_TOMORROW,
            url="https://www.gsfresh.com/product/gs-pear-001"),
    Product(id="em-pear-001", name="이마트 나주 배 3입", mall="emart",
            price=13500, rating=4.4, review_count=754, delivery_date=_DAY2,
            url="https://emart.ssg.com/item/itemView.ssg?itemId=em-pear-001"),
    Product(id="ku-pear-001", name="GAP 인증 신고 배 1.5kg", mall="kurly",
            price=10900, rating=4.7, review_count=1523, delivery_date=_TOMORROW,
            url="https://www.kurly.com/goods/ku-pear-001"),

    # ── 우유 (2L) ────────────────────────────────────────────────────────────
    Product(id="gs-milk-001", name="서울우유 흰우유 2.3L", mall="gs_fresh",
            price=4290, rating=4.8, review_count=8921, delivery_date=_TOMORROW,
            url="https://www.gsfresh.com/product/gs-milk-001", volume_ml=2300),
    Product(id="em-milk-001", name="매일우유 오리지널 2L", mall="emart",
            price=3980, rating=4.7, review_count=7234, delivery_date=_TOMORROW,
            url="https://emart.ssg.com/item/itemView.ssg?itemId=em-milk-001", volume_ml=2000),
    Product(id="ku-milk-001", name="연세우유 생생 2L", mall="kurly",
            price=4100, rating=4.9, review_count=11042, delivery_date=_TOMORROW,
            url="https://www.kurly.com/goods/ku-milk-001", volume_ml=2000),
    Product(id="gs-milk-002", name="남양 맛있는우유 GT 1L", mall="gs_fresh",
            price=2190, rating=4.6, review_count=3412, delivery_date=_TOMORROW,
            url="https://www.gsfresh.com/product/gs-milk-002", volume_ml=1000),

    # ── 식빵 ────────────────────────────────────────────────────────────────
    Product(id="gs-bread-001", name="삼립 촉촉한 식빵 (480g)", mall="gs_fresh",
            price=2990, rating=4.5, review_count=5632, delivery_date=_TOMORROW,
            url="https://www.gsfresh.com/product/gs-bread-001"),
    Product(id="em-bread-001", name="피코크 우유식빵 (500g)", mall="emart",
            price=3500, rating=4.7, review_count=4218, delivery_date=_TOMORROW,
            url="https://emart.ssg.com/item/itemView.ssg?itemId=em-bread-001"),
    Product(id="ku-bread-001", name="밀도 우유 식빵 (400g)", mall="kurly",
            price=4200, rating=4.8, review_count=9871, delivery_date=_TOMORROW,
            url="https://www.kurly.com/goods/ku-bread-001"),

    # ── 어린이 요구르트 ────────────────────────────────────────────────────
    Product(id="gs-yogurt-001", name="야쿠르트 어린이 요구르트 8입", mall="gs_fresh",
            price=4500, rating=4.6, review_count=3892, delivery_date=_TOMORROW,
            url="https://www.gsfresh.com/product/gs-yogurt-001"),
    Product(id="em-yogurt-001", name="빙그레 요플레 어린이 4입", mall="emart",
            price=3200, rating=4.4, review_count=2341, delivery_date=_DAY2,
            url="https://emart.ssg.com/item/itemView.ssg?itemId=em-yogurt-001"),
    Product(id="ku-yogurt-001", name="매일 어린이 요거트 드링크 6입", mall="kurly",
            price=5800, rating=4.9, review_count=6723, delivery_date=_TOMORROW,
            url="https://www.kurly.com/goods/ku-yogurt-001"),
]

_KEYWORDS: dict[str, list[str]] = {
    "사과": ["사과", "apple"],
    "배": ["배", "pear"],
    "우유": ["우유", "milk"],
    "식빵": ["식빵", "bread", "빵"],
    "요구르트": ["요구르트", "요거트", "yogurt", "야쿠르트"],
}


def _matches(product: Product, query: str) -> bool:
    q = query.lower()
    for keyword, aliases in _KEYWORDS.items():
        if any(a in q for a in aliases):
            if keyword in product.name or any(a in product.name.lower() for a in aliases):
                return True
    # fallback: 직접 이름 포함 검색
    return any(w in product.name for w in query.split() if len(w) > 1)


def _sort_key(p: Product, priorities: list[str]) -> tuple:
    key = []
    for priority in priorities:
        if priority == "popularity":
            key.append(-p.review_count)
        elif priority == "rating":
            key.append(-p.rating)
        elif priority == "price":
            key.append(p.price)
    return tuple(key)


class MockMallAdapter(MallAdapter):
    def __init__(self, mall_id: str) -> None:
        self.mall_id = mall_id

    def search_products(self, query: str, filters: SearchFilters) -> list[Product]:
        results = [p for p in _PRODUCTS if p.mall == self.mall_id and _matches(p, query)]

        if filters.min_volume_ml is not None:
            results = [p for p in results if p.volume_ml is not None and p.volume_ml >= filters.min_volume_ml]
        if filters.delivery_date is not None:
            results = [p for p in results if p.delivery_date <= filters.delivery_date]
        if filters.max_price is not None:
            results = [p for p in results if p.price <= filters.max_price]

        results.sort(key=lambda p: _sort_key(p, filters.ranking_priority))
        return results
