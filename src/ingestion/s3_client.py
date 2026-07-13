import os
from pathlib import Path

import boto3

BUCKET_NAME = os.environ["S3_BUCKET_NAME"]

PREFIXES = {
    "filings": "filings/",
    "transcripts": "transcripts/",
    "etf_holdings": "etf-holdings/",
}

_client = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))


def upload_file(local_path: str | Path, prefix: str, key_name: str | None = None) -> str:
    key_name = key_name or Path(local_path).name
    key = PREFIXES[prefix] + key_name
    _client.upload_file(str(local_path), BUCKET_NAME, key)
    return key


def download_file(key: str, local_path: str | Path) -> None:
    _client.download_file(BUCKET_NAME, key, str(local_path))


def list_objects(prefix: str) -> list[str]:
    paginator = _client.get_paginator("list_objects_v2")
    keys = []
    for page in paginator.paginate(Bucket=BUCKET_NAME, Prefix=PREFIXES[prefix]):
        keys.extend(obj["Key"] for obj in page.get("Contents", []))
    return keys
