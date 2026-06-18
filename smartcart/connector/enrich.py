"""검색 결과 제목에서 구조화된 상품 속성을 추출 (LLM 기반).

검색 API가 구조화된 필드(volume_ml 등)를 주지 않을 때, 제목 문자열에서
추출합니다. 용량 같은 물리적 사실은 LLM이 지어낼 위험이 있으므로, 추출한
값이 실제로 제목에 표기돼 있는지(grounding) 검증된 경우에만 채택하고,
그렇지 않으면 추측 없이 None으로 둡니다.
"""
from __future__ import annotations

import re

from pydantic import BaseModel

from smartcart.models import Product

_VOLUME_PATTERN = re.compile(r"(\d+(?:[.,]\d+)?)\s*(ml|mL|ML|L|l|리터|밀리리터)")


def _grounded_volume_candidates_ml(title: str) -> set[int]:
    """제목에 실제로 적힌 용량 표기를 ml 단위로 변환해 후보 집합으로 반환."""
    candidates: set[int] = set()
    for num, unit in _VOLUME_PATTERN.findall(title):
        value = float(num.replace(",", ""))
        candidates.add(round(value * 1000) if unit.lower() in ("l", "리터") else round(value))
    return candidates


class _VolumeExtraction(BaseModel):
    index: int
    volume_ml: int | None = None


class _VolumeExtractionBatch(BaseModel):
    results: list[_VolumeExtraction]


def enrich_volume_ml(products: list[Product]) -> list[Product]:
    """volume_ml이 비어있는 상품의 제목에서 용량을 추출해 채웁니다 (in-place).

    한 번의 LLM 호출로 전체 목록을 일괄 처리합니다(상품당 호출 X).
    """
    targets = [(i, p) for i, p in enumerate(products) if p.volume_ml is None]
    if not targets:
        return products

    from core.llm import make_llm
    from langchain_core.messages import HumanMessage, SystemMessage

    listing = "\n".join(f"{i}: {p.name}" for i, p in targets)
    llm = make_llm(structured_output=_VolumeExtractionBatch)
    result: _VolumeExtractionBatch = llm.invoke([
        SystemMessage(content=(
            "상품명에서 용량(ml 단위)을 추출하세요. 묶음 상품이면 묶음 전체가 아니라 "
            "낱개 1개의 용량을 추출하세요. 용량 표기가 없거나 불명확하면 "
            "volume_ml을 null로 두세요."
        )),
        HumanMessage(content=listing),
    ])

    extracted = {r.index: r.volume_ml for r in result.results}
    for i, p in targets:
        value = extracted.get(i)
        if value is not None and value in _grounded_volume_candidates_ml(p.name):
            p.volume_ml = value

    return products
