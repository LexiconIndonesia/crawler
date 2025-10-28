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
    COALESCE(sqlc.arg(cron_schedule), '0 0 1,15 * *'),
    sqlc.arg(created_by),
    COALESCE(sqlc.arg(status), 'active'::status_enum)
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

-- name: UpdateWebsiteStatus :one
UPDATE website
SET
    status = sqlc.arg(status),
    updated_at = CURRENT_TIMESTAMP
WHERE id = sqlc.arg(id)
RETURNING *;
