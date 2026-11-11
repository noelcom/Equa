from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str
    anthropic_api_key: str = ""
    # Modellval per pipelinesteg. Låses efter jämförelse mot piloten (#12).
    wash_model: str = "claude-haiku-5-5"
    assessment_model: str = "claude-sonnet-5-5"
    # Max antal CV:n som körs samtidigt, för att hålla sig under Anthropics hastighetsgränser.
    max_parallel_cvs: int = Field(default=7, ge=1)
    # Ett CV som stått som queued/processing längre än så anses ha fastnat och tas om av /run.
    stale_cv_minutes: int = Field(default=15, ge=1)
    # Tillfälliga Anthropic-fel (429, timeout, 5xx) provas om med växande väntetid.
    anthropic_max_attempts: int = Field(default=4, ge=1)
    anthropic_retry_backoff_seconds: float = Field(default=2.0, ge=0)
    # Hur ofta raderingsjobbet letar efter utgångna analyser (ADR 0007).
    purge_interval_seconds: float = Field(default=3600, gt=0, le=3600)
    # Adresser som får anropa API:et från en webbläsare. Frontendens adress i drift läggs till här.
    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
