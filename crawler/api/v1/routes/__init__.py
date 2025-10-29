"""API v1 routes."""

from .jobs import router as jobs_router
from .websites import router as websites_router

__all__ = ["websites_router", "jobs_router"]
