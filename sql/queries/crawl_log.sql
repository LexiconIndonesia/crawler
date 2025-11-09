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
    sqlc.arg(log_level),
    sqlc.arg(message),
    sqlc.arg(context),
    sqlc.arg(trace_id)
)
RETURNING *;

-- name: GetCrawlLogByID :one
SELECT
    id,
    job_id,
    website_id,
    step_name,
    log_level,
    message,
    context,
    trace_id,
    created_at
FROM crawl_log
WHERE id = sqlc.arg(id);

-- name: ListLogsByJob :many
SELECT
    id,
    job_id,
    website_id,
    step_name,
    log_level,
    message,
    context,
    trace_id,
    created_at
FROM crawl_log
WHERE job_id = sqlc.arg(job_id)
    AND log_level = COALESCE(sqlc.arg(log_level), log_level)
ORDER BY created_at DESC
OFFSET sqlc.arg(offset_count) LIMIT sqlc.arg(limit_count);

-- name: CountLogsByJob :one
SELECT COUNT(*) FROM crawl_log
WHERE job_id = sqlc.arg(job_id)
    AND log_level = COALESCE(sqlc.arg(log_level), log_level);

-- name: ListLogsByWebsite :many
SELECT
    id,
    job_id,
    website_id,
    step_name,
    log_level,
    message,
    context,
    trace_id,
    created_at
FROM crawl_log
WHERE website_id = sqlc.arg(website_id)
    AND log_level = COALESCE(sqlc.arg(log_level), log_level)
ORDER BY created_at DESC
OFFSET sqlc.arg(offset_count) LIMIT sqlc.arg(limit_count);

-- name: CountLogsByWebsite :one
SELECT COUNT(*) FROM crawl_log
WHERE website_id = sqlc.arg(website_id)
    AND log_level = COALESCE(sqlc.arg(log_level), log_level);

-- name: ListLogsByTraceID :many
SELECT
    id,
    job_id,
    website_id,
    step_name,
    log_level,
    message,
    context,
    trace_id,
    created_at
FROM crawl_log
WHERE trace_id = sqlc.arg(trace_id)
ORDER BY created_at ASC;

-- name: GetLogsByTimeRange :many
SELECT
    id,
    job_id,
    website_id,
    step_name,
    log_level,
    message,
    context,
    trace_id,
    created_at
FROM crawl_log
WHERE job_id = sqlc.arg(job_id)
    AND created_at >= sqlc.arg(start_time)::TIMESTAMP WITH TIME ZONE
    AND created_at <= sqlc.arg(end_time)::TIMESTAMP WITH TIME ZONE
    AND log_level = COALESCE(sqlc.arg(log_level), log_level)
ORDER BY created_at DESC
OFFSET sqlc.arg(offset_count) LIMIT sqlc.arg(limit_count);

-- name: GetErrorLogs :many
SELECT
    id,
    job_id,
    website_id,
    step_name,
    log_level,
    message,
    context,
    trace_id,
    created_at
FROM crawl_log
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

-- name: StreamLogsByJob :many
SELECT
    id,
    job_id,
    website_id,
    step_name,
    log_level,
    message,
    context,
    trace_id,
    created_at
FROM crawl_log
WHERE job_id = sqlc.arg(job_id)
    AND created_at > sqlc.arg(after_timestamp)::TIMESTAMP WITH TIME ZONE
    AND log_level = COALESCE(sqlc.arg(log_level), log_level)
ORDER BY created_at ASC
LIMIT sqlc.arg(limit_count);

-- name: GetLogsAfterID :many
SELECT
    id,
    job_id,
    website_id,
    step_name,
    log_level,
    message,
    context,
    trace_id,
    created_at
FROM crawl_log
WHERE job_id = sqlc.arg(job_id)
    AND id > sqlc.arg(after_log_id)
    AND log_level = COALESCE(sqlc.arg(log_level), log_level)
ORDER BY id ASC
LIMIT sqlc.arg(limit_count);

-- name: GetJobLogsFiltered :many
SELECT
    id,
    job_id,
    website_id,
    step_name,
    log_level,
    message,
    context,
    trace_id,
    created_at,
    COUNT(*) OVER() as total_count
FROM crawl_log
WHERE job_id = sqlc.arg(job_id)
    AND log_level = COALESCE(sqlc.arg(log_level), log_level)
    AND (sqlc.arg(start_time)::TIMESTAMP WITH TIME ZONE IS NULL OR created_at >= sqlc.arg(start_time)::TIMESTAMP WITH TIME ZONE)
    AND (sqlc.arg(end_time)::TIMESTAMP WITH TIME ZONE IS NULL OR created_at <= sqlc.arg(end_time)::TIMESTAMP WITH TIME ZONE)
    AND (sqlc.arg(search_text)::TEXT IS NULL OR message ILIKE '%' || sqlc.arg(search_text)::TEXT || '%')
ORDER BY created_at ASC
OFFSET sqlc.arg(offset_count) LIMIT sqlc.arg(limit_count);

-- name: CountJobLogsFiltered :one
SELECT COUNT(*) FROM crawl_log
WHERE job_id = sqlc.arg(job_id)
    AND log_level = COALESCE(sqlc.arg(log_level), log_level)
    AND (sqlc.arg(start_time)::TIMESTAMP WITH TIME ZONE IS NULL OR created_at >= sqlc.arg(start_time)::TIMESTAMP WITH TIME ZONE)
    AND (sqlc.arg(end_time)::TIMESTAMP WITH TIME ZONE IS NULL OR created_at <= sqlc.arg(end_time)::TIMESTAMP WITH TIME ZONE)
    AND (sqlc.arg(search_text)::TEXT IS NULL OR message ILIKE '%' || sqlc.arg(search_text)::TEXT || '%');
