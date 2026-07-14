import os
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

BUCKET_NAME = os.environ["S3_BUCKET_NAME"]

PREFIXES = {
    "filings": "filings/",
    "transcripts": "transcripts/",
    "etf_holdings": "etf-holdings/",
}

_client = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))


def object_exists(key: str) -> bool:
    try:
        _client.head_object(Bucket=BUCKET_NAME, Key=key)
        return True
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("404", "NoSuchKey"):
            return False
        raise


def upload_file(
    local_path: str | Path, prefix: str, key_name: str | None = None, overwrite: bool = False
) -> str:
    key_name = key_name or Path(local_path).name
    key = PREFIXES[prefix] + key_name
    if not overwrite and object_exists(key):
        return key
    _client.upload_file(str(local_path), BUCKET_NAME, key)
    return key


def key_for(prefix: str, key_name: str) -> str:
    return PREFIXES[prefix] + key_name


def download_file(key: str, local_path: str | Path) -> None:
    _client.download_file(BUCKET_NAME, key, str(local_path))


def read_bytes(key: str) -> bytes:
    """Return an object's raw bytes without touching local disk."""
    resp = _client.get_object(Bucket=BUCKET_NAME, Key=key)
    return resp["Body"].read()


def read_text(key: str, encoding: str = "utf-8") -> str:
    """Return an object's contents decoded as text (lenient on bad bytes)."""
    return read_bytes(key).decode(encoding, errors="replace")


def put_text(key: str, text: str, content_type: str = "text/plain") -> str:
    """Write a string directly to S3 (used for processed/derived outputs)."""
    _client.put_object(
        Bucket=BUCKET_NAME,
        Key=key,
        Body=text.encode("utf-8"),
        ContentType=content_type,
    )
    return key


def list_objects(prefix: str) -> list[str]:
    paginator = _client.get_paginator("list_objects_v2")
    keys = []
    for page in paginator.paginate(Bucket=BUCKET_NAME, Prefix=PREFIXES[prefix]):
        keys.extend(obj["Key"] for obj in page.get("Contents", []))
    return keys
