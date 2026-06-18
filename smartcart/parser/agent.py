"""Parser Agent: 자연어 장보기 요청 → ParsedRequest."""
from __future__ import annotations

import argparse
import json
from datetime import date, timedelta

from langchain_core.messages import HumanMessage, SystemMessage

from core.llm import make_llm
from smartcart.models import ParsedRequest

_SYSTEM_PROMPT = """당신은 자연어 장보기 요청을 구조화된 JSON으로 변환하는 파서입니다.
오늘 날짜: {today}

파싱 규칙:
- items: 각 품목의 이름(name), 수량(qty), 단위(unit), 카테고리(category), 용량 조건(min_volume) 추출
  • 수량 미명시 → qty: 1
  • "2L 이상", "500ml 이상" → min_volume: "2L" / "500ml"
  • category: 과일, 채소, 유제품, 베이커리, 음료, 육류, 간식 등
- ranking_priority: 정렬 기준 배열 (순서가 곧 우선순위)
  • "구매평/구매 많은", "베스트", "많이 팔리는" → ["popularity", "rating", "price"]
  • "평점 높은", "좋은" → ["rating", "popularity", "price"]
  • "저렴한", "싼" → ["price", "popularity", "rating"]
  • 기본값: ["popularity", "rating", "price"]
- budget.type: "정도/약/쯤" → soft, tolerance_pct: 10 / "이하/이내/까지" → hard, tolerance_pct: 0
- delivery.date: 상대 날짜를 절대 날짜(YYYY-MM-DD)로 변환
  • "내일" → {tomorrow} / "모레" → {day_after} / 미명시 → {today}
- delivery.address: "집/home" → "home" / 미명시 → null
- clarification_needed: 모호하거나 확인이 필요한 항목의 질문 목록. 없으면 빈 리스트.
"""


def parse(user_input: str) -> ParsedRequest:
    today = date.today()
    system = _SYSTEM_PROMPT.format(
        today=today.isoformat(),
        tomorrow=(today + timedelta(days=1)).isoformat(),
        day_after=(today + timedelta(days=2)).isoformat(),
    )
    llm = make_llm(structured_output=ParsedRequest)
    return llm.invoke([
        SystemMessage(content=system),
        HumanMessage(content=user_input),
    ])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="자연어 장보기 요청")
    args = ap.parse_args()

    result = parse(args.input)
    print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
