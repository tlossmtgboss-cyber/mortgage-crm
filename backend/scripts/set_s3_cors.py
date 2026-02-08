"""
One-time script to configure S3 bucket CORS policy.
Allows browser-based presigned URL uploads from frontend origins.

Usage: python scripts/set_s3_cors.py
"""
import sys
import os

# Add parent directory to path so we can import services
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.perennia_s3_service import get_s3_service


def set_cors():
    s3_service = get_s3_service()
    bucket = s3_service.bucket_name

    cors_configuration = {
        'CORSRules': [
            {
                'AllowedHeaders': ['Content-Type', 'Authorization', 'x-amz-*'],
                'AllowedMethods': ['GET', 'PUT', 'POST', 'DELETE', 'HEAD'],
                'AllowedOrigins': [
                    'https://app.perenniaai.com',
                    'https://perenniaai.com',
                    'https://*.perenniaai.com',
                    'https://*.railway.app',
                    'http://localhost:3000',
                    'http://localhost:5173',
                ],
                'ExposeHeaders': ['ETag', 'x-amz-version-id'],
                'MaxAgeSeconds': 3600,
            }
        ]
    }

    print(f"Setting CORS on bucket: {bucket}")
    s3_service.s3_client.put_bucket_cors(
        Bucket=bucket,
        CORSConfiguration=cors_configuration,
    )
    print("CORS policy set successfully!")

    # Verify
    result = s3_service.s3_client.get_bucket_cors(Bucket=bucket)
    print(f"Verified CORS rules: {len(result['CORSRules'])} rule(s)")
    for rule in result['CORSRules']:
        print(f"  Origins: {rule['AllowedOrigins']}")
        print(f"  Methods: {rule['AllowedMethods']}")


if __name__ == '__main__':
    set_cors()
