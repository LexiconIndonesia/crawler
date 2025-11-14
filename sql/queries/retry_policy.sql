-- name: GetRetryPolicyByCategory :one
-- Get retry policy by error category
SELECT * FROM retry_policy
WHERE error_category = $1;

-- name: ListAllRetryPolicies :many
-- List all retry policies
SELECT * FROM retry_policy
ORDER BY error_category;

-- name: ListRetryablePolicies :many
-- List only retryable error policies
SELECT * FROM retry_policy
WHERE is_retryable = true
ORDER BY error_category;

-- name: UpdateRetryPolicy :one
-- Update retry policy configuration
UPDATE retry_policy
SET
    is_retryable = COALESCE($2, is_retryable),
    max_attempts = COALESCE($3, max_attempts),
    backoff_strategy = COALESCE($4, backoff_strategy),
    initial_delay_seconds = COALESCE($5, initial_delay_seconds),
    max_delay_seconds = COALESCE($6, max_delay_seconds),
    backoff_multiplier = COALESCE($7, backoff_multiplier),
    description = COALESCE($8, description),
    updated_at = CURRENT_TIMESTAMP
WHERE error_category = $1
RETURNING *;
