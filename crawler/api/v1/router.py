"""API v1 main router."""

from fastapi import APIRouter

from .routes import jobs_router, websites_router

# API v1 main router (tags handled by sub-routers)
router = APIRouter(prefix="/api/v1")

# Include sub-routers with specific tags
router.include_router(websites_router, prefix="/websites", tags=["Websites"])
router.include_router(jobs_router, prefix="/jobs", tags=["Jobs"])
