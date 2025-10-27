"""Common API schemas.

This module re-exports models from the generated OpenAPI models.
"""

from crawler.api.generated import (
    ErrorResponse,
    HealthResponse,
    RootResponse,
    StatusEnum,
)

__all__ = [
    "ErrorResponse",
    "HealthResponse",
    "RootResponse",
    "StatusEnum",
]
