#!/usr/bin/env python3
"""Quick script to create and publish a crawl job."""

import asyncio

from config import get_settings
from crawler.db.generated.models import JobTypeEnum
from crawler.db.repositories.crawl_job import CrawlJobRepository
from crawler.db.repositories.website import WebsiteRepository
from crawler.db.session import async_session_maker
from crawler.services.nats_queue import NATSQueueService


async def main() -> None:
    """Create job in DB and publish to NATS."""
    settings = get_settings()

    # Create session for database operations
    async with async_session_maker() as session:
        try:
            conn = await session.connection()
            job_repo = CrawlJobRepository(conn)
            website_repo = WebsiteRepository(conn)

            # Get the website
            website_id = "019a95fe-054d-77e0-a5a6-284a9e21a9e1"
            website = await website_repo.get_by_id(website_id)
            if not website:
                print(f"❌ Website {website_id} not found")
                return

            print(f"Website: {website.name}")

            # Create job in database
            job = await job_repo.create(
                website_id=website_id,
                job_type=JobTypeEnum.ONE_TIME,
                seed_url=website.base_url,
                priority=5,
                max_retries=3,
            )
            await session.commit()

            if not job:
                print("❌ Failed to create job")
                return

            job_id = str(job.id)
            print(f"✅ Job {job_id} created in database")

            # Publish to NATS
            nats_service = NATSQueueService(settings)
            await nats_service.connect()

            try:
                job_data = {
                    "website_id": website_id,
                    "priority": 5,
                    "job_type": "one_time",
                }

                success = await nats_service.publish_job(job_id, job_data)

                if success:
                    print(f"✅ Job {job_id} published to queue")
                    pending = await nats_service.get_pending_job_count()
                    print(f"Pending jobs in queue: {pending}")
                else:
                    print(f"❌ Failed to publish job {job_id}")
            finally:
                await nats_service.disconnect()

        except Exception as e:
            print(f"❌ Error: {e}")
            await session.rollback()
            raise


if __name__ == "__main__":
    asyncio.run(main())
