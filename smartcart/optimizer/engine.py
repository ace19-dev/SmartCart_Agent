"""Optimizer: 품목별 후보 상품 → 최적 장바구니 조합 (결정론적)."""
from __future__ import annotations

from smartcart.models import (
    Budget, CartItem, DeliveryStatus, Item, OptimizationPack,
    ParsedRequest, Product,
)

_MALL_DISPLAY: dict[str, str] = {
    "gs_fresh": "GS프레시몰",
    "emart":    "이마트",
    "kurly":    "마켓컬리",
    "naver":    "네이버쇼핑",
}


def _sort_key(p: Product, priorities: list[str]) -> tuple:
    key = []
    for pr in priorities:
        if pr == "popularity":
            key.append(-p.review_count)
        elif pr == "rating":
            key.append(-p.rating)
        elif pr == "price":
            key.append(p.price)
    return tuple(key)


def optimize_cart(
    candidates: dict[str, list[Product]],
    request: ParsedRequest,
) -> OptimizationPack:
    """품목별 후보 상품 중 ranking_priority 기준으로 최적 상품을 선택합니다.

    Args:
        candidates: {item.name: [Product, ...]} — MCP에서 조회한 품목별 후보 목록
        request:    ParsedRequest — 파서 출력

    Returns:
        OptimizationPack — 선택된 장바구니, 총액, 예산/배송 충족 여부
    """
    cart: list[CartItem] = []
    total_price = 0
    delivery_ok = True

    for item in request.items:
        products = list(candidates.get(item.name, []))

        # 용량 필터 (우유 2L 이상 등)
        if item.min_volume_ml is not None:
            products = [
                p for p in products
                if p.volume_ml is not None and p.volume_ml >= item.min_volume_ml
            ]

        # 배송일 필터
        if request.delivery.date:
            products = [p for p in products if p.delivery_date <= request.delivery.date]

        if not products:
            delivery_ok = False
            continue

        products.sort(key=lambda p: _sort_key(p, request.ranking_priority))
        best = products[0]

        item_label = item.name if item.qty <= 1 else f"{item.name} x{item.qty}"
        item_price = best.price * item.qty
        total_price += item_price

        cart.append(CartItem(
            item=item_label,
            mall=_MALL_DISPLAY.get(best.mall, best.mall),
            mall_id=best.mall,
            product_id=best.id,
            product=best.name,
            price=item_price,
            rating=best.rating,
            review_count=best.review_count,
            delivery_date=best.delivery_date,
            url=best.url,
            qty=item.qty,
        ))

    # 예산 충족 여부
    b = request.budget
    limit = b.amount if b.type == "hard" else b.amount * (1 + b.tolerance_pct / 100)
    budget_ok = total_price <= limit

    return OptimizationPack(
        total_price=total_price,
        budget=request.budget,
        budget_satisfied=budget_ok,
        delivery=DeliveryStatus(date=request.delivery.date, satisfied=delivery_ok),
        ranking_priority=request.ranking_priority,
        cart=cart,
    )


if __name__ == "__main__":
    import json
    from datetime import date, timedelta

    from smartcart.connector.malls.base import SearchFilters
    from smartcart.connector.server import _build_default_server
    from smartcart.models import Delivery, Preferences
    from smartcart.reflection.checker import check_constraints
    from smartcart.router.deeplink import build_deep_link

    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    request = ParsedRequest(
        items=[
            Item(name="사과",          qty=1, category="과일"),
            Item(name="배",            qty=1, category="과일"),
            Item(name="우유",          qty=1, category="유제품", min_volume="2L"),
            Item(name="식빵",          qty=2, category="베이커리"),
            Item(name="어린이 요구르트", qty=1, category="유제품"),
        ],
        ranking_priority=["popularity", "rating", "price"],
        budget=Budget(amount=40000, type="soft", tolerance_pct=10),
        delivery=Delivery(date=tomorrow, address="home"),
        preferences=Preferences(),
    )

    # 품목별 후보 수집 (Mock MCP — 이 데모는 항상 Mock 데이터로 검증)
    server = _build_default_server(include_mock=True)
    candidates: dict[str, list[Product]] = {}
    for item in request.items:
        filters = SearchFilters(
            ranking_priority=request.ranking_priority,
            delivery_date=request.delivery.date,
            min_volume_ml=item.min_volume_ml,
        )
        result = server.search_products(item.name, filters=filters)
        candidates[item.name] = [Product(**p) for p in json.loads(result.to_tool_str())]

    # 최적화
    pack = optimize_cart(candidates, request)

    # 제약 검증
    constraint = check_constraints(pack, request)

    # 결과 출력
    print("=== OptimizationPack ===")
    print(json.dumps(pack.model_dump(), ensure_ascii=False, indent=2))

    print("\n=== ConstraintResult ===")
    print(json.dumps(constraint.model_dump(), ensure_ascii=False, indent=2))

    print("\n=== 딥링크 ===")
    for c in pack.cart:
        link = build_deep_link(c.mall_id, c.product_id)
        print(f"  [{c.mall}] {c.item}: {link}")
