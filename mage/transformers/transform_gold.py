"""
Transformer – Aggregate Project Silver data into Gold layer.
Calculates project completion rates and workload.
"""

import datetime as dt
import pandas as pd

if 'transformer' not in dir():
    from mage_ai.data_preparation.decorators import transformer
if 'test' not in dir():
    from mage_ai.data_preparation.decorators import test

@transformer
def transform_gold(data, *args, **kwargs):
    if not isinstance(data, dict) or data.get('skip'):
        return data

    df = data['dataframe'].copy()
    run_id = data.get('pipeline_run_id', 'unknown')
    gold_ts = dt.datetime.utcnow().isoformat() + 'Z'
    
    # 0. Robust Column Normalization for Assignee
    assignee_col = 'Người thực hiện'
    if assignee_col not in df.columns:
        # Try to find similar columns if exact match fails
        possible_names = ['assignee', 'người thực hiện', 'người làm', 'nhân sự']
        for col in df.columns:
            if str(col).lower().strip() in possible_names:
                df[assignee_col] = df[col]
                break
    
    if assignee_col not in df.columns:
        df[assignee_col] = 'Chưa phân công'
    else:
        # Fill empty/null with 'Chưa phân công'
        df[assignee_col] = df[assignee_col].fillna('Chưa phân công').replace('', 'Chưa phân công').replace('nan', 'Chưa phân công').replace('None', 'Chưa phân công')

    # 1. Project Summary (by source file/project)
    project_agg = df.groupby('_source_file_key').agg(
        total_tasks=('Mã công việc (ID)', 'count'),
        completed_tasks=('Trạng thái', lambda x: (x == 'Hoàn thành').sum()),
        ongoing_tasks=('Trạng thái', lambda x: (x == 'Đang làm').sum()),
        overdue_tasks=('Trạng thái', lambda x: (x == 'Trễ hạn').sum()),
    ).reset_index()
    
    project_agg['completion_rate'] = (project_agg['completed_tasks'] / project_agg['total_tasks'] * 100).round(2)
    project_agg['_pipeline_run_id'] = run_id
    project_agg['_gold_processed_at'] = gold_ts

    # 2. Assignee Workload
    workload = df.groupby('Người thực hiện').agg(
        task_count=('Mã công việc (ID)', 'count'),
        urgent_tasks=('Khẩn cấp', lambda x: (x == 'Có').sum())
    ).reset_index()
    
    workload['_pipeline_run_id'] = run_id
    workload['_gold_processed_at'] = gold_ts

    print(f"[transform_gold] Projects: {len(project_agg)}, Assignees: {len(workload)}")

    # Preserve all original data (like processed_files, source_key, etc.)
    out_data = data.copy()
    out_data['gold_projects'] = project_agg
    out_data['gold_workload'] = workload
    
    return out_data

@test
def test_output(output, *args):
    # Lenient test: just ensure it is a dict
    assert isinstance(output, dict), 'Output must be a dictionary'
