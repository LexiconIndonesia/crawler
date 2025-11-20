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
    sqlc.arg(website_id),
    sqlc.arg(job_id),
    sqlc.arg(url),
    sqlc.arg(url_hash),
    sqlc.arg(content_hash),
    sqlc.arg(title),
    sqlc.arg(extracted_content),
    sqlc.arg(metadata),
    sqlc.arg(gcs_html_path),
    sqlc.arg(gcs_documents),
    sqlc.arg(crawled_at)
)
ON CONFLICT (website_id, url_hash)
DO UPDATE SET
    job_id = EXCLUDED.job_id,
    content_hash = EXCLUDED.content_hash,
    title = EXCLUDED.title,
    extracted_content = EXCLUDED.extracted_content,
    metadata = EXCLUDED.metadata,
    gcs_html_path = EXCLUDED.gcs_html_path,
    gcs_documents = EXCLUDED.gcs_documents,
    crawled_at = EXCLUDED.crawled_at
RETURNING *;

-- name: GetCrawledPageByID :one
SELECT * FROM crawled_page
WHERE id = sqlc.arg(id);

-- name: GetPageByURLHash :one
SELECT * FROM crawled_page
WHERE website_id = sqlc.arg(website_id) AND url_hash = sqlc.arg(url_hash);

-- name: GetPageByContentHash :one
SELECT * FROM crawled_page
WHERE content_hash = sqlc.arg(content_hash)
ORDER BY crawled_at ASC
LIMIT 1;

-- name: ListPagesByJob :many
SELECT * FROM crawled_page
WHERE job_id = sqlc.arg(job_id)
ORDER BY crawled_at DESC
OFFSET sqlc.arg(offset_count) LIMIT sqlc.arg(limit_count);

-- name: CountPagesByJob :one
SELECT COUNT(*) FROM crawled_page
WHERE job_id = sqlc.arg(job_id);

-- name: ListPagesByWebsite :many
SELECT * FROM crawled_page
WHERE website_id = sqlc.arg(website_id)
ORDER BY crawled_at DESC
OFFSET sqlc.arg(offset_count) LIMIT sqlc.arg(limit_count);

-- name: CountPagesByWebsite :one
SELECT COUNT(*) FROM crawled_page
WHERE website_id = sqlc.arg(website_id);

-- name: MarkPageAsDuplicate :one
UPDATE crawled_page
SET
    is_duplicate = true,
    duplicate_of = sqlc.arg(duplicate_of),
    similarity_score = sqlc.arg(similarity_score)
WHERE id = sqlc.arg(id)
RETURNING *;

-- name: GetDuplicatePages :many
SELECT * FROM crawled_page
WHERE is_duplicate = true
    AND website_id = sqlc.arg(website_id)
ORDER BY crawled_at DESC
OFFSET sqlc.arg(offset_count) LIMIT sqlc.arg(limit_count);

-- name: CountDuplicatePages :one
SELECT COUNT(*) FROM crawled_page
WHERE is_duplicate = true
    AND website_id = sqlc.arg(website_id);

-- name: UpdatePageContent :one
UPDATE crawled_page
SET
    title = COALESCE(sqlc.arg(title), title),
    extracted_content = COALESCE(sqlc.arg(extracted_content), extracted_content),
    metadata = COALESCE(sqlc.arg(metadata), metadata),
    gcs_html_path = COALESCE(sqlc.arg(gcs_html_path), gcs_html_path),
    gcs_documents = COALESCE(sqlc.arg(gcs_documents), gcs_documents)
WHERE id = sqlc.arg(id)
RETURNING *;

-- name: DeleteOldPages :exec
DELETE FROM crawled_page
WHERE crawled_at < CURRENT_TIMESTAMP - INTERVAL '90 days'
    AND website_id = sqlc.arg(website_id);

-- name: GetPageStats :one
SELECT
    COUNT(*) as total_pages,
    COUNT(*) FILTER (WHERE is_duplicate = false) as unique_pages,
    COUNT(*) FILTER (WHERE is_duplicate = true) as duplicate_pages,
    AVG(similarity_score) FILTER (WHERE is_duplicate = true) as avg_similarity_score
FROM crawled_page
WHERE website_id = sqlc.arg(website_id);
