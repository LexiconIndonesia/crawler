"""WebSocket message models.

Shared models for WebSocket communication to avoid circular imports.
"""

from pydantic import BaseModel, ConfigDict, Field

from crawler.db.generated.models import CrawlLog


class WebSocketLogMessage(BaseModel):
    """WebSocket log message format.

    This model defines the structure of log messages sent over WebSocket
    connections. It ensures consistency and type safety for all log streaming.
    """

    id: int = Field(description="Log entry ID")
    job_id: str = Field(description="Crawl job UUID")
    website_id: str = Field(description="Website UUID")
    log_level: str = Field(description="Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)")
    message: str = Field(description="Log message content")
    step_name: str | None = Field(default=None, description="Crawl step name")
    context: dict | None = Field(default=None, description="Additional context as JSON")
    trace_id: str | None = Field(default=None, description="Trace ID for distributed tracing")
    created_at: str = Field(description="ISO 8601 timestamp")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": 12345,
                "job_id": "123e4567-e89b-12d3-a456-426614174000",
                "website_id": "123e4567-e89b-12d3-a456-426614174001",
                "log_level": "INFO",
                "message": "Crawling started",
                "step_name": "init",
                "context": {"url": "https://example.com"},
                "trace_id": "123e4567-e89b-12d3-a456-426614174002",
                "created_at": "2025-01-01T00:00:00Z",
            }
        }
    )

    @classmethod
    def from_crawl_log(cls, log: CrawlLog) -> WebSocketLogMessage:
        """Convert CrawlLog database model to WebSocket message format.

        Args:
            log: CrawlLog from database

        Returns:
            WebSocketLogMessage ready for JSON serialization
        """
        return cls(
            id=log.id,
            job_id=str(log.job_id),
            website_id=str(log.website_id),
            log_level=log.log_level.value,
            message=log.message,
            step_name=log.step_name,
            context=log.context,
            trace_id=str(log.trace_id) if log.trace_id else None,
            created_at=log.created_at.isoformat(),
        )
