"""
One-time setup: Configure CORS on the S3 bucket to allow browser uploads.

Run on Railway (where AWS credentials are set):
    python scripts/setup_s3_cors.py

Or locally with credentials:
    AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... python scripts/setup_s3_cors.py
"""

import os
import sys
import json
import boto3
from botocore.exceptions import ClientError

BUCKET = os.getenv("PERENNIA_S3_BUCKET") or os.getenv("AWS_S3_BUCKET", "perennia-docs")
REGION = os.getenv("AWS_REGION", "us-east-1")

CORS_CONFIG = {
    "CORSRules": [
        {
            "AllowedHeaders": ["*"],
            "AllowedMethods": ["POST", "PUT", "GET"],
            "AllowedOrigins": [
                "https://app.perenniaai.com",
                "http://localhost:3000",
                "http://localhost:5173",
            ],
            "ExposeHeaders": ["ETag"],
            "MaxAgeSeconds": 3600,
        }
    ]
}


def main():
    print(f"Bucket:  {BUCKET}")
    print(f"Region:  {REGION}")

    s3 = boto3.client("s3", region_name=REGION)

    # Verify bucket exists
    try:
        s3.head_bucket(Bucket=BUCKET)
        print(f"Bucket '{BUCKET}' exists.")
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code == "404":
            print(f"Bucket '{BUCKET}' does not exist. Creating...")
            try:
                if REGION == "us-east-1":
                    s3.create_bucket(Bucket=BUCKET)
                else:
                    s3.create_bucket(
                        Bucket=BUCKET,
                        CreateBucketConfiguration={"LocationConstraint": REGION},
                    )
                print(f"Bucket '{BUCKET}' created.")
            except ClientError as ce:
                print(f"Failed to create bucket: {ce}")
                sys.exit(1)
        else:
            print(f"Cannot access bucket: {e}")
            sys.exit(1)

    # Check current CORS
    try:
        current = s3.get_bucket_cors(Bucket=BUCKET)
        print(f"Current CORS rules: {json.dumps(current['CORSRules'], indent=2)}")
    except ClientError:
        print("No CORS rules currently set.")

    # Apply CORS
    s3.put_bucket_cors(Bucket=BUCKET, CORSConfiguration=CORS_CONFIG)
    print(f"CORS configured for {BUCKET}:")
    print(json.dumps(CORS_CONFIG, indent=2))

    # Verify
    verify = s3.get_bucket_cors(Bucket=BUCKET)
    origins = verify["CORSRules"][0]["AllowedOrigins"]
    if "https://app.perenniaai.com" in origins:
        print("\nS3 bucket is ready for browser uploads.")
    else:
        print("\nWARNING: CORS verification failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
