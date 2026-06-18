# SmartCart Agent — 구현 플랜 (Phase 1)

> **목표**: 자연어 장보기 요청 → 품목별 추천 상품 + 딥링크 제공  
> **전제**: Mock 어댑터로 전체 파이프라인 먼저 검증 → 실 API 연동  
> **진입점**: CLI (터미널) → 완성 후 FastAPI 확장  
> **공통 도구 참조**: `smartcart.config` import 시 `sys.path`에 자동 추가 → `core`, `mcp` 등을 로컬 모듈처럼 직접 사용

---

## 디렉터리 구조 (목표)

```
smartcart/
├── config.py              # 환경변수 (.env 기반)
├── models.py              # 공통 Pydantic 모델 (Product, ParsedRequest, OptimizationPack 등)
├── connector/
│   ├── server.py          # 단일 MCP 서버 (몰별 어댑터 등록/라우팅)
│   └── malls/
│       ├── base.py        # MallAdapter ABC (search_products, get_product_detail)
│       ├── mock.py        # Mock 어댑터 (더미 데이터, PoC용)
│       └── gsfresh.py     # GS프레시몰 어댑터 (Step 2 이후 실구현)
├── parser/
│   └── agent.py           # LLM Parser Agent (자연어 → ParsedRequest)
├── optimizer/
│   └── engine.py          # optimize_cart() — 조합 최적화 (결정론적)
├── reflection/
│   └── checker.py         # check_constraints() — 예산/배송 제약 검증
├── router/
│   └── deeplink.py        # build_deep_link() — 쇼핑몰별 URL 생성
├── orchestrator/
│   └── graph.py           # LangGraph ReAct 루프 (전체 파이프라인 연결)
└── main.py                # CLI 진입점
```

**모듈 분류** (README 3.3 기준)

| 모듈 | 분류 | 이유 |
|---|---|---|
| `parser/` | 🟢 Agent | 자연어 해석, 모호성 판단 → LLM 필요 |
| `orchestrator/` | 🟢 Agent | 재계획 여부 판단 → LLM 필요 |
| `connector/` | 🔧 Tool | 표준 MCP Tool로 노출된 외부 연동 |
| `optimizer/` | 🔧 Tool | 조합 최적화 계산 — 결정론적 함수 |
| `reflection/` | 🔧 Tool | 제약조건 수식 검증 — 결정론적 함수 |
| `router/` | 🔧 Tool | URL 스킴 매핑 — 결정론적 함수 |

> Optimizer/Reflection/Router를 LLM 에이전트로 만들면 비용·지연·비결정성이 늘어납니다.
> 입출력이 정해진 계산/매핑은 Tool로 유지하고 Orchestrator가 호출하는 구조를 사용합니다.

---

## Step 1 — 프로젝트 뼈대 + 패키지 설정 ✅

**구현 완료**

생성된 파일:
```
smartcart/
├── __init__.py
├── config.py              ← .env 로드 + agentic-ai-common-tools sys.path 추가
├── connector/
│   ├── __init__.py
│   └── malls/
│       └── __init__.py
├── parser/
│   └── __init__.py
├── optimizer/
│   └── __init__.py
├── reflection/
│   └── __init__.py
├── router/
│   └── __init__.py
└── orchestrator/
    └── __init__.py
.env.example
```

**agentic-ai-common-tools 참조 방식**: pip install 없이 `config.py`에서 `sys.path.insert`로 직접 참조.
- 기본 경로: 이 저장소와 형제 디렉터리 (`../agentic-ai-common-tools`)
- 재정의: `.env`에 `COMMON_TOOLS_DIR=/path/to/...` 설정

**verify** ✅
```bash
# Demo_SmartCart_Agent/ 루트에서 실행
python -c "import smartcart.config; from core.base_mcp import BaseMCP; print('ok')"
```

---

## Step 2 — 쇼핑몰 커넥터 MCP 서버 + Mock 어댑터 ✅

**구현 완료**

생성된 파일:
- `smartcart/models.py` — `Product` Pydantic 모델 (Step 3에서 ParsedRequest 등 추가 예정)
- `smartcart/connector/malls/base.py` — `MallAdapter` ABC + `SearchFilters`
- `smartcart/connector/malls/mock.py` — `MockMallAdapter` (GS프레시·이마트·컬리 더미 데이터)
- `smartcart/connector/server.py` — `MallConnectorMCP` (`BaseMCP` 상속)

주요 설계 결정:
- `MallConnectorMCP.search_products(query, mall_ids, filters)` — 지정 몰 또는 전체 몰에 라우팅 후 결과 합산
- `ranking_priority` 정렬을 `MockMallAdapter`에서 처리 (`popularity`→리뷰수, `rating`→평점, `price`→가격)
- `min_volume_ml` 필터로 "우유 2L 이상" 같은 용량 조건 처리
- `smartcart/__init__.py`에서 `config`를 import → 모든 하위 모듈에서 자동으로 sys.path 세팅

**verify** ✅
```bash
python -m smartcart.connector.server --test
# health_check + 사과/우유(2L 필터)/요구르트 검색 결과 출력 확인
```

---

## Step 3 — Parser Agent ✅

**구현 완료**

생성/수정된 파일:
- `smartcart/models.py` — `Item`, `Budget`, `Delivery`, `Preferences`, `ParsedRequest` 추가 (README 4.1 구조)
  - `Item.min_volume_ml` property: `"2L"` → `2000` 변환 (SearchFilters 연동용)
  - `ParsedRequest.clarification_needed`: 모호한 항목 명확화 질문 목록
- `smartcart/parser/agent.py` — `parse(user_input) -> ParsedRequest`
  - `make_llm(structured_output=ParsedRequest)` 로 구조화 출력
  - 시스템 프롬프트에 오늘 날짜 주입 → "내일" 등 상대 날짜를 절대 날짜로 변환
- `smartcart/config.py` — `LLM_PROVIDER=local` (기본값), `os.environ`에 명시 반영
  - `LOCAL_LLM_MODEL=qwen3:30b-a3b-q4_K_M`

**verify** ✅
```bash
# ollama serve 가 실행 중이어야 함
python -m smartcart.parser.agent \
  --input "사과, 배, 우유 2L 이상 1개, 식빵 2개, 어린이 요구르트 찾아줘. 구매평이나 구매가 많은 곳으로 우선적으로 찾고, 예산은 4만원 정도, 집으로 내일 받아봤으면 좋겠어."
# → ParsedRequest JSON 출력 확인 (ranking_priority, budget.type=soft, delivery.date=내일 절대날짜)
```

---

## Step 4 — Optimizer + Reflection + Router (결정론적 도구 3종) ✅

**구현 완료**

생성/수정된 파일:
- `smartcart/models.py` — `CartItem`, `Substitution`, `Alternative`, `DeliveryStatus`, `OptimizationPack`, `ConstraintViolation`, `ConstraintResult` 추가
- `smartcart/optimizer/engine.py` — `optimize_cart(candidates, request) -> OptimizationPack`
  - 품목별 후보에서 `min_volume_ml` 필터 → 배송일 필터 → `ranking_priority` 정렬 후 최선 상품 선택
  - `qty > 1`이면 `price = best.price * qty`, item label에 `x{qty}` suffix
  - `mall_id` 내부 키 + `mall` 표시명(`GS프레시몰`, `이마트`, `마켓컬리`, `네이버쇼핑`) 분리
  - `--test` CLI: Mock MCP → `optimize_cart` → `check_constraints` → 딥링크 출력
- `smartcart/reflection/checker.py` — `check_constraints(pack, request) -> ConstraintResult`
  - 예산: `hard` → `total <= amount`, `soft` → `total <= amount * (1 + tolerance_pct / 100)`
  - 배송: 각 CartItem의 `delivery_date <= request.delivery.date` (ISO 문자열 비교, time=null이면 날짜 단위)
  - 위반 시 `reason` 코드(`budget_exceeded` / `delivery_unavailable`) + 한국어 `detail` 포함
- `smartcart/router/deeplink.py` — `build_deep_link(mall, product_id) -> str`
  - `gs_fresh`, `emart`, `kurly`, `naver` 4개 쇼핑몰 URL 패턴

**verify** ✅
```bash
python -m smartcart.optimizer.engine --test
# 결과: 총액 36,700원 (예산 40,000 soft 충족), 배송 2026-06-17 충족
# 딥링크: https://www.kurly.com/goods/ku-apple-001 등 5개 출력
```

---

## Step 5 — Orchestrator (LangGraph 파이프라인) ✅

**구현 완료**

생성된 파일:
- `smartcart/orchestrator/graph.py` — LangGraph 상태 그래프
  - **SmartCartState** (TypedDict): `request`, `search_filters`, `excluded_malls`, `candidates`, `pack`, `constraint`, `replan_count`, `best_effort`, `deep_links`
  - **ReplanInstruction** (Pydantic): LLM 재계획 결정 (`item_max_prices`, `excluded_malls`, `ranking_priority`, `notes`)
  - **노드**: `search` → `optimize` → `reflect` → [조건부] `route` or `replan` → `search` (loop)
  - **조건부 엣지** (`_after_reflect`): `constraint.satisfied` → `route`, `replan_count >= MAX_REPLAN_ATTEMPTS` → `route` (best_effort), 그 외 → `replan`
  - `replan_node`: LLM(`make_llm(structured_output=ReplanInstruction)`)으로 위반 분석 → `search_filters` / `excluded_malls` 업데이트
  - `build_graph()` / `run(request) → SmartCartState` 공개 API
- `smartcart/main.py` — CLI 진입점
  - `--input "자연어 요청"`: LLM 파서 → 오케스트레이터 → 결과 출력
  - `--mock-parse`: LLM 없이 고정 ParsedRequest로 그래프만 테스트
- `smartcart/models.py` 수정:
  - `Preferences.organic_preferred` — `@field_validator(mode="before")`로 `None` → `False` 자동 변환
  - `ParsedRequest.preferences` — 기본값 `Preferences()` 추가 (LLM이 필드 생략 시 안전)

```
Parser → Orchestrator
              │
         ┌────▼─────┐
         │  search  │ ← MallConnectorMCP (MCP Tool)
         └────┬─────┘
         ┌────▼─────┐
         │ optimize │ ← optimize_cart()
         └────┬─────┘
         ┌────▼─────┐
         │ reflect  │ ← check_constraints()
         └────┬─────┘
    충족 ─────┤───── 미충족 & 한도 미도달
              │                │
         ┌────▼─────┐    재계획 (replan_node LLM → search 루프)
         │  route   │ ← build_deep_link()
         └──────────┘
```

**verify** ✅
```bash
# LLM 파서 포함 전체 end-to-end (Phase 1 완성)
python -m smartcart.main \
  --input "사과, 배, 우유 2L 이상 1개, 식빵 2개, 어린이 요구르트 찾아줘. 구매평이나 구매가 많은 곳으로 우선적으로 찾고, 예산은 4만원 정도, 집으로 내일 받아봤으면 좋겠어."
# → 총액 36,700원 (예산 40,000원 soft 충족), 배송 2026-06-18 충족
# → 5개 품목 딥링크 출력 (마켓컬리 기준, popularity 우선 정렬)

# LLM 없이 그래프만 테스트
python -m smartcart.main --mock-parse
```

---

## Step 6 — CLI → FastAPI 확장 ✅

**구현 완료**

수정된 파일:
- `smartcart/main.py`
  - `_run_pipeline(request) -> dict`: 오케스트레이터 실행 + 결과 추출(`pack`, `deep_links`,
    `best_effort`, `replan_count`, `violations`)을 CLI/FastAPI 공용 함수로 분리
  - `app = FastAPI(...)` + `POST /chat`
    - 요청: `ChatRequest { message: str }`
    - 처리: `parser.agent.parse(message)` → `_run_pipeline()`
    - 응답: `ChatResponse { pack: OptimizationPack, deep_links: list[dict], best_effort: bool, replan_count: int }`
  - 기존 CLI(`--input` / `--mock-parse`)는 `_run_pipeline()`을 재사용하도록만 리팩터링,
    동작 변경 없음

**verify** ✅
```bash
# 1. CLI 회귀 확인 — 기존과 동일하게 동작
python -m smartcart.main --mock-parse

# 2. FastAPI 서버 기동
uvicorn smartcart.main:app --reload

# 3. /chat 호출
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "사과, 배, 우유 2L 이상 1개, 식빵 2개, 어린이 요구르트 찾아줘. 구매평이나 구매가 많은 곳으로 우선적으로 찾고, 예산은 4만원 정도, 집으로 내일 받아봤으면 좋겠어."}'
# → HTTP 200, OptimizationPack(총액 36,700원, 예산/배송 충족) + deep_links 5건 JSON 응답 확인
```

---

## Step 7 — 쇼핑몰 커넥터 실 API 연동: 네이버쇼핑 ✅

**목표**: Mock 어댑터(GS프레시몰/이마트/마켓컬리/네이버쇼핑)를 실 API 연동으로
교체하기 위해, 각 몰이 외부 개발자에게 공개 API를 제공하는지 조사.

### 조사 결과

| 몰 | 공개 API | 비고 |
|---|---|---|
| **네이버쇼핑** | ✅ 있음 | 일반 가입만으로 Client ID/Secret 발급, 사업 제휴 불필요 |
| 이마트(SSG.COM) | ❌ 없음 | "쓱파트너스" API는 **입점 셀러가 자기 상품을 등록/관리**하는 용도. 제3자가 전체 카탈로그를 검색하는 buyer-side API 아님 |
| 마켓컬리 | ❌ 없음 | 개발자 포털/오픈 API 자체가 없음. 네이버와의 "컬리N마트"는 양사 간 단독 B2B 제휴라 일반 개발자는 접근 불가 |
| GS프레시몰 | ❌ 없음 | 공개 개발자 포털 없음 (G마켓 입점 셀러 코너로는 운영 중) |

→ **네이버쇼핑만 실 API로 교체**, 나머지 3개 몰은 Mock 어댑터를 유지하고
이후 (a) 브라우저 자동화/스크래핑 또는 (b) 각 사와의 정식 B2B 제휴 중 하나가
결정되면 별도 단계로 진행.

> 참고: README의 4개 몰엔 없지만 **11번가 Open API**는 비셀러 일반 개발자도
> 상품/카테고리 조회가 가능(구매 API는 셀러 전용). 그로서리 카테고리도 있어
> 향후 몰 확장 후보가 될 수 있음.

### 네이버쇼핑 검색 API 레퍼런스

- 엔드포인트: `GET https://openapi.naver.com/v1/search/shop.json`
- 인증: 헤더 `X-Naver-Client-Id`, `X-Naver-Client-Secret` (Naver Developers에서 발급)
- 호출 제한: **일 25,000회** (무료)

**요청 파라미터**

| 파라미터 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `query` | String | Y | 검색어 (UTF-8) |
| `display` | Integer | N | 결과 개수 (기본 10, 최대 100) |
| `start` | Integer | N | 시작 위치 (기본 1, 최대 1000) |
| `sort` | String | N | `sim`(정확도, 기본) \| `date` \| `asc`(가격↑) \| `dsc`(가격↓) |
| `filter` | String | N | `naverpay` — 네이버페이 연동 상품만 |
| `exclude` | String | N | `used`(중고)\|`rental`(렌탈)\|`cbshop`(해외직구) 콜론(`:`)으로 조합 제외 — 식료품 검색 품질에 유용 |

**응답 필드 (items 배열)**

| 필드 | 타입 | 설명 |
|---|---|---|
| `title` | String | 상품명 (검색어 일치 부분은 `<b>` 태그로 감싸짐 → 제거 필요) |
| `link` | String | 상품 URL (실제 구매 가능한 딥링크) |
| `image` | String | 썸네일 이미지 URL |
| `lprice` / `hprice` | Integer | 최저가 / 최고가 (정보 없으면 0) |
| `mallName` | String | 판매 쇼핑몰명 (정보 없으면 "네이버") |
| `productId` | Integer | 네이버쇼핑 상품 ID |
| `productType` | Integer | 가격비교 매칭 상태 코드 (1~12, 일반/중고/단종/판매예정 × 매칭 여부) |
| `maker` / `brand` | String | 제조사 / 브랜드 |
| `category1~4` | String | 카테고리 대~세분류 |

**❌ 제공되지 않는 필드** (현재 `Product` 모델이 요구하지만 API엔 없음):
- `rating`, `review_count` — 네이버쇼핑은 가격비교 플랫폼이라 리뷰/평점 데이터를
  주지 않음 (실제 판매처 페이지에만 존재)
- `delivery_date` — 배송 가능 여부/일자 정보 없음
- `volume_ml` (용량) — "우유 2L 이상" 같은 필터에 쓸 정보 없음

**설계 결정 (구현 시 적용)**
- `rating=0.0`, `review_count=0`으로 채움 → `ranking_priority`의
  `popularity`/`rating` 정렬에서 항상 후순위가 되어, 실제 평점이 있는 다른 몰이
  우선 선택됨 (네이버쇼핑은 가격 비교 차원의 보조 후보로만 기능)
- `volume_ml`은 `None` 유지 → optimizer가 용량 조건이 있을 때 자동 제외 (이미
  Step 4에서 구현된 "volume_ml이 None이면 제외" 로직 재사용, 신뢰할 수 없는
  정보를 추측해 채우지 않음)
- `delivery_date`는 요청된 배송 희망일을 그대로 가정(미확정) — Phase 1 범위는
  "딥링크 제공까지"이므로, 실제 배송 가능 여부는 사용자가 링크를 클릭해
  직접 확인
- `exclude=used:rental:cbshop`을 항상 적용해 중고/렌탈/해외직구 결과 제외

### 리뷰/평점 API 추가 조사 결과 — 존재하지 않음 ❌

네이버쇼핑 검색 API에 평점/리뷰수가 없어서, 다른 경로(네이버페이 리뷰 API,
커머스API, 쇼핑인사이트 API)로 리뷰 데이터를 가져올 수 있는지 추가로 확인:

| 후보 | 결과 |
|---|---|
| 네이버 커머스API(스마트스토어 셀러용) | ❌ 리뷰 조회 API 자체가 없음. 네이버 공식 기술지원 저장소(`commerce-api-naver/commerce-api`)에 "상품 리뷰조회 API 기능요청"이 미해결 상태로 올라와 있음(2024~ 현재) — 즉 네이버도 아직 안 만든 기능 |
| 네이버페이 "리뷰 연동" | ❌ 용도가 정반대. 이건 자사몰(메이크샵/카페24 등 입점 사이트)이 **자기 사이트에 네이버페이 구매평 위젯을 노출**하는 기능이라, 제3자가 리뷰 데이터를 읽어오는 API가 아님 |
| 쇼핑인사이트 API(데이터랩) | ❌ 카테고리별 클릭 추이·검색어 트렌드 통계용. 개별 상품 리뷰/평점과 무관 |

→ 평점/리뷰수를 공식 API로 보강할 방법은 현재 없음. `rating=0`/`review_count=0`
placeholder 설계를 그대로 유지.

### 가격비교 사이트는 왜 크롤링 없이 운영되는가 (다나와/에누리 추가 조사)

GS프레시몰/이마트/마켓컬리가 robots.txt로 크롤링을 막아도, 네이버쇼핑 같은
가격비교 사이트는 문제없이 그 몰들의 상품을 보여줍니다. 모순이 아니라 **데이터
유입 방향이 정반대**이기 때문입니다.

- robots.txt가 막는 건 "초청받지 않은" 외부 크롤러입니다.
- 가격비교 등록은 그 반대 방향입니다 — 쇼핑몰이 **자기 발로** 상품 피드(XML/API
  push)를 다나와·에누리·네이버쇼핑의 입점 시스템에 직접 등록합니다. 노출이
  늘면 매출이 늘기 때문에 입점몰에게 손해가 아니라 이득입니다.
- 따라서 GS프레시몰이 robots.txt로 일반 크롤러를 막으면서도, 동시에 네이버쇼핑에는
  자기 상품을 직접 피드로 등록해둘 수 있습니다 — 서로 다른 채널.
- 즉, **우리가 이미 쓰기로 한 네이버쇼핑 검색 API 자체가 이 가격비교
  데이터베이스**입니다. `mallName`에 마켓컬리/이마트몰/GS프레시몰이 실제로
  찍혀 나올 수 있어, 스크래핑 없이도 그 몰들의 상품(가격/링크만, 평점·리뷰는
  여전히 없음)이 검색 결과에 일부 섞여 들어올 수 있습니다.

**다른 비교 사이트(다나와/에누리)에 키워드 검색 API가 있는지도 확인**

| 사이트 | 결과 |
|---|---|
| 다나와 | Open API는 있으나 `prodCode`(다나와 자체 상품 코드)로 조회하는 구조. "이미 아는 다나와 상품의 가격 정보를 제휴사 사이트에 위젯으로 표시"하는 용도라, 네이버처럼 키워드로 검색하는 기능은 없음 → SmartCart의 자연어 품목 검색에는 부적합 |
| 에누리 | 같은 회사(커넥트웨이브)가 운영하지만 공개 개발자 문서/포털 자체를 찾지 못함 — 사실상 없음 |

→ 한국 가격비교 사이트 중 키워드 검색이 가능한 buyer-facing API는 네이버쇼핑이
거의 유일. 현재 `naver.py` 구현 방향이 맞고, 추가로 다른 비교 사이트를 더
연동할 필요는 없음.

**구현 완료**

생성/수정된 파일:
- `smartcart/connector/malls/naver.py` (신규) — `NaverShoppingAdapter`
  - `mcp.http.get_http_mcp()`(agentic-ai-common-tools 공용 HTTP 백엔드, 재시도/타임아웃
    내장)로 `GET /v1/search/shop.json` 호출
  - `exclude=used:rental:cbshop` 항상 적용, `max_body=20_000`으로 응답 잘림 방지
  - 제목의 `<b>` 강조 태그 제거 + HTML 엔티티 디코딩(`_clean_title`)
  - `Product.id`/`url`에 API가 반환한 실제 구매 링크(`link`)를 그대로 저장
  - `NAVER_CLIENT_ID`/`NAVER_CLIENT_SECRET` 미설정 시 생성자에서 `RuntimeError`
- `smartcart/router/deeplink.py` — `naver` URL 패턴을 `"{product_id}"`(그대로 통과)로
  변경. 네이버는 API가 이미 완전한 URL을 주므로, 다른 몰처럼 패턴으로 재조립할
  필요가 없고 오히려 잘못된 URL을 만들 위험이 있음(productId 네임스페이스가
  카탈로그/개별상품마다 달라 패턴 재구성이 불안정)
- `smartcart/connector/server.py` — `_build_default_server()`에서
  `NaverShoppingAdapter` 등록 시도. 키 미설정 시 경고 로그만 남기고 등록된
  어댑터 없이 동작 (graceful degradation). Mock 어댑터(`gs_fresh`/`emart`/`kurly`)는
  `include_mock=True`를 명시적으로 넘겨야 등록됨 — 기본값은 비활성 (Step 8 참고)
- `smartcart/config.py`, `.env.example` — `NAVER_CLIENT_ID`/`NAVER_CLIENT_SECRET` 추가

**verify** ✅
```bash
# 1. 키 미설정 시 — 경고 로그 후 Mock 3개 몰만으로 정상 동작 (회귀 없음)
python -m smartcart.connector.server --test

# 2. 어댑터 단위 로직 검증 (HTTP 응답을 모킹해 파싱/필터링 확인)
python -c "
import json
from unittest.mock import patch
import smartcart
from core.base_mcp import MCPResult
import smartcart.connector.malls.naver as naver_mod
from smartcart.connector.malls.base import SearchFilters

fake_body = json.dumps({'items': [
    {'title': '<b>사과</b> 1kg', 'link': 'https://www.kurly.com/goods/123', 'image': 'http://img',
     'lprice': '7500', 'hprice': '0', 'mallName': '마켓컬리', 'productId': '123', 'productType': '2'},
    {'title': '<b>사과</b> 무농약', 'link': 'https://emart.ssg.com/x', 'image': '',
     'lprice': '12000', 'hprice': '0', 'mallName': '이마트몰', 'productId': '456', 'productType': '1'},
]})
fake_result = MCPResult.ok(data={'status_code': 200, 'body': fake_body, 'ok': True, 'headers': {}})

with patch.object(naver_mod, 'NAVER_CLIENT_ID', 'fake'), patch.object(naver_mod, 'NAVER_CLIENT_SECRET', 'fake'):
    adapter = naver_mod.NaverShoppingAdapter()
    with patch.object(naver_mod, 'get_http_mcp') as mget:
        mget.return_value.get.return_value = fake_result
        for p in adapter.search_products('사과', SearchFilters(max_price=10000, delivery_date='2026-06-18')):
            print(p.model_dump())
"
# → 태그 제거된 '사과 1kg'만 출력 (12,000원 항목은 max_price=10000에 걸려 제외)

# 3. 실제 키 발급 후 — .env에 NAVER_CLIENT_ID/NAVER_CLIENT_SECRET 설정하면
#    python -m smartcart.main --input "..." 실행 시 네이버쇼핑 후보가 합류
```

**다음 작업 (보류)**: GS프레시몰/이마트/마켓컬리 실연동은 (a) 브라우저
자동화/스크래핑 또는 (b) 각 사와의 정식 B2B 제휴 중 하나가 결정되면 진행.
스크래핑 검토 시 참고:
- 마켓컬리: robots.txt가 일반 크롤링 허용(개인정보/주문/팝업 등만 제외)
- 이마트(SSG.COM): robots.txt가 지정된 검색엔진 봇 외 모든 봇(`User-agent: *`) 차단
- GS프레시몰: robots.txt 자체가 403 Forbidden — 강한 봇 차단 정책
- 네이버쇼핑 웹페이지 직접 스크래핑은 비권장: 동일 데이터를 공식 API로 이미
  제공하면서 웹페이지 쪽은 자동화 접근을 강하게 차단(자체 테스트에서 fetch
  자체가 차단됨) → API 우회로 ToS 위반 소지가 큼

---

## Step 8 — Mock 기본값 비활성화 + Reflection 누락 품목 탐지 버그 수정 ✅

### 정책 변경: Mock 어댑터는 기본 비활성화

요청 전까지 Mock 데이터를 쓰지 않기로 함. `smartcart/connector/server.py`의
`_build_default_server(include_mock: bool = False)` — 기본값을 `False`로 변경.

- `include_mock=False`(기본): 실 어댑터만 등록 (현재는 네이버쇼핑만). `gs_fresh`/
  `emart`/`kurly`는 실 API가 없어 등록된 어댑터 자체가 없는 상태가 됨 → 해당
  몰은 검색 결과가 항상 빈 리스트
- `include_mock=True`: Mock 어댑터(`gs_fresh`/`emart`/`kurly`)도 함께 등록
- `python -m smartcart.connector.server --test --mock`처럼 명시적으로 요청할 때만
  Mock 포함. 플래그 없이 `--test`만 실행하면 네이버 단독으로 동작
- 이 함수를 호출하는 모든 곳(`orchestrator/graph.py`의 `search_node`,
  `optimizer/engine.py --test` 데모)이 함께 영향을 받음 — 즉 `main.py --mock-parse`도
  이제 "LLM 파서만 생략"이라는 원래 의미와 별개로, 몰 검색은 기본적으로
  네이버 단독으로 동작하게 됨
- 예외: `smartcart/optimizer/engine.py`의 `__main__` 데모는 원래부터 "Mock MCP로
  전체 파이프라인 검증"이 목적이었으므로(Step 4), `_build_default_server(include_mock=True)`로
  명시적으로 고정 — 이 한 곳만 Mock을 항상 포함하도록 코드에 직접 박아둠

### 버그 발견 및 수정: 품목 누락이 제약 위반으로 탐지되지 않음

**증상**: `ranking_priority=["price"]`로 Mock 없이(네이버 단독) 테스트하던 중
발견. "우유 2L 이상" 조건에서, 네이버 API는 용량(`volume_ml`) 정보를 주지
않아 모든 네이버 우유 후보가 `volume_ml=None`이 되고, optimizer가 이미 구현된
규칙("용량 정보 없는 상품은 신뢰 못 해 제외")에 따라 우유 후보를 전부 제외 →
우유가 장바구니에서 통째로 빠짐.

**근본 원인**: `optimizer_cart()`는 이 상황을 `pack.delivery.satisfied=False`로
정확히 표시했지만, `reflection/checker.py`의 `check_constraints()`는 **장바구니에
이미 들어있는 품목들의 배송일만 비교**하고, "요청했지만 장바구니에 전혀 없는
품목"을 검사하는 로직이 없었음. 그 결과 우유가 빠진 장바구니를
`satisfied: true, violations: []`로 잘못 보고 → 재계획(replan)이 트리거되지
않고 불완전한 장바구니가 그대로 진행됨. `ConstraintViolation.reason`
docstring에는 이미 `"out_of_stock"`이 후보값으로 적혀 있었지만 실제로 쓰인 적
없던 미완성 구현이었음 (Mock 데이터는 모든 품목에 항상 후보가 있어 이 경로가
한 번도 실행되지 않았음).

**수정**: `smartcart/reflection/checker.py` — `check_constraints()` 맨 앞에
`request.items` 각각이 `pack.cart`에 실제로 존재하는지 확인하는 검증 추가.
없으면 `reason="out_of_stock"` 위반으로 등록.

```python
cart_labels = {c.item for c in pack.cart}
for item in request.items:
    label = item.name if item.qty <= 1 else f"{item.name} x{item.qty}"
    if label not in cart_labels:
        violations.append(ConstraintViolation(
            reason="out_of_stock",
            detail=f"{item.name}: 조건에 맞는 후보 상품을 찾지 못해 장바구니에서 제외됨",
        ))
```

**verify** ✅
```bash
# 1. 재현 + 수정 확인 — 우유 2L 필터가 네이버 단독 데이터에서 통과할 후보가 없어
#    out_of_stock 위반이 정확히 발생하는지 확인 (Mock 없이, ranking_priority=["price"])
python -c "
import smartcart, json
from datetime import date, timedelta
from smartcart.connector.malls.base import SearchFilters
from smartcart.connector.server import _build_default_server
from smartcart.models import Budget, Delivery, Item, ParsedRequest, Preferences, Product
from smartcart.optimizer.engine import optimize_cart
from smartcart.reflection.checker import check_constraints

tomorrow = (date.today() + timedelta(days=1)).isoformat()
request = ParsedRequest(
    items=[Item(name='사과'), Item(name='배'), Item(name='우유', min_volume='2L'),
           Item(name='식빵', qty=2), Item(name='어린이 요구르트')],
    ranking_priority=['price'], budget=Budget(amount=40000, type='soft'),
    delivery=Delivery(date=tomorrow), preferences=Preferences(),
)
server = _build_default_server()  # Mock 미포함 (기본값)
candidates = {i.name: [Product(**p) for p in json.loads(
    server.search_products(i.name, filters=SearchFilters(min_volume_ml=i.min_volume_ml)).to_tool_str()
)] for i in request.items}
pack = optimize_cart(candidates, request)
print(check_constraints(pack, request).model_dump())
"
# → {'satisfied': False, 'violations': [{'reason': 'out_of_stock', 'detail': '우유: ...'}]}

# 2. 회귀 확인 — 전 품목이 매칭되는 정상 케이스(Mock 명시 포함)에서 스푸리어스
#    violation 없이 satisfied=true가 나오는지 (Step 4 본래 결과와 동일해야 함)
python -m smartcart.optimizer.engine --test
# → ConstraintResult: satisfied=true, violations=[]; 딥링크 5건(마켓컬리) 출력
```

---

## Step 9 — 제목에서 용량 추출 (LLM 기반 enrich) + replan_node 안정성 수정 ✅

### 배경

네이버쇼핑 API는 `volume_ml`을 구조화된 필드로 안 주지만, 제목 텍스트에는
용량이 적혀있는 경우가 많음 (예: `"서울우유 멸균우유 200ml, 24개"`). 기존
코드는 이걸 시도하지 않고 바로 "정보 없음 → 제외" 처리해서, "우유 2L 이상"
같은 명시적 요청을 사용자에게 묻지도 않고 조용히 빼버리는 문제가 있었음.

용량만이 아니라 앞으로 다른 속성(예: 유기농 여부)도 같은 방식으로 추출할
수 있어야 해서, 정규식 대신 LLM 기반으로 결정. 단, 용량 같은 물리적 사실은
LLM이 지어내면 위험하므로 grounding(제목에 실제로 그 값이 있는지) 검증을
같이 둠.

**구현 완료**

생성/수정된 파일:
- `smartcart/connector/enrich.py` (신규) — `enrich_volume_ml(products) -> list[Product]`
  - `volume_ml`이 `None`인 상품만 모아 **1회 LLM 호출로 일괄 처리** (상품당 호출 X)
  - `core.llm.make_llm(structured_output=_VolumeExtractionBatch)`로 제목 목록 → `{index: volume_ml}` 추출
  - **grounding 검증**: 정규식(`_grounded_volume_candidates_ml`)으로 제목에 실제 적힌
    용량 표기를 ml로 환산한 후보 집합을 만들고, LLM이 추출한 값이 그 집합에 있을
    때만 채택. 없으면 추측하지 않고 `None` 유지
  - 묶음 상품(예: "1L, 12개")은 묶음 전체가 아니라 낱개 1개 용량을 추출하도록 프롬프트에 명시
- `smartcart/models.py` — `Item.requires_volume_info` property 추가
  (`min_volume_ml is not None`). 호출부는 이 property만 보고, 나중에 `max_volume` 같은
  조건이 추가돼도 이 property만 수정하면 됨 (호출부 변경 불필요)
- `smartcart/orchestrator/graph.py`의 `search_node` — 품목이
  `requires_volume_info`이면 후보 목록에 `enrich_volume_ml()` 적용

**검증 중 발견한 버그 (별개): `replan_node`가 로컬 LLM 응답에서 크래시**

이 기능을 테스트하다가 `replan_node`(로컬 qwen3 모델)가
`pydantic_core.ValidationError`로 죽는 걸 발견함:
```
ranking_priority
  Input should be a valid list [type=list_type, input_value={'우유': [...]}, ...]
```
**원인**: 프롬프트에 넘기는 "현재 검색 필터" JSON이 품목마다
`{"우유": {"ranking_priority": [...], ...}, "사과": {...}}` 형태로 `ranking_priority`
키를 반복해서 갖고 있는데, `ReplanInstruction` 스키마의 최상위 `ranking_priority`
필드명과 이름이 같아서, 작은 로컬 모델이 입력 구조를 그대로 흉내내 품목별
중첩 dict로 출력해버림 (Claude 같은 대형 모델은 이 문제가 안 보였을 가능성이 높고,
로컬 모델 사용 중 처음 드러남).

**수정**: `smartcart/orchestrator/graph.py`의 `replan_node`
- 시스템 프롬프트에 `ranking_priority`가 품목별이 아니라 전체에 적용되는
  평평한(flat) 리스트라는 것을 예시와 함께 명시
- `ValidationError` 발생 시 동일 메시지로 1회 재시도하는 안전망 추가

**verify** ✅
```bash
# 1. 용량 추출 단위 테스트 — 실제 네이버 우유 후보 제목에서 추출
python -c "
import smartcart, json
from smartcart.connector.malls.base import SearchFilters
from smartcart.connector.server import _build_default_server
from smartcart.models import Product
from smartcart.connector.enrich import enrich_volume_ml

server = _build_default_server()
products = [Product(**p) for p in json.loads(
    server.search_products('우유', filters=SearchFilters()).to_tool_str())]
enrich_volume_ml(products)
for p in products:
    print(p.name, '->', p.volume_ml)
"
# → "...1L, 12개" -> 1000, "...200ml, 24개" -> 200, 용량 표기 없는 "...48팩" -> None(추측 안 함)

# 2. 전체 파이프라인 회귀 (replan_node 크래시 재현 + 수정 확인, 2회 연속 실행)
python -m smartcart.main --mock-parse
python -m smartcart.main --mock-parse
# → 둘 다 크래시 없이 완료. 재계획 3회 모두 정상 수행, 우유는 여전히 2L 이상 후보를
#   못 찾아 best_effort로 종료(이건 버그가 아니라 실제로 네이버 검색 결과에
#   2L 이상 멸균우유가 없었던 것 — enrich가 용량을 정확히 읽어냈기 때문에
#   "모르니까 제외"가 아니라 "확인했는데 조건 미달"로 바뀐 것)

# 3. (추가 확인) display를 10→100으로 늘리고, 검색어도 "우유"/"흰우유"/
#    "우유 2L"/"흰우유 2L" 등으로 바꿔가며 2L 이상 매물이 정말 없는지 재확인
#    → "우유 2L", "흰우유 2L" 각각 100개 중 2L 이상 0개. 네이버쇼핑 상위
#    결과 안에는 2L 단일 용기 흰우유 매물 자체가 거의 없는 것으로 보임
#    (대형마트 자체 채널 카테고리라 추정) — 시스템 버그가 아니라 데이터
#    소스의 실제 한계로 결론

# 4. 회귀 확인 — Mock 명시 포함(이 데모만 예외) 정상 케이스
python -m smartcart.optimizer.engine --test
# → satisfied=true, violations=[]

# 5. 최종 end-to-end 재검증 — CLI와 FastAPI 둘 다 Mock 없이(네이버 단독) 재확인
python -m smartcart.main --input "사과, 배, 우유 2L 이상 1개, 식빵 2개, 어린이 요구르트 찾아줘. 구매평이나 구매가 많은 곳으로 우선적으로 찾고, 예산은 4만원 정도, 집으로 내일 받아봤으면 좋겠어."
# → CLI: 크래시 없이 완료. 4개 품목 실제 네이버 상품, 우유는 out_of_stock으로 정확히 보고

uvicorn smartcart.main:app --port 8124 &
curl -X POST http://127.0.0.1:8124/chat -H "Content-Type: application/json" \
  -d '{"message": "위와 동일한 자연어 입력"}'
# → HTTP 200, CLI와 동일한 결과를 JSON으로 응답 (best_effort:true, replan_count:3)
```

**정책 재확인**: 검증 과정에서 `connector/server.py --test --mock`(회귀 확인용)을 실행하려
했다가 사용자가 즉시 중단시킴 — "검증/테스트 목적"이라도 명시적으로 요청받지
않으면 Mock을 켜지 않기로 함(Step 8의 정책보다 더 엄격하게 적용). 단,
`optimizer/engine.py --test`는 Step 4 때부터 Mock 전용 데모로 합의된 예외라
그대로 유지.

---

## Step 10 — replan을 HITL(사용자 개입) 루프로 전환 ✅

### 배경 (설계가 두 번 바뀐 과정)

처음엔 "재계획 3회를 혼자 다 쓰고, 그래도 안 되면 마지막에 한 번만 사용자에게
묻는" 구조로 만들었으나, 사용자 의도는 달랐음:

> "재계획을 3회 실시 후에 물어보는 게 아니라, **1번째 재계획 때부터** 가진
> 정보를 LLM에게 보내 다양한 옵션을 만들고, 그걸 사용자에게 제공한다.
> 사용자에게 묻고 → 답에 따라 또 묻는 과정을 계속한다."

즉 기존 `replan_node`(혼자 조용히 필터를 바꾸는 LLM 노드)를 없애고, **그 판단
능력 자체를 "선택지 제안"으로 바꿔서 매 라운드 사용자에게 묻는 구조**로
전환. `replan_node`가 예전에 혼자 결정했던 것(가격 상한/제외몰/예산/배송일
조정)은 사라지지 않고, 이제 LLM이 만든 "선택지"로 사용자 앞에 제시된다.

### 새 토폴로지

```
search → optimize → reflect ─┬─ 충족 ──────────────────────→ route
                              └─ 미충족 & 라운드 한도(MAX_REPLAN_ATTEMPTS) 남음
                                  → clarify (선택지 제시 + 사용자 응답 대기)
                                       ├─ "지금까지 결과로 진행" 선택 → route
                                       └─ 그 외 선택 → request/필터에 반영 → search (재검색, loop)
```

`replan` 노드는 삭제. `clarify`가 그 역할을 흡수해 매 라운드 실행됨.

### 선택지를 만드는 방식 (숫자는 코드가, 다양성/판단은 LLM이)

- **`out_of_stock` 위반** (예: "우유 2L 이상" — 후보 자체가 없음): **코드가
  결정론적으로 계산**. 이미 가진 후보 데이터로 `unit_volume_ml × n ≥
  min_volume_ml`을 만족하는 최소 `n`(2~4)을 찾아 "N개 구매" 옵션을 만들고
  가격도 미리 계산. 숫자를 LLM이 만들지 않으므로 hallucination 위험 없음.
- **`budget_exceeded`/`delivery_unavailable` 등** (정답이 하나로 정해지지
  않는 판단 문제): **LLM이 제안**. 예전 `replan_node`가 혼자 적용했던 종류의
  조정(예산 한도 변경, 배송일 변경, 몰 제외, 품목별 가격 상한)을 2~3개의
  서로 다른 선택지로 만들어 제시
- 옵션이 4개를 넘으면, **LLM이 어떤 걸 보여줄지만 큐레이션**(이미 있는
  옵션 중 인덱스로 선택 — 새 숫자를 만들지 않음)
- 항상 "지금까지 찾은 결과로 진행 (best-effort)" 옵션을 마지막에 고정 추가
- 사용자가 숫자로 답하면 그대로 인덱싱, 자유 텍스트면 LLM이 선택지 중
  가장 가까운 것에 매칭(실패 시 첫 옵션으로 안전 폴백)

**구현 완료**

생성/수정된 파일 (`smartcart/orchestrator/graph.py` 전면 재작성):
- `MemorySaver` 체크포인터(모듈 전역) — 그래프를 멈췄다 정확히 이어가는 데 필요
- `_compute_volume_options(item_name, item, sorted_products)` — out_of_stock용
  결정론적 옵션 계산 (`multiply_qty`/`relax_volume`/`drop_item`)
- `_propose_filter_options(state, violations)` — budget/delivery용 LLM 제안
  (`adjust_budget`/`adjust_delivery`/`exclude_mall`/`adjust_max_price`)
- `_curate_options` — 4개 초과 시 LLM 큐레이션, 실패 시 앞 4개로 폴백
- `_resolve_choice` — 답변(숫자/자유텍스트) → 옵션 매칭
- `_apply_choice` — 선택을 `request`(items/budget/delivery)나
  `search_filters`/`excluded_malls`에 반영, `replan_count` 증가
- `clarify_node` — 위 함수들을 조합해 `interrupt()`로 멈추고 질문, 응답 받아 적용
- `_after_reflect`: 불만족 + 라운드 한도 남음 → `clarify` (한도면 `route`)
- `_after_clarify`: `accept_best_effort` 선택 시 `route`, 그 외엔 `search`로
  돌아가 재검색(필터/품목이 바뀌었으니 새로 검색해야 함)
- `replan_node`/`ReplanInstruction` 삭제 (clarify가 역할 흡수)
- `start(request)` / `resume(thread_id, answer)`: `{"thread_id", "state", "interrupt"}`
  반환, `main.py`(CLI 대화형 루프, FastAPI `/chat`+`/chat/resume`)는 Step 9에서
  만든 그대로 재사용 (변경 없음)

**verify** ✅
```bash
# CLI 다중 라운드 — 1번째 답으로 "우유 2개 구매"(용량 충족) 선택 →
# 그 결과 총액이 예산을 초과해 2번째 라운드(예산 위반)가 자동으로 또 옴 →
# "best-effort로 진행" 선택
printf "1\n4\n" | python -m smartcart.main --mock-parse
# → 1라운드 질문(용량 미달 옵션 4개) → 2라운드 질문(예산 초과, LLM 제안 옵션
#   3개 + best-effort) → 최종 출력: 우유 x2(30,400원, 1라운드에서 고른 그
#   상품) 포함, best_effort:true, "재계획 2회"

# FastAPI 동일 시나리오 — /chat → /chat/resume(1) → /chat/resume(4)
# → 매 단계 needs_clarification/question이 CLI와 동일하게 나오고,
#   최종 pack.cart가 CLI 결과와 정확히 일치

# 회귀 확인 — clarify 경로를 안 타는 정상 케이스(Mock, Step 4 그대로)
python -m smartcart.optimizer.engine --test
# → satisfied=true, violations=[] (이전과 동일, 영향 없음)
```

**알려진 한계** (Step 9에서 옮김, 그대로 적용)
- `MemorySaver`는 프로세스 메모리 전용 — 재시작하면 대기 중인 `thread_id` 소실
- FastAPI 멀티 워커 환경에서는 동작 안 함(단일 프로세스 가정)
- 한 라운드에 여러 `out_of_stock` 품목이 있으면 전부 옵션으로 나열되지만,
  사용자는 한 번에 하나만 선택 가능 — 나머지는 다음 라운드에서 다시 물어봄

---

## Step 11 — out_of_stock(검색 결과 0건) 위반에 LLM 대안 옵션 추가 ✅

Step 10까지는 `out_of_stock` 위반 중 용량 조건(`min_volume_ml`)이 있는 경우만
`_compute_volume_options`로 선택지를 만들었고, 단순히 검색 결과가 0건인
품목(용량과 무관)은 어떤 선택지도 생성되지 않아 다른 위반이 없으면
"지금까지 결과로 진행"만 남는 문제가 있었음.

- `Item`에 `search_query: str | None` 필드 추가 — 표시용 `name`은 그대로 두고,
  실제 몰 검색에 쓰는 질의어만 바꿀 수 있게 분리 (`candidates`/`search_filters`
  딕셔너리 키는 계속 `name`이라 기존 필터가 유실되지 않음)
- `search_node`: `server.search_products(item.search_query or item.name, ...)`
- `_propose_item_not_found_options(item_name, request)` 추가 — 검색 결과 0건인
  품목에 대해 LLM이 `rename_query`(다른/더 일반적인 검색어) 또는
  `adjust_max_price` 선택지를 1~2개 제안. `drop_item`은 호출 측(`clarify_node`)이
  항상 별도로 보장
- `_apply_choice`에 `rename_query` 처리 추가 — 선택된 품목의 `search_query`만
  갱신, `name`/라벨/기존 필터는 그대로 유지
- `_LLMOption`에 `new_query` 필드 추가, `action` 후보에 `rename_query` 포함

---

## Phase 2 안전 설계 원칙 (자동 구매 구현 전 필독)

> Phase 2(장바구니 담기 ~ 결제 자동화)를 구현할 때 반드시 아래 원칙을 지켜야 합니다.
> CLAUDE.md의 Phase 2 안전 원칙과 함께 적용하세요.

### 중복 결제 방지 (Idempotency)

**문제 상황**: 동일한 장바구니 요청이 두 번 실행될 수 있습니다.
- 네트워크 타임아웃 후 재시도
- 사용자가 "결제해줘"를 두 번 입력
- 에이전트 루프가 오작동해 `place_order` 노드를 중복 실행

**구현 필수 사항**:

1. **주문 idempotency key**: `place_order` 호출 전에 `order_id`를 생성합니다.
   - 생성 방식: `SHA256(user_id + session_id + cart_fingerprint)`
   - `cart_fingerprint`: `{mall_id}:{product_id}:{qty}` 목록을 정렬 후 해시
   - 같은 `order_id`로 두 번 결제 시도하면 두 번째는 멱등적으로 무시해야 합니다.

2. **주문 상태 체크**: `place_order` 실행 전에 Audit Log에서 동일 `order_id`의
   `PENDING` / `SUCCESS` 상태를 먼저 조회합니다.
   - 이미 `SUCCESS`면 즉시 기존 결과를 반환하고 결제 API를 호출하지 않습니다.
   - 이미 `PENDING`이면 진행 중임을 사용자에게 알리고 대기합니다.

3. **HITL 승인 토큰**: 사용자 승인(Human-in-the-Loop) 단계에서 일회용 토큰을
   발급합니다. `place_order`는 이 토큰을 소비(consume)한 뒤에만 실행되며,
   토큰은 1회 사용 후 무효화됩니다.

4. **결제 API 멱등 키 전달**: 쇼핑몰 결제 API가 멱등 키(`idempotency-key` 헤더 등)를
   지원하면 반드시 `order_id`를 함께 전달해 쇼핑몰 측에서도 중복 처리를 차단합니다.

**Audit Log 필수 기록 항목** (성공·실패 모두):
```
order_id | session_id | user_id | cart_fingerprint
| status (PENDING/SUCCESS/FAILED) | timestamp | error_detail
```

---

## 의존성 흐름 요약

```
Step 1 (뼈대)
  └─ Step 2 (MCP + Mock)   ← 독립 검증 가능
  └─ Step 3 (Parser)       ← 독립 검증 가능
  └─ Step 4 (도구 3종)     ← 독립 검증 가능
       └─ Step 5 (Orchestrator)  ← Step 2·3·4 모두 필요
            └─ Step 6 (FastAPI)
```

Step 2·3·4는 서로 독립적으로 구현·검증할 수 있어 병렬 작업이 가능합니다.
