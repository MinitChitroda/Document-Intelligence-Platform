"""
storage/s3_client.py
AWS S3 client: raw/ -> curated/ -> failed/ prefixes.
"""

import os
import logging
import boto3
from botocore.exceptions import ClientError
from typing import Optional

logger = logging.getLogger(__name__)

# Initialize boto3 client lazily or at module level
s3_client = boto3.client('s3')
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "document-platform-local-bucket")

def upload_file_obj(file_obj, s3_key: str) -> bool:
    """Uploads a file-like object to S3."""
    try:
        s3_client.upload_fileobj(file_obj, S3_BUCKET_NAME, s3_key)
        return True
    except ClientError as e:
        logger.error(f"S3 Upload failed for key {s3_key}: {e}")
        return False
        
def upload_file_bytes(content: bytes, s3_key: str) -> bool:
    """Uploads raw bytes to S3."""
    try:
        s3_client.put_object(Bucket=S3_BUCKET_NAME, Key=s3_key, Body=content)
        return True
    except ClientError as e:
        logger.error(f"S3 PutObject failed for key {s3_key}: {e}")
        return False

def download_file(s3_key: str, local_path: str) -> bool:
    """Downloads a file from S3 to a local path."""
    try:
        s3_client.download_file(S3_BUCKET_NAME, s3_key, local_path)
        return True
    except ClientError as e:
        logger.error(f"S3 Download failed for key {s3_key}: {e}")
        return False

def get_object_bytes(s3_key: str) -> Optional[bytes]:
    """Returns the raw bytes of an object from S3."""
    try:
        response = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=s3_key)
        return response['Body'].read()
    except ClientError as e:
        logger.error(f"S3 GetObject failed for key {s3_key}: {e}")
        return None

def move_object(source_key: str, dest_key: str) -> bool:
    """Moves an object in S3 by copying it to the new key and deleting the old one."""
    try:
        copy_source = {'Bucket': S3_BUCKET_NAME, 'Key': source_key}
        s3_client.copy_object(CopySource=copy_source, Bucket=S3_BUCKET_NAME, Key=dest_key)
        s3_client.delete_object(Bucket=S3_BUCKET_NAME, Key=source_key)
        return True
    except ClientError as e:
        logger.error(f"S3 Move failed for {source_key} -> {dest_key}: {e}")
        return False

def object_exists(s3_key: str) -> bool:
    """Checks if an object exists in S3."""
    try:
        s3_client.head_object(Bucket=S3_BUCKET_NAME, Key=s3_key)
        return True
    except ClientError:
        return False
