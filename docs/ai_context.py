"""
DataLakehouse – AI/LLM Semantic Context
========================================
This file provides structured metadata about the DataLakehouse ClickHouse schema
to help AI assistants (Gemini CLI, GitHub Copilot, etc.) understand table semantics
and generate accurate SQL or data analysis code.

How to use:
  - Reference this file in your AI assistant's context window.
  - Import METADATA in any Python script that needs schema awareness.
  - The 'tables' list mirrors the live ClickHouse 'analytics' database schema.

Related files:
  - docs/ARCHITECTURE.md       — full system architecture and data flow
  - docs/PIPELINE_GUIDE.md     — ETL pipeline block details
  - clickhouse/init/001_analytics_schema.sql  — full DDL
"""

# ─── Database: analytics ──────────────────────────────────────────────────────
# Connection: http://dlh-clickhouse:8123 (internal) or http://localhost:28123 (host)
# Engine default: ReplacingMergeTree (all tables support idempotent re-ingestion)

METADATA = {
    "database": "analytics",
    "connection": {
        "host": "dlh-clickhouse",
        "http_port": 8123,
        "tcp_port": 9000,
        "host_http_port": 28123,  # exposed on host
    },
    "tables": [
        # ── PostgreSQL / demo pipeline tables ───────────────────────────────
        {
            "name": "silver_demo",
            "layer": "silver",
            "pipeline": "etl_postgres_to_lakehouse",
            "description": "Cleaned, typed rows extracted from the PostgreSQL source table. "
                           "Each row represents one order/record with lineage metadata.",
            "columns": {
                "id": "Unique row identifier (from source)",
                "name": "Record name or customer name",
                "value": "Numeric value (order amount, metric, etc.)",
                "region": "Geographic region label",
                "category": "Product or data category",
                "created_at": "Original creation timestamp from source",
                "_pipeline_run_id": "UUID of the ETL run that produced this row",
                "_source_table": "Source table name in PostgreSQL",
                "_extracted_at": "Timestamp when data was extracted from source",
                "_silver_processed_at": "Timestamp when Silver transform completed",
            },
        },
        {
            "name": "gold_demo_daily",
            "layer": "gold",
            "pipeline": "etl_postgres_to_lakehouse",
            "description": "Daily aggregated sales/metrics. One row per calendar day.",
            "columns": {
                "order_date": "DATE — the aggregation day",
                "total_value": "Sum of 'value' for that day",
                "record_count": "Number of records for that day",
                "avg_value": "Average value for that day",
                "_pipeline_run_id": "UUID of the ETL run",
                "_gold_processed_at": "Timestamp when Gold aggregation completed",
            },
        },
        {
            "name": "gold_demo_weekly",
            "layer": "gold",
            "pipeline": "etl_postgres_to_lakehouse",
            "description": "Weekly aggregated metrics (ISO week). One row per week.",
            "columns": {
                "week_start": "DATE — Monday of the ISO week",
                "total_value": "Sum of 'value' for that week",
                "record_count": "Number of records for that week",
                "_pipeline_run_id": "UUID of the ETL run",
            },
        },
        {
            "name": "gold_demo_monthly",
            "layer": "gold",
            "pipeline": "etl_postgres_to_lakehouse",
            "description": "Monthly aggregated metrics. One row per year-month.",
            "columns": {
                "year": "INTEGER — calendar year",
                "month": "INTEGER — calendar month (1–12)",
                "total_value": "Sum of 'value' for that month",
                "record_count": "Number of records for that month",
                "_pipeline_run_id": "UUID of the ETL run",
            },
        },
        {
            "name": "gold_demo_yearly",
            "layer": "gold",
            "pipeline": "etl_postgres_to_lakehouse",
            "description": "Yearly aggregated metrics. One row per year.",
            "columns": {
                "year": "INTEGER — calendar year",
                "total_value": "Sum of 'value' for that year",
                "record_count": "Number of records for that year",
                "_pipeline_run_id": "UUID of the ETL run",
            },
        },
        {
            "name": "gold_demo_by_region",
            "layer": "gold",
            "pipeline": "etl_postgres_to_lakehouse",
            "description": "Metrics grouped by geographic region.",
            "columns": {
                "region": "Region label",
                "total_value": "Sum of 'value' for that region",
                "record_count": "Number of records in that region",
                "_pipeline_run_id": "UUID of the ETL run",
            },
        },
        {
            "name": "gold_demo_by_category",
            "layer": "gold",
            "pipeline": "etl_postgres_to_lakehouse",
            "description": "Metrics grouped by product/data category.",
            "columns": {
                "category": "Category label",
                "total_value": "Sum of 'value' for that category",
                "record_count": "Number of records in that category",
                "_pipeline_run_id": "UUID of the ETL run",
            },
        },
        {
            "name": "pipeline_runs",
            "layer": "monitoring",
            "pipeline": "all",
            "description": "Execution log for all ETL pipeline runs. "
                           "Used by Grafana monitoring dashboard.",
            "columns": {
                "run_id": "UUID identifying the pipeline run",
                "pipeline_name": "Name of the Mage pipeline",
                "status": "Run status: 'success' | 'error' | 'running'",
                "rows_loaded": "Number of rows loaded in this run",
                "error_message": "Error detail if status = 'error', else NULL",
                "started_at": "Run start timestamp",
                "completed_at": "Run completion timestamp",
            },
        },
        # ── Excel pipeline tables (12 project reports) ──────────────────────
        {
            "name": "project_reports",
            "layer": "silver",
            "pipeline": "etl_excel_to_lakehouse",
            "description": "Detailed task rows from the 12 uploaded Excel project reports. "
                           "Use this table to look up task status, assigned person, and urgency.",
            "columns": {
                "_source_file_key": "Project name or original Excel filename",
                "Mã công việc (ID)": "Unique task identifier within the project",
                "Tên công việc": "Short description of the task",
                "Trạng thái": "Current status: Hoàn thành | Đang làm | Trễ hạn | Chưa làm",
                "Người thực hiện": "Assigned staff member (defaults to 'Chưa phân công' if missing)",
                "Khẩn cấp": "Urgency flag: Có (yes) | Không (no)",
                "_db_processed_at": "Timestamp when this row was loaded into ClickHouse",
            },
        },
        {
            "name": "gold_projects_summary",
            "layer": "gold",
            "pipeline": "etl_excel_to_lakehouse",
            "description": "KPI rollup per project. Use to compare completion rates across projects.",
            "columns": {
                "_source_file_key": "Project name or original Excel filename",
                "total_tasks": "Total number of tasks in the project",
                "completed_tasks": "Number of tasks with status = Hoàn thành",
                "completion_rate": "Completion rate as a decimal (0.0 – 1.0)",
                "overdue_tasks": "Number of tasks with status = Trễ hạn",
                "in_progress_tasks": "Number of tasks with status = Đang làm",
            },
        },
        {
            "name": "gold_workload_report",
            "layer": "gold",
            "pipeline": "etl_excel_to_lakehouse",
            "description": "Workload summary per assigned person across all projects.",
            "columns": {
                "Người thực hiện": "Name of the staff member",
                "task_count": "Total number of tasks assigned to this person",
                "urgent_tasks": "Number of urgent tasks (Khẩn cấp = Có)",
                "overdue_tasks": "Number of overdue tasks assigned to this person",
            },
        },
        # ── CSV pipeline tables ──────────────────────────────────────────────
        {
            "name": "csv_clean_rows",
            "layer": "silver",
            "pipeline": "etl_csv_upload_to_reporting",
            "description": "Cleaned and normalised rows from CSV file uploads. "
                           "Schema varies based on the uploaded CSV columns.",
            "columns": {
                "_source_file_key": "Original CSV filename",
                "_db_processed_at": "Timestamp when this row was loaded into ClickHouse",
                "...": "All other columns are taken directly from the CSV headers",
            },
        },
    ],
    # ── Example queries ──────────────────────────────────────────────────────
    "example_queries": [
        {
            "description": "Compare project completion rates",
            "sql": (
                "SELECT _source_file_key AS project, "
                "round(completion_rate * 100, 1) AS completion_pct, "
                "overdue_tasks "
                "FROM analytics.gold_projects_summary "
                "ORDER BY completion_pct DESC"
            ),
        },
        {
            "description": "Find staff with the most overdue tasks",
            "sql": (
                "SELECT \"Người thực hiện\", overdue_tasks, task_count "
                "FROM analytics.gold_workload_report "
                "ORDER BY overdue_tasks DESC LIMIT 10"
            ),
        },
        {
            "description": "Daily revenue trend (last 30 days)",
            "sql": (
                "SELECT order_date, total_value, record_count "
                "FROM analytics.gold_demo_daily "
                "WHERE order_date >= today() - 30 "
                "ORDER BY order_date"
            ),
        },
        {
            "description": "Latest pipeline run status",
            "sql": (
                "SELECT pipeline_name, status, rows_loaded, started_at "
                "FROM analytics.pipeline_runs "
                "ORDER BY started_at DESC LIMIT 10"
            ),
        },
    ],
}
