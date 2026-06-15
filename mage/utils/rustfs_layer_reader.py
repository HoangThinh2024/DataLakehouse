"""
RustFS Lake Layer Reader – Utility to read latest data from Bronze/Silver/Gold layers.

Handles:
- Listing parquet files from a given layer (bucket/prefix)
- Reading latest dated partition
- Combining multiple run_id parquet files into single DataFrame
- Consistent timestamp handling across layers
"""

import os
import io
import datetime as dt
from typing import Optional

import boto3
import pandas as pd
from botocore.client import Config as BotoConfig
from botocore.exceptions import ClientError


def _s3_client():
    """Create S3 client for RustFS."""
    return boto3.client(
        "s3",
        endpoint_url=os.getenv("RUSTFS_ENDPOINT_URL", "http://dlh-rustfs:9000"),
        aws_access_key_id=os.getenv("RUSTFS_ACCESS_KEY", "rustfsadmin"),
        aws_secret_access_key=os.getenv("RUSTFS_SECRET_KEY", "rustfsadmin"),
        region_name=os.getenv("RUSTFS_REGION", "us-east-1"),
        config=BotoConfig(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
        ),
    )


def list_layer_partitions(bucket: str, prefix: str) -> list[str]:
    """
    List all dt=YYYY-MM-DD partitions under a layer prefix.
    Returns sorted list of dates (newest first).
    """
    client = _s3_client()
    partitions = set()

    try:
        paginator = client.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=bucket, Prefix=prefix)

        for page in pages:
            if "Contents" not in page:
                continue
            for obj in page["Contents"]:
                key = obj["Key"]
                # Extract dt=YYYY-MM-DD from path
                if "/dt=" in key:
                    parts = key.split("/dt=")
                    if len(parts) > 1:
                        date_part = parts[1].split("/")[0]
                        partitions.add(date_part)
    except ClientError:
        pass

    return sorted(partitions, reverse=True)


def read_latest_layer(
    bucket: str, prefix: str, date_str: Optional[str] = None
) -> pd.DataFrame:
    """
    Read the latest parquet file from a specific date partition or latest date.

    This avoids reloading every historical run in the same date partition when
    ClickHouse only needs the newest lake snapshot.
    """
    if not date_str:
        # Get latest partition
        partitions = list_layer_partitions(bucket, prefix)
        if not partitions:
            return pd.DataFrame()
        date_str = partitions[0]

    layer_path = f"{prefix}/dt={date_str}"
    client = _s3_client()
    dfs = []

    try:
        paginator = client.get_paginator("list_objects_v2")
        parquet_count = 0

        for page in paginator.paginate(Bucket=bucket, Prefix=layer_path):
            for obj in page.get("Contents", []):
                key = obj.get("Key", "")
                if not key.endswith(".parquet"):
                    continue
                parquet_count += 1
                obj_response = client.get_object(Bucket=bucket, Key=key)
                buffer = io.BytesIO(obj_response["Body"].read())
                df = pd.read_parquet(buffer, engine="pyarrow")
                dfs.append(df)
                print(
                    f"[read_latest_layer] Read {len(df)} rows from s3://{bucket}/{key}"
                )

        if parquet_count == 0:
            return pd.DataFrame()

    except ClientError as exc:
        print(f"[read_latest_layer] Error reading s3://{bucket}/{layer_path}: {exc}")
        return pd.DataFrame()

    if not dfs:
        return pd.DataFrame()

    result = pd.concat(dfs, ignore_index=True)
    print(f"[read_latest_layer] Combined {len(result)} rows from {len(dfs)} files")
    return result


def read_latest_bronze(date_str: Optional[str] = None) -> pd.DataFrame:
    """Read latest Bronze layer data."""
    bucket = os.getenv("RUSTFS_BRONZE_BUCKET", "bronze")
    prefix = os.getenv("RUSTFS_BRONZE_PREFIX", "demo")
    return read_latest_layer(bucket, prefix, date_str)


def read_latest_silver(date_str: Optional[str] = None) -> pd.DataFrame:
    """Read latest Silver layer data."""
    bucket = os.getenv("RUSTFS_SILVER_BUCKET", "silver")
    prefix = os.getenv("RUSTFS_SILVER_PREFIX", "demo")
    return read_latest_layer(bucket, prefix, date_str)


def read_latest_gold_daily(date_str: Optional[str] = None) -> pd.DataFrame:
    """Read latest Gold daily aggregation layer."""
    bucket = os.getenv("RUSTFS_GOLD_BUCKET", "gold")
    return read_latest_layer(bucket, "demo_daily", date_str)


def read_latest_gold_weekly(date_str: Optional[str] = None) -> pd.DataFrame:
    """Read latest Gold weekly aggregation layer."""
    bucket = os.getenv("RUSTFS_GOLD_BUCKET", "gold")
    return read_latest_layer(bucket, "demo_weekly", date_str)


def read_latest_gold_monthly(date_str: Optional[str] = None) -> pd.DataFrame:
    """Read latest Gold monthly aggregation layer."""
    bucket = os.getenv("RUSTFS_GOLD_BUCKET", "gold")
    return read_latest_layer(bucket, "demo_monthly", date_str)


def read_latest_gold_yearly(date_str: Optional[str] = None) -> pd.DataFrame:
    """Read latest Gold yearly aggregation layer."""
    bucket = os.getenv("RUSTFS_GOLD_BUCKET", "gold")
    return read_latest_layer(bucket, "demo_yearly", date_str)


def read_latest_gold_region(date_str: Optional[str] = None) -> pd.DataFrame:
    """Read latest Gold by-region aggregation layer."""
    bucket = os.getenv("RUSTFS_GOLD_BUCKET", "gold")
    return read_latest_layer(bucket, "demo_by_region", date_str)


def read_latest_gold_category(date_str: Optional[str] = None) -> pd.DataFrame:
    """Read latest Gold by-category aggregation layer."""
    bucket = os.getenv("RUSTFS_GOLD_BUCKET", "gold")
    return read_latest_layer(bucket, "demo_by_category", date_str)


def read_all_gold() -> dict:
    """Read all Gold layer tables as a dict."""
    return {
        "gold_daily": read_latest_gold_daily(),
        "gold_weekly": read_latest_gold_weekly(),
        "gold_monthly": read_latest_gold_monthly(),
        "gold_yearly": read_latest_gold_yearly(),
        "gold_region": read_latest_gold_region(),
        "gold_category": read_latest_gold_category(),
    }


def read_accumulated_layer(
    bucket: str,
    prefix: str,
    deduplicate_by: Optional[str] = None,
    timestamp_col: Optional[str] = None,
) -> pd.DataFrame:
    """
    Read all parquet files from all date partitions under a layer prefix,
    combine them, and optionally deduplicate to keep only the latest version of each group.
    """
    client = _s3_client()
    dfs = []

    try:
        paginator = client.get_paginator("list_objects_v2")
        parquet_count = 0

        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj.get("Key", "")
                if not key.endswith(".parquet"):
                    continue
                if "/dt=" not in key:
                    continue
                parquet_count += 1
                obj_response = client.get_object(Bucket=bucket, Key=key)
                buffer = io.BytesIO(obj_response["Body"].read())
                df = pd.read_parquet(buffer, engine="pyarrow")
                dfs.append(df)
                print(
                    f"[read_accumulated_layer] Read {len(df)} rows from s3://{bucket}/{key}"
                )

        if parquet_count == 0:
            return pd.DataFrame()

    except ClientError as exc:
        print(f"[read_accumulated_layer] Error reading s3://{bucket}/{prefix}: {exc}")
        return pd.DataFrame()

    if not dfs:
        return pd.DataFrame()

    result = pd.concat(dfs, ignore_index=True)
    print(f"[read_accumulated_layer] Combined {len(result)} rows from {len(dfs)} files")

    if (
        deduplicate_by
        and timestamp_col
        and deduplicate_by in result.columns
        and timestamp_col in result.columns
    ):
        result[timestamp_col] = pd.to_datetime(result[timestamp_col], errors="coerce")
        latest_versions = (
            result.groupby(deduplicate_by)[timestamp_col].max().reset_index()
        )
        result = pd.merge(
            result, latest_versions, on=[deduplicate_by, timestamp_col], how="inner"
        )
        print(
            f"[read_accumulated_layer] Deduplicated to {len(result)} rows for latest versions of each {deduplicate_by}"
        )

    return result


def read_latest_excel_silver(date_str: Optional[str] = None) -> pd.DataFrame:
    """Read latest Excel projects Silver layer data."""
    if date_str:
        bucket = os.getenv("RUSTFS_SILVER_BUCKET", "silver")
        prefix = "excel_projects"
        return read_latest_layer(bucket, prefix, date_str)

    bucket = os.getenv("RUSTFS_SILVER_BUCKET", "silver")
    prefix = "excel_projects"
    return read_accumulated_layer(
        bucket=bucket,
        prefix=prefix,
        deduplicate_by="_source_file_key",
        timestamp_col="_extracted_at",
    )


def read_latest_excel_gold_projects(date_str: Optional[str] = None) -> pd.DataFrame:
    """Read latest Excel Gold projects summary aggregation."""
    if date_str:
        bucket = os.getenv("RUSTFS_GOLD_BUCKET", "gold")
        return read_latest_layer(bucket, "projects", date_str)

    bucket = os.getenv("RUSTFS_GOLD_BUCKET", "gold")
    return read_accumulated_layer(
        bucket=bucket,
        prefix="projects",
        deduplicate_by="_source_file_key",
        timestamp_col="_gold_processed_at",
    )


def read_latest_excel_gold_workload(date_str: Optional[str] = None) -> pd.DataFrame:
    """Read latest Excel Gold workload aggregation."""
    if date_str:
        bucket = os.getenv("RUSTFS_GOLD_BUCKET", "gold")
        return read_latest_layer(bucket, "workload", date_str)

    # Dynamically calculate workload from accumulated Silver to ensure consistency across all projects
    df_silver = read_latest_excel_silver()
    if df_silver.empty:
        return pd.DataFrame()

    df = df_silver.copy()
    assignee_col = "Người thực hiện"
    fallback_col = "Người giao việc"

    if assignee_col not in df.columns:
        possible_names = ["assignee", "người thực hiện", "người làm", "nhân sự"]
        for col in df.columns:
            if str(col).lower().strip() in possible_names:
                df[assignee_col] = df[col]
                break

    if assignee_col in df.columns:
        if fallback_col in df.columns:
            df[assignee_col] = df[assignee_col].fillna(df[fallback_col])
            df.loc[df[assignee_col].isin(["", "nan", "None"]), assignee_col] = df.loc[
                df[assignee_col].isin(["", "nan", "None"]), fallback_col
            ]

        df[assignee_col] = (
            df[assignee_col]
            .fillna("Chưa phân công")
            .replace(
                {
                    "": "Chưa phân công",
                    "nan": "Chưa phân công",
                    "None": "Chưa phân công",
                }
            )
        )
    else:
        df[assignee_col] = (
            df[fallback_col] if fallback_col in df.columns else "Chưa phân công"
        )
        df[assignee_col] = df[assignee_col].fillna("Chưa phân công")

    workload = (
        df.groupby("Người thực hiện")
        .agg(
            task_count=("Mã công việc (ID)", "count"),
            urgent_tasks=("Khẩn cấp", lambda x: (x == "Có").sum()),
        )
        .reset_index()
    )

    workload["_pipeline_run_id"] = "dynamic_calc"
    workload["_gold_processed_at"] = (
        dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    )
    return workload


def read_all_excel_gold() -> dict:
    """Read all Excel Gold layer tables as a dict."""
    return {
        "gold_projects": read_latest_excel_gold_projects(),
        "gold_workload": read_latest_excel_gold_workload(),
    }


def read_latest_csv_silver(date_str: Optional[str] = None) -> pd.DataFrame:
    """Read latest CSV Silver layer data (cleaned uploaded CSV)."""
    bucket = os.getenv("RUSTFS_SILVER_BUCKET", "silver")
    prefix = os.getenv("RUSTFS_CSV_SILVER_PREFIX", "csv_upload")
    return read_latest_layer(bucket, prefix, date_str)


def read_csv_silver_by_run_id(
    run_id: str, date_str: Optional[str] = None
) -> pd.DataFrame:
    """Read a specific cleaned CSV Silver file by run_id."""
    if not run_id:
        return pd.DataFrame()

    bucket = os.getenv("RUSTFS_SILVER_BUCKET", "silver")
    prefix = os.getenv("RUSTFS_CSV_SILVER_PREFIX", "csv_upload")
    if not date_str:
        date_str = dt.date.today().isoformat()

    key = f"{prefix}/dt={date_str}/{run_id}.parquet"
    client = _s3_client()

    try:
        obj_response = client.get_object(Bucket=bucket, Key=key)
        buffer = io.BytesIO(obj_response["Body"].read())
        df = pd.read_parquet(buffer, engine="pyarrow")
        print(
            f"[read_csv_silver_by_run_id] Read {len(df)} rows from s3://{bucket}/{key}"
        )
        return df
    except ClientError as exc:
        print(f"[read_csv_silver_by_run_id] Error reading s3://{bucket}/{key}: {exc}")
        return pd.DataFrame()
