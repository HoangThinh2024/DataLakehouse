import os

SQLALCHEMY_DATABASE_URI = (
    f"postgresql+psycopg2://{os.getenv('SUPERSET_DB_USER', 'dlh_superset_user')}:"
    f"{os.getenv('SUPERSET_DB_PASSWORD', 'change-me')}@dlh-postgres:5432/"
    f"{os.getenv('SUPERSET_DB_NAME', 'dlh_superset')}"
)

SECRET_KEY = os.getenv('SUPERSET_SECRET_KEY', 'replace-this-secret')

# Allow ClickHouse (via clickhouse-connect) and PostgreSQL connections from the UI
PREVENT_UNSAFE_DB_CONNECTIONS = False

FEATURE_FLAGS = {
    "ENABLE_TEMPLATE_PROCESSING": True,
    "DASHBOARD_NATIVE_FILTERS": True,
    "DASHBOARD_CROSS_FILTERS": True,
}

# Honor X-Forwarded-* headers when running behind reverse proxies
# (e.g., Nginx Proxy Manager / openresty) so login redirects keep HTTPS.
ENABLE_PROXY_FIX = True
PROXY_FIX_CONFIG = {
    "x_for": 1,
    "x_proto": 1,
    "x_host": 1,
    "x_port": 1,
    "x_prefix": 1,
}
PREFERRED_URL_SCHEME = os.getenv("SUPERSET_PREFERRED_URL_SCHEME", "http")

# Pre-register ClickHouse as an allowed database engine
# Requires: pip install clickhouse-connect (installed in docker-compose command)
ADDITIONAL_DATABASE_CONFIG_MAP = {}

