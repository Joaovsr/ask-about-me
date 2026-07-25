from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://ask_about_me:ask_about_me@localhost:5432/ask_about_me"
    openai_api_key: SecretStr | None = None
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    embedding_batch_size: int = 64
    generation_model: str = "gpt-5.6-sol"
    generation_max_output_tokens: int = 1200
    openai_timeout_seconds: float = 30
    openai_max_retries: int = 2
    admin_password: SecretStr | None = None
    admin_session_secret: SecretStr | None = None
    admin_cookie_secure: bool = True
    chunk_target_tokens: int = 350
    chunk_max_tokens: int = 500
    chunk_overlap_tokens: int = 50

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="AAM_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
