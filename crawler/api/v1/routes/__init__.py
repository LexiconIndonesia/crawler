"""API v1 routes."""

from .dlq import router as dlq_router
from .duplicates import router as duplicates_router
from .jobs import router as jobs_router
from .websites import router as websites_router

__all__ = ["websites_router", "jobs_router", "dlq_router", "duplicates_router"]
