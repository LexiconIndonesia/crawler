-- name: CreateWebsite :one
INSERT INTO website (
    name,
    base_url,
    config,
    created_by,
    status
) VALUES (
    $1, $2, $3, $4, COALESCE($5, 'active'::status_enum)
)
RETURNING *;

-- name: GetWebsiteByID :one
SELECT * FROM website
WHERE id = $1;

-- name: GetWebsiteByName :one
SELECT * FROM website
WHERE name = $1;

-- name: ListWebsites :many
SELECT * FROM website
WHERE status = COALESCE($1, status)
ORDER BY created_at DESC
LIMIT $2 OFFSET $3;

-- name: CountWebsites :one
SELECT COUNT(*) FROM website
WHERE status = COALESCE($1, status);

-- name: UpdateWebsite :one
UPDATE website
SET
    name = COALESCE($2, name),
    base_url = COALESCE($3, base_url),
    config = COALESCE($4, config),
    status = COALESCE($5, status),
    updated_at = CURRENT_TIMESTAMP
WHERE id = $1
RETURNING *;

-- name: DeleteWebsite :exec
DELETE FROM website
WHERE id = $1;

-- name: UpdateWebsiteStatus :one
UPDATE website
SET
    status = $2,
    updated_at = CURRENT_TIMESTAMP
WHERE id = $1
RETURNING *;
