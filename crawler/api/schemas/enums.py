"""Common API enums."""

from enum import Enum


class StatusEnum(str, Enum):
    """Status of website or job."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ACTIVE = "active"
    INACTIVE = "inactive"
