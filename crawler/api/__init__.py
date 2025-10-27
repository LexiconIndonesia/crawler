"""API package."""

from .routes import router
from .v1 import router_v1

__all__ = ["router", "router_v1"]
