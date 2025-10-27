-- name: CreateScheduledJob :one
INSERT INTO scheduled_job (
    website_id,
    cron_schedule,
    next_run_time,
    is_active,
    job_config
) VALUES (
    sqlc.arg(website_id),
    sqlc.arg(cron_schedule),
    sqlc.arg(next_run_time),
    COALESCE(sqlc.arg(is_active), true),
    sqlc.arg(job_config)
)
RETURNING *;

-- name: GetScheduledJobByID :one
SELECT * FROM scheduled_job
WHERE id = sqlc.arg(id);

-- name: GetScheduledJobsByWebsiteID :many
SELECT * FROM scheduled_job
WHERE website_id = sqlc.arg(website_id)
ORDER BY created_at DESC;

-- name: ListActiveScheduledJobs :many
SELECT * FROM scheduled_job
WHERE is_active = true
ORDER BY next_run_time ASC
LIMIT sqlc.arg(limit_count) OFFSET sqlc.arg(offset_count);

-- name: GetJobsDueForExecution :many
SELECT * FROM scheduled_job
WHERE is_active = true
  AND next_run_time <= sqlc.arg(cutoff_time)
ORDER BY next_run_time ASC
LIMIT sqlc.arg(limit_count);

-- name: UpdateScheduledJob :one
UPDATE scheduled_job
SET
    cron_schedule = COALESCE(sqlc.arg(cron_schedule), cron_schedule),
    next_run_time = COALESCE(sqlc.arg(next_run_time), next_run_time),
    last_run_time = COALESCE(sqlc.arg(last_run_time), last_run_time),
    is_active = COALESCE(sqlc.arg(is_active), is_active),
    job_config = COALESCE(sqlc.arg(job_config), job_config),
    updated_at = CURRENT_TIMESTAMP
WHERE id = sqlc.arg(id)
RETURNING *;

-- name: UpdateScheduledJobNextRun :one
UPDATE scheduled_job
SET
    next_run_time = sqlc.arg(next_run_time),
    last_run_time = sqlc.arg(last_run_time),
    updated_at = CURRENT_TIMESTAMP
WHERE id = sqlc.arg(id)
RETURNING *;

-- name: ToggleScheduledJobStatus :one
UPDATE scheduled_job
SET
    is_active = sqlc.arg(is_active),
    updated_at = CURRENT_TIMESTAMP
WHERE id = sqlc.arg(id)
RETURNING *;

-- name: DeleteScheduledJob :exec
DELETE FROM scheduled_job
WHERE id = sqlc.arg(id);

-- name: CountScheduledJobs :one
SELECT COUNT(*) FROM scheduled_job
WHERE website_id = COALESCE(sqlc.arg(website_id), website_id)
  AND is_active = COALESCE(sqlc.arg(is_active), is_active);
