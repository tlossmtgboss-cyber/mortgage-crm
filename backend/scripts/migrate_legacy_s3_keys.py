"""
One-shot migration: move S3 objects without org prefix to org-prefixed keys.
Usage:
    python -m scripts.migrate_legacy_s3_keys --dry-run
    python -m scripts.migrate_legacy_s3_keys --execute
"""
import argparse
import logging
import os

import boto3
from botocore.exceptions import ClientError
from sqlalchemy import text

from database import SessionLocal

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

ORG_PREFIXES = ("org-", "org/", "org_")


def iter_legacy_docs(db):
    rows = db.execute(text(
        "SELECT id, storage_key, organization_id FROM smart_documents "
        "WHERE storage_key IS NOT NULL"
    )).fetchall()
    for row in rows:
        key = row[1]
        if key and not any(key.startswith(p) for p in ORG_PREFIXES):
            yield {"id": row[0], "storage_key": key, "organization_id": row[2]}


def new_key_for(doc):
    if not doc["organization_id"]:
        raise ValueError(f"Document {doc['id']} has no organization_id")
    return f"org-{doc['organization_id']}/{doc['storage_key'].lstrip('/')}"


def copy_and_verify(s3, bucket, old_key, new_key):
    try:
        s3.copy_object(
            Bucket=bucket,
            CopySource={"Bucket": bucket, "Key": old_key},
            Key=new_key,
            MetadataDirective="COPY",
            ServerSideEncryption="AES256",
        )
    except ClientError as e:
        return False, f"copy failed: {e}"
    try:
        old_head = s3.head_object(Bucket=bucket, Key=old_key)
        new_head = s3.head_object(Bucket=bucket, Key=new_key)
    except ClientError as e:
        return False, f"head failed: {e}"
    if old_head["ContentLength"] != new_head["ContentLength"]:
        return False, "size mismatch after copy"
    return True, "ok"


def run(execute):
    bucket = os.environ.get("SMART_DOCS_S3_BUCKET") or os.environ.get("PERENNIA_S3_BUCKET")
    if not bucket:
        raise RuntimeError("Set SMART_DOCS_S3_BUCKET or PERENNIA_S3_BUCKET")
    s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    db = SessionLocal()
    moved = skipped = failed = 0
    try:
        for doc in iter_legacy_docs(db):
            try:
                new_key = new_key_for(doc)
            except ValueError as e:
                logger.error("SKIP doc_id=%s: %s", doc["id"], e)
                skipped += 1
                continue

            if not execute:
                logger.info("DRY doc_id=%s  %s  ->  %s", doc["id"], doc["storage_key"], new_key)
                moved += 1
                continue

            ok, msg = copy_and_verify(s3, bucket, doc["storage_key"], new_key)
            if not ok:
                logger.error("FAIL doc_id=%s: %s", doc["id"], msg)
                failed += 1
                continue

            old_key = doc["storage_key"]
            db.execute(text(
                "UPDATE smart_documents SET storage_key = :new_key WHERE id = :id"
            ), {"new_key": new_key, "id": doc["id"]})
            db.commit()

            try:
                s3.delete_object(Bucket=bucket, Key=old_key)
            except ClientError as e:
                logger.error("DELETE_ORPHAN doc_id=%s old=%s: %s", doc["id"], old_key, e)
            moved += 1
    finally:
        db.close()

    logger.info("moved=%s skipped=%s failed=%s execute=%s", moved, skipped, failed, execute)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", dest="execute", action="store_false")
    g.add_argument("--execute", dest="execute", action="store_true")
    run(p.parse_args().execute)
