import logging

import boto3
from botocore.exceptions import ClientError
from django.conf import settings

logger = logging.getLogger(__name__)


def _get_s3_client():
    return boto3.client("s3", region_name=settings.AWS_REGION)


def is_s3_configured() -> bool:
    return bool(settings.DOCUMENTS_BUCKET_NAME)


def upload_document(key: str, pdf_bytes: bytes, content_type: str = "application/pdf") -> bool:
    if not is_s3_configured():
        logger.warning("DOCUMENTS_BUCKET_NAME not set — skipping S3 upload")
        return False

    try:
        _get_s3_client().put_object(
            Bucket=settings.DOCUMENTS_BUCKET_NAME,
            Key=key,
            Body=pdf_bytes,
            ContentType=content_type,
            ServerSideEncryption="AES256",
        )
        logger.info("Uploaded document to s3://%s/%s", settings.DOCUMENTS_BUCKET_NAME, key)
        return True
    except ClientError:
        logger.exception("Failed to upload document to S3: %s", key)
        return False


def download_document(key: str) -> bytes | None:
    if not is_s3_configured():
        return None

    try:
        response = _get_s3_client().get_object(
            Bucket=settings.DOCUMENTS_BUCKET_NAME,
            Key=key,
        )
        return response["Body"].read()
    except ClientError:
        logger.exception("Failed to download document from S3: %s", key)
        return None


def generate_presigned_url(key: str, expiration: int = 3600, filename: str = "") -> str | None:
    if not is_s3_configured():
        return None

    params = {
        "Bucket": settings.DOCUMENTS_BUCKET_NAME,
        "Key": key,
    }
    if filename:
        params["ResponseContentDisposition"] = f'attachment; filename="{filename}"'

    try:
        return _get_s3_client().generate_presigned_url(
            "get_object",
            Params=params,
            ExpiresIn=expiration,
        )
    except ClientError:
        logger.exception("Failed to generate presigned URL for: %s", key)
        return None
