"""Database session management."""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config import Settings, get_settings


def create_engine(settings: Settings) -> AsyncEngine:
    """Create async database engine from settings.

    Args:
        settings: Application settings

    Returns:
        Configured async database engine with connection pooling
    """
    # Disable pool_pre_ping in test environment to avoid event loop closure issues
    use_pool_pre_ping = settings.environment != "testing"

    return create_async_engine(
        str(settings.database_url),
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        echo=settings.debug,
        # Connection pool settings for better concurrency handling
        pool_pre_ping=use_pool_pre_ping,  # Disabled in tests to prevent event loop issues
        pool_recycle=3600,  # Recycle connections after 1 hour
        # Asyncpg-specific settings via connect_args
        connect_args={
            "server_settings": {
                "jit": "off",  # Disable JIT for better performance in some cases
            },
            "command_timeout": 60,  # Command timeout in seconds
        },
    )


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create async session factory from engine.

    Args:
        engine: Async database engine

    Returns:
        Configured async session factory
    """
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


# Module-level singletons initialized with default settings
# These are shared across the application lifecycle
_settings = get_settings()
engine = create_engine(_settings)
async_session_maker = create_sessionmaker(engine)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get database session dependency.

    Creates a session with automatic transaction management:
    - Commits on successful completion
    - Rolls back on exceptions
    - Handles closed connections gracefully

    Usage in route handlers:
        async def my_route(db: Annotated[AsyncSession, Depends(get_db)]):
            ...
    """
    async with async_session_maker() as session:
        try:
            yield session
            # Only commit if session is not closed and is dirty
            if session.in_transaction():
                await session.commit()
        except Exception:
            # Only rollback if session is not closed
            if session.in_transaction():
                await session.rollback()
            raise


# Type alias for dependency injection
DBSessionDep = Annotated[AsyncSession, Depends(get_db)]
