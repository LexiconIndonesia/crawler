-- name: UpsertContentHash :one
INSERT INTO content_hash (
    content_hash,
    first_seen_page_id,
    occurrence_count,
    last_seen_at
) VALUES (
    $1, $2, 1, CURRENT_TIMESTAMP
)
ON CONFLICT (content_hash)
DO UPDATE SET
    occurrence_count = content_hash.occurrence_count + 1,
    last_seen_at = CURRENT_TIMESTAMP
RETURNING *;

-- name: GetContentHash :one
SELECT * FROM content_hash
WHERE content_hash = $1;

-- name: ListContentHashes :many
SELECT * FROM content_hash
ORDER BY occurrence_count DESC
LIMIT $1 OFFSET $2;

-- name: GetMostCommonHashes :many
SELECT * FROM content_hash
WHERE occurrence_count > $1
ORDER BY occurrence_count DESC
LIMIT $2;

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
