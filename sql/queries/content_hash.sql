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

-- name: UpsertContentHashWithSimhash :one
INSERT INTO content_hash (
    content_hash,
    first_seen_page_id,
    occurrence_count,
    simhash_fingerprint,
    last_seen_at
) VALUES (
    sqlc.arg(content_hash),
    sqlc.arg(first_seen_page_id),
    1,
    sqlc.arg(simhash_fingerprint),
    CURRENT_TIMESTAMP
)
ON CONFLICT (content_hash)
DO UPDATE SET
    occurrence_count = content_hash.occurrence_count + 1,
    simhash_fingerprint = COALESCE(EXCLUDED.simhash_fingerprint, content_hash.simhash_fingerprint),
    last_seen_at = CURRENT_TIMESTAMP
RETURNING *;

-- name: FindSimilarContent :many
-- Find content with similar Simhash fingerprints (within Hamming distance threshold)
-- Uses XOR (#) to find differing bits, converts to bit(64), and counts '1' bits
-- Compatible with PostgreSQL 12+
SELECT *,
    length(replace((simhash_fingerprint # sqlc.arg(target_fingerprint)::BIGINT)::bit(64)::text, '0', '')) as hamming_distance
FROM content_hash
WHERE simhash_fingerprint IS NOT NULL
    AND length(replace((simhash_fingerprint # sqlc.arg(target_fingerprint)::BIGINT)::bit(64)::text, '0', '')) <= sqlc.arg(max_distance)
    AND content_hash != sqlc.arg(exclude_hash)
ORDER BY hamming_distance ASC
LIMIT sqlc.arg(limit_count);

-- name: GetContentHashByFingerprint :one
SELECT * FROM content_hash
WHERE simhash_fingerprint = sqlc.arg(simhash_fingerprint);
