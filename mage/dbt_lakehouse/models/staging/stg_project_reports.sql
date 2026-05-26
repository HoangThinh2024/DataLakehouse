{{ config(materialized='view') }}

with source as (
    select * from {{ source('clickhouse', 'project_reports') }}
),

renamed as (
    select
        "Mã công việc (ID)" as task_id,
        "Mã công việc cha (ID)" as parent_task_id,
        "Tên công việc" as task_name,
        "Người thực hiện" as assignee,
        "Người giao việc" as assigner,
        case when "Khẩn cấp" in ('Có', 'Yes', 'True', '1', 'true', 'Y') then true else false end as is_urgent,
        "Trạng thái" as status,
        toFloat64OrNull("Số tiền") as amount,
        toFloat64OrNull("Diện tích (ha)") as area_ha,
        "_source_file_key" as source_file,
        "_extracted_at" as extracted_at,
        "_silver_processed_at" as silver_processed_at
    from source
)

select * from renamed
