-- name: CreateCrawlLog :one
INSERT INTO crawl_log (
    job_id,
    website_id,
    step_name,
    log_level,
    message,
    context,
    trace_id
) VALUES (
    sqlc.arg(job_id),
    sqlc.arg(website_id),
    sqlc.arg(step_name),
    COALESCE(sqlc.arg(log_level), 'INFO')::log_level_enum,
    sqlc.arg(message),
    sqlc.arg(context),
    sqlc.arg(trace_id)
)
RETURNING *;

-- name: GetCrawlLogByID :one
SELECT * FROM crawl_log
WHERE id = sqlc.arg(id);

-- name: ListLogsByJob :many
SELECT * FROM crawl_log
WHERE job_id = sqlc.arg(job_id)
    AND log_level = COALESCE(sqlc.arg(log_level), log_level)
ORDER BY created_at DESC
OFFSET sqlc.arg(offset_count) LIMIT sqlc.arg(limit_count);

-- name: CountLogsByJob :one
SELECT COUNT(*) FROM crawl_log
WHERE job_id = sqlc.arg(job_id)
    AND log_level = COALESCE(sqlc.arg(log_level), log_level);

-- name: ListLogsByWebsite :many
SELECT * FROM crawl_log
WHERE website_id = sqlc.arg(website_id)
    AND log_level = COALESCE(sqlc.arg(log_level), log_level)
ORDER BY created_at DESC
OFFSET sqlc.arg(offset_count) LIMIT sqlc.arg(limit_count);

-- name: CountLogsByWebsite :one
SELECT COUNT(*) FROM crawl_log
WHERE website_id = sqlc.arg(website_id)
    AND log_level = COALESCE(sqlc.arg(log_level), log_level);

-- name: ListLogsByTraceID :many
SELECT * FROM crawl_log
WHERE trace_id = sqlc.arg(trace_id)
ORDER BY created_at ASC;

-- name: GetLogsByTimeRange :many
SELECT * FROM crawl_log
WHERE job_id = sqlc.arg(job_id)
    AND created_at >= sqlc.arg(start_time)::TIMESTAMP WITH TIME ZONE
    AND created_at <= sqlc.arg(end_time)::TIMESTAMP WITH TIME ZONE
    AND log_level = COALESCE(sqlc.arg(log_level), log_level)
ORDER BY created_at DESC
OFFSET sqlc.arg(offset_count) LIMIT sqlc.arg(limit_count);

-- name: GetErrorLogs :many
SELECT * FROM crawl_log
WHERE job_id = sqlc.arg(job_id)
    AND log_level IN ('ERROR', 'CRITICAL')
ORDER BY created_at DESC
LIMIT sqlc.arg(limit_count);

-- name: DeleteOldLogs :exec
DELETE FROM crawl_log
WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '30 days';

-- name: DeleteLogsByJob :exec
DELETE FROM crawl_log
WHERE job_id = sqlc.arg(job_id);

-- name: GetLogStatsByJob :one
SELECT
    COUNT(*) as total_logs,
    COUNT(*) FILTER (WHERE log_level = 'DEBUG') as debug_count,
    COUNT(*) FILTER (WHERE log_level = 'INFO') as info_count,
    COUNT(*) FILTER (WHERE log_level = 'WARNING') as warning_count,
    COUNT(*) FILTER (WHERE log_level = 'ERROR') as error_count,
    COUNT(*) FILTER (WHERE log_level = 'CRITICAL') as critical_count
FROM crawl_log
WHERE job_id = sqlc.arg(job_id);
