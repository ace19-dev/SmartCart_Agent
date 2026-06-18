"""공통 Pydantic 모델.

Step 2: Product
Step 3: Item, Budget, Delivery, Preferences, ParsedRequest
Step 4: CartItem, Substitution, Alternative, OptimizationPack, ConstraintResult
"""
from __future__ import annotations

from pydantic import BaseModel, field_validator


# ── Step 2: 검색 결과 상품 ─────────────────────────────────────────────────────

class Product(BaseModel):
    id: str
    name: str
    mall: str           # "gs_fresh" | "emart" | "kurly" | "naver"
    price: int          # 원
    rating: float       # 0.0 ~ 5.0
    review_count: int
    delivery_date: str  # YYYY-MM-DD (최선 배송일)
    url: str
    image_url: str = ""
    volume_ml: int | None = None  # 용량 (음료/유제품)
    quantity: int = 1             # 묶음 단위


# ── Step 3: Parser 출력 (README 4.1) ──────────────────────────────────────────

class Item(BaseModel):
    name: str
    qty: int = 1
    unit: str | None = None        # "봉지" | "개" | "묶음"
    category: str | None = None    # "과일" | "유제품" | "베이커리"
    min_volume: str | None = None  # "2L", "500ml" 등 문자열 그대로

    @property
    def min_volume_ml(self) -> int | None:
        """min_volume 문자열을 ml 정수로 변환. SearchFilters 연동에 사용."""
        if not self.min_volume:
            return None
        v = self.min_volume.strip().lower().replace(" ", "")
        try:
            # "ml"도 "l"로 끝나므로, 더 구체적인 접미사(ml)부터 검사해야 함
            if v.endswith("ml"):
                return int(float(v[:-2]))
            if v.endswith("l"):
                return int(float(v[:-1]) * 1000)
        except ValueError:
            pass
        return None

    @property
    def requires_volume_info(self) -> bool:
        """검색 결과에 volume_ml 보강(제목 추출)이 필요한지 여부.

        지금은 min_volume 조건 유무로만 판단하지만, 향후 max_volume 등
        용량 관련 조건이 추가되면 이 property만 수정하면 됩니다.
        """
        return self.min_volume_ml is not None


class Budget(BaseModel):
    amount: int
    type: str = "soft"          # "soft"(±tolerance_pct%) | "hard"(초과 불가)
    tolerance_pct: float = 10.0


class Delivery(BaseModel):
    date: str                   # YYYY-MM-DD
    time: str | None = None
    address: str | None = None


class Preferences(BaseModel):
    min_rating: float | None = None
    organic_preferred: bool = False

    @field_validator("organic_preferred", mode="before")
    @classmethod
    def _coerce_none(cls, v: object) -> bool:
        return False if v is None else v


class ParsedRequest(BaseModel):
    items: list[Item]
    ranking_priority: list[str] = ["popularity", "rating", "price"]
    budget: Budget
    delivery: Delivery
    preferences: Preferences = Preferences()
    clarification_needed: list[str] = []  # 모호한 항목에 대한 명확화 질문


# ── Step 4: Optimizer 출력 (README 4.2) ───────────────────────────────────────

class CartItem(BaseModel):
    item: str           # "사과", "식빵 x2" (qty>1이면 suffix)
    mall: str           # 표시명 "마켓컬리" | "GS프레시몰" | "이마트" | "네이버쇼핑"
    mall_id: str        # 내부 ID "kurly" (딥링크용)
    product_id: str     # 상품 ID (딥링크용)
    product: str        # 상품명
    price: int          # qty 반영된 총 가격
    rating: float
    review_count: int
    delivery_date: str
    url: str
    qty: int = 1


class Substitution(BaseModel):
    original_item: str
    original_product: str
    original_price: int
    reason: str         # "budget_exceeded" | "delivery_unavailable" | "out_of_stock"
    reason_detail: str
    replacement_product: str
    replacement_price: int


class Alternative(BaseModel):
    for_item: str
    suggestion: str
    price: int
    review_count: int
    reason: str


class DeliveryStatus(BaseModel):
    date: str
    satisfied: bool


class OptimizationPack(BaseModel):
    total_price: int
    budget: Budget
    budget_satisfied: bool
    delivery: DeliveryStatus
    ranking_priority: list[str]
    cart: list[CartItem]
    substitutions: list[Substitution] = []
    alternatives: list[Alternative] = []


# ── Step 4: Reflection 출력 ────────────────────────────────────────────────────

class ConstraintViolation(BaseModel):
    reason: str         # "budget_exceeded" | "delivery_unavailable" | "out_of_stock"
    detail: str


class ConstraintResult(BaseModel):
    satisfied: bool
    violations: list[ConstraintViolation] = []
