-- name: CreateRetryHistory :one
-- Record a retry attempt
INSERT INTO retry_history (
    job_id,
    attempt_number,
    error_category,
    error_message,
    stack_trace,
    retry_delay_seconds
) VALUES (
    $1, $2, $3, $4, $5, $6
) RETURNING *;

-- name: GetRetryHistoryByJobID :many
-- Get all retry history for a job
SELECT * FROM retry_history
WHERE job_id = $1
ORDER BY attempt_number ASC;

-- name: GetLatestRetryAttempt :one
-- Get the most recent retry attempt for a job
SELECT * FROM retry_history
WHERE job_id = $1
ORDER BY attempted_at DESC, attempt_number DESC
LIMIT 1;

-- name: CountRetryAttemptsByCategory :many
-- Count retry attempts grouped by error category (analytics)
SELECT
    error_category,
    COUNT(*) as total_attempts,
    COUNT(DISTINCT job_id) as unique_jobs
FROM retry_history
WHERE attempted_at >= $1
GROUP BY error_category
ORDER BY total_attempts DESC;

-- name: GetFailureRateByCategory :many
-- Get failure rate by category in a time window (analytics)
SELECT
    error_category,
    COUNT(*) as failure_count,
    AVG(retry_delay_seconds) as avg_delay_seconds
FROM retry_history
WHERE attempted_at >= sqlc.arg('start_time') AND attempted_at < sqlc.arg('end_time')
GROUP BY error_category
ORDER BY failure_count DESC;
