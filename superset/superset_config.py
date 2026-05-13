import os

SQLALCHEMY_DATABASE_URI = (
    f"postgresql+psycopg2://{os.getenv('SUPERSET_DB_USER', 'dlh_superset_user')}:"
    f"{os.getenv('SUPERSET_DB_PASSWORD', 'change-me')}@dlh-postgres:5432/"
    f"{os.getenv('SUPERSET_DB_NAME', 'dlh_superset')}"
)

SECRET_KEY = os.getenv('SUPERSET_SECRET_KEY', 'replace-this-secret')

# --- Authentication Configuration (OIDC/SSO) ---
try:
    from flask_appbuilder.security.manager import AUTH_OAUTH
    HAS_OIDC = True
except ImportError:
    AUTH_OAUTH = 1
    HAS_OIDC = False

AUTH_TYPE = AUTH_OAUTH if (os.getenv("SUPERSET_OIDC_CLIENT_ID") and HAS_OIDC) else 1 
AUTH_USER_REGISTRATION = True
AUTH_USER_REGISTRATION_ROLE = "Public" # Default role for new users

OIDC_CLIENT_ID = os.getenv("SUPERSET_OIDC_CLIENT_ID")
OIDC_CLIENT_SECRET = os.getenv("SUPERSET_OIDC_CLIENT_SECRET")
OIDC_DISCOVERY_URL = os.getenv("SUPERSET_OIDC_DISCOVERY_URL")

if AUTH_TYPE == AUTH_OAUTH:
    OAUTH_PROVIDERS = [
        {
            "name": "authentik",
            "token_key": "access_token",
            "icon": "fa-address-card",
            "remote_app": {
                "client_id": OIDC_CLIENT_ID,
                "client_secret": OIDC_CLIENT_SECRET,
                "server_metadata_url": OIDC_DISCOVERY_URL,
                "client_kwargs": {
                    "scope": "openid email profile"
                },
            },
        }
    ]

# Allow ClickHouse (via clickhouse-connect) and PostgreSQL connections from the UI
PREVENT_UNSAFE_DB_CONNECTIONS = False

FEATURE_FLAGS = {
    "ENABLE_TEMPLATE_PROCESSING": True,
    "DASHBOARD_NATIVE_FILTERS": True,
    "DASHBOARD_CROSS_FILTERS": True,
}

# Honor X-Forwarded-* headers when running behind reverse proxies
ENABLE_PROXY_FIX = True
PROXY_FIX_CONFIG = {
    "x_for": 1,
    "x_proto": 1,
    "x_host": 1,
    "x_port": 1,
    "x_prefix": 1,
}
PREFERRED_URL_SCHEME = os.getenv("SUPERSET_PREFERRED_URL_SCHEME", "https")

# Session and CSRF
SESSION_COOKIE_SAMESITE = "None"
SESSION_COOKIE_SECURE = True
WTF_CSRF_ENABLED = False # Disable CSRF temporarily to troubleshoot login if needed, though not recommended for prod
TALISMAN_CONFIG = {
    "content_security_policy": None,
    "force_https": False,
}

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

# Shared caching layer
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
