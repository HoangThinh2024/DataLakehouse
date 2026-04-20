#!/usr/bin/env python3
"""
DataLakehouse – Unified ETL + Dashboard runner.

Steps:
  1. Load environment (custom workspace preferred over defaults).
  2. Connect to the configured PostgreSQL workspace.
  3. Ask the user whether to create a sample table in the custom schema.
  4. If yes → create the table and insert sample data.
  5. Run ETL: extract from PostgreSQL → archive in RustFS → load into ClickHouse.
  6. Create (or update) the comprehensive Superset analytics dashboard.

Run from the project root:
  python3 scripts/run_etl_and_dashboard.py

Environment variables (from .env or shell):
  CUSTOM_DB_NAME, CUSTOM_DB_USER, CUSTOM_DB_PASSWORD, CUSTOM_SCHEMA
  SOURCE_DB_NAME, SOURCE_DB_USER, SOURCE_DB_PASSWORD, SOURCE_SCHEMA
  POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
  RUSTFS_*, CLICKHOUSE_*, SUPERSET_*
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Environment loading
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = REPO_ROOT / ".env"


def _has_surrogates(value: str) -> bool:
    return any(0xD800 <= ord(ch) <= 0xDFFF for ch in value)


def _sanitize_env_value(value: str) -> str:
    """Normalize environment values that may contain surrogate-escaped bytes on WSL."""
    if not value:
        return value
    if not _has_surrogates(value):
        return value

    raw = value.encode("utf-8", errors="surrogateescape")
    for encoding in ("utf-8", "cp1258", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return

    raw_bytes = path.read_bytes()
    text = ""
    decode_errors: list[str] = []

    # Windows editors can save .env as UTF-8 BOM or UTF-16 with BOM.
    if raw_bytes.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            text = raw_bytes.decode("utf-16")
            print(f"Warning: loaded {path} using utf-16 encoding", file=sys.stderr)
        except UnicodeDecodeError as exc:
            decode_errors.append(f"utf-16: {exc}")
    elif raw_bytes.startswith(b"\xef\xbb\xbf"):
        try:
            text = raw_bytes.decode("utf-8-sig")
            print(f"Warning: loaded {path} using utf-8-sig encoding", file=sys.stderr)
        except UnicodeDecodeError as exc:
            decode_errors.append(f"utf-8-sig: {exc}")

    if not text:
        for encoding in ("utf-8", "cp1258", "cp1252", "latin-1"):
            try:
                text = raw_bytes.decode(encoding)
                if encoding != "utf-8":
                    print(f"Warning: loaded {path} using {encoding} encoding", file=sys.stderr)
                break
            except UnicodeDecodeError as exc:
                decode_errors.append(f"{encoding}: {exc}")

    if not text:
        # Last-resort decode so a malformed byte does not block orchestration startup.
        text = raw_bytes.decode("utf-8", errors="replace")
        print(
            f"Warning: loaded {path} with UTF-8 replacement for invalid bytes. "
            f"Decode attempts failed: {'; '.join(decode_errors)}",
            file=sys.stderr,
        )

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            existing = os.environ.get(key)
            # Keep explicit shell overrides, except when value is encoding-corrupted.
            if existing is None or _has_surrogates(existing):
                os.environ[key] = value


_load_env_file(ENV_FILE)


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name, "")
    value = _sanitize_env_value(value)
    return value if value else default


def _host_bind_ip() -> str:
    ip = _env("DLH_BIND_IP", "127.0.0.1")
    return "127.0.0.1" if ip in {"0.0.0.0", "::"} else ip


# ---------------------------------------------------------------------------
# Resolve effective source DB credentials
# ---------------------------------------------------------------------------
def _effective_source() -> dict[str, Any]:
    """
    Return the DB connection settings that ETL should use.
    Priority: CUSTOM_DB_* > SOURCE_DB_* > POSTGRES_*.
    """
    source_db = _env("SOURCE_DB_NAME")
    source_user = _env("SOURCE_DB_USER")
    source_password = _env("SOURCE_DB_PASSWORD")
    source_schema = _env("SOURCE_SCHEMA")

    custom_db = _env("CUSTOM_DB_NAME")
    custom_user = _env("CUSTOM_DB_USER")
    custom_password = _env("CUSTOM_DB_PASSWORD")
    custom_schema = _env("CUSTOM_SCHEMA")

    # Respect explicit SOURCE_* configuration first.
    if source_db and source_user and source_password:
        return {
            "host": _env("SOURCE_DB_HOST", _env("DLH_BIND_IP", "127.0.0.1")),
            "port": int(_env("SOURCE_DB_PORT", _env("DLH_POSTGRES_PORT", "25432"))),
            "dbname": source_db,
            "user": source_user,
            "password": source_password,
            "schema": source_schema or custom_schema or "public",
            "is_custom": bool(custom_db and source_db == custom_db),
        }

    if custom_db and custom_user and custom_password:
        return {
            "host": _env("SOURCE_DB_HOST", _env("DLH_BIND_IP", "127.0.0.1")),
            "port": int(_env("SOURCE_DB_PORT", _env("DLH_POSTGRES_PORT", "25432"))),
            "dbname": custom_db,
            "user": custom_user,
            "password": custom_password,
            "schema": custom_schema or "public",
            "is_custom": True,
        }

    # Fall back to SOURCE_DB_* or POSTGRES_*
    return {
        "host": _env("SOURCE_DB_HOST", _env("DLH_BIND_IP", "127.0.0.1")),
        "port": int(_env("SOURCE_DB_PORT", _env("DLH_POSTGRES_PORT", "25432"))),
        "dbname": _env("SOURCE_DB_NAME", _env("POSTGRES_DB", "datalakehouse")),
        "user": _env("SOURCE_DB_USER", _env("POSTGRES_USER", "dlh_admin")),
        "password": _env("SOURCE_DB_PASSWORD", _env("POSTGRES_PASSWORD", "")),
        "schema": _env("SOURCE_SCHEMA", _env("CUSTOM_SCHEMA", "public")),
        "is_custom": False,
    }


def _default_source_table() -> str:
    explicit = _env("SOURCE_TABLE")
    if explicit:
        return explicit

    candidates = [
        name.strip()
        for name in _env("SOURCE_TABLE_CANDIDATES", "Demo,test_projects,sales_orders").split(",")
        if name.strip()
    ]
    return candidates[0] if candidates else "sales_orders"


def _source_table_candidates() -> list[str]:
    names = [
        name.strip()
        for name in _env("SOURCE_TABLE_CANDIDATES", "Demo,test_projects,sales_orders").split(",")
        if name.strip()
    ]
    if not names:
        names = ["sales_orders"]
    return names


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run DataLakehouse ETL and optionally create Superset dashboard"
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Run non-interactively using existing/default source table selection",
    )
    parser.add_argument(
        "--create-sample-table",
        action="store_true",
        help="In --auto mode, create sample table if needed before running ETL",
    )
    parser.add_argument(
        "--table",
        default="",
        help="Force table name for ETL source",
    )
    parser.add_argument(
        "--skip-dashboard",
        action="store_true",
        help="Run ETL only and skip Superset dashboard creation",
    )
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# PostgreSQL helpers
# ---------------------------------------------------------------------------
def _pg_connect(cfg: dict[str, Any]):
    try:
        import psycopg2
    except ImportError:
        print("❌  psycopg2 not found. Install it: pip install psycopg2-binary")
        sys.exit(1)

    return psycopg2.connect(
        host=cfg["host"],
        port=cfg["port"],
        dbname=cfg["dbname"],
        user=cfg["user"],
        password=cfg["password"],
        connect_timeout=10,
    )


def _table_exists(conn, schema: str, table: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = %s AND table_name = %s
            """,
            (schema, table),
        )
        return cur.fetchone() is not None


def _list_tables(conn, schema: str) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = %s AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """,
            (schema,),
        )
        return [r[0] for r in cur.fetchall()]


def create_sample_table(conn, schema: str, table_name: str) -> int:
    """Create a sample sales table and insert demo rows. Returns row count inserted."""
    with conn.cursor() as cur:
        cur.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS "{schema}"."{table_name}" (
                id           SERIAL PRIMARY KEY,
                product_name TEXT        NOT NULL,
                category     TEXT,
                unit_price   NUMERIC(14,2),
                quantity     INTEGER,
                order_date   DATE,
                region       TEXT,
                status       TEXT,
                customer     TEXT,
                created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        rows: list[tuple[Any, ...]] = [
            ("Laptop Pro 15",   "Electronics",  25000000, 1, "2024-01-03", "Hanoi",        "completed", "Nguyen Van A"),
            ("Smart Watch X",   "Electronics",   4500000, 2, "2024-01-05", "Ho Chi Minh",  "completed", "Tran Thi B"),
            ("Running Shoes",   "Sports",        1200000, 3, "2024-01-07", "Da Nang",       "completed", "Le Van C"),
            ("Cookbook Deluxe", "Books",          350000, 5, "2024-01-09", "Can Tho",       "completed", "Pham Thi D"),
            ("Yoga Mat Premium","Sports",         750000, 2, "2024-01-11", "Hanoi",         "processing","Hoang Van E"),
            ("Bluetooth Speaker","Electronics",  2100000, 1, "2024-01-13", "Hai Phong",    "completed", "Vu Thi F"),
            ("Linen Shirt",     "Fashion",        480000, 4, "2024-01-15", "Ho Chi Minh",  "completed", "Dang Van G"),
            ("Garden Hose 20m", "Home & Garden",  390000, 2, "2024-01-17", "Hanoi",        "completed", "Bui Thi H"),
            ("Novel Bestseller","Books",          120000, 8, "2024-01-19", "Da Nang",      "completed", "Nguyen Van I"),
            ("4K Monitor",      "Electronics",  12500000, 1, "2024-01-21", "Ho Chi Minh",  "pending",   "Tran Van J"),
            ("Trekking Poles",  "Sports",         920000, 2, "2024-02-01", "Hanoi",        "completed", "Le Thi K"),
            ("Ceramic Pots Set","Home & Garden",  670000, 3, "2024-02-03", "Can Tho",      "completed", "Pham Van L"),
            ("Denim Jacket",    "Fashion",        990000, 2, "2024-02-05", "Ho Chi Minh",  "returned",  "Hoang Thi M"),
            ("USB-C Hub",       "Electronics",   1350000, 2, "2024-02-07", "Hanoi",        "completed", "Vu Van N"),
            ("Planter Box",     "Home & Garden",  290000, 5, "2024-02-09", "Da Nang",      "completed", "Dang Thi O"),
            ("Bicycle Helmet",  "Sports",         650000, 1, "2024-02-11", "Hai Phong",    "completed", "Bui Van P"),
            ("Python Cookbook", "Books",          280000, 4, "2024-02-13", "Ho Chi Minh",  "completed", "Nguyen Thi Q"),
            ("Gaming Chair",    "Electronics",   5800000, 1, "2024-02-15", "Hanoi",        "completed", "Tran Van R"),
            ("Summer Dress",    "Fashion",        420000, 3, "2024-02-17", "Can Tho",      "completed", "Le Van S"),
            ("Electric Kettle", "Home & Garden",  480000, 2, "2024-02-19", "Ho Chi Minh",  "completed", "Pham Thi T"),
        ]
        cur.executemany(
            f"""
            INSERT INTO "{schema}"."{table_name}"
              (product_name, category, unit_price, quantity, order_date, region, status, customer)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            -- Skip rows that already exist (primary-key conflict on id).
            -- Safe to re-run: existing data is not modified.
            ON CONFLICT DO NOTHING
            """,
            rows,
        )
        conn.commit()
        return len(rows)


# ---------------------------------------------------------------------------
# ETL runner (delegates to demo_to_lakehouse.py logic)
# ---------------------------------------------------------------------------
def run_etl(cfg: dict[str, Any], table_name: str) -> None:
    """
    Set env vars so demo_to_lakehouse.py uses the correct workspace,
    then import and call its main() function.
    """
    # Override env vars for this process
    os.environ["SOURCE_DB_HOST"] = cfg["host"]
    os.environ["SOURCE_DB_PORT"] = str(cfg["port"])
    os.environ["SOURCE_DB_NAME"] = cfg["dbname"]
    os.environ["SOURCE_DB_USER"] = cfg["user"]
    os.environ["SOURCE_DB_PASSWORD"] = cfg["password"]
    os.environ["SOURCE_SCHEMA"] = cfg["schema"]
    os.environ["SOURCE_TABLE"] = table_name
    # Also align CUSTOM_DB_* so demo_to_lakehouse picks them up
    if cfg["is_custom"]:
        os.environ["CUSTOM_DB_NAME"] = cfg["dbname"]
        os.environ["CUSTOM_DB_USER"] = cfg["user"]
        os.environ["CUSTOM_DB_PASSWORD"] = cfg["password"]
        os.environ["CUSTOM_SCHEMA"] = cfg["schema"]

    # RustFS (host-side defaults)
    if not os.environ.get("RUSTFS_ENDPOINT_URL"):
        bind_ip = _host_bind_ip()
        rustfs_port = _env("DLH_RUSTFS_API_PORT", "29100")
        os.environ["RUSTFS_ENDPOINT_URL"] = f"http://{bind_ip}:{rustfs_port}"

    # ClickHouse (host-side defaults)
    if not os.environ.get("CLICKHOUSE_HTTP_URL"):
        bind_ip = _host_bind_ip()
        ch_port = _env("DLH_CLICKHOUSE_HTTP_PORT", "28123")
        os.environ["CLICKHOUSE_HTTP_URL"] = f"http://{bind_ip}:{ch_port}"

    etl_script = REPO_ROOT / "scripts" / "demo_to_lakehouse.py"
    if not etl_script.exists():
        print(f"❌  ETL script not found: {etl_script}")
        sys.exit(1)

    # Import and run
    import importlib.util
    spec = importlib.util.spec_from_file_location("demo_to_lakehouse", etl_script)
    if spec is None or spec.loader is None:
        print(f"❌  Could not load ETL module from {etl_script}")
        sys.exit(1)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)  # type: ignore[attr-defined]
    except Exception as exc:
        print(f"❌  Failed to load ETL module ({etl_script}): {exc}")
        sys.exit(1)
    rc = module.main()
    if rc != 0:
        print(f"❌  ETL finished with exit code {rc}")
        sys.exit(rc)


# ---------------------------------------------------------------------------
# Dashboard runner
# ---------------------------------------------------------------------------
def run_dashboard() -> None:
    """Set host-side Superset URL and call the dashboard creation script."""
    if not os.environ.get("SUPERSET_URL"):
        bind_ip = _host_bind_ip()
        superset_port = _env("DLH_SUPERSET_PORT", "28088")
        os.environ["SUPERSET_URL"] = f"http://{bind_ip}:{superset_port}"

    dashboard_script = REPO_ROOT / "scripts" / "create_superset_demo_dashboard.py"
    if not dashboard_script.exists():
        print(f"❌  Dashboard script not found: {dashboard_script}")
        sys.exit(1)

    import importlib.util
    spec = importlib.util.spec_from_file_location("create_superset_demo_dashboard", dashboard_script)
    if spec is None or spec.loader is None:
        print(f"❌  Could not load dashboard module from {dashboard_script}")
        sys.exit(1)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)  # type: ignore[attr-defined]
    except ModuleNotFoundError as exc:
        missing = getattr(exc, "name", None) or str(exc)
        print(
            f"❌  Missing Python package '{missing}' for dashboard module ({dashboard_script})."
        )
        print("    Install Python dependencies with:")
        print("    uv sync --all-groups")
        print("    (or fallback: pip install boto3 psycopg2-binary requests)")
        sys.exit(1)
    except Exception as exc:
        print(f"❌  Failed to load dashboard module ({dashboard_script}): {exc}")
        sys.exit(1)
    module.main()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    print()
    print("=" * 60)
    print("  DataLakehouse – ETL & Dashboard Runner")
    print("=" * 60)

    cfg = _effective_source()
    label = "custom workspace" if cfg["is_custom"] else "default workspace"

    # Extract non-sensitive fields for display – keeps password out of log lines.
    src_host: str = cfg["host"]
    src_port: int = cfg["port"]
    src_dbname: str = cfg["dbname"]
    src_schema: str = cfg["schema"]
    src_user: str = cfg["user"]

    print(f"\n📦  Source: {label}")
    print(f"    Host   : {src_host}:{src_port}")
    print(f"    DB     : {src_dbname}")
    print(f"    Schema : {src_schema}")
    print(f"    User   : {src_user}")
    print(f"    Pass   : {'*' * 8}")

    # ── Connect ──────────────────────────────────────────────
    print("\n🔌  Connecting to PostgreSQL …")
    try:
        conn = _pg_connect(cfg)
        conn.autocommit = False
        print("    Connected ✓")
    except Exception as exc:
        print(f"\n❌  Cannot connect to PostgreSQL: {exc}")
        print(
            "\n  Tip: Make sure the stack is running (`docker compose up -d`) and the"
            "\n  DLH_POSTGRES_PORT / SOURCE_DB_HOST settings in .env match your host."
        )
        return 1

    # ── Check / create schema ─────────────────────────────────
    schema = src_schema
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s", (schema,)
        )
        if not cur.fetchone():
            print(f"\n  Schema '{schema}' does not exist yet – it will be created.")

    # ── Test table ────────────────────────────────────────────
    etl_table = _default_source_table()
    tables = _list_tables(conn, schema)

    if args.auto:
        desired_table = (args.table or "").strip()
        auto_candidates = [desired_table] if desired_table else _source_table_candidates()

        if args.create_sample_table:
            table_name = desired_table or "sales_orders"
            if _table_exists(conn, schema, table_name):
                print(f"  ℹ️  Table '{schema}.{table_name}' already exists – skipping creation.")
            else:
                print(f"  ✏️  Creating '{schema}.{table_name}' …")
                n = create_sample_table(conn, schema, table_name)
                print(f"  ✅  Created table with {n} sample rows.")
            etl_table = table_name
        else:
            picked = ""
            for candidate in auto_candidates:
                if candidate and candidate in tables:
                    picked = candidate
                    break

            if picked:
                etl_table = picked
                print(f"  🤖 Auto mode selected source table: '{etl_table}'")
            elif tables:
                etl_table = tables[0]
                print(f"  🤖 Auto mode selected first table: '{etl_table}'")
            else:
                # Auto-bootstrap data to guarantee ETL can run end-to-end.
                etl_table = desired_table or "sales_orders"
                print(f"  ⚠️  No tables found in schema '{schema}'.")
                print(f"  ✏️  Auto mode will create sample table '{schema}.{etl_table}' …")
                n = create_sample_table(conn, schema, etl_table)
                print(f"  ✅  Created table with {n} sample rows.")
    else:
        print()
        answer = input(
            f"  ❓ Create a sample 'sales_orders' table in schema '{schema}' of '{src_dbname}'? [y/N]: "
        ).strip().lower()

        if answer in ("y", "yes"):
            table_name = input(
                "     Table name [sales_orders]: "
            ).strip() or "sales_orders"

            if _table_exists(conn, schema, table_name):
                print(f"  ℹ️  Table '{schema}.{table_name}' already exists – skipping creation.")
            else:
                print(f"  ✏️  Creating '{schema}.{table_name}' …")
                n = create_sample_table(conn, schema, table_name)
                print(f"  ✅  Created table with {n} sample rows.")

            etl_table = table_name
        else:
            if tables:
                display_tables = tables[:10]
                print(f"\n  Available tables in schema '{schema}': {display_tables}")
                chosen = input(f"  Table for ETL [{display_tables[0]}]: ").strip() or display_tables[0]
                etl_table = chosen
            else:
                print(f"\n  ⚠️  No tables found in schema '{schema}'. ETL will use default 'Demo' table.")

    conn.close()

    # ── ETL ───────────────────────────────────────────────────
    print("\n🚀  Running ETL pipeline …")
    print(f"    Source: {src_dbname}.{schema}.{etl_table}")
    try:
        run_etl(cfg, etl_table)
        print("  ✅  ETL complete.")
    except SystemExit as exc:
        print(f"  ❌  ETL failed (exit code {exc.code})")
        return int(exc.code) if exc.code is not None else 1

    # ── Dashboard ─────────────────────────────────────────────
    if args.skip_dashboard:
        print("\n⏭️  Skipping Superset dashboard creation (--skip-dashboard).")
    else:
        print("\n📊  Creating Superset dashboard …")
        try:
            run_dashboard()
        except Exception as exc:
            print(f"\n  ⚠️  Dashboard creation failed: {exc}")
            print(
                "  Make sure Superset is healthy and SUPERSET_ADMIN_USER / "
                "SUPERSET_ADMIN_PASSWORD are correct."
            )
            return 1

    print("\n" + "=" * 60)
    print("  All done! Open Superset to view your dashboards.")
    bind_ip = _host_bind_ip()
    superset_port = _env("DLH_SUPERSET_PORT", "28088")
    print(f"  Superset: http://{bind_ip}:{superset_port}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
