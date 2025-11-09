-- name: CreateConfigHistory :one
INSERT INTO website_config_history (
    website_id,
    version,
    config,
    changed_by,
    change_reason
) VALUES (
    sqlc.arg(website_id),
    sqlc.arg(version),
    sqlc.arg(config),
    sqlc.arg(changed_by),
    sqlc.arg(change_reason)
)
RETURNING *;

-- name: GetLatestConfigVersion :one
SELECT COALESCE(MAX(version), 0) AS latest_version
FROM website_config_history
WHERE website_id = sqlc.arg(website_id);

-- name: GetConfigHistory :many
SELECT * FROM website_config_history
WHERE website_id = sqlc.arg(website_id)
ORDER BY version DESC
OFFSET sqlc.arg(offset_count) LIMIT sqlc.arg(limit_count);

-- name: GetConfigByVersion :one
SELECT * FROM website_config_history
WHERE website_id = sqlc.arg(website_id)
  AND version = sqlc.arg(version);
