"""Application configuration using pydantic-settings."""

import os
from typing import Annotated, Literal

from fastapi import Depends
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
    app_name: str = "Lexicon Crawler API"
    app_version: str = "1.0.0"
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

    # Log Retention & Partitioning
    log_retention_days: int = Field(
        default=90,
        description="Number of days to retain crawl logs before dropping partitions",
    )
    log_partition_months_ahead: int = Field(
        default=3,
        description="Number of future months to pre-create log partitions",
    )

    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0", description="Redis connection URL")
    redis_max_connections: int = 10
    redis_ttl: int = 3600  # 1 hour default TTL
    url_dedup_ttl: int = Field(
        default=86400,
        description="URL deduplication cache TTL in seconds (default: 24 hours)",
    )
    ws_token_ttl: int = Field(
        default=600,
        description="WebSocket token TTL in seconds (default: 10 minutes)",
    )

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

    # Browser Pool Settings
    browser_pool_size: int = Field(
        default=3,
        description="Number of browser instances to maintain in the pool",
    )
    browser_max_contexts_per_browser: int = Field(
        default=5,
        description="Maximum number of contexts per browser instance",
    )
    browser_context_timeout: int = Field(
        default=300,
        description="Timeout in seconds for acquiring a browser context",
    )
    browser_health_check_interval: int = Field(
        default=60,
        description="Interval in seconds for browser health checks",
    )
    browser_default_type: Literal["chromium", "firefox", "webkit"] = Field(
        default="chromium",
        description="Default browser type for the pool",
    )
    browser_max_recovery_attempts: int = Field(
        default=3,
        description="Maximum number of recovery attempts for a crashed browser",
    )
    browser_recovery_backoff_base: float = Field(
        default=2.0,
        description="Base multiplier for exponential backoff (seconds = base^attempt)",
    )

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

    @field_validator("browser_max_recovery_attempts")
    @classmethod
    def validate_max_recovery_attempts(cls, v: int) -> int:
        """Validate max recovery attempts is positive."""
        if v < 1:
            raise ValueError("browser_max_recovery_attempts must be at least 1")
        return v

    @field_validator("browser_recovery_backoff_base")
    @classmethod
    def validate_recovery_backoff_base(cls, v: float) -> float:
        """Validate backoff base is greater than 1."""
        if v <= 1.0:
            raise ValueError(
                "browser_recovery_backoff_base must be greater than 1.0 for exponential backoff"
            )
        return v

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is a valid option."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f"log_level must be one of {valid_levels}")
        return v_upper


def get_settings() -> Settings:
    """Get settings instance for dependency injection.

    FastAPI will cache this automatically within the same request.
    For cross-request caching, Settings class itself uses Pydantic's
    validation caching and the instance is lightweight to create.
    """
    return Settings()


# Type alias for dependency injection
SettingsDep = Annotated[Settings, Depends(get_settings)]
