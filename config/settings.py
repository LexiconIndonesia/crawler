"""Application configuration using pydantic-settings."""

import os
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment-specific configuration.

    Configuration priority (highest to lowest):
    1. Environment variables
    2. .env.{ENVIRONMENT} file (e.g., .env.production)
    3. .env file (shared defaults)
    4. Field defaults in this class
    """

    model_config = SettingsConfigDict(
        env_file=(
            ".env",
            f".env.{os.getenv('ENVIRONMENT', 'development')}",
        ),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "Lexicon Crawler"
    app_version: str = "0.1.0"
    debug: bool = False
    environment: Literal["development", "staging", "production", "testing"] = Field(
        default="development",
        description="Application environment",
    )

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_workers: int = 1

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://crawler:crawler@localhost:5432/crawler",
        description="PostgreSQL connection URL",
    )
    database_pool_size: int = 5
    database_max_overflow: int = 5
    database_echo: bool = False

    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0", description="Redis connection URL")
    redis_max_connections: int = 10
    redis_ttl: int = 3600  # 1 hour default TTL

    # NATS
    nats_url: str = Field(default="nats://localhost:4222", description="NATS server URL")
    nats_stream_name: str = "CRAWLER_TASKS"
    nats_consumer_name: str = "crawler-worker"

    # Google Cloud Storage
    gcs_bucket_name: str = Field(
        default="lexicon-crawler-storage", description="GCS bucket for storing raw HTML"
    )
    google_application_credentials_base64: str | None = Field(
        default=None, description="Base64-encoded GCS service account credentials JSON"
    )

    # Crawler Settings
    max_concurrent_requests: int = 5
    request_timeout: int = 30
    max_retries: int = 3
    retry_delay: int = 5
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

    # Rate Limiting
    rate_limit_requests: int = 1000
    rate_limit_period: int = 60  # seconds

    # Monitoring
    enable_metrics: bool = True
    metrics_port: int = 9090

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"
    log_file: str = "logs/crawler.log"

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is a valid option."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f"log_level must be one of {valid_levels}")
        return v_upper


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
