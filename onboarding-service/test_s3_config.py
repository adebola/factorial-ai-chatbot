#!/usr/bin/env python3
"""
S3/MinIO Configuration Test Script
Run this script to diagnose S3 connection issues in production
"""

import os
import sys
from minio import Minio
from minio.error import S3Error
from datetime import datetime

def test_minio_configuration():
    """Test MinIO configuration and connectivity"""

    print("=== MinIO Configuration Test ===")
    print(f"Test Time: {datetime.now()}")
    print()

    # Check environment variables
    print("1. Checking Environment Variables:")
    required_vars = ["MINIO_ENDPOINT", "MINIO_ACCESS_KEY", "MINIO_SECRET_KEY", "MINIO_BUCKET_NAME"]
    optional_vars = ["MINIO_SECURE", "AWS_REGION"]

    missing_vars = []
    for var in required_vars:
        value = os.environ.get(var)
        if value:
            # Mask sensitive values
            if "KEY" in var:
                masked_value = value[:4] + "*" * (len(value) - 8) + value[-4:] if len(value) > 8 else "***"
                print(f"   ✅ {var}: {masked_value}")
            else:
                print(f"   ✅ {var}: {value}")
        else:
            print(f"   ❌ {var}: NOT SET")
            missing_vars.append(var)

    for var in optional_vars:
        value = os.environ.get(var)
        print(f"   🔧 {var}: {value or 'NOT SET (using default)'}")

    if missing_vars:
        print(f"\n❌ Missing required variables: {missing_vars}")
        return False

    print("\n2. Testing S3/MinIO Connection:")

    try:
        # Initialize client
        endpoint = os.environ.get("MINIO_ENDPOINT")
        access_key = os.environ.get("MINIO_ACCESS_KEY")
        secret_key = os.environ.get("MINIO_SECRET_KEY")
        secure = os.environ.get("MINIO_SECURE", "false").lower() == "true"
        region = os.environ.get("AWS_REGION", "us-east-1")
        bucket_name = os.environ.get("MINIO_BUCKET_NAME")

        print(f"   Endpoint: {endpoint}")
        print(f"   Secure: {secure}")
        print(f"   Region: {region}")
        print(f"   Bucket: {bucket_name}")

        client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
            region=region if region else None
        )

        print("   ✅ MinIO client initialized successfully")

        # Test bucket access
        print("\n3. Testing Bucket Access:")

        try:
            bucket_exists = client.bucket_exists(bucket_name)
            print(f"   ✅ Bucket '{bucket_name}' exists: {bucket_exists}")

            if not bucket_exists:
                print("   ⚠️  Bucket does not exist. Attempting to create...")
                client.make_bucket(bucket_name)
                print("   ✅ Bucket created successfully")

        except S3Error as e:
            print(f"   ❌ Bucket access failed: {e}")
            print(f"      Code: {e.code}")
            print(f"      Message: {e.message}")
            return False

        # Test file upload
        print("\n4. Testing File Upload:")

        try:
            test_content = b"Test file content for S3 configuration validation"
            test_object_name = f"test-uploads/config-test-{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

            from io import BytesIO
            client.put_object(
                bucket_name,
                test_object_name,
                BytesIO(test_content),
                length=len(test_content),
                content_type="text/plain"
            )

            print(f"   ✅ Test file uploaded successfully: {test_object_name}")

            # Test file download
            print("\n5. Testing File Download:")
            response = client.get_object(bucket_name, test_object_name)
            downloaded_content = response.read()

            if downloaded_content == test_content:
                print("   ✅ Test file downloaded and verified successfully")
            else:
                print("   ❌ Downloaded content doesn't match uploaded content")
                return False

            # Clean up test file
            client.remove_object(bucket_name, test_object_name)
            print("   ✅ Test file cleaned up")

        except S3Error as e:
            print(f"   ❌ File operations failed: {e}")
            print(f"      Code: {e.code}")
            print(f"      Message: {e.message}")

            # Additional debugging for SignatureDoesNotMatch (MinIO specific)
            if e.code == "SignatureDoesNotMatch":
                print("\n🔍 MINIO SIGNATURE MISMATCH DEBUGGING:")
                print("   Common causes for MinIO:")
                print("   1. Incorrect MinIO Access Key or Secret Key")
                print("   2. Clock synchronization issues between client and MinIO server")
                print("   3. MinIO server endpoint configuration mismatch")
                print("   4. HTTPS/HTTP mismatch (secure setting)")
                print("   5. Region parameter being passed to MinIO (shouldn't for pure MinIO)")
                print()
                print("   Suggested fixes for MinIO:")
                print("   1. Verify MINIO_ACCESS_KEY and MINIO_SECRET_KEY are correct")
                print("   2. Ensure server time is synchronized (NTP)")
                print("   3. Check MINIO_ENDPOINT format (e.g., 'minio.example.com:9000')")
                print("   4. Verify MINIO_SECURE matches your MinIO server setup")
                print("   5. Remove AWS_REGION parameter for pure MinIO installs")
                print("   6. Check MinIO server logs for more details")

            return False

        print("\n✅ All S3/MinIO tests passed successfully!")
        return True

    except Exception as e:
        print(f"\n❌ Connection failed: {e}")
        return False

if __name__ == "__main__":
    success = test_minio_configuration()
    sys.exit(0 if success else 1)