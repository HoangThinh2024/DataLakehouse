{{ config(materialized='table') }}

with staging as (
    select * from {{ ref('stg_project_reports') }}
),

final as (
    select
        source_file,
        count(task_id) as total_tasks,
        sum(case when status = 'Hoàn thành' then 1 else 0 end) as completed_tasks,
        sum(case when status = 'Đang làm' then 1 else 0 end) as ongoing_tasks,
        sum(case when status = 'Trễ hạn' then 1 else 0 end) as overdue_tasks,
        round(completed_tasks / total_tasks * 100, 2) as completion_rate,
        now() as dbt_processed_at
    from staging
    group by source_file
)

select * from final
