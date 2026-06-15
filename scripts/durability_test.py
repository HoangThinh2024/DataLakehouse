#!/usr/bin/env python3
"""
Durability and Stability Test for DataLakehouse (Direct S3 Ingestion).

This script:
1. Cleans up existing watcher processes.
2. Starts a fresh instance of realtime_watcher.sh.
3. Performs stress/load tests by uploading multiple unique files directly to S3 (RustFS).
4. Verifies database row counts in ClickHouse before and after.
5. Asserts that the correct pipelines are triggered without duplicate runs or errors.
6. Cleans up resources and logs results.
"""

import os
import sys
import time
import subprocess
import uuid
import boto3
from botocore.client import Config as BotoConfig
from clickhouse_driver import Client
from dotenv import load_dotenv

# Setup paths
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

load_dotenv(os.path.join(REPO_ROOT, ".env"))

# Sample source files
SOURCE_EXCEL = os.path.join(
    REPO_ROOT, "scripts/test_data/noxh-hoan-cau.report.10.58.10.04.26.xlsx"
)
SOURCE_CSV = os.path.join(REPO_ROOT, "scripts/test_data/test.csv")
WATCHER_LOG = os.path.join(REPO_ROOT, "watcher_test.log")


def get_ch_client():
    ch_host = os.getenv("CLICKHOUSE_HOST", "localhost")
    if ch_host == "dlh-clickhouse":
        ch_host = "localhost"
    return Client(
        host=ch_host,
        port=int(os.getenv("CLICKHOUSE_TCP_PORT", "29000")),
        database=os.getenv("CLICKHOUSE_DB", "analytics"),
        user=os.getenv("CLICKHOUSE_USER", "default"),
        password=os.getenv("CLICKHOUSE_PASSWORD", "") or "",
        connect_timeout=10,
    )


def get_s3_client():
    rustfs_endpoint = os.getenv(
        "RUSTFS_EXTERNAL_ENDPOINT",
        os.getenv("RUSTFS_ENDPOINT_URL", "http://localhost:29100"),
    )
    if "dlh-rustfs" in rustfs_endpoint:
        rustfs_endpoint = rustfs_endpoint.replace("dlh-rustfs:9000", "localhost:29100")
    return boto3.client(
        "s3",
        endpoint_url=rustfs_endpoint,
        aws_access_key_id=os.getenv("RUSTFS_ACCESS_KEY", "doe"),
        aws_secret_access_key=os.getenv("RUSTFS_SECRET_KEY", "change-me-in-production"),
        config=BotoConfig(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def get_row_counts(client):
    try:
        reports_count = client.execute("SELECT count() FROM project_reports")[0][0]
        summary_count = client.execute("SELECT count() FROM fct_projects_summary")[0][0]
        return reports_count, summary_count
    except Exception as e:
        print(f"Error querying ClickHouse: {e}")
        return 0, 0


def cleanup_watchers():
    print("Stopping any running watcher processes...")
    subprocess.run("pkill -f realtime_watcher.sh", shell=True)
    time.sleep(2)


def main():
    print("=" * 60)
    print("DATALAKEHOUSE STABILITY & DURABILITY LOAD TEST (DIRECT S3)")
    print("=" * 60)

    ch_client = get_ch_client()
    s3_client = get_s3_client()
    bucket = os.getenv("RUSTFS_BRONZE_BUCKET", "bronze")

    reports_before, summary_before = get_row_counts(ch_client)
    print(f"Baseline ClickHouse Counts:")
    print(f"  - project_reports: {reports_before} rows")
    print(f"  - fct_projects_summary: {summary_before} rows")

    cleanup_watchers()

    # Clear target log
    if os.path.exists(WATCHER_LOG):
        os.remove(WATCHER_LOG)

    # Start watcher redirecting to test log
    print("Starting realtime_watcher.sh in background...")
    watcher_cmd = f"./scripts/realtime_watcher.sh > {WATCHER_LOG} 2>&1 &"
    subprocess.run(watcher_cmd, shell=True, cwd=REPO_ROOT)
    time.sleep(5)  # Wait for boot

    # Ingest 2 Excel files and 1 CSV file directly to S3 over time, sleeping 15s between each
    # to guarantee separate polling cycles.
    excel_keys = []
    csv_keys = []

    print("\nSimulating direct S3 uploads (2 Excel, 1 CSV)...")
    for i in range(2):
        unique_name = f"durability_excel_test_{i}_{uuid.uuid4().hex[:6]}.xlsx"
        object_key = f"Data Mẫu 12 dự án/{unique_name}"
        s3_client.upload_file(SOURCE_EXCEL, bucket, object_key)
        excel_keys.append(object_key)
        print(f"  [+] Uploaded Excel to S3: {object_key}")
        time.sleep(15)

    for i in range(1):
        unique_name = f"durability_csv_test_{i}_{uuid.uuid4().hex[:6]}.csv"
        object_key = f"csv_upload/{unique_name}"
        s3_client.upload_file(SOURCE_CSV, bucket, object_key)
        csv_keys.append(object_key)
        print(f"  [+] Uploaded CSV to S3: {object_key}")
        time.sleep(15)

    print(
        "\nWaiting for S3 watcher and Mage pipelines to complete execution (40 seconds)..."
    )
    for sec in range(4):
        time.sleep(10)
        print(f"  ... {10 * (sec + 1)} seconds elapsed")

    # Read ClickHouse counts after
    reports_after, summary_after = get_row_counts(ch_client)
    print(f"\nPost-Test ClickHouse Counts:")
    print(f"  - project_reports: {reports_after} rows")
    print(f"  - fct_projects_summary: {summary_after} rows")

    # Read watcher logs
    print("\nAuditing Execution Logs...")
    if not os.path.exists(WATCHER_LOG):
        print("[-] Error: Watcher log not found!")
        sys.exit(1)

    with open(WATCHER_LOG, "r") as f:
        log_content = f.read()

    excel_triggers = log_content.count(
        "Triggering Mage Pipeline: etl_excel_to_lakehouse"
    )
    csv_triggers = log_content.count(
        "Triggering Mage Pipeline: etl_csv_upload_to_reporting"
    )
    errors = log_content.count("failed!")
    dbt_runs = log_content.count("dbt run completed successfully")

    print(f"Watcher Stats:")
    print(f"  - Excel Pipeline Triggers: {excel_triggers} (Expected: 2)")
    print(f"  - CSV Pipeline Triggers: {csv_triggers} (Expected: 1)")
    print(f"  - pipeline/ingestion errors detected: {errors} (Expected: 0)")
    print(f"  - Successful DBT runs: {dbt_runs}")

    # Clean up the uploaded S3 keys
    print("\nCleaning up test S3 files...")
    for key in excel_keys + csv_keys:
        try:
            s3_client.delete_object(Bucket=bucket, Key=key)
            print(f"  [-] Deleted S3 object: {key}")
        except Exception as e:
            print(f"  [-] Failed to delete S3 object {key}: {e}")

    cleanup_watchers()

    # Evaluation
    success = True
    if excel_triggers != 2:
        print("[-] Failure: Excel pipeline was not triggered exactly 2 times!")
        success = False
    if csv_triggers != 1:
        print("[-] Failure: CSV pipeline was not triggered exactly 1 times!")
        success = False
    if errors > 0:
        print("[-] Failure: Watcher logged execution errors!")
        success = False
    if reports_after <= reports_before:
        print("[-] Failure: Row count in ClickHouse did not increase!")
        success = False

    if success:
        print("\n" + "=" * 60)
        print("DURABILITY & STABILITY TEST: PASSED ✅")
        print("=" * 60)
        sys.exit(0)
    else:
        print("\n" + "=" * 60)
        print("DURABILITY & STABILITY TEST: FAILED ❌")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
