-- Pipeline runs dimension (placeholder for now until Airflow integration)
WITH source AS (
    SELECT DISTINCT tenant_id FROM {{ ref('stg_bronze_documents') }}
)
SELECT
    MD5('dummy_run_' || COALESCE(tenant_id, 'default')) AS run_id,
    CURRENT_TIMESTAMP AS execution_date,
    'success' AS status,
    tenant_id
FROM source

