"""SmartCart Agent CLI 진입점 (Phase 1).

사용법:
  python -m smartcart.main --input "사과, 우유 2L, 식빵 2개. 예산 4만원, 내일 집으로"
  python -m smartcart.main --mock-parse   # LLM 파서 없이 고정 요청으로 테스트
  uvicorn smartcart.main:app --reload     # FastAPI 서버 (POST /chat)
"""
from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from typing import Optional

from fastapi import FastAPI
from pydantic import BaseModel

from smartcart.models import Budget, Delivery, Item, OptimizationPack, ParsedRequest, Preferences


def _mock_request() -> ParsedRequest:
    """--mock-parse 플래그: LLM 없이 고정 ParsedRequest 사용."""
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    return ParsedRequest(
        items=[
            Item(name="사과",           qty=1, category="과일"),
            Item(name="배",             qty=1, category="과일"),
            Item(name="우유",           qty=1, category="유제품", min_volume="2L"),
            Item(name="식빵",           qty=2, category="베이커리"),
            Item(name="어린이 요구르트", qty=1, category="유제품"),
        ],
        ranking_priority=["popularity", "rating", "price"],
        budget=Budget(amount=40000, type="soft", tolerance_pct=10),
        delivery=Delivery(date=tomorrow, address="home"),
        preferences=Preferences(),
    )


def _state_to_result(state: dict) -> dict:
    return {
        "pack":         state["pack"],
        "deep_links":   state["deep_links"],
        "best_effort":  state["best_effort"],
        "replan_count": state["replan_count"],
        "violations":   state["constraint"].violations,
    }


def _run_pipeline(request: ParsedRequest) -> dict:
    """ParsedRequest → 최적화 결과 + 딥링크. CLI 전용 — clarify 질문이 오면
    터미널에서 바로 입력받아 이어갑니다(대화형, blocking).
    """
    from smartcart.orchestrator.graph import resume as resume_graph
    from smartcart.orchestrator.graph import start

    result = start(request)
    while result["interrupt"] is not None:
        print("\n" + result["interrupt"]["question"])
        answer = input("> ").strip()
        result = resume_graph(result["thread_id"], answer)

    return _state_to_result(result["state"])


def main() -> None:
    parser = argparse.ArgumentParser(description="SmartCart Agent — Phase 1 CLI")
    parser.add_argument("--input", "-i", help="자연어 장보기 요청")
    parser.add_argument("--mock-parse", action="store_true", help="LLM 파서 없이 고정 요청으로 테스트")
    args = parser.parse_args()

    if not args.input and not args.mock_parse:
        parser.error("--input 또는 --mock-parse 중 하나를 지정하세요")

    # 1. 파싱
    if args.mock_parse:
        request = _mock_request()
        print("[mock-parse] LLM 파서 생략 — 고정 ParsedRequest 사용\n")
    else:
        from smartcart.parser.agent import parse
        print("파싱 중...", flush=True)
        request = parse(args.input)
        print(f"파싱 완료: {len(request.items)}개 품목\n")

    print(json.dumps(request.model_dump(), ensure_ascii=False, indent=2), "\n")

    # 2. 오케스트레이터 실행 (search → optimize → reflect → route)
    print("최적화 중...", flush=True)
    result = _run_pipeline(request)

    pack        = result["pack"]
    deep_links  = result["deep_links"]
    best_effort = result["best_effort"]

    # 3. 결과 출력
    sat_label = "충족" if not best_effort else f"미충족 (best_effort, 재계획 {result['replan_count']}회)"
    delivery_label = "충족" if pack.delivery.satisfied else "미충족"

    print("=" * 60)
    print(f"총액:  {pack.total_price:,}원  (예산 {pack.budget.amount:,}원 {pack.budget.type})")
    print(f"예산:  {sat_label}")
    print(f"배송:  {pack.delivery.date}  {delivery_label}")
    if best_effort and result["violations"]:
        for v in result["violations"]:
            print(f"  ⚠  {v.detail}")
    print("=" * 60)
    print()

    for item in deep_links:
        print(f"[{item['mall']}] {item['item']} — {item['product']}")
        print(f"  {item['price']:,}원 | ★{item['rating']} ({item['review_count']:,}리뷰) | 배송 {item['delivery_date']}")
        print(f"  {item['url']}")
        print()


# ── FastAPI (Step 6, Step 10에서 clarify 지원 추가) ─────────────────────────

class ChatRequest(BaseModel):
    message: str


class ResumeRequest(BaseModel):
    thread_id: str
    answer: str


class ChatResponse(BaseModel):
    thread_id: Optional[str] = None
    needs_clarification: bool = False
    question: Optional[str] = None
    pack: Optional[OptimizationPack] = None
    deep_links: Optional[list[dict]] = None
    best_effort: Optional[bool] = None
    replan_count: Optional[int] = None


app = FastAPI(title="SmartCart Agent")


def _graph_result_to_response(thread_id: str, graph_result: dict) -> ChatResponse:
    if graph_result["interrupt"] is not None:
        return ChatResponse(
            thread_id=thread_id,
            needs_clarification=True,
            question=graph_result["interrupt"]["question"],
        )
    result = _state_to_result(graph_result["state"])
    return ChatResponse(
        thread_id=thread_id,
        pack=result["pack"],
        deep_links=result["deep_links"],
        best_effort=result["best_effort"],
        replan_count=result["replan_count"],
    )


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    from smartcart.orchestrator.graph import start
    from smartcart.parser.agent import parse

    request = parse(req.message)
    graph_result = start(request)
    return _graph_result_to_response(graph_result["thread_id"], graph_result)


@app.post("/chat/resume", response_model=ChatResponse)
def chat_resume(req: ResumeRequest) -> ChatResponse:
    from smartcart.orchestrator.graph import resume as resume_graph

    graph_result = resume_graph(req.thread_id, req.answer)
    return _graph_result_to_response(req.thread_id, graph_result)


if __name__ == "__main__":
    main()
