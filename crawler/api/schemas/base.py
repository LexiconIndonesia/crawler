"""Base API response schemas."""

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = Field(..., description="Overall health status", examples=["healthy", "unhealthy"])
    timestamp: str = Field(..., description="Check timestamp (ISO 8601)")
    checks: dict[str, str] = Field(..., description="Individual service checks")


class RootResponse(BaseModel):
    """Root endpoint response."""

    message: str = Field(..., description="Welcome message")
    version: str = Field(..., description="Application version")
    environment: str = Field(..., description="Environment name")


class ErrorResponse(BaseModel):
    """Standard error response."""

    detail: str = Field(..., description="Error message")
    error_code: str | None = Field(None, description="Machine-readable error code")
    field: str | None = Field(
        None, description="Field that caused the error (for validation errors)"
    )
