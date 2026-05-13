{{ config(materialized='table') }}

with excel_staging as (
    select * from {{ ref('stg_project_reports') }}
),

cdc_staging as (
    select * from {{ ref('stg_demo_cdc') }}
),

combined as (
    select * from excel_staging
    union all
    select * from cdc_staging
),

final as (
    select
        source_file,
        count(task_id) as total_tasks,
        sum(case when status in ('Hoàn thành', 'Active', 'completed') then 1 else 0 end) as completed_tasks,
        sum(case when status in ('Đang làm', 'New', 'In Progress') then 1 else 0 end) as ongoing_tasks,
        sum(case when status = 'Trễ hạn' then 1 else 0 end) as overdue_tasks,
        if(total_tasks > 0, round(completed_tasks / total_tasks * 100, 2), 0) as completion_rate,
        now() as dbt_processed_at
    from combined
    group by source_file
)

select * from final
