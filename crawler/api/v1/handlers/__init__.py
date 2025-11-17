"""API v1 handlers."""

from .dlq import (
    get_dlq_entry_handler,
    get_dlq_stats_handler,
    list_dlq_entries_handler,
    resolve_dlq_entry_handler,
    retry_dlq_entry_handler,
)
from .duplicates import (
    get_duplicate_group_details_handler,
    get_duplicate_group_stats_handler,
    list_duplicate_groups_handler,
)
from .jobs import (
    cancel_job_handler,
    create_seed_job_handler,
    create_seed_job_inline_handler,
    generate_ws_token_handler,
)
from .logs import get_job_logs_handler
from .websites import (
    create_website_handler,
    delete_website_handler,
    get_config_history_handler,
    get_config_version_handler,
    get_website_by_id_handler,
    list_websites_handler,
    pause_schedule_handler,
    resume_schedule_handler,
    rollback_config_handler,
    trigger_crawl_handler,
    update_website_handler,
)

__all__ = [
    "create_website_handler",
    "delete_website_handler",
    "get_config_history_handler",
    "get_config_version_handler",
    "get_website_by_id_handler",
    "list_websites_handler",
    "pause_schedule_handler",
    "resume_schedule_handler",
    "rollback_config_handler",
    "trigger_crawl_handler",
    "update_website_handler",
    "create_seed_job_handler",
    "create_seed_job_inline_handler",
    "cancel_job_handler",
    "generate_ws_token_handler",
    "get_job_logs_handler",
    "list_duplicate_groups_handler",
    "get_duplicate_group_details_handler",
    "get_duplicate_group_stats_handler",
    "list_dlq_entries_handler",
    "get_dlq_entry_handler",
    "retry_dlq_entry_handler",
    "resolve_dlq_entry_handler",
    "get_dlq_stats_handler",
]
