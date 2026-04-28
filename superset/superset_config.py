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

REDIS_HOST = os.getenv("REDIS_HOST", "dlh-redis")
REDIS_PORT = os.getenv("REDIS_PORT", "6379")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")
SUPERSET_REDIS_CACHE_DB = os.getenv("SUPERSET_REDIS_CACHE_DB", "2")
SUPERSET_REDIS_RESULTS_DB = os.getenv("SUPERSET_REDIS_RESULTS_DB", "3")

if REDIS_PASSWORD:
    REDIS_AUTH = f":{REDIS_PASSWORD}@"
else:
    REDIS_AUTH = ""

REDIS_CACHE_URI = f"redis://{REDIS_AUTH}{REDIS_HOST}:{REDIS_PORT}/{SUPERSET_REDIS_CACHE_DB}"
REDIS_RESULTS_URI = f"redis://{REDIS_AUTH}{REDIS_HOST}:{REDIS_PORT}/{SUPERSET_REDIS_RESULTS_DB}"

# Shared caching layer for charts/dashboard metadata and SQL Lab async results.
CACHE_CONFIG = {
    "CACHE_TYPE": "RedisCache",
    "CACHE_DEFAULT_TIMEOUT": 300,
    "CACHE_KEY_PREFIX": "superset_cache_",
    "CACHE_REDIS_URL": REDIS_CACHE_URI,
}

DATA_CACHE_CONFIG = {
    "CACHE_TYPE": "RedisCache",
    "CACHE_DEFAULT_TIMEOUT": 300,
    "CACHE_KEY_PREFIX": "superset_data_",
    "CACHE_REDIS_URL": REDIS_CACHE_URI,
}

RESULTS_BACKEND = {
    "CACHE_TYPE": "RedisCache",
    "CACHE_DEFAULT_TIMEOUT": 3600,
    "CACHE_KEY_PREFIX": "superset_results_",
    "CACHE_REDIS_URL": REDIS_RESULTS_URI,
}

