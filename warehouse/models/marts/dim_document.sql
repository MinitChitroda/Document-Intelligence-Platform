WITH source AS (
    SELECT * FROM {{ ref('stg_bronze_documents') }}
)
SELECT
    document_id,
    file_hash,
    version,
    status,
    source_type,
    created_at AS valid_from,
    LEAD(created_at, 1, '9999-12-31'::TIMESTAMP WITH TIME ZONE) OVER (
        PARTITION BY tenant_id, document_id 
        ORDER BY version ASC
    ) AS valid_to,
    CASE 
        WHEN ROW_NUMBER() OVER (
            PARTITION BY tenant_id, document_id 
            ORDER BY version DESC
        ) = 1 THEN TRUE 
        ELSE FALSE 
    END AS is_current,
    tenant_id
FROM source

