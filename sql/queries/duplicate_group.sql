-- Duplicate Group Queries
-- These queries manage duplicate groups and relationships between original and duplicate content.

-- name: CreateDuplicateGroup :one
-- Create a new duplicate group with a canonical page
INSERT INTO duplicate_group (
    canonical_page_id
) VALUES (
    $1
) RETURNING *;

-- name: GetDuplicateGroup :one
-- Get a duplicate group by ID
SELECT * FROM duplicate_group
WHERE id = $1;

-- name: GetDuplicateGroupByCanonicalPage :one
-- Get duplicate group for a canonical page
SELECT * FROM duplicate_group
WHERE canonical_page_id = $1;

-- name: AddDuplicateRelationship :one
-- Add a page as a duplicate to a group
INSERT INTO duplicate_relationship (
    group_id,
    duplicate_page_id,
    detection_method,
    similarity_score,
    confidence_threshold,
    detected_by
) VALUES (
    $1, $2, $3, $4, $5, $6
) RETURNING *;

-- name: GetDuplicateRelationship :one
-- Get a specific duplicate relationship
SELECT * FROM duplicate_relationship
WHERE id = $1;

-- name: GetDuplicateRelationshipByPage :one
-- Check if a page is already marked as duplicate in a group
SELECT * FROM duplicate_relationship
WHERE group_id = $1 AND duplicate_page_id = $2;

-- name: ListDuplicatesInGroup :many
-- List all duplicates in a group with their pages
SELECT
    dr.*,
    cp.url,
    cp.crawled_at,
    cp.content_hash
FROM duplicate_relationship dr
JOIN crawled_page cp ON cp.id = dr.duplicate_page_id
WHERE dr.group_id = $1
ORDER BY dr.detected_at DESC;

-- name: FindDuplicateGroupForPage :one
-- Find which duplicate group a page belongs to (if any)
SELECT dg.*
FROM duplicate_group dg
JOIN duplicate_relationship dr ON dr.group_id = dg.id
WHERE dr.duplicate_page_id = $1;

-- name: GetGroupWithCanonicalPage :one
-- Get group info with canonical page details
SELECT
    dg.*,
    cp.url as canonical_url,
    cp.crawled_at as canonical_crawled_at,
    cp.content_hash as canonical_content_hash
FROM duplicate_group dg
JOIN crawled_page cp ON cp.id = dg.canonical_page_id
WHERE dg.id = $1;

-- name: ListAllDuplicateGroups :many
-- List all duplicate groups with pagination
SELECT * FROM duplicate_group
ORDER BY created_at DESC
LIMIT $1 OFFSET $2;

-- name: GetDuplicateGroupStats :one
-- Get statistics for a duplicate group
SELECT
    dg.id,
    dg.canonical_page_id,
    dg.group_size,
    COUNT(dr.id) as relationship_count,
    AVG(dr.similarity_score) as avg_similarity,
    MIN(dr.detected_at) as first_detected,
    MAX(dr.detected_at) as last_detected
FROM duplicate_group dg
LEFT JOIN duplicate_relationship dr ON dr.group_id = dg.id
WHERE dg.id = $1
GROUP BY dg.id, dg.canonical_page_id, dg.group_size;

-- name: RemoveDuplicateRelationship :exec
-- Remove a duplicate relationship (will trigger group_size update)
DELETE FROM duplicate_relationship
WHERE id = $1;

-- name: RemoveDuplicateGroup :exec
-- Remove an entire duplicate group (CASCADE will remove relationships)
DELETE FROM duplicate_group
WHERE id = $1;

-- name: UpdateDuplicateSimilarityScore :one
-- Update the similarity score for a duplicate relationship
UPDATE duplicate_relationship
SET similarity_score = $2
WHERE id = $1
RETURNING *;

-- name: CountDuplicatesByMethod :many
-- Count duplicates grouped by detection method
SELECT
    detection_method,
    COUNT(*) as count
FROM duplicate_relationship
GROUP BY detection_method
ORDER BY count DESC;

-- name: FindPagesWithoutDuplicateGroup :many
-- Find pages marked as is_duplicate but not in any duplicate_group
SELECT cp.*
FROM crawled_page cp
WHERE cp.is_duplicate = true
  AND NOT EXISTS (
      SELECT 1 FROM duplicate_relationship dr
      WHERE dr.duplicate_page_id = cp.id
  )
LIMIT $1 OFFSET $2;

-- name: GetCanonicalPageForDuplicate :one
-- Get the canonical (original) page for a duplicate
SELECT cp.*
FROM crawled_page cp
JOIN duplicate_group dg ON dg.canonical_page_id = cp.id
JOIN duplicate_relationship dr ON dr.group_id = dg.id
WHERE dr.duplicate_page_id = $1;
