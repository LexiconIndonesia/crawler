-- name: CreateCrawledPage :one
INSERT INTO crawled_page (
    website_id,
    job_id,
    url,
    url_hash,
    content_hash,
    title,
    extracted_content,
    metadata,
    gcs_html_path,
    gcs_documents,
    crawled_at
) VALUES (
    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11
)
RETURNING *;

-- name: GetCrawledPageByID :one
SELECT * FROM crawled_page
WHERE id = $1;

-- name: GetPageByURLHash :one
SELECT * FROM crawled_page
WHERE website_id = $1 AND url_hash = $2;

-- name: GetPageByContentHash :one
SELECT * FROM crawled_page
WHERE content_hash = $1
ORDER BY crawled_at ASC
LIMIT 1;

-- name: ListPagesByJob :many
SELECT * FROM crawled_page
WHERE job_id = $1
ORDER BY crawled_at DESC
LIMIT $2 OFFSET $3;

-- name: CountPagesByJob :one
SELECT COUNT(*) FROM crawled_page
WHERE job_id = $1;

-- name: ListPagesByWebsite :many
SELECT * FROM crawled_page
WHERE website_id = $1
ORDER BY crawled_at DESC
LIMIT $2 OFFSET $3;

-- name: CountPagesByWebsite :one
SELECT COUNT(*) FROM crawled_page
WHERE website_id = $1;

-- name: MarkPageAsDuplicate :one
UPDATE crawled_page
SET
    is_duplicate = true,
    duplicate_of = $2,
    similarity_score = $3
WHERE id = $1
RETURNING *;

-- name: GetDuplicatePages :many
SELECT * FROM crawled_page
WHERE is_duplicate = true
    AND website_id = $1
ORDER BY crawled_at DESC
LIMIT $2 OFFSET $3;

-- name: CountDuplicatePages :one
SELECT COUNT(*) FROM crawled_page
WHERE is_duplicate = true
    AND website_id = $1;

-- name: UpdatePageContent :one
UPDATE crawled_page
SET
    title = COALESCE($2, title),
    extracted_content = COALESCE($3, extracted_content),
    metadata = COALESCE($4, metadata),
    gcs_html_path = COALESCE($5, gcs_html_path),
    gcs_documents = COALESCE($6, gcs_documents)
WHERE id = $1
RETURNING *;

-- name: DeleteOldPages :exec
DELETE FROM crawled_page
WHERE crawled_at < CURRENT_TIMESTAMP - INTERVAL '90 days'
    AND website_id = $1;

-- name: GetPageStats :one
SELECT
    COUNT(*) as total_pages,
    COUNT(*) FILTER (WHERE is_duplicate = false) as unique_pages,
    COUNT(*) FILTER (WHERE is_duplicate = true) as duplicate_pages,
    AVG(similarity_score) FILTER (WHERE is_duplicate = true) as avg_similarity_score
FROM crawled_page
WHERE website_id = $1;
