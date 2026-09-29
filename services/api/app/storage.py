from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from .config import settings


def client():
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
    )


def ensure_bucket() -> None:
    if settings.storage_backend == "local":
        Path(settings.local_storage_path).mkdir(parents=True, exist_ok=True)
        return
    s3 = client()
    try:
        s3.head_bucket(Bucket=settings.s3_bucket)
    except ClientError:
        s3.create_bucket(Bucket=settings.s3_bucket)


def put_bytes(path: str, content: bytes, content_type: str = "image/png") -> None:
    if settings.storage_backend == "local":
        target = Path(settings.local_storage_path) / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return
    ensure_bucket()
    client().put_object(
        Bucket=settings.s3_bucket, Key=path, Body=content, ContentType=content_type
    )


def get_bytes(path: str) -> bytes:
    if settings.storage_backend == "local":
        return (Path(settings.local_storage_path) / path).read_bytes()
    return client().get_object(Bucket=settings.s3_bucket, Key=path)["Body"].read()


def delete_object(path: str) -> None:
    if settings.storage_backend == "local":
        (Path(settings.local_storage_path) / path).unlink(missing_ok=True)
        return
    client().delete_object(Bucket=settings.s3_bucket, Key=path)
