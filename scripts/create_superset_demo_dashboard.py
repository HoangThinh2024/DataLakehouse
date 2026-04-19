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
CH_HTTP_PORT = os.getenv("DLH_CLICKHOUSE_HTTP_PORT", "28123")
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
    DB_URI = f"clickhousedb+connect://{CH_USER}:{CH_PASSWORD}@dlh-clickhouse:8123/{CH_DB}"
else:
    DB_URI = f"clickhousedb+connect://{CH_USER}@dlh-clickhouse:8123/{CH_DB}"

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
            json={"username": username, "password": password, "provider": "db", "refresh": True},
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
        res = self.session.get(f"{self.base_url}{path}", headers=self.headers, timeout=60)
        res.raise_for_status()
        return res.json()

    def post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        res = self.session.post(f"{self.base_url}{path}", headers=self.headers, json=payload, timeout=60)
        res.raise_for_status()
        return res.json()

    def put(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        res = self.session.put(f"{self.base_url}{path}", headers=self.headers, json=payload, timeout=60)
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


def ensure_dataset(client: SupersetClient, database_id: int, table_name: str) -> int:
    items = client.get(f"/api/v1/dataset/?q={_query()}").get("result", [])
    for item in items:
        db = item.get("database") or {}
        if db.get("id") == database_id and item.get("schema") == SCHEMA and item.get("table_name") == table_name:
            return int(item["id"])
    payload = {"database": database_id, "schema": SCHEMA, "table_name": table_name}
    created = client.post("/api/v1/dataset/", payload)
    return int(created["id"])


def ensure_dashboard(client: SupersetClient) -> int:
    items = client.get(f"/api/v1/dashboard/?q={_query()}").get("result", [])
    for item in items:
        if item.get("dashboard_title") == DASHBOARD_TITLE:
            return int(item["id"])
    payload = {"dashboard_title": DASHBOARD_TITLE, "slug": DASHBOARD_SLUG, "published": True}
    created = client.post("/api/v1/dashboard/", payload)
    return int(created["id"])


def _simple_metric(column_name: str, aggregate: str, label: str) -> Dict[str, Any]:
    return {
        "expressionType": "SIMPLE",
        "column": {"column_name": column_name},
        "aggregate": aggregate,
        "label": label,
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
    items = client.get(f"/api/v1/chart/?q={_query()}").get("result", [])
    for item in items:
        if item.get("slice_name") == slice_name:
            return int(item["id"])
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
    Layout structure (3 rows):
      Row 1 – KPI metrics (3 big-number tiles)
      Row 2 – Bar (category revenue) + Pie (region orders)
      Row 3 – Line graph (daily revenue) + Table (daily summary)
      Row 4 – Bar (top regions by revenue)
    """
    layout: Dict[str, Any] = {
        "ROOT_ID": {"id": "ROOT_ID", "type": "ROOT", "children": ["GRID_ID"], "parents": []},
        "GRID_ID": {
            "id": "GRID_ID",
            "type": "GRID",
            "children": ["ROW-kpi", "ROW-cat-region", "ROW-time-table", "ROW-region-bar"],
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

    def _chart_cell(cell_id: str, row_id: str, chart_id: int, width: int = 4, height: int = 50) -> Dict[str, Any]:
        return {
            "id": cell_id,
            "type": "CHART",
            "children": [],
            "parents": ["ROOT_ID", "GRID_ID", row_id],
            "meta": {"chartId": chart_id, "width": width, "height": height},
        }

    # Row 1 – KPI
    layout["ROW-kpi"] = _row("ROW-kpi", ["CHART-kpi-revenue", "CHART-kpi-orders", "CHART-kpi-avg"])
    layout["CHART-kpi-revenue"] = _chart_cell("CHART-kpi-revenue", "ROW-kpi", chart_ids["kpi_revenue"], 4, 40)
    layout["CHART-kpi-orders"] = _chart_cell("CHART-kpi-orders", "ROW-kpi", chart_ids["kpi_orders"], 4, 40)
    layout["CHART-kpi-avg"] = _chart_cell("CHART-kpi-avg", "ROW-kpi", chart_ids["kpi_avg"], 4, 40)

    # Row 2 – Bar + Pie
    layout["ROW-cat-region"] = _row("ROW-cat-region", ["CHART-bar-cat", "CHART-pie-region"])
    layout["CHART-bar-cat"] = _chart_cell("CHART-bar-cat", "ROW-cat-region", chart_ids["bar_category"], 6, 60)
    layout["CHART-pie-region"] = _chart_cell("CHART-pie-region", "ROW-cat-region", chart_ids["pie_region"], 6, 60)

    # Row 3 – Line + Table
    layout["ROW-time-table"] = _row("ROW-time-table", ["CHART-line-daily", "CHART-table-daily"])
    layout["CHART-line-daily"] = _chart_cell("CHART-line-daily", "ROW-time-table", chart_ids["line_daily"], 6, 60)
    layout["CHART-table-daily"] = _chart_cell("CHART-table-daily", "ROW-time-table", chart_ids["table_daily"], 6, 60)

    # Row 4 – Top regions bar
    layout["ROW-region-bar"] = _row("ROW-region-bar", ["CHART-bar-region"])
    layout["CHART-bar-region"] = _chart_cell("CHART-bar-region", "ROW-region-bar", chart_ids["bar_region"], 12, 60)

    return layout


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print(f"Connecting to Superset at {BASE_URL} …")
    client = SupersetClient(BASE_URL, ADMIN_USER, ADMIN_PASSWORD)

    db_id = ensure_database(client)
    print(f"ClickHouse database id: {db_id}")

    ds_daily = ensure_dataset(client, db_id, "gold_demo_daily")
    ds_region = ensure_dataset(client, db_id, "gold_demo_by_region")
    ds_category = ensure_dataset(client, db_id, "gold_demo_by_category")
    ds_silver = ensure_dataset(client, db_id, "silver_demo")
    dashboard_id = ensure_dashboard(client)

    print(f"Dashboard id: {dashboard_id}  Creating / verifying charts …")

    chart_ids: Dict[str, int] = {}

    # ── KPI: Total Revenue ──────────────────────────────────────────────────
    chart_ids["kpi_revenue"] = ensure_chart(
        client,
        dashboard_id=dashboard_id,
        dataset_id=ds_daily,
        slice_name="DLH – Tổng Doanh Thu (Total Revenue)",
        viz_type="big_number_total",
        params={
            "datasource": f"{ds_daily}__table",
            "viz_type": "big_number_total",
            "metric": _simple_metric("total_revenue", "SUM", "Total Revenue"),
            "adhoc_filters": [],
            "subheader": "VND",
            "header_font_size": 0.4,
            "subheader_font_size": 0.15,
        },
    )

    # ── KPI: Total Orders ───────────────────────────────────────────────────
    chart_ids["kpi_orders"] = ensure_chart(
        client,
        dashboard_id=dashboard_id,
        dataset_id=ds_daily,
        slice_name="DLH – Tổng Đơn Hàng (Total Orders)",
        viz_type="big_number_total",
        params={
            "datasource": f"{ds_daily}__table",
            "viz_type": "big_number_total",
            "metric": _simple_metric("order_count", "SUM", "Total Orders"),
            "adhoc_filters": [],
            "subheader": "đơn hàng",
            "header_font_size": 0.4,
            "subheader_font_size": 0.15,
        },
    )

    # ── KPI: Average Order Value ────────────────────────────────────────────
    chart_ids["kpi_avg"] = ensure_chart(
        client,
        dashboard_id=dashboard_id,
        dataset_id=ds_daily,
        slice_name="DLH – Giá Trị ĐH Trung Bình (Avg Order Value)",
        viz_type="big_number_total",
        params={
            "datasource": f"{ds_daily}__table",
            "viz_type": "big_number_total",
            "metric": _simple_metric("avg_order_value", "AVG", "Avg Order Value"),
            "adhoc_filters": [],
            "subheader": "VND / đơn",
            "header_font_size": 0.4,
            "subheader_font_size": 0.15,
        },
    )

    # ── Bar chart: Revenue by Category ─────────────────────────────────────
    chart_ids["bar_category"] = ensure_chart(
        client,
        dashboard_id=dashboard_id,
        dataset_id=ds_category,
        slice_name="DLH – Doanh Thu theo Danh Mục (Revenue by Category)",
        viz_type="echarts_bar",
        params={
            "datasource": f"{ds_category}__table",
            "viz_type": "echarts_bar",
            "x_axis": "category",
            "metrics": [_simple_metric("total_revenue", "SUM", "Doanh Thu")],
            "groupby": [],
            "adhoc_filters": [],
            "row_limit": 50,
            "order_desc": True,
            "show_legend": False,
            "show_bar_value": True,
            "orientation": "vertical",
        },
    )

    # ── Pie chart: Orders by Region ─────────────────────────────────────────
    chart_ids["pie_region"] = ensure_chart(
        client,
        dashboard_id=dashboard_id,
        dataset_id=ds_region,
        slice_name="DLH – Đơn Hàng theo Vùng (Orders by Region)",
        viz_type="pie",
        params={
            "datasource": f"{ds_region}__table",
            "viz_type": "pie",
            "groupby": ["region"],
            "metric": _simple_metric("order_count", "SUM", "Số Đơn"),
            "adhoc_filters": [],
            "row_limit": 20,
            "show_labels": True,
            "show_legend": True,
            "donut": False,
        },
    )

    # ── Line graph: Daily Revenue Over Time ─────────────────────────────────
    chart_ids["line_daily"] = ensure_chart(
        client,
        dashboard_id=dashboard_id,
        dataset_id=ds_daily,
        slice_name="DLH – Doanh Thu Theo Ngày (Daily Revenue)",
        viz_type="echarts_timeseries_line",
        params={
            "datasource": f"{ds_daily}__table",
            "viz_type": "echarts_timeseries_line",
            "x_axis": "order_date",
            "metrics": [_simple_metric("total_revenue", "SUM", "Doanh Thu")],
            "groupby": [],
            "adhoc_filters": [],
            "time_grain_sqla": "P1D",
            "time_range": "No filter",
            "row_limit": 500,
            "show_legend": True,
            "area": False,
            "smooth": True,
        },
    )

    # ── Table: Daily Sales Summary ───────────────────────────────────────────
    chart_ids["table_daily"] = ensure_chart(
        client,
        dashboard_id=dashboard_id,
        dataset_id=ds_daily,
        slice_name="DLH – Bảng Tổng Hợp Doanh Số (Daily Sales Table)",
        viz_type="table",
        params={
            "datasource": f"{ds_daily}__table",
            "viz_type": "table",
            "all_columns": [
                "order_date", "order_count", "total_revenue",
                "avg_order_value", "total_quantity",
                "unique_customers", "unique_regions",
            ],
            "adhoc_filters": [],
            "order_desc": True,
            "row_limit": 100,
            "include_search": True,
            "show_cell_bars": True,
        },
    )

    # ── Bar chart: Top Regions by Revenue ───────────────────────────────────
    chart_ids["bar_region"] = ensure_chart(
        client,
        dashboard_id=dashboard_id,
        dataset_id=ds_region,
        slice_name="DLH – Doanh Thu theo Vùng (Revenue by Region)",
        viz_type="echarts_bar",
        params={
            "datasource": f"{ds_region}__table",
            "viz_type": "echarts_bar",
            "x_axis": "region",
            "metrics": [_simple_metric("total_revenue", "SUM", "Doanh Thu")],
            "groupby": [],
            "adhoc_filters": [],
            "row_limit": 20,
            "order_desc": True,
            "show_legend": False,
            "show_bar_value": True,
            "orientation": "vertical",
        },
    )

    # ── Assemble dashboard layout ───────────────────────────────────────────
    layout = build_layout(chart_ids)
    client.put(
        f"/api/v1/dashboard/{dashboard_id}",
        {
            "position_json": _to_params(layout),
            "json_metadata": _to_params({"color_scheme": "supersetColors"}),
            "published": True,
        },
    )

    result = client.get(f"/api/v1/dashboard/{dashboard_id}").get("result", {})
    dashboard_url = result.get("url") or f"/superset/dashboard/{dashboard_id}/"

    print("\n✅  Superset dashboard ready!")
    print(f"   Title : {DASHBOARD_TITLE}")
    print(f"   URL   : {BASE_URL}{dashboard_url}")
    print("\nCharts created:")
    chart_labels = {
        "kpi_revenue": "KPI – Tổng Doanh Thu",
        "kpi_orders": "KPI – Tổng Đơn Hàng",
        "kpi_avg": "KPI – Giá Trị TB",
        "bar_category": "Biểu đồ cột – Doanh Thu / Danh Mục",
        "pie_region": "Biểu đồ tròn – Đơn Hàng / Vùng",
        "line_daily": "Đồ thị đường – Doanh Thu Theo Ngày",
        "table_daily": "Bảng tính – Tổng Hợp Doanh Số",
        "bar_region": "Biểu đồ cột – Doanh Thu / Vùng",
    }
    for key, label in chart_labels.items():
        print(f"   [{chart_ids[key]:>5}] {label}")


if __name__ == "__main__":
    main()
