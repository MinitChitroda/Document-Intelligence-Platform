WITH source AS (
    SELECT * FROM {{ ref('stg_bronze_documents') }}
)
SELECT
    load_id AS processing_id,
    document_id,
    MD5('dummy_run_' || COALESCE(tenant_id, 'default')) AS pipeline_run_id,
    ocr_confidence,
    page_count,
    created_at AS processing_timestamp,
    tenant_id
FROM source

