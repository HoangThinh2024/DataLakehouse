#!/usr/bin/env python3
"""
Diagnostic Script to Test Individual Services in the DataLakehouse Stack.
Performs both container-level checks and deep service connectivity/query validation.
"""

import os
import sys
import subprocess
import requests
from pathlib import Path
from dotenv import load_dotenv

# ANSI Colors
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
BOLD = "\033[1m"
UNDERLINE = "\033[4m"
RESET = "\033[0m"

REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")

# Port settings from environment
POSTGRES_PORT = os.getenv("DLH_POSTGRES_PORT", "25432")
CLICKHOUSE_HTTP_PORT = os.getenv("DLH_CLICKHOUSE_HTTP_PORT", "28123")
RUSTFS_API_PORT = os.getenv("DLH_RUSTFS_API_PORT", "29100")
RUSTFS_CONSOLE_PORT = os.getenv("DLH_RUSTFS_CONSOLE_PORT", "29101")
REDIS_PORT = os.getenv("DLH_REDIS_PORT", "26379")
REDIS_GUI_PORT = os.getenv("DLH_REDIS_GUI_PORT", "25540")
MAGE_PORT = os.getenv("DLH_MAGE_PORT", "26789")
SUPERSET_PORT = os.getenv("DLH_SUPERSET_PORT", "28088")
GRAFANA_PORT = os.getenv("DLH_GRAFANA_PORT", "23001")
AUTHENTIK_PORT = os.getenv("DLH_AUTHENTIK_PORT", "29090")
REDPANDA_CONSOLE_PORT = os.getenv("DLH_REDPANDA_CONSOLE_PORT", "29080")
CLOUDBEAVER_PORT = os.getenv("DLH_CLOUDBEAVER_PORT", "28978")
DOCKHAND_PORT = os.getenv("DLH_DOCKHAND_PORT", "23000")

# Database credentials
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_DB = os.getenv("POSTGRES_DB", "datalakehouse")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "change-me-in-production")
CLICKHOUSE_USER = os.getenv("CLICKHOUSE_USER", "doe")
CLICKHOUSE_DB = os.getenv("CLICKHOUSE_DB", "analytics")

def log_header(title):
    print(f"\n{BOLD}{BLUE}{'='*60}{RESET}")
    print(f"{BOLD}{BLUE} {title.upper()}{RESET}")
    print(f"{BOLD}{BLUE}{'='*60}{RESET}")

def run_command(cmd, shell=True, timeout=10):
    try:
        result = subprocess.run(
            cmd,
            shell=shell,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"
    except Exception as e:
        return -2, "", str(e)

def format_status(success, details=""):
    if success:
        return f"{GREEN}✓ PASS{RESET} {details}"
    else:
        return f"{RED}✗ FAIL{RESET} {details}"

# --- Check Functions ---

def test_container_running(container_name):
    cmd = f"docker inspect -f '{{{{.State.Running}}}}' {container_name}"
    code, stdout, stderr = run_command(cmd)
    if code == 0 and stdout == "true":
        # Get health if defined
        health_cmd = f"docker inspect -f '{{{{if .State.Health}}}}{{{{.State.Health.Status}}}}{{{{else}}}}no-healthcheck{{{{end}}}}' {container_name}"
        _, h_stdout, _ = run_command(health_cmd)
        status_info = f"Running"
        if h_stdout and h_stdout != "no-healthcheck":
            status_info += f" ({h_stdout})"
        return True, status_info
    return False, f"Not Running ({stderr or 'Stopped'})"

def test_postgres():
    container = "dlh-postgres"
    ok, details = test_container_running(container)
    if not ok:
        return False, f"Container offline: {details}"
    
    # 1. pg_isready check
    cmd = f"docker exec {container} pg_isready -U {POSTGRES_USER} -d {POSTGRES_DB}"
    code, stdout, stderr = run_command(cmd)
    if code != 0:
        return False, f"PostgreSQL not ready: {stdout or stderr}"
        
    # 2. Query check
    query_cmd = f"docker exec {container} psql -U {POSTGRES_USER} -d {POSTGRES_DB} -c 'SELECT 1;'"
    code, stdout, stderr = run_command(query_cmd)
    if code != 0:
        return False, f"Query failed: {stderr}"
        
    return True, "Ready, Query OK"

def test_clickhouse():
    container = "dlh-clickhouse"
    ok, details = test_container_running(container)
    if not ok:
        return False, f"Container offline: {details}"
        
    # Query check
    query_cmd = f"docker exec {container} clickhouse-client --query 'SELECT 1'"
    code, stdout, stderr = run_command(query_cmd)
    if code != 0:
        return False, f"Query failed: {stderr}"
    return True, f"Query OK (CH Version: {stdout.strip() if stdout else 'Unknown'})"

def test_redis():
    container = "dlh-redis"
    ok, details = test_container_running(container)
    if not ok:
        return False, f"Container offline: {details}"
        
    # PING check
    ping_cmd = f"docker exec {container} redis-cli -a '{REDIS_PASSWORD}' ping"
    code, stdout, stderr = run_command(ping_cmd)
    if "PONG" in stdout:
        return True, "PING -> PONG OK"
    return False, f"PING failed: {stdout or stderr}"

def test_redpanda():
    container = "dlh-redpanda"
    ok, details = test_container_running(container)
    if not ok:
        return False, f"Container offline: {details}"
        
    # Cluster health check
    health_cmd = f"docker exec {container} rpk cluster health"
    code, stdout, stderr = run_command(health_cmd)
    
    is_healthy = False
    for line in stdout.splitlines():
        if "Healthy:" in line and "true" in line:
            is_healthy = True
            break
            
    if code == 0 and is_healthy:
        return True, "Cluster healthy"
    return False, f"rpk cluster health check failed:\n{stdout or stderr}"

def test_http_endpoint(name, url, expected_code=200):
    try:
        response = requests.get(url, timeout=3, allow_redirects=True)
        if response.status_code == expected_code or (expected_code == 200 and response.ok):
            return True, f"HTTP {response.status_code} OK"
        return False, f"HTTP {response.status_code} (Expected {expected_code})"
    except requests.exceptions.RequestException as e:
        return False, f"Connection Refused: {str(e)}"

# --- Main Test Pipeline ---

def main():
    log_header("DataLakehouse Stack Health & Service Diagnostics")
    
    # 1. Verify Docker Compose containers exist and are up
    print(f"\n{BOLD}1. Docker Container Status:{RESET}")
    containers = [
        "dlh-postgres", "dlh-clickhouse", "dlh-rustfs", "dlh-redis", 
        "dlh-redpanda", "dlh-redpanda-console", "dlh-ingest-cdc", 
        "dlh-mage", "dlh-superset", "dlh-grafana", "dlh-authentik-server", 
        "dlh-authentik-worker", "dlh-redis-insight", "dlh-prometheus", 
        "dlh-node-exporter", "dlh-dockhand", "dlh-cloudbeaver", "zoraxy"
    ]
    
    all_ok = True
    container_results = {}
    for c in containers:
        running, info = test_container_running(c)
        container_results[c] = (running, info)
        print(f"  - {c:<25} : {format_status(running, info)}")
        if not running:
            # authentik-worker might be non-critical for core data pipelines but we still want all ok
            all_ok = False
            
    # 2. Deep Service Functional Checks
    log_header("Database & Event Broker Queries")
    
    # Postgres
    pg_ok, pg_details = test_postgres()
    print(f"  - PostgreSQL Core DB   : {format_status(pg_ok, pg_details)}")
    if not pg_ok: all_ok = False
    
    # ClickHouse
    ch_ok, ch_details = test_clickhouse()
    print(f"  - ClickHouse OLAP      : {format_status(ch_ok, ch_details)}")
    if not ch_ok: all_ok = False
    
    # Redis
    redis_ok, redis_details = test_redis()
    print(f"  - Redis Cache/Queue    : {format_status(redis_ok, redis_details)}")
    if not redis_ok: all_ok = False
    
    # Redpanda
    rp_ok, rp_details = test_redpanda()
    print(f"  - Redpanda Event Bus   : {format_status(rp_ok, rp_details)}")
    if not rp_ok: all_ok = False
    
    # 3. HTTP Interface & Web Port Checks
    log_header("Web Interface Health Checks")
    
    web_services = [
        ("Mage Orchestrator", f"http://127.0.0.1:{MAGE_PORT}/api/status"),
        ("RustFS S3 Health", f"http://127.0.0.1:{RUSTFS_API_PORT}/health"),
        ("RustFS Web Console", f"http://127.0.0.1:{RUSTFS_CONSOLE_PORT}/rustfs/console/health"),
        ("Superset Health", f"http://127.0.0.1:{SUPERSET_PORT}/health"),
        ("Grafana Health", f"http://127.0.0.1:{GRAFANA_PORT}/api/health"),
        ("Authentik Ready", f"http://127.0.0.1:{AUTHENTIK_PORT}/-/health/ready/"),
        ("Redpanda Console UI", f"http://127.0.0.1:{REDPANDA_CONSOLE_PORT}/"),
        ("CloudBeaver Database", f"http://127.0.0.1:{CLOUDBEAVER_PORT}/"),
        ("Dockhand Docker GUI", f"http://127.0.0.1:{DOCKHAND_PORT}/"),
    ]
    
    for label, url in web_services:
        web_ok, web_details = test_http_endpoint(label, url)
        print(f"  - {label:<22} : {format_status(web_ok, f'({url}) -> {web_details}')}")
        if not web_ok: all_ok = False

    # 4. Final Verdict
    print(f"\n{BOLD}{BLUE}{'='*60}{RESET}")
    if all_ok:
        print(f"{BOLD}{GREEN}  ALL SERVICES ARE RUNNING AND FULLY FUNCTIONAL! 🚀{RESET}")
        print(f"{BOLD}{BLUE}{'='*60}{RESET}\n")
        sys.exit(0)
    else:
        print(f"{BOLD}{RED}  WARNING: ONE OR MORE SERVICES FAILED THE DIAGNOSTICS! ⚠️{RESET}")
        print(f"{BOLD}{BLUE}{'='*60}{RESET}\n")
        sys.exit(1)

if __name__ == "__main__":
    main()
