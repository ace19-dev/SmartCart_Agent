"""
SmartCart 환경변수 및 경로 설정.

이 모듈을 가장 먼저 import하면:
  1. .env 파일을 로드한다.
  2. agentic-ai-common-tools를 sys.path에 추가해 로컬 모듈처럼 사용 가능하게 한다.
     → from core.base_mcp import BaseMCP
     → from core.llm import make_llm
"""
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── agentic-ai-common-tools 경로 설정 ─────────────────────────────────────────
# 기본값: 이 저장소와 형제 디렉터리 (dl-repo/agentic-ai-common-tools)
# 다른 위치라면 .env에 COMMON_TOOLS_DIR 를 설정하세요.
_default_tools_dir = Path(__file__).resolve().parents[2] / "agentic-ai-common-tools"
COMMON_TOOLS_DIR: str = os.getenv("COMMON_TOOLS_DIR", str(_default_tools_dir))

if COMMON_TOOLS_DIR not in sys.path:
    sys.path.insert(0, COMMON_TOOLS_DIR)

# ── LLM ───────────────────────────────────────────────────────────────────────
# LLM_PROVIDER: "local"(기본) | "anthropic" | "openai" | "gemini"
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "local")
LLM_MODEL: str = os.getenv("LLM_MODEL", "claude-sonnet-4-6")
LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "4096"))
LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0"))

ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
LOCAL_LLM_BASE_URL: str = os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:11434/v1")
LOCAL_LLM_MODEL: str = os.getenv("LOCAL_LLM_MODEL", "qwen3:30b-a3b-q4_K_M")
LOCAL_LLM_API_KEY: str = os.getenv("LOCAL_LLM_API_KEY", "ollama")

# core/llm.py의 `import config`가 이 값들을 가져가도록 os.environ에 명시 반영
os.environ.setdefault("LLM_PROVIDER", LLM_PROVIDER)
os.environ.setdefault("LLM_MODEL", LLM_MODEL)
os.environ.setdefault("LLM_MAX_TOKENS", str(LLM_MAX_TOKENS))
os.environ.setdefault("LOCAL_LLM_BASE_URL", LOCAL_LLM_BASE_URL)
os.environ.setdefault("LOCAL_LLM_MODEL", LOCAL_LLM_MODEL)
os.environ.setdefault("LOCAL_LLM_API_KEY", LOCAL_LLM_API_KEY)

# ── SmartCart 도메인 ───────────────────────────────────────────────────────────
MAX_REPLAN_ATTEMPTS: int = int(os.getenv("MAX_REPLAN_ATTEMPTS", "3"))
BUDGET_SOFT_TOLERANCE_PCT: float = float(os.getenv("BUDGET_SOFT_TOLERANCE_PCT", "10"))

# clarify(HITL) 대화 상태(thread_id별 체크포인트)를 파일 DB에 영속화 — 프로세스
# 재시작 후에도 답변 대기 중이던 대화를 이어갈 수 있게 함 (MemorySaver는 재시작 시 소실)
_default_checkpoint_db = Path(__file__).resolve().parents[1] / "data" / "checkpoints.sqlite3"
CHECKPOINT_DB_PATH: str = os.getenv("CHECKPOINT_DB_PATH", str(_default_checkpoint_db))

# ── 쇼핑몰 커넥터 API ──────────────────────────────────────────────────────────
# 네이버 검색(쇼핑) Open API — https://developers.naver.com 에서 발급
# (gs_fresh/emart/kurly는 공개 검색 API가 없어 Mock 어댑터를 유지)
NAVER_CLIENT_ID: str = os.getenv("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET: str = os.getenv("NAVER_CLIENT_SECRET", "")

# ── 로깅 ──────────────────────────────────────────────────────────────────────
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
