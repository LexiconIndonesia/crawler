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
WITH job_stats AS (
    SELECT
        website_id,
        COUNT(*) AS total_jobs,
        COUNT(*) FILTER (WHERE status = 'completed') AS completed_jobs,
        COUNT(*) FILTER (WHERE status = 'failed') AS failed_jobs,
        COUNT(*) FILTER (WHERE status = 'cancelled') AS cancelled_jobs,
        MAX(completed_at) FILTER (WHERE status = 'completed') AS last_crawl_at
    FROM crawl_job
    WHERE website_id = sqlc.arg(website_id)
    GROUP BY website_id
),
page_stats AS (
    SELECT
        cj.website_id,
        COUNT(cp.id) AS total_pages_crawled
    FROM crawl_job cj
    JOIN crawled_page cp ON cp.job_id = cj.id
    WHERE cj.website_id = sqlc.arg(website_id)
    GROUP BY cj.website_id
)
SELECT
    COALESCE(js.total_jobs, 0)::INTEGER AS total_jobs,
    COALESCE(js.completed_jobs, 0)::INTEGER AS completed_jobs,
    COALESCE(js.failed_jobs, 0)::INTEGER AS failed_jobs,
    COALESCE(js.cancelled_jobs, 0)::INTEGER AS cancelled_jobs,
    CASE
        WHEN COALESCE(js.total_jobs, 0) = 0 THEN 0.0
        ELSE (COALESCE(js.completed_jobs, 0)::FLOAT / js.total_jobs::FLOAT * 100.0)
    END AS success_rate,
    COALESCE(ps.total_pages_crawled, 0)::INTEGER AS total_pages_crawled,
    js.last_crawl_at
FROM website w
LEFT JOIN job_stats js ON w.id = js.website_id
LEFT JOIN page_stats ps ON w.id = ps.website_id
WHERE w.id = sqlc.arg(website_id);

-- name: DeleteCrawledPagesByWebsite :exec
DELETE FROM crawled_page WHERE website_id = $1;