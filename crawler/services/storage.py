"""Google Cloud Storage service."""

import base64
import json
import tempfile
from pathlib import Path
from typing import Optional

from google.cloud import storage
from google.oauth2 import service_account

from config import get_settings
from crawler.core.logging import get_logger

logger = get_logger(__name__)


class StorageService:
    """GCS storage service for raw HTML and documents."""

    def __init__(self) -> None:
        """Initialize storage service with base64-encoded credentials."""
        settings = get_settings()
        self.bucket_name = settings.gcs_bucket_name

        # Decode base64 credentials and create temporary credentials
        if settings.google_application_credentials_base64:
            try:
                # Decode base64 credentials
                credentials_json = base64.b64decode(
                    settings.google_application_credentials_base64
                ).decode("utf-8")
                credentials_dict = json.loads(credentials_json)

                # Create credentials from dict
                credentials = service_account.Credentials.from_service_account_info(
                    credentials_dict
                )

                # Initialize client with credentials
                self.client = storage.Client(
                    credentials=credentials, project=credentials_dict.get("project_id")
                )
                logger.info("gcs_initialized", bucket=self.bucket_name)
            except Exception as e:
                logger.error("gcs_initialization_error", error=str(e))
                raise
        else:
            # Fall back to default credentials (for local development)
            self.client = storage.Client()
            logger.warning("using_default_gcs_credentials")

        self.bucket = self.client.bucket(self.bucket_name)

    async def upload_html(self, url: str, content: str, task_id: str) -> str:
        """Upload raw HTML to GCS."""
        try:
            # Create blob path: tasks/{task_id}/{url_hash}.html
            blob_name = f"tasks/{task_id}/{hash(url)}.html"
            blob = self.bucket.blob(blob_name)

            # Upload content
            blob.upload_from_string(content, content_type="text/html")

            logger.info("html_uploaded", url=url, task_id=task_id, blob_name=blob_name)

            return blob_name
        except Exception as e:
            logger.error("html_upload_error", url=url, task_id=task_id, error=str(e))
            raise

    async def download_html(self, blob_name: str) -> str:
        """Download HTML from GCS."""
        try:
            blob = self.bucket.blob(blob_name)
            content = blob.download_as_text()

            logger.info("html_downloaded", blob_name=blob_name)
            return content
        except Exception as e:
            logger.error("html_download_error", blob_name=blob_name, error=str(e))
            raise

    async def delete_html(self, blob_name: str) -> bool:
        """Delete HTML from GCS."""
        try:
            blob = self.bucket.blob(blob_name)
            blob.delete()

            logger.info("html_deleted", blob_name=blob_name)
            return True
        except Exception as e:
            logger.error("html_delete_error", blob_name=blob_name, error=str(e))
            return False

    async def list_blobs(self, prefix: Optional[str] = None) -> list[str]:
        """List blobs with optional prefix filter."""
        try:
            blobs = self.client.list_blobs(self.bucket_name, prefix=prefix)
            return [blob.name for blob in blobs]
        except Exception as e:
            logger.error("list_blobs_error", prefix=prefix, error=str(e))
            return []
