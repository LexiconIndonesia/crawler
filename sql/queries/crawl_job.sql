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
    sqlc.arg(website_id),
    COALESCE(sqlc.arg(job_type), 'one_time'::job_type_enum),
    sqlc.arg(seed_url),
    sqlc.arg(embedded_config),
    COALESCE(sqlc.arg(priority), 5),
    sqlc.arg(scheduled_at),
    COALESCE(sqlc.arg(max_retries), 3),
    sqlc.arg(metadata),
    sqlc.arg(variables)
)
RETURNING *;

-- name: GetCrawlJobByID :one
SELECT * FROM crawl_job
WHERE id = sqlc.arg(id);

-- name: ListCrawlJobs :many
SELECT * FROM crawl_job
WHERE
    website_id = COALESCE(sqlc.arg(website_id), website_id)
    AND status = COALESCE(sqlc.arg(status), status)
    AND job_type = COALESCE(sqlc.arg(job_type), job_type)
ORDER BY priority DESC, created_at ASC
LIMIT sqlc.arg(limit_count) OFFSET sqlc.arg(offset_count);

-- name: CountCrawlJobs :one
SELECT COUNT(*) FROM crawl_job
WHERE
    website_id = COALESCE(sqlc.arg(website_id), website_id)
    AND status = COALESCE(sqlc.arg(status), status);

-- name: GetPendingJobs :many
SELECT * FROM crawl_job
WHERE status = 'pending'
    AND (scheduled_at IS NULL OR scheduled_at <= CURRENT_TIMESTAMP)
ORDER BY priority DESC, created_at ASC
LIMIT sqlc.arg(limit_count);

-- name: UpdateCrawlJobStatus :one
UPDATE crawl_job
SET
    status = sqlc.arg(status)::status_enum,
    started_at = CASE WHEN sqlc.arg(status)::status_enum = 'running'::status_enum THEN COALESCE(sqlc.arg(started_at), CURRENT_TIMESTAMP) ELSE started_at END,
    completed_at = CASE WHEN sqlc.arg(status)::status_enum IN ('completed'::status_enum, 'failed'::status_enum, 'cancelled'::status_enum) THEN COALESCE(sqlc.arg(completed_at), CURRENT_TIMESTAMP) ELSE completed_at END,
    error_message = sqlc.arg(error_message),
    updated_at = CURRENT_TIMESTAMP
WHERE id = sqlc.arg(id)
RETURNING *;

-- name: UpdateCrawlJobProgress :one
UPDATE crawl_job
SET
    progress = sqlc.arg(progress),
    updated_at = CURRENT_TIMESTAMP
WHERE id = sqlc.arg(id)
RETURNING *;

-- name: CancelCrawlJob :one
UPDATE crawl_job
SET
    status = 'cancelled',
    cancelled_at = CURRENT_TIMESTAMP,
    cancelled_by = sqlc.arg(cancelled_by),
    cancellation_reason = sqlc.arg(cancellation_reason),
    updated_at = CURRENT_TIMESTAMP
WHERE id = sqlc.arg(id)
RETURNING *;

-- name: IncrementJobRetryCount :one
UPDATE crawl_job
SET
    retry_count = retry_count + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE id = sqlc.arg(id)
RETURNING *;

-- name: GetJobsByWebsite :many
SELECT * FROM crawl_job
WHERE website_id = sqlc.arg(website_id)
ORDER BY created_at DESC
LIMIT sqlc.arg(limit_count) OFFSET sqlc.arg(offset_count);

-- name: GetRunningJobs :many
SELECT * FROM crawl_job
WHERE status = 'running'
ORDER BY started_at ASC;

-- name: GetFailedJobsForRetry :many
SELECT * FROM crawl_job
WHERE status = 'failed'
    AND retry_count < max_retries
ORDER BY priority DESC, created_at ASC
LIMIT sqlc.arg(limit_count);

-- name: DeleteOldCompletedJobs :exec
DELETE FROM crawl_job
WHERE status IN ('completed', 'cancelled')
    AND completed_at < CURRENT_TIMESTAMP - INTERVAL '30 days';
