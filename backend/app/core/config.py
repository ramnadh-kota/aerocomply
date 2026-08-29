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


@lru_cache
def get_settings() -> Settings:
    return Settings()
