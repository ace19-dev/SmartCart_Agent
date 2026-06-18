"""Reflection: 예산·배송 제약 검증 (결정론적)."""
from __future__ import annotations

from smartcart.models import ConstraintResult, ConstraintViolation, OptimizationPack, ParsedRequest


def check_constraints(pack: OptimizationPack, request: ParsedRequest) -> ConstraintResult:
    """OptimizationPack이 ParsedRequest의 예산·배송 제약을 충족하는지 검증합니다.

    Returns:
        ConstraintResult.satisfied=True 이면 Orchestrator가 route 단계로 진행,
        False 이면 violations 목록을 근거로 재계획(replan)을 트리거합니다.
    """
    violations: list[ConstraintViolation] = []

    # ── 품목 누락 검증 ─────────────────────────────────────────────────────────
    # optimizer가 조건에 맞는 후보를 찾지 못해 장바구니에서 제외한 품목 탐지
    cart_labels = {c.item for c in pack.cart}
    for item in request.items:
        label = item.name if item.qty <= 1 else f"{item.name} x{item.qty}"
        if label not in cart_labels:
            violations.append(ConstraintViolation(
                reason="out_of_stock",
                detail=f"{item.name}: 조건에 맞는 후보 상품을 찾지 못해 장바구니에서 제외됨",
            ))

    # ── 예산 검증 ──────────────────────────────────────────────────────────────
    b = request.budget
    if b.type == "hard":
        limit = b.amount
    else:  # soft
        limit = b.amount * (1 + b.tolerance_pct / 100)

    if pack.total_price > limit:
        over = pack.total_price - int(limit)
        violations.append(ConstraintViolation(
            reason="budget_exceeded",
            detail=(
                f"총액 {pack.total_price:,}원이 허용 한도 {int(limit):,}원을 "
                f"{over:,}원 초과 (예산 {b.amount:,}원, "
                f"{'hard' if b.type == 'hard' else f'soft ±{b.tolerance_pct:.0f}%'})"
            ),
        ))

    # ── 배송 검증 ──────────────────────────────────────────────────────────────
    # delivery.time이 null이면 날짜 단위로만 비교
    req_date = request.delivery.date
    for cart_item in pack.cart:
        if cart_item.delivery_date > req_date:
            violations.append(ConstraintViolation(
                reason="delivery_unavailable",
                detail=(
                    f"{cart_item.item}: 최선 배송일 {cart_item.delivery_date}이 "
                    f"요청 기한 {req_date}을 초과"
                ),
            ))

    return ConstraintResult(satisfied=len(violations) == 0, violations=violations)
