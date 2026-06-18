from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel

from smartcart.models import Product


class SearchFilters(BaseModel):
    ranking_priority: list[str] = ["popularity", "rating", "price"]
    max_price: int | None = None
    delivery_date: str | None = None   # 이 날짜까지 배송 가능해야 함 (YYYY-MM-DD)
    min_volume_ml: int | None = None   # 최소 용량 (예: 우유 2L → 2000)
    min_quantity: int | None = None    # 최소 묶음 수량


class MallAdapter(ABC):
    mall_id: str  # "gs_fresh" | "emart" | "kurly" | "naver"

    @abstractmethod
    def search_products(self, query: str, filters: SearchFilters) -> list[Product]: ...
