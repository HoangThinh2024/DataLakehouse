# samples/

This directory contains documentation and usage instructions for the sample Excel data files.

> [!NOTE]
> The actual Excel files for the 12 projects have been ingested and are stored directly in the RustFS (S3-compatible) `bronze` bucket under the `Data sample/` prefix.

## Usage

### Direct Upload via RustFS Console

1. Open RustFS Console at `http://localhost:29101`.
2. Navigate to the `bronze` bucket.
3. Upload one or more Excel (`.xlsx`) files under the `Data Mẫu 12 dự án/` prefix or CSV (`.csv`) files under the `csv_upload/` prefix.
4. The real-time watcher (`scripts/realtime_watcher.sh`) will automatically detect the upload in S3 and trigger the corresponding Mage pipeline (`etl_excel_to_lakehouse` or `etl_csv_upload_to_reporting`).

### Direct Upload via CLI (MinIO Client)

```bash
# Set up MinIO client alias
mc alias set local http://localhost:29100 <RUSTFS_ACCESS_KEY> <RUSTFS_SECRET_KEY>

# Upload a file to the S3 bronze bucket
mc cp my_report.xlsx "local/bronze/Data Mẫu 12 dự án/"
```

### Expected ClickHouse output

After the pipeline runs, data appears in:

| Table | Description |
|-------|-------------|
| `analytics.project_reports` | Detailed task rows (one row per task per project) |
| `analytics.gold_projects_summary` | Per-project KPI rollup |
| `analytics.gold_workload_report` | Per-person workload summary |

Verify:

```sql
SELECT _source_file_key, count() AS tasks
FROM analytics.project_reports
GROUP BY _source_file_key
ORDER BY _source_file_key;
```

## Expected Excel Schema

Each project report file must contain a sheet with these columns
(column names are case-insensitive, leading/trailing spaces are stripped):

| Column (Vietnamese) | Description |
|--------------------|-------------|
| `Mã công việc (ID)` | Unique task identifier |
| `Tên công việc` | Task description |
| `Trạng thái` | Status: `Hoàn thành`, `Đang làm`, `Trễ hạn`, `Chưa làm` |
| `Người thực hiện` | Assigned person (auto-filled with `Chưa phân công` if missing) |
| `Khẩn cấp` | Urgent flag: `Có` / `Không` |

Rows with empty `Mã công việc (ID)` are automatically skipped (junk/header rows).
