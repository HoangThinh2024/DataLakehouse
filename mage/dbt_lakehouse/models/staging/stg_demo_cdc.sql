{{ config(materialized='view') }}

with source as (
    select * from {{ source('clickhouse', 'silver_demo') }}
),

standardized as (
    select
        toString(id) as task_id,
        '' as parent_task_id,
        name as task_name,
        customer_email as assignee,
        '' as assigner,
        false as is_urgent,
        status as status,
        value as amount,
        toFloat64(quantity) as area_ha,
        _source_table as source_file,
        created_at as extracted_at,
        _silver_processed_at as silver_processed_at
    from source
    where _pipeline_run_id = 'realtime-rpc-optimized'
)

select * from standardized
