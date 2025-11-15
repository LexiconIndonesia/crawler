"""API v1 main router."""

from fastapi import APIRouter

from .routes import dlq_router, duplicates_router, jobs_router, websites_router

# API v1 main router (tags handled by sub-routers)
router = APIRouter(prefix="/api/v1")

# Include sub-routers with specific tags
router.include_router(websites_router, prefix="/websites", tags=["Websites"])
router.include_router(jobs_router, prefix="/jobs", tags=["Jobs"])
router.include_router(dlq_router, prefix="/dlq", tags=["Dead Letter Queue"])
router.include_router(duplicates_router, prefix="/duplicates", tags=["Duplicates"])
