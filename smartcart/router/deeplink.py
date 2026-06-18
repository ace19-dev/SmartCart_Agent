"""쇼핑몰별 딥링크(상품 URL) 생성."""
from __future__ import annotations

_URL_PATTERNS: dict[str, str] = {
    "gs_fresh": "https://www.gsfresh.com/product/detail/{product_id}",
    "emart":    "https://emart.ssg.com/item/itemView.ssg?itemId={product_id}",
    "kurly":    "https://www.kurly.com/goods/{product_id}",
    "naver":    "{product_id}",  # 네이버쇼핑 검색 API가 완전한 상품 URL을 반환 → product_id에 그대로 저장됨
}


def build_deep_link(mall: str, product_id: str) -> str:
    """mall ID와 product_id로 쇼핑몰 상품 페이지 URL을 생성합니다."""
    pattern = _URL_PATTERNS.get(mall)
    if not pattern:
        raise ValueError(f"지원하지 않는 쇼핑몰: {mall!r}. 지원 목록: {list(_URL_PATTERNS)}")
    return pattern.format(product_id=product_id)
