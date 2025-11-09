-- name: CreateWebsite :one
INSERT INTO website (
    name,
    base_url,
    config,
    cron_schedule,
    created_by,
    status
) VALUES (
    sqlc.arg(name),
    sqlc.arg(base_url),
    sqlc.arg(config),
    sqlc.arg(cron_schedule),
    sqlc.arg(created_by),
    sqlc.arg(status)
)
RETURNING *;

-- name: GetWebsiteByID :one
SELECT * FROM website
WHERE id = sqlc.arg(id);

-- name: GetWebsiteByName :one
SELECT * FROM website
WHERE name = sqlc.arg(name);

-- name: ListWebsites :many
SELECT * FROM website
WHERE status = COALESCE(sqlc.arg(status), status)
ORDER BY created_at DESC
OFFSET sqlc.arg(offset_count) LIMIT sqlc.arg(limit_count);

-- name: CountWebsites :one
SELECT COUNT(*) FROM website
WHERE status = COALESCE(sqlc.arg(status), status);

-- name: UpdateWebsite :one
UPDATE website
SET
    name = COALESCE(sqlc.arg(name), name),
    base_url = COALESCE(sqlc.arg(base_url), base_url),
    config = COALESCE(sqlc.arg(config), config),
    cron_schedule = COALESCE(sqlc.arg(cron_schedule), cron_schedule),
    status = COALESCE(sqlc.arg(status), status),
    updated_at = CURRENT_TIMESTAMP
WHERE id = sqlc.arg(id)
RETURNING *;

-- name: DeleteWebsite :exec
DELETE FROM website
WHERE id = sqlc.arg(id);

-- name: SoftDeleteWebsite :one
UPDATE website
SET
    deleted_at = CURRENT_TIMESTAMP,
    status = 'inactive',
    updated_at = CURRENT_TIMESTAMP
WHERE id = sqlc.arg(id)
  AND deleted_at IS NULL
RETURNING *;

-- name: UpdateWebsiteStatus :one
UPDATE website
SET
    status = sqlc.arg(status),
    updated_at = CURRENT_TIMESTAMP
WHERE id = sqlc.arg(id)
RETURNING *;

-- name: GetWebsiteStatistics :one
SELECT
    COALESCE(COUNT(cj.id), 0)::INTEGER AS total_jobs,
    COALESCE(COUNT(cj.id) FILTER (WHERE cj.status = 'completed'), 0)::INTEGER AS completed_jobs,
    COALESCE(COUNT(cj.id) FILTER (WHERE cj.status = 'failed'), 0)::INTEGER AS failed_jobs,
    COALESCE(COUNT(cj.id) FILTER (WHERE cj.status = 'cancelled'), 0)::INTEGER AS cancelled_jobs,
    CASE
        WHEN COUNT(cj.id) = 0 THEN 0.0
        ELSE (COUNT(cj.id) FILTER (WHERE cj.status = 'completed')::FLOAT / COUNT(cj.id)::FLOAT * 100.0)
    END AS success_rate,
    COALESCE(SUM((
        SELECT COUNT(*)
        FROM crawled_page cp
        WHERE cp.job_id = cj.id
    )), 0)::INTEGER AS total_pages_crawled,
    MAX(cj.completed_at) FILTER (WHERE cj.status = 'completed') AS last_crawl_at
FROM website w
LEFT JOIN crawl_job cj ON cj.website_id = w.id
WHERE w.id = sqlc.arg(website_id)
GROUP BY w.id;
