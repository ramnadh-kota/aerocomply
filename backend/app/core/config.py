from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application configuration, loaded from environment variables / .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "AeroComply"
    environment: str = "development"  # development | staging | production
    debug: bool = False

    api_v1_prefix: str = "/api/v1"

    database_url: str = "postgresql+psycopg://aerocomply:aerocomply@localhost:5432/aerocomply"

    jwt_secret_key: str = "CHANGE_ME_IN_PRODUCTION"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    cors_allow_origins: list[str] = ["http://localhost:3000"]

    log_level: str = "INFO"

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "aerocomply_dev"

    redis_url: str = "redis://localhost:6379/0"

    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "aerocomply"
    s3_secret_key: str = "aerocomply_dev_secret"
    s3_bucket: str = "aerocomply-evidence"

    # AI agent (Lisa). Absent/empty -> NotConfiguredProvider is used and the
    # /lisa/ask endpoint returns an honest 503 ai_not_configured error; the
    # frontend falls back to the existing deterministic engine. Never
    # hardcode a real key here or anywhere else in the codebase.
    ai_provider: str = "auto"  # "auto" | "openai_compatible" | "anthropic" | "none"
    # e.g. "http://localhost:11434/v1" (Ollama) or "http://localhost:8000/v1" (vLLM)
    ai_base_url: str = ""
    ai_model: str = ""  # e.g. "qwen2.5:14b", "llama3.3:70b"
    ai_api_key: str = ""  # Optional API key for OpenAI-compatible endpoint
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-5"
    ai_max_tool_round_trips: int = 6
    ai_request_timeout_seconds: float = 30.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
