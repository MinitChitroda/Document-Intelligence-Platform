WITH source AS (
    SELECT * FROM {{ source('bronze', 'bronze_documents') }}
)
SELECT
    id AS load_id,
    document_id,
    file_hash,
    version,
    status,
    COALESCE(source_type, 'unknown') AS source_type,
    ocr_confidence,
    page_count,
    created_at,
    tenant_id
FROM source

