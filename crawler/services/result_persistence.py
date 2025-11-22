"""Result persistence service for saving crawl results to database.

This service handles persisting crawled pages and extracted data to the database
after successful workflow execution.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from crawler.core.logging import get_logger
from crawler.db.repositories import ContentHashRepository, CrawledPageRepository
from crawler.services.content_normalizer import ContentNormalizer
from crawler.utils.simhash import Simhash

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection

    from crawler.services.step_execution_context import StepExecutionContext

logger = get_logger(__name__)


class ResultPersistenceService:
    """Service for persisting crawl results to database."""

    def __init__(self, conn: AsyncConnection):
        """Initialize result persistence service.

        Args:
            conn: Database connection
        """
        self.conn = conn
        self.page_repo = CrawledPageRepository(conn)
        self.content_hash_repo = ContentHashRepository(conn)
        self.normalizer = ContentNormalizer()

    async def persist_workflow_results(
        self,
        job_id: str,
        website_id: str,
        context: StepExecutionContext,
    ) -> dict[str, int]:
        """Persist all workflow results to database.

        Args:
            job_id: Job ID
            website_id: Website ID
            context: Execution context with step results

        Returns:
            Dictionary with persistence statistics (pages_saved, pages_failed)
        """
        pages_saved = 0
        pages_failed = 0

        logger.info(
            "persist_workflow_results_starting",
            job_id=job_id,
            total_steps=len(context.step_results),
        )

        # Process each step result
        for step_name, step_result in context.step_results.items():
            # Guard: skip failed steps
            if step_result.error:
                logger.debug("persist_skipping_failed_step", step_name=step_name)
                continue

            # Extract pages from step result
            try:
                pages = self._extract_pages_from_step(step_name, step_result.extracted_data)

                if not pages:
                    logger.debug("persist_no_pages_in_step", step_name=step_name)
                    continue

                logger.info(
                    "persist_step_pages",
                    step_name=step_name,
                    page_count=len(pages),
                )

                # Save each page
                for page_data in pages:
                    try:
                        await self._save_page(
                            job_id=job_id,
                            website_id=website_id,
                            page_data=page_data,
                        )
                        pages_saved += 1
                    except Exception as e:
                        pages_failed += 1
                        logger.error(
                            "persist_page_failed",
                            url=page_data.get("_url", "unknown"),
                            error=str(e),
                            exc_info=True,
                        )

            except Exception as e:
                logger.error(
                    "persist_step_failed",
                    step_name=step_name,
                    error=str(e),
                    exc_info=True,
                )
                continue

        logger.info(
            "persist_workflow_results_completed",
            job_id=job_id,
            pages_saved=pages_saved,
            pages_failed=pages_failed,
        )

        return {"pages_saved": pages_saved, "pages_failed": pages_failed}

    def _extract_pages_from_step(
        self, step_name: str, extracted_data: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Extract page data from step result.

        Args:
            step_name: Name of the step
            extracted_data: Extracted data from step

        Returns:
            List of page data dictionaries with _url field
        """
        pages: list[dict[str, Any]] = []

        # Guard: no extracted data
        if not extracted_data:
            return pages

        # Case 1: Single page result (has _url field directly)
        if "_url" in extracted_data:
            pages.append(extracted_data)
            return pages

        # Case 2: Multiple pages in "items" array (scrape steps)
        if "items" in extracted_data and isinstance(extracted_data["items"], list):
            for item in extracted_data["items"]:
                if isinstance(item, dict) and "_url" in item:
                    pages.append(item)
            return pages

        # Case 3: Crawl step result (no pages to persist, just URLs)
        # Skip crawl steps - they don't have extractable content
        logger.debug(
            "extract_pages_no_urls",
            step_name=step_name,
            extracted_keys=list(extracted_data.keys()),
        )

        return pages

    async def _save_page(
        self,
        job_id: str,
        website_id: str,
        page_data: dict[str, Any],
    ) -> None:
        """Save a single page to database with duplicate detection.

        Args:
            job_id: Job ID
            website_id: Website ID
            page_data: Page data with _url and extracted fields
        """
        # Extract URL and content
        url = page_data.get("_url")
        content = page_data.get("_content")

        if not url:
            logger.warning("save_page_missing_url", page_data_keys=list(page_data.keys()))
            return

        # Remove internal fields before storing
        extracted_data = {k: v for k, v in page_data.items() if not k.startswith("_")}

        # Generate hashes
        url_hash = self._hash_url(url)
        content_hash = self._hash_content(content)

        # Generate Simhash fingerprint if content is available
        simhash_fingerprint = None
        if content:
            try:
                # Normalize content for hashing
                normalized_content = self.normalizer.normalize_for_hash(content)
                if normalized_content:
                    # Generate fingerprint
                    simhash = Simhash(normalized_content)
                    simhash_fingerprint = simhash.fingerprint
            except Exception as e:
                logger.warning("simhash_generation_failed", url=url, error=str(e))

        # Extract title if present
        title = extracted_data.get("title")

        # Serialize extracted data to JSON string
        extracted_json = json.dumps(extracted_data, ensure_ascii=False)

        # Step 1: Check if content is duplicate (by content_hash)
        duplicate_of = None
        similarity_score = None
        existing_page_with_content = await self.page_repo.get_by_content_hash(content_hash)

        if existing_page_with_content:
            # Content already exists - this is a duplicate
            duplicate_of = str(existing_page_with_content.id)
            similarity_score = 100  # Exact match

            logger.info(
                "page_duplicate_detected_exact",
                url=url,
                content_hash=content_hash,
                duplicate_of=duplicate_of,
            )

        # Step 1.5: Check for fuzzy duplicate if no exact match found and we have a fingerprint
        elif simhash_fingerprint is not None:
            # Find similar content within Hamming distance of 3 (approx 95% similarity)
            similar_content = await self.content_hash_repo.find_similar(
                target_fingerprint=simhash_fingerprint,
                max_distance=3,
                limit=1,
            )

            if similar_content:
                # Found a similar page
                match = similar_content[0]

                # Get the page ID associated with this content hash
                # Note: find_similar returns content_hash rows,
                # we need to find a page with this hash
                similar_page = await self.page_repo.get_by_content_hash(match.content_hash)

                if similar_page:
                    duplicate_of = str(similar_page.id)

                    # Calculate similarity score: (1 - distance/64) * 100
                    # distance is in match.hamming_distance
                    distance = match.hamming_distance
                    similarity_score = int((1 - distance / 64) * 100)

                    logger.info(
                        "page_duplicate_detected_fuzzy",
                        url=url,
                        duplicate_of=duplicate_of,
                        distance=distance,
                        similarity_score=similarity_score,
                    )

        # Step 2: Save to database (ON CONFLICT handles same URL gracefully)
        saved_page = await self.page_repo.create(
            website_id=website_id,
            job_id=job_id,
            url=url,
            url_hash=url_hash,
            content_hash=content_hash,
            crawled_at=datetime.now(UTC),
            title=str(title) if title else None,
            extracted_content=extracted_json,
            metadata=None,  # Can be extended later
            gcs_html_path=None,  # Can be extended for GCS storage
            gcs_documents=None,
        )

        # Step 2.5: Upsert content hash with Simhash fingerprint
        if saved_page:
            try:
                if simhash_fingerprint is not None:
                    await self.content_hash_repo.upsert_with_simhash(
                        content_hash_value=content_hash,
                        first_seen_page_id=saved_page.id,
                        simhash_fingerprint=simhash_fingerprint,
                    )
                else:
                    # Fallback to standard upsert if no fingerprint
                    await self.content_hash_repo.upsert(
                        content_hash_value=content_hash,
                        first_seen_page_id=saved_page.id,
                    )
            except Exception as e:
                logger.error("content_hash_upsert_failed", error=str(e))

        # Step 3: Mark as duplicate if content already exists
        if duplicate_of and saved_page:
            await self.page_repo.mark_as_duplicate(
                page_id=str(saved_page.id),
                duplicate_of=duplicate_of,
                similarity_score=similarity_score,
            )
            logger.info(
                "page_marked_as_duplicate",
                url=url,
                page_id=str(saved_page.id),
                duplicate_of=duplicate_of,
                similarity_score=similarity_score,
            )
        else:
            logger.debug("page_saved", url=url, extracted_fields=len(extracted_data))

    def _hash_url(self, url: str) -> str:
        """Generate SHA256 hash of URL for deduplication.

        Args:
            url: URL to hash

        Returns:
            Hex digest of SHA256 hash
        """
        return hashlib.sha256(url.encode("utf-8")).hexdigest()

    def _hash_content(self, content: str | dict[str, Any] | None) -> str:
        """Generate SHA256 hash of content for duplicate detection.

        Args:
            content: Content to hash (HTML string or JSON dict)

        Returns:
            Hex digest of SHA256 hash
        """
        if content is None:
            # Use empty string hash for None content
            content_str = ""
        elif isinstance(content, dict):
            # For dict content, serialize to JSON
            content_str = json.dumps(content, sort_keys=True, ensure_ascii=False)
        else:
            # For string content, use as-is
            content_str = str(content)

        return hashlib.sha256(content_str.encode("utf-8")).hexdigest()
