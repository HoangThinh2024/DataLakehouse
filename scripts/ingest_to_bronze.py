import os
import shutil
import boto3
import datetime as dt
from pathlib import Path
from botocore.client import Config as BotoConfig

# Configuration
REPO_ROOT = Path(__file__).resolve().parents[1]
BRONZE_LOCAL = REPO_ROOT / "mage" / "bronze_local"
ARCHIVE_DIR = BRONZE_LOCAL / "archive"

# S3 Configuration (RustFS)
# When running from host, use localhost. Inside docker, use dlh-rustfs.
RUSTFS_ENDPOINT = os.getenv('RUSTFS_EXTERNAL_ENDPOINT', os.getenv('RUSTFS_ENDPOINT_URL', 'http://localhost:29100'))
# Force localhost if we are clearly on the host and it looks like it's trying to use internal DNS
if "dlh-rustfs" in RUSTFS_ENDPOINT and not os.path.exists("/.dockerenv"):
    RUSTFS_ENDPOINT = RUSTFS_ENDPOINT.replace("dlh-rustfs:9000", "localhost:29100")
RUSTFS_ACCESS_KEY = os.getenv('RUSTFS_ACCESS_KEY', 'doe')
RUSTFS_SECRET_KEY = os.getenv('RUSTFS_SECRET_KEY', 'Do12345678910..')
RUSTFS_BUCKET = os.getenv('RUSTFS_BRONZE_BUCKET', 'bronze')

def get_s3_client():
    return boto3.client(
        's3',
        endpoint_url=RUSTFS_ENDPOINT,
        aws_access_key_id=RUSTFS_ACCESS_KEY,
        aws_secret_access_key=RUSTFS_SECRET_KEY,
        config=BotoConfig(signature_version='s3v4', s3={'addressing_style': 'path'})
    )

def ingest_files():
    s3 = get_s3_client()
    
    # Ensure archive directory exists
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    
    # List all Excel/CSV files in bronze_local
    files = list(BRONZE_LOCAL.glob("*.xlsx")) + list(BRONZE_LOCAL.glob("*.csv"))
    
    if not files:
        print("No new files found in bronze_local.")
        return

    for file_path in files:
        file_name = file_path.name
        # Skip files already in archive (shouldn't happen with glob above)
        if file_path.parent == ARCHIVE_DIR:
            continue
            
        print(f"Ingesting: {file_name} ...")
        
        # Upload to S3
        # Prefix by file type to match existing pipeline expectations
        prefix = "Data Mẫu 12 dự án" if file_name.endswith(".xlsx") else "csv_upload"
        object_key = f"{prefix}/{file_name}"
        
        try:
            s3.upload_file(str(file_path), RUSTFS_BUCKET, object_key)
            print(f"  ✓ Uploaded to s3://{RUSTFS_BUCKET}/{object_key}")
            
            # Move to archive
            dest_path = ARCHIVE_DIR / file_name
            # Handle collision in archive
            if dest_path.exists():
                timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
                dest_path = ARCHIVE_DIR / f"{file_path.stem}_{timestamp}{file_path.suffix}"
            
            shutil.move(str(file_path), str(dest_path))
            print(f"  ✓ Moved to {dest_path.relative_to(REPO_ROOT)}")
            
        except Exception as e:
            print(f"  ✗ Error ingesting {file_name}: {e}")

if __name__ == "__main__":
    # Load .env if running locally
    env_path = REPO_ROOT / ".env"
    if env_path.exists():
        from dotenv import load_dotenv
        load_dotenv(env_path)
        # Refresh config from env
        RUSTFS_ENDPOINT = os.getenv('RUSTFS_ENDPOINT_URL', RUSTFS_ENDPOINT)
        RUSTFS_ACCESS_KEY = os.getenv('RUSTFS_ACCESS_KEY', RUSTFS_ACCESS_KEY)
        RUSTFS_SECRET_KEY = os.getenv('RUSTFS_SECRET_KEY', RUSTFS_SECRET_KEY)
        RUSTFS_BUCKET = os.getenv('RUSTFS_BRONZE_BUCKET', RUSTFS_BUCKET)

    ingest_to_bronze_py = Path(__file__).resolve()
    print(f"--- Starting Ingestion to Bronze Layer ---")
    ingest_files()
    print(f"--- Ingestion Complete ---")
