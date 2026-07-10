WITH source AS (
    SELECT DISTINCT source_type, tenant_id FROM {{ ref('stg_bronze_documents') }}
)
SELECT
    source_type,
    CASE
        WHEN source_type IN ('text_pdf', 'text_native') THEN 'Text-Native PDF'
        WHEN source_type IN ('scanned_pdf', 'scanned') THEN 'Scanned PDF'
        WHEN source_type IN ('image') THEN 'Image Document'
        WHEN source_type IN ('csv') THEN 'CSV File'
        ELSE 'Unknown'
    END AS description,
    tenant_id
FROM source


