import os

SQLALCHEMY_DATABASE_URI = (
    f"postgresql+psycopg2://{os.getenv('SUPERSET_DB_USER', 'dlh_superset_user')}:"
    f"{os.getenv('SUPERSET_DB_PASSWORD', 'change-me')}@dlh-postgres:5432/"
    f"{os.getenv('SUPERSET_DB_NAME', 'dlh_superset')}"
)

SECRET_KEY = os.getenv('SUPERSET_SECRET_KEY', 'replace-this-secret')
