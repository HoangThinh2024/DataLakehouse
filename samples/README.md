# samples/

This directory contains sample Excel data files used for testing and demonstrating
the `etl_excel_to_lakehouse` pipeline.

## Files

| File | Description |
|------|-------------|
| `Tong hop tien do 12 du an.xlsx` | Summary workbook aggregating progress across all 12 projects |
| `KHOI DA.xlsx` | Project report for Khởi Đầu project |
| `kcn-ninh-diem-2.report.*.xlsx` | Project report: KCN Ninh Điềm 2 |
| `kcn-ninh-diem-3.report.*.xlsx` | Project report: KCN Ninh Điềm 3 |
| `kdc-ninh-long.report.*.xlsx` | Project report: KDC Ninh Long |
| `kdc-ninh-thuy.report.*.xlsx` | Project report: KDC Ninh Thủy |
| `kdt-bac-hon-heo.report.*.xlsx` | Project report: KĐT Bắc Hòn Hèo |
| `kdt-my-a.report.*.xlsx` | Project report: KĐT Mỹ Á |
| `kdt-quoc-anh.report.*.xlsx` | Project report: KĐT Quốc Anh |
| `khu-do-thi-tmdv-bac-ninh-hoa.report.*.xlsx` | Project report: KĐT TMDV Bắc Ninh Hòa |
| `khu-do-thi-tmdv-dong-bac-ninh-hoa-*.report.*.xlsx` | Project report: KĐT TMDV Đông Bắc Ninh Hòa |
| `khu-do-thi-tmdv-nam-van-phong-*.report.*.xlsx` | Project report: KĐT TMDV Nam Vân Phong |
| `mo-khoang-san.report.*.xlsx` | Project report: Mỏ Khoáng Sản |
| `noxh-hoan-cau.report.*.xlsx` | Project report: NOXH Hoàn Cầu |

## Usage

### Manual upload via RustFS Console

1. Open RustFS Console at `http://localhost:29101`.
2. Navigate to bucket `bronze` → folder `excel_upload/`.
3. Upload one or more files from this directory.
4. The realtime watcher (`scripts/realtime_watcher.sh`) will detect the upload and
   trigger the `etl_excel_to_lakehouse` pipeline automatically.

### Manual upload via CLI

```bash
# Set up MinIO client alias
mc alias set local http://localhost:29100 <RUSTFS_ACCESS_KEY> <RUSTFS_SECRET_KEY>

# Upload a single file
mc cp samples/Tong\ hop\ tien\ do\ 12\ du\ an.xlsx local/bronze/excel_upload/

# Upload all files
mc cp samples/*.xlsx local/bronze/excel_upload/
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
