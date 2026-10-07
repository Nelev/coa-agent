"""Settings, read from the environment and .env. Cached; tests clear the cache."""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openrouter_api_key: SecretStr | None = None
    openrouter_model: str = "openai/gpt-4.1"
    extraction_model: str | None = None
    tool_budget: int = 12
    state_dir: Path = Path("state")

    @property
    def read_model(self) -> str:
        return self.extraction_model or self.openrouter_model

    @property
    def uploads_dir(self) -> Path:
        return self.state_dir / "uploads"

    @property
    def trace_db_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.state_dir / 'trace.db'}"

    @property
    def checkpoints_path(self) -> Path:
        return self.state_dir / "checkpoints.db"

    @property
    def recursion_limit(self) -> int:
        # Hard backstop only; the router enforces the budget.
        return 2 * self.tool_budget + 4


@lru_cache
def get_settings() -> Settings:
    return Settings()
