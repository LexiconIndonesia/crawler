-- Dead Letter Queue Queries
-- SQLAlchemy-compatible queries for managing permanently failed jobs

-- name: AddToDeadLetterQueue :one
-- Add a permanently failed job to the DLQ
INSERT INTO dead_letter_queue (
    job_id,
    seed_url,
    website_id,
    job_type,
    priority,
    error_category,
    error_message,
    stack_trace,
    http_status,
    total_attempts,
    first_attempt_at,
    last_attempt_at
) VALUES (
    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12
) RETURNING *;

-- name: GetDLQEntryByID :one
-- Get a single DLQ entry by ID
SELECT * FROM dead_letter_queue
WHERE id = $1;

-- name: GetDLQEntryByJobID :one
-- Get a DLQ entry by job_id
SELECT * FROM dead_letter_queue
WHERE job_id = $1;

-- name: ListDLQEntries :many
-- List DLQ entries with pagination and filtering
SELECT * FROM dead_letter_queue
WHERE ($1::error_category_enum IS NULL OR error_category = $1)
  AND ($2::uuid IS NULL OR website_id = $2)
  AND ($3::boolean IS NULL OR
       ($3 = true AND resolved_at IS NULL) OR
       ($3 = false AND resolved_at IS NOT NULL))
ORDER BY added_to_dlq_at DESC
LIMIT $4 OFFSET $5;

-- name: CountDLQEntries :one
-- Count DLQ entries with filtering
SELECT COUNT(*) FROM dead_letter_queue
WHERE ($1::error_category_enum IS NULL OR error_category = $1)
  AND ($2::uuid IS NULL OR website_id = $2)
  AND ($3::boolean IS NULL OR
       ($3 = true AND resolved_at IS NULL) OR
       ($3 = false AND resolved_at IS NOT NULL));

-- name: MarkDLQRetryAttempted :one
-- Mark that a DLQ entry was manually retried
UPDATE dead_letter_queue
SET
    retry_attempted = true,
    retry_attempted_at = CURRENT_TIMESTAMP,
    retry_success = $2
WHERE id = $1
RETURNING *;

-- name: MarkDLQResolved :one
-- Mark a DLQ entry as resolved with notes
UPDATE dead_letter_queue
SET
    resolved_at = CURRENT_TIMESTAMP,
    resolution_notes = $2
WHERE id = $1
RETURNING *;

-- name: GetDLQStats :one
-- Get statistics about DLQ entries
SELECT
    COUNT(*) as total_entries,
    COUNT(*) FILTER (WHERE resolved_at IS NULL) as unresolved_count,
    COUNT(*) FILTER (WHERE retry_attempted = true) as retry_attempted_count,
    COUNT(*) FILTER (WHERE retry_success = true) as retry_success_count
FROM dead_letter_queue;

-- name: GetDLQStatsByCategory :many
-- Get DLQ statistics grouped by error category
SELECT
    error_category,
    COUNT(*) as entry_count,
    COUNT(*) FILTER (WHERE resolved_at IS NULL) as unresolved_count
FROM dead_letter_queue
GROUP BY error_category
ORDER BY entry_count DESC;

-- name: GetDLQEntriesForWebsite :many
-- Get all DLQ entries for a specific website
SELECT * FROM dead_letter_queue
WHERE website_id = $1
ORDER BY added_to_dlq_at DESC
LIMIT $2 OFFSET $3;

-- name: DeleteDLQEntry :exec
-- Delete a DLQ entry (hard delete)
DELETE FROM dead_letter_queue
WHERE id = $1;

-- name: GetOldestUnresolvedDLQEntries :many
-- Get oldest unresolved DLQ entries (for alerting)
SELECT * FROM dead_letter_queue
WHERE resolved_at IS NULL
ORDER BY added_to_dlq_at ASC
LIMIT $1;

-- name: BulkMarkDLQResolved :exec
-- Mark multiple DLQ entries as resolved
UPDATE dead_letter_queue
SET
    resolved_at = CURRENT_TIMESTAMP,
    resolution_notes = $2
WHERE id = ANY($1::BIGINT[]);
