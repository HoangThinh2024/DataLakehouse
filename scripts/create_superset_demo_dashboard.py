#!/usr/bin/env python3
"""Create or update a Superset demo dashboard for the 100k CSV showcase.

Run from host machine:
  python scripts/create_superset_demo_dashboard.py

Environment variables:
  SUPERSET_URL (default: http://127.0.0.1:28088)
  SUPERSET_ADMIN_USER (default: admin)
  SUPERSET_ADMIN_PASSWORD (default: admin)
  SUPERSET_DEMO_DASHBOARD_TITLE (default: Data Lakehouse CSV Demo 100k)
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict

import requests

BASE_URL = os.getenv("SUPERSET_URL", "http://127.0.0.1:28088").rstrip("/")
ADMIN_USER = os.getenv("SUPERSET_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("SUPERSET_ADMIN_PASSWORD", "admin")
DASHBOARD_TITLE = os.getenv("SUPERSET_DEMO_DASHBOARD_TITLE", "Data Lakehouse CSV Demo 100k")
DASHBOARD_SLUG = "data-lakehouse-csv-demo-100k"

DB_NAME = "ClickHouse Analytics"
DB_URI = "clickhousedb+connect://default:@dlh-clickhouse:8123/analytics"
SCHEMA = "analytics"


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
            # Some Superset builds reject partial dashboard updates on chart PUT.
            # Reuse the existing chart and rely on dashboard layout update below.
            chart_id = int(item["id"])
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


def build_layout(chart_ids: Dict[str, int]) -> Dict[str, Any]:
    return {
        "ROOT_ID": {"id": "ROOT_ID", "type": "ROOT", "children": ["GRID_ID"], "parents": []},
        "GRID_ID": {"id": "GRID_ID", "type": "GRID", "children": ["ROW-1", "ROW-2"], "parents": ["ROOT_ID"]},
        "ROW-1": {
            "id": "ROW-1",
            "type": "ROW",
            "children": ["CHART-overview", "CHART-quality"],
            "parents": ["ROOT_ID", "GRID_ID"],
            "meta": {"background": "BACKGROUND_TRANSPARENT"},
        },
        "CHART-overview": {
            "id": "CHART-overview",
            "type": "CHART",
            "children": [],
            "parents": ["ROOT_ID", "GRID_ID", "ROW-1"],
            "meta": {"chartId": chart_ids["kpi_cleaned"], "width": 6, "height": 60},
        },
        "CHART-quality": {
            "id": "CHART-quality",
            "type": "CHART",
            "children": [],
            "parents": ["ROOT_ID", "GRID_ID", "ROW-1"],
            "meta": {"chartId": chart_ids["quality_table"], "width": 6, "height": 60},
        },
        "ROW-2": {
            "id": "ROW-2",
            "type": "ROW",
            "children": ["CHART-bar", "CHART-events"],
            "parents": ["ROOT_ID", "GRID_ID"],
            "meta": {"background": "BACKGROUND_TRANSPARENT"},
        },
        "CHART-bar": {
            "id": "CHART-bar",
            "type": "CHART",
            "children": [],
            "parents": ["ROOT_ID", "GRID_ID", "ROW-2"],
            "meta": {"chartId": chart_ids["quality_bar"], "width": 6, "height": 60},
        },
        "CHART-events": {
            "id": "CHART-events",
            "type": "CHART",
            "children": [],
            "parents": ["ROOT_ID", "GRID_ID", "ROW-2"],
            "meta": {"chartId": chart_ids["events_table"], "width": 6, "height": 60},
        },
    }


def main() -> None:
    client = SupersetClient(BASE_URL, ADMIN_USER, ADMIN_PASSWORD)

    db_id = ensure_database(client)
    ds_quality = ensure_dataset(client, db_id, "csv_quality_metrics")
    ds_events = ensure_dataset(client, db_id, "csv_upload_events")
    dashboard_id = ensure_dashboard(client)

    chart_ids = {
        "kpi_cleaned": ensure_chart(
            client,
            dashboard_id=dashboard_id,
            dataset_id=ds_quality,
            slice_name="DLH 100k - CSV Data Overview",
            viz_type="table",
            params={
                "datasource": f"{ds_quality}__table",
                "viz_type": "table",
                "all_columns": ["source_key", "raw_rows", "cleaned_rows", "dropped_rows", "duplicate_rows", "processed_at"],
                "adhoc_filters": [],
                "order_desc": True,
                "row_limit": 10,
            },
        ),
        "quality_table": ensure_chart(
            client,
            dashboard_id=dashboard_id,
            dataset_id=ds_quality,
            slice_name="DLH 100k - CSV Quality Metrics",
            viz_type="table",
            params={
                "datasource": f"{ds_quality}__table",
                "viz_type": "table",
                "all_columns": ["source_key", "raw_rows", "cleaned_rows", "dropped_rows", "duplicate_rows", "processed_at"],
                "adhoc_filters": [],
                "order_desc": True,
                "row_limit": 50,
            },
        ),
        "events_table": ensure_chart(
            client,
            dashboard_id=dashboard_id,
            dataset_id=ds_events,
            slice_name="DLH 100k - CSV Upload Events",
            viz_type="table",
            params={
                "datasource": f"{ds_events}__table",
                "viz_type": "table",
                "all_columns": ["source_key", "status", "error_message", "processed_at", "row_count"],
                "adhoc_filters": [],
                "order_desc": True,
                "row_limit": 50,
            },
        ),
        "quality_bar": ensure_chart(
            client,
            dashboard_id=dashboard_id,
            dataset_id=ds_quality,
            slice_name="DLH 100k - CSV Row Processing Comparison",
            viz_type="echarts_timeseries",
            params={
                "datasource": f"{ds_quality}__table",
                "viz_type": "echarts_timeseries",
                "x_axis": {"type": "time", "label": "File"},
                "y_axis": {"label": "Row Count"},
                "time_grain_sqla": None,
                "time_range": "No filter",
                "granularity_sqla": None,
                "groupby": ["source_key"],
                "metrics": [
                    {
                        "label": "Cleaned Rows",
                        "expressionType": "SIMPLE",
                        "column": {"column_name": "cleaned_rows"},
                        "aggregate": "SUM",
                    },
                    {
                        "label": "Dropped Rows",
                        "expressionType": "SIMPLE",
                        "column": {"column_name": "dropped_rows"},
                        "aggregate": "SUM",
                    },
                ],
                "adhoc_filters": [],
                "order_desc": True,
                "row_limit": 100,
            },
        ),
    }

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
    print("Superset dashboard ready")
    print(f"- dashboard_id: {dashboard_id}")
    print(f"- title: {DASHBOARD_TITLE}")
    print(f"- url: {BASE_URL}{dashboard_url}")
    for key, value in chart_ids.items():
        print(f"- chart_{key}: {value}")


if __name__ == "__main__":
    main()
