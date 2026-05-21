import boto3
import os
from botocore.config import Config

def count_objects(bucket_name, endpoint_url, access_key, secret_key):
    s3 = boto3.client(
        's3',
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version='s3v4', s3={'addressing_style': 'path'})
    )
    
    count = 0
    try:
        paginator = s3.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=bucket_name):
            if 'Contents' in page:
                count += len(page['Contents'])
    except Exception as e:
        print(f"Error counting objects in {bucket_name}: {e}")
        return None
    return count

if __name__ == "__main__":
    from dotenv import load_dotenv
    
    REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(REPO_ROOT, ".env"))

    endpoint = os.getenv('RUSTFS_EXTERNAL_ENDPOINT', os.getenv('RUSTFS_ENDPOINT_URL', 'http://localhost:29100'))
    if "dlh-rustfs" in endpoint:
        endpoint = endpoint.replace("dlh-rustfs:9000", "localhost:29100")
    
    access_key = os.getenv('RUSTFS_ACCESS_KEY', 'doe')
    secret_key = os.getenv('RUSTFS_SECRET_KEY', 'change-me-in-production')
    buckets = ["bronze", "silver", "gold", "general"]
    
    total_count = 0
    for bucket in buckets:
        count = count_objects(bucket, endpoint, access_key, secret_key)
        if count is not None:
            print(f"Bucket '{bucket}': {count} objects")
            total_count += count
    
    print("-" * 30)
    print(f"Total objects in data lake: {total_count}")
