"""Application configuration using pydantic-settings."""

from functools import lru_cache
from typing import Optional

from pydantic import Field, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "Lexicon Crawler"
    app_version: str = "0.1.0"
    debug: bool = False
    environment: str = Field(
        default="development", description="Environment: development, staging, production"
    )

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_workers: int = 1

    # Database
    database_url: PostgresDsn = Field(
        default="postgresql+asyncpg://crawler:crawler@localhost:5432/crawler",
        description="PostgreSQL connection URL",
    )
    database_pool_size: int = 20
    database_max_overflow: int = 10

    # Redis
    redis_url: RedisDsn = Field(
        default="redis://localhost:6379/0", description="Redis connection URL"
    )
    redis_ttl: int = 3600  # 1 hour default TTL

    # NATS
    nats_url: str = Field(default="nats://localhost:4222", description="NATS server URL")
    nats_stream_name: str = "CRAWLER_TASKS"
    nats_consumer_name: str = "crawler-worker"

    # Google Cloud Storage
    gcs_bucket_name: str = Field(
        default="lexicon-crawler-storage", description="GCS bucket for storing raw HTML"
    )
    google_application_credentials_base64: Optional[str] = Field(
        default=None, description="Base64-encoded GCS service account credentials JSON"
    )

    # Crawler Settings
    max_concurrent_requests: int = 10
    request_timeout: int = 30
    max_retries: int = 3
    retry_delay: int = 5
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

    # Rate Limiting
    rate_limit_requests: int = 100
    rate_limit_period: int = 60  # seconds

    # Monitoring
    enable_metrics: bool = True
    metrics_port: int = 9090

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"
    log_file: str = "logs/crawler.log"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
