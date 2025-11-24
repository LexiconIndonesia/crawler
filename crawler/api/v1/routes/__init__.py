"""API v1 routes."""

from .dlq import router as dlq_router
from .duplicates import router as duplicates_router
from .jobs import router as jobs_router
from .scheduled_jobs import router as scheduled_jobs_router
from .websites import router as websites_router

__all__ = [
    "dlq_router",
    "duplicates_router",
    "jobs_router",
    "scheduled_jobs_router",
    "websites_router",
]
