"""Pytest configuration and fixtures."""

import asyncio
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from config import get_settings
from crawler.db.repositories import (
    ContentHashRepository,
    CrawlJobRepository,
    CrawledPageRepository,
    CrawlLogRepository,
    WebsiteRepository,
)

settings = get_settings()

# SQL schema files location
SCHEMA_DIR = Path(__file__).parent.parent / "sql" / "schema"


async def create_schema(conn: AsyncConnection) -> None:
    """Execute SQL schema files to create database tables."""
    # Read and execute schema files in order
    schema_files = [
        SCHEMA_DIR / "000_migration_tracking.sql",
        SCHEMA_DIR / "001_initial_schema.sql",
    ]

    # Get the raw asyncpg connection for executing multi-statement scripts
    raw_conn = await conn.get_raw_connection()

    for schema_file in schema_files:
        if schema_file.exists():
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


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session.

    This fixture creates a new database session for each test function,
    and rolls back all changes after the test completes.
    """
    # Create test engine
    engine = create_async_engine(str(settings.database_url), echo=False)

    # Create all tables from SQL schema
    async with engine.begin() as conn:
        await create_schema(conn)

    # Create session
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        async with session.begin():
            yield session
            await session.rollback()

    # Drop all tables after test
    async with engine.begin() as conn:
        await drop_schema(conn)

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_connection() -> AsyncGenerator[AsyncConnection, None]:
    """Create a test database connection for sqlc repositories.

    This fixture creates a new database connection for each test function,
    and rolls back all changes after the test completes.
    """
    # Create test engine
    engine = create_async_engine(str(settings.database_url), echo=False)

    # Create all tables from SQL schema
    async with engine.begin() as conn:
        await create_schema(conn)

    # Create connection with transaction
    async with engine.connect() as connection:
        async with connection.begin() as transaction:
            yield connection
            await transaction.rollback()

    # Drop all tables after test
    async with engine.begin() as conn:
        await drop_schema(conn)

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
