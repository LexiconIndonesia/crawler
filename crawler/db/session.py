"""Database session management."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config import get_settings

settings = get_settings()

# Create async engine
engine = create_async_engine(
    str(settings.database_url),
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    echo=settings.debug,
)

# Create async session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get database session dependency.

    Creates a session with automatic transaction management:
    - Commits on successful completion
    - Rolls back on exceptions
    - Handles closed connections gracefully
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
