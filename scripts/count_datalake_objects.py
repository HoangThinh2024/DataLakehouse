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
    endpoint = "http://localhost:29100"
    access_key = "doe"
    secret_key = "Do12345678910.."
    buckets = ["bronze", "silver", "gold", "general"]
    
    total_count = 0
    for bucket in buckets:
        count = count_objects(bucket, endpoint, access_key, secret_key)
        if count is not None:
            print(f"Bucket '{bucket}': {count} objects")
            total_count += count
    
    print("-" * 30)
    print(f"Total objects in data lake: {total_count}")
