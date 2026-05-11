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
    endpoint = "http://localhost:29100"
    access_key = "doe"
    secret_key = "Do12345678910.."
    buckets = ["bronze", "silver", "gold"]
    
    for bucket in buckets:
        list_objects(bucket, endpoint, access_key, secret_key)
