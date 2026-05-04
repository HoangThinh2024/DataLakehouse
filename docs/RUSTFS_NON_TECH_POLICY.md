# RustFS Custom IAM Policy: Non-Tech User

This document contains the JSON definition for the `Policy for non_tech user` policy used in the Data Lakehouse project. This policy is designed for non-technical users who need to upload data directly to the object storage.

## Policy Details

- **Policy Name:** `Policy for non_tech user`
- **Purpose:** Allows users to view all buckets but only perform object operations (Upload, Download, Delete) within the `bronze` bucket.
- **Created:** 2026-05-04

## JSON Definition

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "AllowUserToSeeAllBuckets",
            "Effect": "Allow",
            "Action": [
                "s3:GetBucketLocation",
                "s3:ListAllMyBuckets"
            ],
            "Resource": [
                "arn:aws:s3:::*"
            ]
        },
        {
            "Sid": "AllowClickIntoAndViewBonzeBucket",
            "Effect": "Allow",
            "Action": [
                "s3:ListBucket",
                "s3:GetBucketLocation"
            ],
            "Resource": [
                "arn:aws:s3:::bronze"
            ]
        },
        {
            "Sid": "AllowActionsInsideBonzeBucket",
            "Effect": "Allow",
            "Action": [
                "s3:GetObjectVersion",
                "s3:PutObject",
                "s3:GetObject",
                "s3:DeleteObject"
            ],
            "Resource": [
                "arn:aws:s3:::bronze/*"
            ]
        }
    ]
}
```

## How to Apply

To apply this policy using the MinIO Client (`mc`):

1. Save the JSON content above to a file named `non_tech_policy.json`.
2. Run the following command:
   ```bash
   mc admin policy create rustfs non-tech-policy non_tech_policy.json
   ```
3. Assign the policy to a user:
   ```bash
   mc admin policy attach rustfs non-tech-policy --user <username>
   ```
