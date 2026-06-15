#!/usr/bin/env python3
"""Create or update a comprehensive Superset dashboard for the DataLakehouse.

Charts included:
  - KPI: Total Revenue       (big_number_total)
  - KPI: Total Orders        (big_number_total)
  - KPI: Average Order Value (big_number_total)
  - Bar chart: Revenue by Category
  - Pie chart: Orders by Region
  - Line graph: Revenue Over Time (daily)
  - Table: Daily Sales Summary
  - Bar chart: Top Regions by Revenue

Environment variables:
  SUPERSET_URL             (default: http://127.0.0.1:28088)
  SUPERSET_ADMIN_USER      (default: admin)
  SUPERSET_ADMIN_PASSWORD  (default: admin)
  CLICKHOUSE_USER          (default: default)
  CLICKHOUSE_PASSWORD      (default: "")
  CLICKHOUSE_DB            (default: analytics)
  DLH_BIND_IP              (default: 127.0.0.1)
  DLH_CLICKHOUSE_HTTP_PORT (default: 28123)

Run from host machine:
  python scripts/create_superset_demo_dashboard.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

import requests

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = REPO_ROOT / ".env"


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


_load_env_file(ENV_FILE)

BIND_IP = os.getenv("DLH_BIND_IP", "127.0.0.1")
if BIND_IP in {"0.0.0.0", "::"}:
    BIND_IP = "127.0.0.1"
CH_HTTP_PORT = os.getenv("DLH_CLICKHOUSE_HTTP_PORT", "28123")
CH_HOST = os.getenv("CLICKHOUSE_HOST", "dlh-clickhouse")
CH_PORT = os.getenv("CLICKHOUSE_PORT", "8123")
CH_USER = os.getenv("CLICKHOUSE_USER", "default") or "default"
CH_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "") or ""
CH_DB = os.getenv("CLICKHOUSE_DB", "analytics")

BASE_URL = os.getenv("SUPERSET_URL", f"http://{BIND_IP}:28088").rstrip("/")
ADMIN_USER = os.getenv("SUPERSET_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("SUPERSET_ADMIN_PASSWORD", "admin")

DASHBOARD_TITLE = os.getenv("SUPERSET_DASHBOARD_TITLE", "DataLakehouse Analytics")
DASHBOARD_SLUG = "datalakehouse-analytics"

DB_NAME = "ClickHouse Analytics"
# Build URI from env vars so it reflects user-configured ports and credentials
if CH_PASSWORD:
    DB_URI = (
        f"clickhousedb+connect://{CH_USER}:{CH_PASSWORD}@{CH_HOST}:{CH_PORT}/{CH_DB}"
    )
else:
    DB_URI = f"clickhousedb+connect://{CH_USER}@{CH_HOST}:{CH_PORT}/{CH_DB}"

SCHEMA = CH_DB


# ---------------------------------------------------------------------------
# Superset API client
# ---------------------------------------------------------------------------


def _query(page: int = 0, page_size: int = 1000) -> str:
    return f"(page:{page},page_size:{page_size})"


def _to_params(data: Dict[str, Any]) -> str:
    return json.dumps(data, separators=(",", ":"), ensure_ascii=True)


class SupersetClient:
    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url
        self.session = requests.Session()

        login = self.session.post(
            f"{self.base_url}/api/v1/security/login",
            json={
                "username": username,
                "password": password,
                "provider": "db",
                "refresh": True,
            },
            timeout=30,
        )
        login.raise_for_status()
        access_token = login.json()["access_token"]

        auth_headers = {"Authorization": f"Bearer {access_token}"}
        csrf = self.session.get(
            f"{self.base_url}/api/v1/security/csrf_token/",
            headers=auth_headers,
            timeout=30,
        )
        csrf.raise_for_status()
        csrf_token = csrf.json()["result"]

        self.headers = {
            **auth_headers,
            "X-CSRFToken": csrf_token,
            "Referer": self.base_url,
            "Content-Type": "application/json",
        }

    def get(self, path: str) -> Dict[str, Any]:
        res = self.session.get(
            f"{self.base_url}{path}", headers=self.headers, timeout=60
        )
        res.raise_for_status()
        return res.json()

    def post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        res = self.session.post(
            f"{self.base_url}{path}", headers=self.headers, json=payload, timeout=60
        )
        res.raise_for_status()
        return res.json()

    def put(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        res = self.session.put(
            f"{self.base_url}{path}", headers=self.headers, json=payload, timeout=60
        )
        res.raise_for_status()
        return res.json()


# ---------------------------------------------------------------------------
# Resource helpers
# ---------------------------------------------------------------------------


def ensure_database(client: SupersetClient) -> int:
    items = client.get(f"/api/v1/database/?q={_query()}").get("result", [])
    for item in items:
        if item.get("database_name") == DB_NAME:
            return int(item["id"])
    payload = {
        "database_name": DB_NAME,
        "sqlalchemy_uri": DB_URI,
        "expose_in_sqllab": True,
        "allow_run_async": True,
    }
    created = client.post("/api/v1/database/", payload)
    return int(created["id"])


def cleanup_old_resources(client: SupersetClient) -> None:
    # Delete old "DLH –" charts
    charts = client.get(f"/api/v1/chart/?q={_query()}").get("result", [])
    for c in charts:
        if c.get("slice_name", "").startswith("DLH –"):
            try:
                client.session.delete(
                    f"{BASE_URL}/api/v1/chart/{c['id']}",
                    headers=client.headers,
                    timeout=30,
                )
                print(f"Deleted old chart: {c['slice_name']}")
            except Exception:
                pass


def ensure_dataset(
    client: SupersetClient,
    database_id: int,
    table_name: str,
    *,
    datetime_col: str | None = None,
    metrics: List[Dict[str, Any]] | None = None,
) -> int:
    items = client.get(f"/api/v1/dataset/?q={_query()}").get("result", [])
    dataset_id = None
    for item in items:
        db = item.get("database") or {}
        if (
            db.get("id") == database_id
            and item.get("schema") == SCHEMA
            and item.get("table_name") == table_name
        ):
            dataset_id = int(item["id"])
            break

    if dataset_id is None:
        payload: Dict[str, Any] = {
            "database": database_id,
            "schema": SCHEMA,
            "table_name": table_name,
        }
        created = client.post("/api/v1/dataset/", payload)
        dataset_raw_id = created.get("id") or (created.get("result") or {}).get("id")
        if not dataset_raw_id:
            raise RuntimeError(
                f"Could not parse dataset id from Superset response: {created}"
            )
        dataset_id = int(dataset_raw_id)

    # Fetch full dataset metadata to get existing metrics and columns
    ds_data = client.get(f"/api/v1/dataset/{dataset_id}")["result"]
    existing_metrics = ds_data.get("metrics", [])

    update_payload: Dict[str, Any] = {
        "database_id": database_id,
        "schema": SCHEMA,
        "table_name": table_name,
    }

    if datetime_col:
        update_payload["main_dttm_col"] = datetime_col

    if metrics:
        new_metrics = []
        for m in metrics:
            found = False
            for em in existing_metrics:
                if em["metric_name"] == m["metric_name"]:
                    # Preserve ID to update instead of create duplicate
                    m_copy = m.copy()
                    m_copy["id"] = em["id"]
                    new_metrics.append(m_copy)
                    found = True
                    break
            if not found:
                new_metrics.append(m)

        # We also need to keep other existing metrics that aren't in our 'metrics' list
        # but for this demo script, we prefer to have only what we define.
        update_payload["metrics"] = new_metrics

    client.put(f"/api/v1/dataset/{dataset_id}", update_payload)

    # Ensure the datetime column is marked as is_dttm
    if datetime_col:
        # Re-fetch as put might have changed things
        ds_data = client.get(f"/api/v1/dataset/{dataset_id}")["result"]
        cols = ds_data.get("columns", [])
        changed = False
        for c in cols:
            if c["column_name"] == datetime_col and not c.get("is_dttm"):
                c["is_dttm"] = True
                changed = True
        if changed:
            client.put(f"/api/v1/dataset/{dataset_id}", {"columns": cols})

    return dataset_id


def ensure_dashboard(client: SupersetClient) -> int:
    items = client.get(f"/api/v1/dashboard/?q={_query()}").get("result", [])
    for item in items:
        if item.get("dashboard_title") == DASHBOARD_TITLE:
            return int(item["id"])
    payload = {
        "dashboard_title": DASHBOARD_TITLE,
        "slug": DASHBOARD_SLUG,
        "published": True,
    }
    created = client.post("/api/v1/dashboard/", payload)
    return int(created["id"])


def _simple_metric(column_name: str, aggregate: str, label: str) -> Dict[str, Any]:
    return {
        "expressionType": "SIMPLE",
        "column": {"column_name": column_name},
        "aggregate": aggregate,
        "label": label,
    }


def _time_filter(column: str, time_range: str = "No filter") -> Dict[str, Any]:
    return {
        "expressionType": "SIMPLE",
        "subject": column,
        "operator": "TEMPORAL_RANGE",
        "comparator": time_range,
        "clause": "WHERE",
    }


def ensure_chart(
    client: SupersetClient,
    *,
    dashboard_id: int,
    dataset_id: int,
    slice_name: str,
    viz_type: str,
    params: Dict[str, Any],
) -> int:
    # Ensure params contains datasource
    params["datasource"] = f"{dataset_id}__table"

    items = client.get(f"/api/v1/chart/?q={_query()}").get("result", [])
    for item in items:
        if item.get("slice_name") == slice_name:
            chart_id = int(item["id"])
            update_payload = {
                "slice_name": slice_name,
                "viz_type": viz_type,
                "datasource_id": dataset_id,
                "datasource_type": "table",
                "params": _to_params(params),
                "dashboards": [dashboard_id],
            }
            client.put(f"/api/v1/chart/{chart_id}", update_payload)
            return chart_id
    payload = {
        "slice_name": slice_name,
        "viz_type": viz_type,
        "datasource_id": dataset_id,
        "datasource_type": "table",
        "params": _to_params(params),
        "dashboards": [dashboard_id],
    }
    created = client.post("/api/v1/chart/", payload)
    return int(created["id"])


# ---------------------------------------------------------------------------
# Dashboard layout builder
# ---------------------------------------------------------------------------


def build_layout(chart_ids: Dict[str, int]) -> Dict[str, Any]:
    """
    Improved layout structure:
      - Header (Markdown)
      - Row 1: KPI metrics (3 tiles)
      - Divider
      - Row 2: Analysis (Bar + Pie)
      - Divider
      - Row 3: Trends (Line)
      - Row 4: Details (Table)
    """
    layout: Dict[str, Any] = {
        "ROOT_ID": {
            "id": "ROOT_ID",
            "type": "ROOT",
            "children": ["GRID_ID"],
            "parents": [],
        },
        "GRID_ID": {
            "id": "GRID_ID",
            "type": "GRID",
            "children": [
                "ROW-header",
                "ROW-kpi",
                "DIVIDER-1",
                "ROW-cat-region",
                "DIVIDER-2",
                "ROW-line",
                "ROW-table",
                "ROW-region-bar",
            ],
            "parents": ["ROOT_ID"],
        },
    }

    def _row(row_id: str, children: List[str]) -> Dict[str, Any]:
        return {
            "id": row_id,
            "type": "ROW",
            "children": children,
            "parents": ["ROOT_ID", "GRID_ID"],
            "meta": {"background": "BACKGROUND_TRANSPARENT"},
        }

    def _chart_cell(
        cell_id: str, row_id: str, chart_id: int, width: int = 4, height: int = 50
    ) -> Dict[str, Any]:
        return {
            "id": cell_id,
            "type": "CHART",
            "children": [],
            "parents": ["ROOT_ID", "GRID_ID", row_id],
            "meta": {"chartId": chart_id, "width": width, "height": height},
        }

    def _markdown_cell(
        cell_id: str, row_id: str, code: str, width: int = 12, height: int = 20
    ) -> Dict[str, Any]:
        return {
            "id": cell_id,
            "type": "MARKDOWN",
            "children": [],
            "parents": ["ROOT_ID", "GRID_ID", row_id],
            "meta": {"width": width, "height": height, "code": code},
        }

    def _divider(div_id: str) -> Dict[str, Any]:
        return {
            "id": div_id,
            "type": "DIVIDER",
            "children": [],
            "parents": ["ROOT_ID", "GRID_ID"],
        }

    # Header
    header_md = (
        "<div style='text-align: center; background: linear-gradient(90deg, #1d3557 0%, #457b9d 100%); "
        "padding: 20px; border-radius: 8px; color: white; margin-bottom: 20px;'>"
        "<h1 style='margin: 0; font-size: 32px;'>🚀 DataLakehouse Analytics</h1>"
        "<p style='margin: 5px 0 0; opacity: 0.8;'>Hệ thống phân tích dữ liệu bán hàng đa kênh – Real-time Dashboard</p>"
        "</div>"
    )
    layout["ROW-header"] = _row("ROW-header", ["MD-header"])
    layout["MD-header"] = _markdown_cell("MD-header", "ROW-header", header_md, 12, 25)

    # Row 1 – KPI
    layout["ROW-kpi"] = _row(
        "ROW-kpi", ["CHART-kpi-revenue", "CHART-kpi-orders", "CHART-kpi-avg"]
    )
    layout["CHART-kpi-revenue"] = _chart_cell(
        "CHART-kpi-revenue", "ROW-kpi", chart_ids["kpi_revenue"], 4, 30
    )
    layout["CHART-kpi-orders"] = _chart_cell(
        "CHART-kpi-orders", "ROW-kpi", chart_ids["kpi_orders"], 4, 30
    )
    layout["CHART-kpi-avg"] = _chart_cell(
        "CHART-kpi-avg", "ROW-kpi", chart_ids["kpi_avg"], 4, 30
    )

    # Dividers
    layout["DIVIDER-1"] = _divider("DIVIDER-1")
    layout["DIVIDER-2"] = _divider("DIVIDER-2")

    # Row 2 – Bar + Pie
    layout["ROW-cat-region"] = _row(
        "ROW-cat-region", ["CHART-bar-cat", "CHART-pie-region"]
    )
    layout["CHART-bar-cat"] = _chart_cell(
        "CHART-bar-cat", "ROW-cat-region", chart_ids["bar_category"], 7, 60
    )
    layout["CHART-pie-region"] = _chart_cell(
        "CHART-pie-region", "ROW-cat-region", chart_ids["pie_region"], 5, 60
    )

    # Row 3 – Trends
    layout["ROW-line"] = _row("ROW-line", ["CHART-line-daily"])
    layout["CHART-line-daily"] = _chart_cell(
        "CHART-line-daily", "ROW-line", chart_ids["line_daily"], 12, 60
    )

    # Row 4 – Details
    layout["ROW-table"] = _row("ROW-table", ["CHART-table-daily"])
    layout["CHART-table-daily"] = _chart_cell(
        "CHART-table-daily", "ROW-table", chart_ids["table_daily"], 12, 80
    )

    # Row 5 – Region Bar (Secondary)
    layout["ROW-region-bar"] = _row("ROW-region-bar", ["CHART-bar-region"])
    layout["CHART-bar-region"] = _chart_cell(
        "CHART-bar-region", "ROW-region-bar", chart_ids["bar_region"], 12, 50
    )

    return layout


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print(f"Connecting to Superset at {BASE_URL} …")
    client = SupersetClient(BASE_URL, ADMIN_USER, ADMIN_PASSWORD)

    cleanup_old_resources(client)

    db_id = ensure_database(client)
    print(f"ClickHouse database id: {db_id}")

    # Standard metrics with 'm_' prefix to avoid collision with column names
    metrics_daily = [
        {
            "metric_name": "m_total_revenue",
            "expression": "SUM(total_revenue)",
            "d3format": ",.2f",
            "metric_type": "sum",
        },
        {
            "metric_name": "m_order_count",
            "expression": "SUM(order_count)",
            "d3format": ",",
            "metric_type": "sum",
        },
        {
            "metric_name": "m_avg_order_value",
            "expression": "SUM(total_revenue) / SUM(order_count)",
            "d3format": ",.2f",
            "metric_type": "other",
        },
    ]
    metrics_region = [
        {
            "metric_name": "m_total_revenue",
            "expression": "SUM(total_revenue)",
            "d3format": ",.2f",
            "metric_type": "sum",
        },
        {
            "metric_name": "m_order_count",
            "expression": "SUM(order_count)",
            "d3format": ",",
            "metric_type": "sum",
        },
    ]
    metrics_category = [
        {
            "metric_name": "m_total_revenue",
            "expression": "SUM(total_revenue)",
            "d3format": ",.2f",
            "metric_type": "sum",
        },
        {
            "metric_name": "m_order_count",
            "expression": "SUM(order_count)",
            "d3format": ",",
            "metric_type": "sum",
        },
    ]

    ds_daily = ensure_dataset(
        client,
        db_id,
        "gold_demo_daily",
        datetime_col="order_date",
        metrics=metrics_daily,
    )
    ds_region = ensure_dataset(
        client,
        db_id,
        "gold_demo_by_region",
        datetime_col="report_date",
        metrics=metrics_region,
    )
    ds_category = ensure_dataset(
        client,
        db_id,
        "gold_demo_by_category",
        datetime_col="report_date",
        metrics=metrics_category,
    )
    ds_silver = ensure_dataset(
        client, db_id, "silver_demo", datetime_col="_silver_processed_at"
    )
    dashboard_id = ensure_dashboard(client)

    print(f"Dashboard id: {dashboard_id}  Creating / verifying charts …")

    chart_ids: Dict[str, int] = {}

    CHART_CONFIGS = [
        {
            "key": "kpi_revenue",
            "dataset": ds_daily,
            "name": "[KPI] Tổng Doanh Thu",
            "type": "big_number_total",
            "params": {
                "metric": "m_total_revenue",
                "adhoc_filters": [_time_filter("order_date")],
                "subheader": "VND",
                "y_axis_format": ",.2f",
                "header_font_size": 0.4,
                "subheader_font_size": 0.15,
            },
        },
        {
            "key": "kpi_orders",
            "dataset": ds_daily,
            "name": "[KPI] Tổng Đơn Hàng",
            "type": "big_number_total",
            "params": {
                "metric": "m_order_count",
                "adhoc_filters": [_time_filter("order_date")],
                "subheader": "đơn hàng",
                "y_axis_format": ",",
                "header_font_size": 0.4,
                "subheader_font_size": 0.15,
            },
        },
        {
            "key": "kpi_avg",
            "dataset": ds_daily,
            "name": "[KPI] Giá Trị TB / Đơn",
            "type": "big_number_total",
            "params": {
                "metric": "m_avg_order_value",
                "adhoc_filters": [_time_filter("order_date")],
                "subheader": "VND",
                "y_axis_format": ",.2f",
                "header_font_size": 0.4,
                "subheader_font_size": 0.15,
            },
        },
        {
            "key": "bar_category",
            "dataset": ds_category,
            "name": "Doanh Thu theo Danh Mục",
            "type": "echarts_timeseries_bar",
            "params": {
                "x_axis": "category",
                "groupby": [],
                "metrics": ["m_total_revenue"],
                "adhoc_filters": [_time_filter("report_date")],
                "time_range": "No filter",
                "row_limit": 50,
                "order_desc": True,
                "show_bar_value": True,
                "y_axis_format": ",.0f",
                "orientation": "vertical",
                "timeseries_limit_metric": "m_total_revenue",
                "show_legend": False,
                "rich_tooltip": True,
            },
        },
        {
            "key": "pie_region",
            "dataset": ds_region,
            "name": "Phân Bổ Đơn Hàng theo Vùng",
            "type": "pie",
            "params": {
                "groupby": ["region"],
                "metric": "m_order_count",
                "adhoc_filters": [_time_filter("report_date")],
                "row_limit": 20,
                "show_labels": True,
                "show_legend": True,
                "donut": True,
                "label_type": "key_value_percent",
                "roseType": "area",
                "innerRadius": 40,
            },
        },
        {
            "key": "line_daily",
            "dataset": ds_daily,
            "name": "Diễn Biến Doanh Thu theo Ngày",
            "type": "echarts_timeseries_line",
            "params": {
                "x_axis": "order_date",
                "groupby": [],
                "metrics": ["m_total_revenue"],
                "adhoc_filters": [_time_filter("order_date")],
                "time_grain_sqla": None,
                "time_range": "No filter",
                "row_limit": 500,
                "show_legend": True,
                "smooth": True,
                "y_axis_format": ",.0f",
                "order_desc": False,
                "rich_tooltip": True,
                "markerEnabled": True,
            },
        },
        {
            "key": "table_daily",
            "dataset": ds_daily,
            "name": "Chi Tiết Doanh Số Hàng Ngày",
            "type": "table",
            "params": {
                "all_columns": [
                    "order_date",
                    "order_count",
                    "total_revenue",
                    "avg_order_value",
                    "total_quantity",
                    "unique_customers",
                    "unique_regions",
                ],
                "metrics": [],
                "adhoc_filters": [_time_filter("order_date")],
                "time_grain_sqla": None,
                "order_desc": True,
                "row_limit": 100,
                "include_search": True,
                "show_cell_bars": True,
                "table_timestamp_format": "smart_date",
                "column_config": {
                    "total_revenue": {
                        "d3NumberFormat": ",.2f",
                        "horizontalAlign": "right",
                    },
                    "avg_order_value": {
                        "d3NumberFormat": ",.2f",
                        "horizontalAlign": "right",
                    },
                    "order_count": {"horizontalAlign": "center"},
                    "order_date": {"columnWidth": 120},
                },
            },
        },
        {
            "key": "bar_region",
            "dataset": ds_region,
            "name": "Top Vùng Miền theo Doanh Thu",
            "type": "echarts_timeseries_bar",
            "params": {
                "x_axis": "region",
                "groupby": [],
                "metrics": ["m_total_revenue"],
                "adhoc_filters": [_time_filter("report_date")],
                "time_range": "No filter",
                "row_limit": 20,
                "order_desc": True,
                "show_bar_value": True,
                "y_axis_format": ",.0f",
                "timeseries_limit_metric": "m_total_revenue",
                "show_legend": False,
                "rich_tooltip": True,
            },
        },
    ]

    for cfg in CHART_CONFIGS:
        chart_ids[cfg["key"]] = ensure_chart(
            client,
            dashboard_id=dashboard_id,
            dataset_id=cfg["dataset"],
            slice_name=cfg["name"],
            viz_type=cfg["type"],
            params=cfg["params"],
        )

    # ── Assemble dashboard layout ───────────────────────────────────────────
    layout = build_layout(chart_ids)
    client.put(
        f"/api/v1/dashboard/{dashboard_id}",
        {
            "position_json": _to_params(layout),
            "json_metadata": _to_params(
                {
                    "color_scheme": "d3Category10",
                    "refresh_frequency": 60,
                    "filter_scopes": {},
                    "native_filter_configuration": [],
                    "global_chart_configuration": {"crossFilters": {"enabled": True}},
                }
            ),
            "published": True,
        },
    )

    result = client.get(f"/api/v1/dashboard/{dashboard_id}").get("result", {})
    dashboard_url = result.get("url") or f"/superset/dashboard/{dashboard_id}/"

    print("\n✅  Superset dashboard ready!")
    print(f"   Title : {DASHBOARD_TITLE}")
    print(f"   URL   : {BASE_URL}{dashboard_url}")
    print("\nCharts created:")
    for key, cid in chart_ids.items():
        print(f"   [{cid:>5}] {key}")


if __name__ == "__main__":
    main()
