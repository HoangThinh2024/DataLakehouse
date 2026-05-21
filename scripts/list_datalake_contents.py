import boto3
import os
from botocore.config import Config

def list_objects(bucket_name, endpoint_url, access_key, secret_key, max_items=10):
    s3 = boto3.client(
        's3',
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version='s3v4', s3={'addressing_style': 'path'})
    )
    
    print(f"\n--- Top {max_items} objects in '{bucket_name}' ---")
    try:
        response = s3.list_objects_v2(Bucket=bucket_name, MaxKeys=max_items)
        if 'Contents' in response:
            for obj in response['Contents']:
                print(f"Key: {obj['Key']}, Size: {obj['Size']} bytes, LastModified: {obj['LastModified']}")
        else:
            print("No objects found.")
    except Exception as e:
        print(f"Error listing objects in {bucket_name}: {e}")

if __name__ == "__main__":
    from dotenv import load_dotenv
    
    REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(REPO_ROOT, ".env"))

    endpoint = os.getenv('RUSTFS_EXTERNAL_ENDPOINT', os.getenv('RUSTFS_ENDPOINT_URL', 'http://localhost:29100'))
    if "dlh-rustfs" in endpoint:
        endpoint = endpoint.replace("dlh-rustfs:9000", "localhost:29100")
    
    access_key = os.getenv('RUSTFS_ACCESS_KEY', 'doe')
    secret_key = os.getenv('RUSTFS_SECRET_KEY', 'change-me-in-production')
    buckets = ["bronze", "silver", "gold"]
    
    for bucket in buckets:
        list_objects(bucket, endpoint, access_key, secret_key)
