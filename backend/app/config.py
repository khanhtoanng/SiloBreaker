from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SB_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/silobreaker"
    # Only fixtures/input is ever read at runtime. fixtures/oracle is for tests/evaluation.
    fixtures_input_dir: Path = REPO_ROOT / "fixtures" / "input"
    # "offline" uses the deterministic rule-based extractor; "openai" calls a real model.
    ai_provider: str = "offline"
    openai_model: str = "gpt-4.1-mini"
    openai_api_key: str | None = None
    ai_timeout_seconds: float = 60.0
    # Bounded provider usage per AI stage (docs/02 NFR "Provider usage").
    ai_max_retries: int = 2
    ai_max_calls_per_stage: int = 3
    # Help Assistant agent, separate from ai_provider so detection, exercise generation and
    # assessment keep their own provider. "offline" keeps the lexical assistant; "local" lets
    # a model on an OpenAI-compatible server choose read-only tools (app.assistant.agent).
    assistant_provider: str = "offline"
    # Llama app; Ollama works with http://localhost:11434/v1.
    assistant_base_url: str = "http://localhost:9931/v1"
    # Required with "local": the exact id listed at GET {assistant_base_url}/models.
    assistant_model: str | None = None
    assistant_api_key: str = "local"  # local servers ignore it
    assistant_max_tool_calls: int = 4
    assistant_timeout_seconds: float = 60.0
    # Versions frozen into every analysis snapshot (FR-03). The scoring version lives with
    # the rules it describes: app.scoring.rules.SCORING_VERSION.
    prompt_version: str = "detect/1"
    schema_version: str = "analysis/1"
    cors_origins: list[str] = ["http://localhost:5173"]
    # Web accounts: server-side sessions behind an HttpOnly cookie.
    session_cookie_name: str = "sb_session"
    session_ttl_hours: int = 8
    # Set true when served over HTTPS; the local dev server is plain HTTP.
    session_cookie_secure: bool = False
    # Seeds the shuffle that gives candidates their "Candidate A".."D" aliases. Fixed so
    # tests are repeatable; set a private value in a real deployment.
    candidate_alias_seed: str = "silobreaker-demo"
    # Signs the learning coach's practice tokens so they need no storage. Demo default; set
    # a private value in a real deployment.
    coach_secret: str = "silobreaker-demo-coach"


@lru_cache
def get_settings() -> Settings:
    return Settings()
