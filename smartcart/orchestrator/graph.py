"""SmartCart Orchestrator — LangGraph 파이프라인.

토폴로지:
  search → optimize → reflect → [route
                                  | clarify → search (불만족 시 매 라운드, HITL)]

reflect가 불만족이면 매 라운드(최대 MAX_REPLAN_ATTEMPTS회) clarify로 가서
사용자에게 선택지를 묻습니다. 선택지는:
  - out_of_stock 위반: 이미 가진 후보 데이터로 결정론적으로 계산(숫자 검증됨)
  - budget/delivery 위반: LLM이 제안(예산/배송일 조정, 몰 제외, 가격 상한 등 —
    예전 replan_node가 혼자 결정했던 것과 같은 종류의 조정을, 이제는 옵션으로
    제시하고 사용자가 고른 것만 적용)
"""
from __future__ import annotations

import json
import logging
import math
import uuid
from typing import Optional
from typing_extensions import TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.types import Command, interrupt
from pydantic import BaseModel

from smartcart.config import MAX_REPLAN_ATTEMPTS
from smartcart.connector.enrich import enrich_volume_ml
from smartcart.connector.malls.base import SearchFilters
from smartcart.connector.server import _build_default_server
from smartcart.models import (
    ConstraintResult, Item, OptimizationPack, ParsedRequest, Product,
)
from smartcart.optimizer.engine import optimize_cart
from smartcart.reflection.checker import check_constraints
from smartcart.router.deeplink import build_deep_link

logger = logging.getLogger(__name__)

_checkpointer = MemorySaver()


class SmartCartState(TypedDict):
    request: ParsedRequest
    search_filters: dict        # {item_name: SearchFilters kwargs dict}
    excluded_malls: list        # 검색에서 제외할 mall_id 목록
    candidates: dict            # {item_name: list[Product]}
    pack: Optional[OptimizationPack]
    constraint: Optional[ConstraintResult]
    replan_count: int           # clarify(질문) 라운드 횟수
    best_effort: bool
    deep_links: list            # [{item, mall, product, price, rating, ...}]
    accepted_best_effort: bool  # 사용자가 "지금까지 결과로 진행"을 선택했는지


def _initial_filters(request: ParsedRequest) -> dict:
    return {
        item.name: {
            "ranking_priority": request.ranking_priority,
            "min_volume_ml": item.min_volume_ml,
            "delivery_date": request.delivery.date,
        }
        for item in request.items
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


# ── 노드 함수 ──────────────────────────────────────────────────────────────────

def search_node(state: SmartCartState) -> dict:
    server = _build_default_server()
    excluded = set(state.get("excluded_malls", []))
    all_mall_ids = list(server._adapters.keys())
    available = [m for m in all_mall_ids if m not in excluded] or None

    candidates: dict = {}
    valid_fields = set(SearchFilters.model_fields.keys())

    for item in state["request"].items:
        raw_kwargs = state["search_filters"].get(item.name, {})
        filters = SearchFilters(**{k: v for k, v in raw_kwargs.items() if k in valid_fields})
        result = server.search_products(item.name, mall_ids=available, filters=filters)
        if result.success:
            candidates[item.name] = [Product(**p) for p in json.loads(result.to_tool_str())]
        else:
            candidates[item.name] = []

        if item.requires_volume_info:
            candidates[item.name] = enrich_volume_ml(candidates[item.name])

    return {"candidates": candidates}


def optimize_node(state: SmartCartState) -> dict:
    return {"pack": optimize_cart(state["candidates"], state["request"])}


def reflect_node(state: SmartCartState) -> dict:
    return {"constraint": check_constraints(state["pack"], state["request"])}


def route_node(state: SmartCartState) -> dict:
    deep_links = []
    for c in state["pack"].cart:
        deep_links.append({
            "item": c.item,
            "mall": c.mall,
            "product": c.product,
            "price": c.price,
            "rating": c.rating,
            "review_count": c.review_count,
            "delivery_date": c.delivery_date,
            "url": build_deep_link(c.mall_id, c.product_id),
        })
    return {
        "deep_links": deep_links,
        "best_effort": not state["constraint"].satisfied,
    }


# ── clarify (HITL): 위반이 있으면 매 라운드 사용자에게 선택지 제시 ────────────────

def _compute_volume_options(item_name: str, item: Item, sorted_products: list[Product]) -> list[dict]:
    """out_of_stock(용량 조건) 위반 — 이미 가진 후보 데이터로 숫자가 검증된 선택지를 계산."""
    min_ml = item.min_volume_ml
    options: list[dict] = []

    seen_qty: set[int] = set()
    for p in sorted([p for p in sorted_products if p.volume_ml], key=lambda p: p.price):
        for n in (2, 3, 4):
            if n in seen_qty:
                continue
            if p.volume_ml * n >= min_ml:
                seen_qty.add(n)
                options.append({
                    "action": "multiply_qty",
                    "item_name": item_name,
                    "qty": n,
                    "description": (
                        f"{item_name}: {p.name} {n}개 구매 — {p.volume_ml * n:,}ml 충족 "
                        f"(단가 {p.price:,}원 × {n} = {p.price * n:,}원)"
                    ),
                })
                break

    if sorted_products:
        top = sorted_products[0]
        options.append({
            "action": "relax_volume",
            "item_name": item_name,
            "description": (
                f"{item_name}: 용량 조건 없이 진행 — {top.name} "
                f"({top.price:,}원, 현재 정렬 기준 1순위)"
            ),
        })

    options.append({
        "action": "drop_item",
        "item_name": item_name,
        "description": f"{item_name}은 제외하고 나머지만 진행",
    })
    return options


class _LLMOption(BaseModel):
    description: str
    action: str  # "adjust_budget" | "adjust_delivery" | "exclude_mall" | "adjust_max_price"
    item_name: Optional[str] = None
    new_budget_amount: Optional[int] = None
    new_delivery_date: Optional[str] = None
    excluded_mall: Optional[str] = None
    new_max_price: Optional[int] = None


class _LLMOptionBatch(BaseModel):
    options: list[_LLMOption]


def _propose_filter_options(state: SmartCartState, violations: list) -> list[dict]:
    """budget/delivery 등 숫자 계산이 결정론적이지 않은 위반 — LLM이 조정 옵션을 제안.

    예전 replan_node가 혼자 결정했던 것(예산상한/배송일/제외몰/가격상한 조정)과
    같은 종류의 판단이지만, 이제는 "제안"만 하고 사용자가 고른 것만 적용됩니다.
    """
    from core.llm import make_llm
    from langchain_core.messages import HumanMessage, SystemMessage

    request = state["request"]
    pack = state["pack"]
    violation_text = "\n".join(f"- [{v.reason}] {v.detail}" for v in violations)
    known_malls = list(_build_default_server()._adapters.keys())

    prompt = (
        f"장바구니 제약 위반:\n{violation_text}\n\n"
        f"예산: {request.budget.amount:,}원 ({request.budget.type}), "
        f"배송 기한: {request.delivery.date}, 현재 총액: {pack.total_price:,}원\n"
        f"등록된 쇼핑몰: {known_malls}\n\n"
        "이 위반을 해결할 수 있는, 서로 다른 방향의 선택지 2~3개를 만드세요. "
        "각 선택지는 description(사용자에게 보여줄 한국어 한 줄 설명)과 "
        "action(adjust_budget/adjust_delivery/exclude_mall/adjust_max_price 중 하나), "
        "그리고 해당 액션에 필요한 구체적인 값을 채워야 합니다."
    )
    try:
        llm = make_llm(structured_output=_LLMOptionBatch)
        result: _LLMOptionBatch = llm.invoke([
            SystemMessage(content="SmartCart 재계획 에이전트. 제약 위반을 해결할 선택지를 제안하세요."),
            HumanMessage(content=prompt),
        ])
        return [o.model_dump() for o in result.options]
    except Exception:
        logger.warning("clarify: 필터 조정 옵션 생성 실패", exc_info=True)
        return []


class _CurationResult(BaseModel):
    selected_indices: list[int]


def _curate_options(options: list[dict]) -> list[dict]:
    """선택지가 많을 때만 LLM으로 다양하고 유용한 4개를 고릅니다.

    숫자는 이미 전부 검증/제안된 값이고, LLM은 그중 어떤 걸 보여줄지만 고릅니다.
    """
    if len(options) <= 4:
        return options

    from core.llm import make_llm
    from langchain_core.messages import HumanMessage, SystemMessage

    try:
        llm = make_llm(structured_output=_CurationResult)
        result: _CurationResult = llm.invoke([
            SystemMessage(content=(
                "아래는 사용자에게 보여줄 선택지 후보입니다. 내용을 바꾸지 말고, "
                "가장 다양하고 유용한 선택지를 최대 4개까지 인덱스(0부터)로 고르세요."
            )),
            HumanMessage(content=json.dumps(options, ensure_ascii=False, indent=2)),
        ])
        selected = [options[i] for i in result.selected_indices if 0 <= i < len(options)]
        if selected:
            return selected[:4]
    except Exception:
        logger.warning("clarify: 선택지 큐레이션 실패 — 앞에서 4개만 사용", exc_info=True)
    return options[:4]


def _resolve_choice(answer: str, options: list[dict]) -> dict:
    """사용자 답변을 옵션 중 하나로 매칭합니다. 숫자 답변은 그대로, 자유 텍스트는 LLM이 매칭."""
    answer = (answer or "").strip()
    if answer.isdigit():
        idx = int(answer) - 1
        if 0 <= idx < len(options):
            return options[idx]

    from core.llm import make_llm
    from langchain_core.messages import HumanMessage, SystemMessage

    class _Match(BaseModel):
        index: int

    listing = "\n".join(f"{i + 1}. {o['description']}" for i, o in enumerate(options))
    try:
        llm = make_llm(structured_output=_Match)
        result: _Match = llm.invoke([
            SystemMessage(content="사용자 답변이 아래 선택지 중 어느 것에 가장 가까운지 0부터 시작하는 인덱스로 답하세요."),
            HumanMessage(content=f"선택지:\n{listing}\n\n사용자 답변: {answer!r}"),
        ])
        if 0 <= result.index < len(options):
            return options[result.index]
    except Exception:
        logger.warning("clarify: 답변 해석 실패 — 첫 옵션으로 진행", exc_info=True)
    return options[0]


def _apply_choice(state: SmartCartState, choice: dict) -> dict:
    """선택된 옵션을 실제로 request/search_filters/excluded_malls에 반영."""
    action = choice["action"]
    request = state["request"]

    if action == "accept_best_effort":
        return {"accepted_best_effort": True, "replan_count": state["replan_count"] + 1}

    if action == "drop_item":
        request = request.model_copy(update={
            "items": [i for i in request.items if i.name != choice["item_name"]]
        })
    elif action == "multiply_qty":
        new_items = []
        for i in request.items:
            if i.name == choice["item_name"]:
                per_unit_ml = math.ceil(i.min_volume_ml / choice["qty"])
                i = i.model_copy(update={"qty": choice["qty"], "min_volume": f"{per_unit_ml}ml"})
            new_items.append(i)
        request = request.model_copy(update={"items": new_items})
    elif action == "relax_volume":
        new_items = []
        for i in request.items:
            if i.name == choice["item_name"]:
                i = i.model_copy(update={"min_volume": None})
            new_items.append(i)
        request = request.model_copy(update={"items": new_items})
    elif action == "adjust_budget" and choice.get("new_budget_amount"):
        request = request.model_copy(update={
            "budget": request.budget.model_copy(update={"amount": choice["new_budget_amount"]})
        })
    elif action == "adjust_delivery" and choice.get("new_delivery_date"):
        request = request.model_copy(update={
            "delivery": request.delivery.model_copy(update={"date": choice["new_delivery_date"]})
        })

    updates: dict = {
        "request": request,
        "replan_count": state["replan_count"] + 1,
        "accepted_best_effort": False,
    }

    if action == "exclude_mall" and choice.get("excluded_mall"):
        updates["excluded_malls"] = list(set(state.get("excluded_malls", [])) | {choice["excluded_mall"]})
    if action == "adjust_max_price" and choice.get("item_name") and choice.get("new_max_price"):
        sf = dict(state["search_filters"])
        item_name = choice["item_name"]
        sf[item_name] = {**sf.get(item_name, {}), "max_price": choice["new_max_price"]}
        updates["search_filters"] = sf

    return updates


def clarify_node(state: SmartCartState) -> dict:
    request = state["request"]
    violations = state["constraint"].violations

    options: list[dict] = []
    for v in violations:
        if v.reason != "out_of_stock":
            continue
        item_name = v.detail.split(":")[0].strip()
        item = next((i for i in request.items if i.name == item_name), None)
        if item is None or item.min_volume_ml is None:
            continue
        products = state["candidates"].get(item_name, [])
        sorted_products = sorted(products, key=lambda p: _sort_key(p, request.ranking_priority))
        options += _compute_volume_options(item_name, item, sorted_products)

    other_violations = [v for v in violations if v.reason != "out_of_stock"]
    if other_violations:
        options += _propose_filter_options(state, other_violations)

    options.append({"action": "accept_best_effort", "description": "지금까지 찾은 결과로 진행 (best-effort)"})
    options = _curate_options(options)

    question = "\n".join([
        "다음 조건을 그대로 만족시키지 못했습니다. 어떻게 할까요?",
        *[f"{i}. {o['description']}" for i, o in enumerate(options, 1)],
    ])

    answer = interrupt({"question": question, "options": options})
    choice = _resolve_choice(answer, options)
    return _apply_choice(state, choice)


# ── 조건부 라우팅 ──────────────────────────────────────────────────────────────

def _after_reflect(state: SmartCartState) -> str:
    if state["constraint"].satisfied:
        return "route"
    if state["replan_count"] >= MAX_REPLAN_ATTEMPTS:
        return "route"  # best_effort — 질문 라운드 한도 초과
    return "clarify"


def _after_clarify(state: SmartCartState) -> str:
    return "route" if state.get("accepted_best_effort") else "search"


# ── 그래프 구성 ────────────────────────────────────────────────────────────────

def build_graph():
    """SmartCart LangGraph 파이프라인을 빌드하고 컴파일합니다 (체크포인터 포함 — clarify HITL용)."""
    g = StateGraph(SmartCartState)

    g.add_node("search",   search_node)
    g.add_node("optimize", optimize_node)
    g.add_node("reflect",  reflect_node)
    g.add_node("route",    route_node)
    g.add_node("clarify",  clarify_node)

    g.set_entry_point("search")
    g.add_edge("search",   "optimize")
    g.add_edge("optimize", "reflect")
    g.add_conditional_edges(
        "reflect",
        _after_reflect,
        {"route": "route", "clarify": "clarify"},
    )
    g.add_conditional_edges(
        "clarify",
        _after_clarify,
        {"search": "search", "route": "route"},
    )
    g.add_edge("route", END)

    return g.compile(checkpointer=_checkpointer)


def _get_interrupt(graph, config: dict) -> Optional[dict]:
    snapshot = graph.get_state(config)
    if snapshot.next:
        for task in snapshot.tasks:
            if task.interrupts:
                return task.interrupts[0].value
    return None


def start(request: ParsedRequest) -> dict:
    """새 대화를 시작합니다.

    반환: {"thread_id", "state", "interrupt"}
    interrupt가 None이 아니면 사용자 답변이 필요한 상태(state는 미완성)이며,
    resume(thread_id, answer)로 이어가야 합니다.
    """
    graph = build_graph()
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    initial: SmartCartState = {
        "request":        request,
        "search_filters": _initial_filters(request),
        "excluded_malls": [],
        "candidates":     {},
        "pack":           None,
        "constraint":     None,
        "replan_count":   0,
        "best_effort":    False,
        "deep_links":     [],
        "accepted_best_effort": False,
    }
    state = graph.invoke(initial, config)
    return {"thread_id": thread_id, "state": state, "interrupt": _get_interrupt(graph, config)}


def resume(thread_id: str, answer: str) -> dict:
    """clarify 질문에 대한 답변을 받아 대화를 이어갑니다. 반환 형식은 start()와 동일."""
    graph = build_graph()
    config = {"configurable": {"thread_id": thread_id}}
    state = graph.invoke(Command(resume=answer), config)
    return {"thread_id": thread_id, "state": state, "interrupt": _get_interrupt(graph, config)}
