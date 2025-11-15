"""Repository for retry_policy table operations."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncConnection

from crawler.db.generated import models
from crawler.db.generated import retry_policy as queries


class RetryPolicyRepository:
    """Repository for retry_policy table operations."""

    def __init__(self, conn: AsyncConnection):
        self.conn = conn
        self.querier = queries.AsyncQuerier(conn)

    async def get_by_category(
        self, error_category: models.ErrorCategoryEnum
    ) -> models.RetryPolicy | None:
        """Get retry policy by error category.

        Args:
            error_category: The error category to look up

        Returns:
            RetryPolicy if found, None otherwise
        """
        return await self.querier.get_retry_policy_by_category(error_category=error_category)

    async def list_all(self) -> list[models.RetryPolicy]:
        """List all retry policies.

        Returns:
            List of all retry policies ordered by error_category
        """
        policies = []
        async for policy in self.querier.list_all_retry_policies():
            policies.append(policy)
        return policies

    async def list_retryable(self) -> list[models.RetryPolicy]:
        """List only retryable error policies.

        Returns:
            List of retryable policies ordered by error_category
        """
        policies = []
        async for policy in self.querier.list_retryable_policies():
            policies.append(policy)
        return policies

    async def update(
        self,
        error_category: models.ErrorCategoryEnum,
        is_retryable: bool | None = None,
        max_attempts: int | None = None,
        backoff_strategy: models.BackoffStrategyEnum | None = None,
        initial_delay_seconds: int | None = None,
        max_delay_seconds: int | None = None,
        backoff_multiplier: float | None = None,
        description: str | None = None,
    ) -> models.RetryPolicy | None:
        """Update retry policy for an error category.

        Args:
            error_category: The error category to update
            is_retryable: Whether errors of this type should be retried
            max_attempts: Maximum number of retry attempts
            backoff_strategy: Backoff strategy (exponential/linear/fixed)
            initial_delay_seconds: Initial delay between retries
            max_delay_seconds: Maximum delay between retries
            backoff_multiplier: Multiplier for backoff calculation
            description: Human-readable description of the error category

        Returns:
            Updated RetryPolicy if found, None otherwise
        """
        # Get current policy for default values
        current = await self.querier.get_retry_policy_by_category(error_category=error_category)
        if not current:
            return None

        return await self.querier.update_retry_policy(
            error_category=error_category,
            is_retryable=is_retryable if is_retryable is not None else current.is_retryable,
            max_attempts=max_attempts if max_attempts is not None else current.max_attempts,
            backoff_strategy=(
                backoff_strategy if backoff_strategy is not None else current.backoff_strategy
            ),
            initial_delay_seconds=(
                initial_delay_seconds
                if initial_delay_seconds is not None
                else current.initial_delay_seconds
            ),
            max_delay_seconds=(
                max_delay_seconds if max_delay_seconds is not None else current.max_delay_seconds
            ),
            backoff_multiplier=(
                backoff_multiplier if backoff_multiplier is not None else current.backoff_multiplier
            ),
            description=description if description is not None else current.description,
        )
