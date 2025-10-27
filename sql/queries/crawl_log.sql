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
    $1, $2, $3, COALESCE($4, 'INFO'), $5, $6, $7
)
RETURNING *;

-- name: GetCrawlLogByID :one
SELECT * FROM crawl_log
WHERE id = $1;

-- name: ListLogsByJob :many
SELECT * FROM crawl_log
WHERE job_id = $1
    AND log_level = COALESCE($2, log_level)
ORDER BY created_at DESC
LIMIT $3 OFFSET $4;

-- name: CountLogsByJob :one
SELECT COUNT(*) FROM crawl_log
WHERE job_id = $1
    AND log_level = COALESCE($2, log_level);

-- name: ListLogsByWebsite :many
SELECT * FROM crawl_log
WHERE website_id = $1
    AND log_level = COALESCE($2, log_level)
ORDER BY created_at DESC
LIMIT $3 OFFSET $4;

-- name: CountLogsByWebsite :one
SELECT COUNT(*) FROM crawl_log
WHERE website_id = $1
    AND log_level = COALESCE($2, log_level);

-- name: ListLogsByTraceID :many
SELECT * FROM crawl_log
WHERE trace_id = $1
ORDER BY created_at ASC;

-- name: GetLogsByTimeRange :many
SELECT * FROM crawl_log
WHERE job_id = $1
    AND created_at >= $2::TIMESTAMP WITH TIME ZONE
    AND created_at <= $3::TIMESTAMP WITH TIME ZONE
    AND log_level = COALESCE($4, log_level)
ORDER BY created_at DESC
LIMIT $5 OFFSET $6;

-- name: GetErrorLogs :many
SELECT * FROM crawl_log
WHERE job_id = $1
    AND log_level IN ('ERROR', 'CRITICAL')
ORDER BY created_at DESC
LIMIT $2;

-- name: DeleteOldLogs :exec
DELETE FROM crawl_log
WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '30 days';

-- name: DeleteLogsByJob :exec
DELETE FROM crawl_log
WHERE job_id = $1;

-- name: GetLogStatsByJob :one
SELECT
    COUNT(*) as total_logs,
    COUNT(*) FILTER (WHERE log_level = 'DEBUG') as debug_count,
    COUNT(*) FILTER (WHERE log_level = 'INFO') as info_count,
    COUNT(*) FILTER (WHERE log_level = 'WARNING') as warning_count,
    COUNT(*) FILTER (WHERE log_level = 'ERROR') as error_count,
    COUNT(*) FILTER (WHERE log_level = 'CRITICAL') as critical_count
FROM crawl_log
WHERE job_id = $1;
