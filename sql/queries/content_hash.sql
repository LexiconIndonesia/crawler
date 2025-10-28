-- name: UpsertContentHash :one
INSERT INTO content_hash (
    content_hash,
    first_seen_page_id,
    occurrence_count,
    last_seen_at
) VALUES (
    sqlc.arg(content_hash),
    sqlc.arg(first_seen_page_id),
    1,
    CURRENT_TIMESTAMP
)
ON CONFLICT (content_hash)
DO UPDATE SET
    occurrence_count = content_hash.occurrence_count + 1,
    last_seen_at = CURRENT_TIMESTAMP
RETURNING *;

-- name: GetContentHash :one
SELECT * FROM content_hash
WHERE content_hash = sqlc.arg(content_hash);

-- name: ListContentHashes :many
SELECT * FROM content_hash
ORDER BY occurrence_count DESC
OFFSET sqlc.arg(offset_count) LIMIT sqlc.arg(limit_count);

-- name: GetMostCommonHashes :many
SELECT * FROM content_hash
WHERE occurrence_count > sqlc.arg(min_count)
ORDER BY occurrence_count DESC
LIMIT sqlc.arg(limit_count);

-- name: GetContentHashStats :one
SELECT
    COUNT(*) as total_hashes,
    SUM(occurrence_count) as total_occurrences,
    AVG(occurrence_count) as avg_occurrences,
    MAX(occurrence_count) as max_occurrences
FROM content_hash;

-- name: DeleteOldContentHashes :exec
DELETE FROM content_hash
WHERE last_seen_at < CURRENT_TIMESTAMP - INTERVAL '90 days';
