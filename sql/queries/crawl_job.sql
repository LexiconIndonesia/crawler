-- name: CreateCrawlJob :one
INSERT INTO crawl_job (
    website_id,
    job_type,
    seed_url,
    embedded_config,
    priority,
    scheduled_at,
    max_retries,
    metadata,
    variables
) VALUES (
    $1, COALESCE($2, 'one_time'::job_type_enum), $3, $4, COALESCE($5, 5),
    $6, COALESCE($7, 3), $8, $9
)
RETURNING *;

-- name: GetCrawlJobByID :one
SELECT * FROM crawl_job
WHERE id = $1;

-- name: ListCrawlJobs :many
SELECT * FROM crawl_job
WHERE
    website_id = COALESCE($1, website_id)
    AND status = COALESCE($2, status)
    AND job_type = COALESCE($3, job_type)
ORDER BY priority DESC, created_at ASC
LIMIT $4 OFFSET $5;

-- name: CountCrawlJobs :one
SELECT COUNT(*) FROM crawl_job
WHERE
    website_id = COALESCE($1, website_id)
    AND status = COALESCE($2, status);

-- name: GetPendingJobs :many
SELECT * FROM crawl_job
WHERE status = 'pending'
    AND (scheduled_at IS NULL OR scheduled_at <= CURRENT_TIMESTAMP)
ORDER BY priority DESC, created_at ASC
LIMIT $1;

-- name: UpdateCrawlJobStatus :one
UPDATE crawl_job
SET
    status = $2::status_enum,
    started_at = CASE WHEN $2::status_enum = 'running'::status_enum THEN COALESCE($3, CURRENT_TIMESTAMP) ELSE started_at END,
    completed_at = CASE WHEN $2::status_enum IN ('completed'::status_enum, 'failed'::status_enum, 'cancelled'::status_enum) THEN COALESCE($4, CURRENT_TIMESTAMP) ELSE completed_at END,
    error_message = $5,
    updated_at = CURRENT_TIMESTAMP
WHERE id = $1
RETURNING *;

-- name: UpdateCrawlJobProgress :one
UPDATE crawl_job
SET
    progress = $2,
    updated_at = CURRENT_TIMESTAMP
WHERE id = $1
RETURNING *;

-- name: CancelCrawlJob :one
UPDATE crawl_job
SET
    status = 'cancelled',
    cancelled_at = CURRENT_TIMESTAMP,
    cancelled_by = $2,
    cancellation_reason = $3,
    updated_at = CURRENT_TIMESTAMP
WHERE id = $1
RETURNING *;

-- name: IncrementJobRetryCount :one
UPDATE crawl_job
SET
    retry_count = retry_count + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE id = $1
RETURNING *;

-- name: GetJobsByWebsite :many
SELECT * FROM crawl_job
WHERE website_id = $1
ORDER BY created_at DESC
LIMIT $2 OFFSET $3;

-- name: GetRunningJobs :many
SELECT * FROM crawl_job
WHERE status = 'running'
ORDER BY started_at ASC;

-- name: GetFailedJobsForRetry :many
SELECT * FROM crawl_job
WHERE status = 'failed'
    AND retry_count < max_retries
ORDER BY priority DESC, created_at ASC
LIMIT $1;

-- name: DeleteOldCompletedJobs :exec
DELETE FROM crawl_job
WHERE status IN ('completed', 'cancelled')
    AND completed_at < CURRENT_TIMESTAMP - INTERVAL '30 days';
