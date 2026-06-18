# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

Tradeoff: These guidelines bias toward caution over speed. For trivial tasks, use judgment.

1. Think Before Coding
Don't assume. Don't hide confusion. Surface tradeoffs.

Before implementing:

State your assumptions explicitly. If uncertain, ask.
If multiple interpretations exist, present them - don't pick silently.
If a simpler approach exists, say so. Push back when warranted.
If something is unclear, stop. Name what's confusing. Ask.
2. Simplicity First
Minimum code that solves the problem. Nothing speculative.

No features beyond what was asked.
No abstractions for single-use code.
No "flexibility" or "configurability" that wasn't requested.
No error handling for impossible scenarios.
If you write 200 lines and it could be 50, rewrite it.
Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

3. Surgical Changes
Touch only what you must. Clean up only your own mess.

When editing existing code:

Don't "improve" adjacent code, comments, or formatting.
Don't refactor things that aren't broken.
Match existing style, even if you'd do it differently.
If you notice unrelated dead code, mention it - don't delete it.
When your changes create orphans:

Remove imports/variables/functions that YOUR changes made unused.
Don't remove pre-existing dead code unless asked.
The test: Every changed line should trace directly to the user's request.

4. Goal-Driven Execution
Define success criteria. Loop until verified.

Transform tasks into verifiable goals:

"Add validation" → "Write tests for invalid inputs, then make them pass"
"Fix the bug" → "Write a test that reproduces it, then make it pass"
"Refactor X" → "Ensure tests pass before and after"
For multi-step tasks, state a brief plan:

1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

These guidelines are working if: fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.


---

## 프로젝트 개요

SmartCart Agent는 자연어 장보기 요청(예: "사과, 배, 우유 2L 이상 1개, 식빵 2개,
어린이 요구르트 찾아줘. 구매평이나 구매가 많은 곳으로 우선적으로 찾고, 예산은
4만원 정도, 집으로 내일 받아봤으면 좋겠어.")을 분석해 여러 이커머스에서 최적의
장바구니 조합을 찾아주는 Agentic AI입니다.

- **Phase 1 (현재 목표)**: 품목별 추천 상품 + **구매 링크(딥링크)** 제공까지.
  사용자가 링크를 클릭해 직접 결제.
- **Phase 2 (향후)**: 사용자 승인을 받아 장바구니 담기~결제까지 자동 수행.

전체 아키텍처, 데이터 모델, 모듈별 책임은 [README.md](./README.md)를 단일 진실
공급원(source of truth)으로 삼습니다. 아키텍처를 변경하는 작업을 할 때는
README.md의 다이어그램/테이블도 함께 업데이트하세요.

## 다이어그램 (docs/diagrams/)

README의 아키텍처 다이어그램은 PNG 이미지로 임베드되어 있고(모든 마크다운
뷰어에서 보이도록), mermaid 소스는 각 이미지 아래 `<details>` 안과
`docs/diagrams/src/*.mmd`에 동일하게 보관됩니다. 다이어그램을 수정할 때는:

1. README의 `<details>` 안 mermaid 코드와 `docs/diagrams/src/*.mmd` 파일을 동일하게 수정
2. 아래 명령으로 PNG 재생성:
   ```bash
   npx -y @mermaid-js/mermaid-cli -i docs/diagrams/src/<name>.mmd -o docs/diagrams/<name>.png -b white -s 2
   ```
3. mermaid 문법 검증도 위 명령으로 함께 됩니다 (에러가 나면 PNG가 생성되지 않음).
   특히 sequenceDiagram에서 `participant` 별칭이 `opt`/`alt`/`loop`/`par` 등 예약어와
   대소문자 무관하게 충돌하지 않도록 주의하세요 (예: `Opt`는 `opt`와 충돌).

## 현재 상태

이 저장소는 **설계/기획 단계**입니다. 아직 애플리케이션 코드, 빌드/테스트
스크립트가 없습니다. 코드를 추가할 때는:

- README.md 3절(시스템 아키텍처)의 모듈 구성을 기준으로 디렉터리를 구성하세요
  (예: `parser/`, `orchestrator/`, `search/`, `optimizer/`, `reflection/`,
  `router/`, `purchase/` 등).
- 새 기술 스택을 도입하면 README 5절(기술 스택)에도 반영하세요.
- 로드맵(README 6절)의 단계를 참고해 Phase 1 범위를 벗어나는 자동 구매 관련
  코드(Phase 2)는 명시적으로 요청받지 않으면 구현하지 마세요.

## MCP 서버 설계/개발 가이드

쇼핑몰 커넥터 등 MCP Server/Tool을 설계·구현하기 전에:

- 먼저 `/home/ace19/dl-repo/agentic-ai-common-tools` (특히 `core/base_mcp.py`의
  `BaseMCP`/`MCPResult` 공통 인터페이스와 `mcp/`, `mcp/backends/` 하위의
  memory/logging/http/auth/retrieval 등 기존 구현)를 먼저 살펴보세요.
- 필요한 기능을 이미 제공한다면 그대로 가져와 재사용하고, 기능이 부족하면
  새로 만들지 말고 해당 저장소의 코드를 개선/확장하세요.
- SmartCart 전용 로직(쇼핑몰별 `search_products`/`add_to_cart`/`place_order`
  등)은 이 저장소(SmartCart_Agent)에 구현하고, agentic-ai-common-tools는
  공통 인프라(BaseMCP 패턴, Memory/Logging/HTTP/Auth backend 등)를 참조·재사용하는
  용도로만 사용하세요.

## 연동 제외 쇼핑몰

- **쿠팡(Coupang)은 연동 대상에서 제외합니다.** MCP 커넥터, 검색 결과, 예시
  데이터, 다이어그램 등 어디에도 쿠팡을 신규로 추가하지 마세요. 기존에 남아있는
  쿠팡 관련 예시/다이어그램은 발견 시 다른 쇼핑몰(이마트몰, 마켓컬리, 네이버
  쇼핑 등)로 대체하는 것을 권장합니다.

## 핵심 도메인 개념 (코드 작성 시 일관되게 사용)

- `ranking_priority`: 정렬 우선순위 배열. `popularity`(리뷰 수/판매량/베스트
  순위) > `rating` > `price` 순으로 사용. "구매평이나 구매가 많은 곳" 같은
  요청은 `popularity`를 1순위로 파싱.
  - 이 우선순위는 **초기 검색/최적화 단계의 정렬 기준**이며, 재계획
    (Reflection에서 예산/배송 제약 미충족 시) 단계에서 어떤 조건을 조정할지
    (용량/수량 변경, 브랜드 전환, 다른 쇼핑몰 재검색 등)는 고정된 규칙으로
    정해두지 않습니다. **재계획은 LLM이 혼자 조용히 결정/적용하지 않고, 매
    라운드 사용자에게 선택지를 제시(HITL)한 뒤 사용자가 고른 대로 적용합니다**
    — 숫자가 검증 가능한 경우(예: 용량×수량)는 코드가 결정론적으로 옵션을
    계산하고, 예산/배송일/제외몰처럼 판단이 필요한 경우는 LLM이 옵션을
    제안하되 최종 적용은 항상 사용자의 선택을 따릅니다.
- `max_replan_attempts`: 재계획 **질문 라운드**의 최대 횟수(기본값 3) — 매
  라운드 사용자에게 묻고, 응답에 따라 재검색 후 다시 검증하는 과정을 반복하는
  한도입니다. 한도에 도달해도(또는 사용자가 "지금까지 결과로 진행"을
  선택하면) 그 시점까지 찾은 최선의 조합을 `best_effort` 결과로 제시하고
  충족하지 못한 제약을 사유와 함께 명시합니다. 무한 루프 및 무한 질문을
  방지하기 위한 안전장치이므로 구현 시 반드시 적용하세요.
- `budget.type`: `"soft"`(정도/약 — 허용오차 기본 ±10%) vs `"hard"`(이하/이내).
- `delivery`: `date`(YYYY-MM-DD), `time`(nullable), `address` 단위로 표현.
  시간이 명시되지 않으면 `time: null`로 두고 날짜 단위로만 검증.
- 각 장바구니 항목은 `mall`, `product`, `price`, `rating`, `review_count`,
  `delivery_date`, `url`을 포함.

## Phase 2 (자동 구매) 작업 시 안전 원칙

Phase 2 관련 코드(결제 자동화, 자격증명 처리 등)를 작성/수정할 때는 반드시:

- 결제를 실제로 트리거하는 코드는 **항상 사용자의 명시적 승인(HITL) 단계** 뒤에
  와야 합니다. 승인 없이 결제가 진행되는 경로를 만들지 마세요.
- 쇼핑몰 자격증명/결제수단은 평문으로 저장하거나 로그에 남기지 마세요. 항상
  Secrets Vault 추상화를 통해서만 조회하도록 작성하세요.
- 모든 주문 시도/결과는 Audit Log에 기록되도록 설계하세요 (실패 포함).
- 실제 결제 API/계정에 연결되는 통합 테스트는 만들지 말고, mock/sandbox를
  사용하세요.

## 언어/문서 컨벤션

- README 및 설계 문서는 한국어로 작성합니다.
- 코드 식별자(변수/함수/클래스명)는 영문, 주석은 필요한 경우에만 한국어로
  작성합니다.
- Mermaid 다이어그램(flowchart, sequenceDiagram)은 README의 기존 스타일을
  따릅니다.
