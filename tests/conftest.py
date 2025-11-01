"""Pytest configuration and fixtures."""

import asyncio
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
import redis.asyncio as redis
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from config import Settings, get_settings
from crawler.db.repositories import (
    ContentHashRepository,
    CrawledPageRepository,
    CrawlJobRepository,
    CrawlLogRepository,
    ScheduledJobRepository,
    WebsiteRepository,
)
from main import create_app

# Module-level settings for test setup
_test_settings = get_settings()

# SQL schema files location
SCHEMA_DIR = Path(__file__).parent.parent / "sql" / "schema"


async def create_schema(conn: AsyncConnection) -> None:
    """Execute SQL schema files to create database tables.

    Automatically discovers and loads all .sql files from SCHEMA_DIR in sorted order.
    """
    # Get the raw asyncpg connection for executing multi-statement scripts
    raw_conn = await conn.get_raw_connection()

    # Discover all SQL files in sorted order
    schema_files = sorted(SCHEMA_DIR.glob("*.sql"))

    for schema_file in schema_files:
        sql_content = schema_file.read_text()
        # Use asyncpg's execute which handles multi-statement scripts
        await raw_conn.driver_connection.execute(sql_content)


async def drop_schema(conn: AsyncConnection) -> None:
    """Drop all tables and types automatically by querying the database."""
    raw_conn = await conn.get_raw_connection()

    # Get all tables in public schema (excluding system tables)
    tables_query = """
        SELECT tablename
        FROM pg_tables
        WHERE schemaname = 'public'
        ORDER BY tablename;
    """
    tables = await raw_conn.driver_connection.fetch(tables_query)

    # Drop all tables with CASCADE
    for table in tables:
        drop_table_sql = f"DROP TABLE IF EXISTS {table['tablename']} CASCADE;"
        await raw_conn.driver_connection.execute(drop_table_sql)

    # Get all custom types (enums, composites, etc.)
    types_query = """
        SELECT typname
        FROM pg_type
        WHERE typnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public')
        AND typtype = 'e'  -- only enum types
        ORDER BY typname;
    """
    types = await raw_conn.driver_connection.fetch(types_query)

    # Drop all custom types with CASCADE
    for type_row in types:
        drop_type_sql = f"DROP TYPE IF EXISTS {type_row['typname']} CASCADE;"
        await raw_conn.driver_connection.execute(drop_type_sql)


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def settings() -> Settings:
    """Provide application settings for tests.

    Returns:
        Application settings instance
    """
    return get_settings()


@pytest_asyncio.fixture(scope="function")
async def db_session(test_db_schema) -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session.

    This fixture reuses the session-scoped schema and creates a transaction
    for each test function, rolling back all changes after the test completes.

    Args:
        test_db_schema: Session-scoped fixture that ensures schema exists
    """
    # Create test engine
    engine = create_async_engine(str(_test_settings.database_url), echo=False)

    # Create session
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        async with session.begin():
            yield session
            await session.rollback()

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_connection(test_db_schema) -> AsyncGenerator[AsyncConnection, None]:
    """Create a test database connection for sqlc repositories.

    This fixture reuses the session-scoped schema and creates a transaction
    for each test function, rolling back all changes after the test completes.

    Args:
        test_db_schema: Session-scoped fixture that ensures schema exists
    """
    # Create test engine
    engine = create_async_engine(str(_test_settings.database_url), echo=False)

    # Create connection with transaction
    async with engine.connect() as connection:
        async with connection.begin() as transaction:
            yield connection
            await transaction.rollback()

    await engine.dispose()


@pytest_asyncio.fixture
async def website_repo(db_connection: AsyncConnection) -> WebsiteRepository:
    """Create website repository fixture."""
    return WebsiteRepository(db_connection)


@pytest_asyncio.fixture
async def crawl_job_repo(db_connection: AsyncConnection) -> CrawlJobRepository:
    """Create crawl job repository fixture."""
    return CrawlJobRepository(db_connection)


@pytest_asyncio.fixture
async def crawled_page_repo(db_connection: AsyncConnection) -> CrawledPageRepository:
    """Create crawled page repository fixture."""
    return CrawledPageRepository(db_connection)


@pytest_asyncio.fixture
async def content_hash_repo(db_connection: AsyncConnection) -> ContentHashRepository:
    """Create content hash repository fixture."""
    return ContentHashRepository(db_connection)


@pytest_asyncio.fixture
async def crawl_log_repo(db_connection: AsyncConnection) -> CrawlLogRepository:
    """Create crawl log repository fixture."""
    return CrawlLogRepository(db_connection)


@pytest_asyncio.fixture
async def scheduled_job_repo(db_connection: AsyncConnection) -> ScheduledJobRepository:
    """Create scheduled job repository fixture."""
    return ScheduledJobRepository(db_connection)


@pytest_asyncio.fixture
async def redis_client() -> AsyncGenerator[redis.Redis, None]:
    """Create a Redis client for testing.

    This fixture provides a Redis client without reusing the global pool
    to avoid event loop issues in tests. Flushes test keys after each test.
    """
    client = redis.from_url(
        str(_test_settings.redis_url),
        encoding="utf-8",
        decode_responses=True,
    )
    try:
        # Verify connection
        await client.ping()
        yield client
        # Clean up test keys after each test
        await client.flushdb()
    finally:
        # Clean up connection
        await client.aclose()


@pytest_asyncio.fixture(scope="session")
async def test_db_schema():
    """Set up database schema once for all integration tests."""
    engine = create_async_engine(str(_test_settings.database_url), echo=False)

    # Drop existing schema first to ensure clean state
    async with engine.begin() as conn:
        await drop_schema(conn)

    # Create fresh schema
    async with engine.begin() as conn:
        await create_schema(conn)

    yield

    # Drop schema after tests
    async with engine.begin() as conn:
        await drop_schema(conn)

    await engine.dispose()


@pytest_asyncio.fixture
async def test_client(test_db_schema) -> AsyncGenerator[AsyncClient, None]:
    """Create FastAPI test client for integration tests.

    This fixture provides an async HTTP client for testing API endpoints.
    The database schema is set up once per test session.
    Each test gets fresh state by truncating all tables after completion.

    Args:
        test_db_schema: Session-scoped fixture that ensures schema exists
    """
    import crawler.db.session as db_module
    from crawler.db import get_db

    # Create test engine with minimal pooling to avoid connection leaks
    engine = create_async_engine(
        str(_test_settings.database_url),
        echo=False,
        pool_pre_ping=False,
        pool_size=1,  # Minimal pool size for tests
        max_overflow=0,  # No overflow connections
        pool_timeout=30,
        pool_recycle=3600,
    )

    # Override module-level engine to prevent event loop issues
    original_engine = db_module.engine
    original_sessionmaker = db_module.async_session_maker

    db_module.engine = engine
    db_module.async_session_maker = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    # Create session maker
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Use context manager for proper session lifecycle management
    async with async_session() as session:
        async with session.begin():

            async def get_test_db() -> AsyncGenerator[AsyncSession, None]:
                """Return the shared test session."""
                yield session

            # Create app and override dependency
            app = create_app()
            app.dependency_overrides[get_db] = get_test_db

            # Create client
            transport = ASGITransport(app=app)
            try:
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    yield client
            finally:
                # Clean up overrides
                app.dependency_overrides.clear()

    # Cleanup after session context exits
    # Dispose engine and wait for all connections to close
    await engine.dispose()

    # Restore original module-level engine
    db_module.engine = original_engine
    db_module.async_session_maker = original_sessionmaker
