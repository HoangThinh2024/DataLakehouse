# Design Document: Great Expectations Data Quality Validator

## 1. Overview
Implement a dedicated Data Quality (DQ) layer in the DataLakehouse using Great Expectations (GX). This layer will act as a gatekeeper between the Silver and Gold/Serving layers, ensuring that only high-quality data reaches ClickHouse.

## 2. Architecture
- **Tooling:** Great Expectations (GX) integrated into Mage.ai.
- **Workflow Integration:** A new `data_loader` or `transformer` block in Mage titled `validate_silver_data`.
- **Data Source:** Parquet files stored in the RustFS Silver bucket.
- **Persistence:** Validation results will be logged to the Mage console and can optionally be saved to a `validation_reports` folder in RustFS (General bucket).

## 3. Implementation Details

### A. GX Context
We will use an **Ephemeral Data Context** to avoid complex configuration files in the early stage. The context will be initialized programmatically within the Mage block.

### B. Validation Suite: `silver_excel_suite`
Target Table: `project_reports` (Silver layer)
Rules:
1. `expect_column_values_to_not_be_null` for `Mã công việc (ID)`.
2. `expect_column_values_to_be_unique` for `Mã công việc (ID)`.
3. `expect_column_values_to_be_in_set` for `Trạng thái` (Allowed: 'Đang triển khai', 'Hoàn thành', 'Chưa bắt đầu', 'Tạm dừng').
4. `expect_column_values_to_be_between` for `Số tiền` and `Diện tích (ha)` (Minimum: 0).
5. `expect_column_to_exist` for all core metadata columns (`_extracted_at`, `_source_file_key`).

### C. Error Handling
- **Failure Policy:** If validation fails (Success = False), the block will raise an exception, effectively stopping the downstream `load_excel_to_clickhouse` block.
- **Reporting:** A summary of failed expectations will be printed to the Mage logs.

## 4. Integration Plan
1. Create `mage/transformers/validate_silver_data.py`.
2. Update `mage/pipelines/etl_excel_to_lakehouse/metadata.yaml` to insert the validation block between `excel_silver_to_rustfs` and `load_excel_to_clickhouse`.
3. Test with both valid and intentionally corrupted sample data.

## 5. Future Scalability
- **Data Docs:** In a later phase, we can host GX Data Docs (HTML reports) on a static site or inside the RustFS console.
- **Custom Rules:** Add business-specific rules (e.g., `End Date` must be after `Start Date`).
