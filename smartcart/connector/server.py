"""MallConnectorMCP — 몰별 어댑터를 등록·라우팅하는 단일 MCP 서버."""
from __future__ import annotations

import json
import logging

from core.base_mcp import BaseMCP, MCPResult

from smartcart.connector.malls.base import MallAdapter, SearchFilters
from smartcart.models import Product


class MallConnectorMCP(BaseMCP):
    """등록된 MallAdapter를 라우팅해 search_products MCP Tool로 노출.

    신규 쇼핑몰 추가 시 이 클래스를 수정하지 않고 어댑터만 register()하면 됩니다.
    """

    def __init__(self) -> None:
        self._adapters: dict[str, MallAdapter] = {}

    def register(self, adapter: MallAdapter) -> None:
        self._adapters[adapter.mall_id] = adapter

    def search_products(
        self,
        query: str,
        mall_ids: list[str] | None = None,
        filters: SearchFilters | None = None,
    ) -> MCPResult:
        """query를 mall_ids 목록의 어댑터에 라우팅하고 결과를 합산합니다.

        mall_ids가 None이면 등록된 전체 어댑터를 대상으로 합니다.
        """
        targets = mall_ids if mall_ids is not None else list(self._adapters.keys())
        if not targets:
            return MCPResult.fail("등록된 어댑터가 없습니다")

        filters = filters or SearchFilters()
        results: list[Product] = []
        errors: list[str] = []

        for mall_id in targets:
            adapter = self._adapters.get(mall_id)
            if adapter is None:
                errors.append(f"{mall_id}: 어댑터 미등록")
                continue
            try:
                results.extend(adapter.search_products(query, filters))
            except Exception as exc:
                errors.append(f"{mall_id}: {exc}")

        data = [p.model_dump() for p in results]
        meta: dict = {"total": len(data)}
        if errors:
            meta["errors"] = errors
        return MCPResult.ok(data, **meta)

    def health_check(self) -> MCPResult:
        if not self._adapters:
            return MCPResult.fail("등록된 어댑터 없음")
        return MCPResult.ok({"adapters": list(self._adapters.keys())})


def _build_default_server(include_mock: bool = False) -> MallConnectorMCP:
    """등록된 실 어댑터로 서버를 구성합니다.

    include_mock=True를 명시적으로 넘기지 않으면 Mock 어댑터(gs_fresh/emart/kurly)는
    등록하지 않습니다 — 실 API가 없는 몰은 결과가 비어 있는 채로 둡니다.
    """
    server = MallConnectorMCP()

    if include_mock:
        from smartcart.connector.malls.mock import MockMallAdapter
        for mall_id in ("gs_fresh", "emart", "kurly"):
            server.register(MockMallAdapter(mall_id))

    from smartcart.connector.malls.naver import NaverShoppingAdapter
    try:
        server.register(NaverShoppingAdapter())
    except RuntimeError as exc:
        logging.getLogger(__name__).warning("네이버쇼핑 어댑터 비활성화: %s", exc)

    return server


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="등록된 어댑터로 테스트 검색 실행")
    parser.add_argument("--mock", action="store_true", help="Mock 어댑터(gs_fresh/emart/kurly)도 포함")
    args = parser.parse_args()

    if args.test:
        server = _build_default_server(include_mock=args.mock)

        print("=== health_check ===")
        print(server.health_check().to_tool_str())

        test_cases = [
            ("사과", SearchFilters()),
            ("우유", SearchFilters(min_volume_ml=2000)),
            ("요구르트", SearchFilters(ranking_priority=["popularity", "rating", "price"])),
        ]
        for query, filters in test_cases:
            print(f"\n=== search_products('{query}') ===")
            result = server.search_products(query, filters=filters)
            products = json.loads(result.to_tool_str())
            for p in products:
                print(f"  [{p['mall']}] {p['name']} — {p['price']:,}원 | ★{p['rating']} ({p['review_count']:,}리뷰) | 배송 {p['delivery_date']}")
