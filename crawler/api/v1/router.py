"""API v1 main router."""

from fastapi import APIRouter

from .routes import websites_router

# API v1 main router
router = APIRouter(prefix="/api/v1", tags=["API v1"])

# Include sub-routers
router.include_router(websites_router, prefix="/websites", tags=["Websites"])
