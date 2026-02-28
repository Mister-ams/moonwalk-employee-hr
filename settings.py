"""Application settings -- loaded once at startup.

Uses pydantic-settings to validate required env vars at import time.
Missing required vars raise ValidationError before Railway marks service healthy.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str = ""
    LOOMI_API_KEY: str = ""  # used to protect admin endpoints (formerly HR_API_KEY)
    OPENAI_API_KEY: str = ""  # used by LLM parser
    ANTHROPIC_API_KEY: str = ""  # reserved for future Anthropic model usage

    CORS_ORIGINS: str = "https://app.appsmith.com"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
