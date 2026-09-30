"""Permanent conversation archive in S3.

Separate from state_store's DynamoDB item, which trims history to the last 20
messages to bound LLM cost and is never meant as a record of what was said.
This module exists purely for audit/reporting -- the agent never reads from
here, only writes.

Objects live under `conversations/<wa_id>/...` and expire via the bucket's own
90-day lifecycle rule (deployment/template.yaml), so nothing here needs to
track or enforce retention itself.

Every function no-ops (returns None) when MEDIA_BUCKET is unset, so deploying
this code before the bucket exists in the stack is safe -- the feature is
simply dormant until the next deploy adds it.
"""

import time

import boto3

from . import config

_s3 = None


def _client():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3", region_name=config.AWS_REGION)
    return _s3


def log_text(wa_id, direction, text, message_id=None):
    """Archive one text turn. `direction` is 'in' (student) or 'out' (bot)."""
    if not config.MEDIA_BUCKET:
        return None
    import json

    key = f"conversations/{wa_id}/{int(time.time() * 1000)}-{direction}.json"
    body = json.dumps({
        "wa_id": wa_id,
        "direction": direction,
        "text": text,
        "message_id": message_id,
    }).encode("utf-8")
    _client().put_object(
        Bucket=config.MEDIA_BUCKET, Key=key, Body=body,
        ContentType="application/json",
    )
    return key


def store_image(wa_id, content, content_type, message_id=None, caption=""):
    """Archive an inbound image. Returns its S3 key, or None if archiving is off.

    The same key doubles as the hold used to attach this image to a ticket that
    does not exist yet -- see state_store.add_pending_attachment.
    """
    if not config.MEDIA_BUCKET:
        return None
    ext = (content_type or "image/jpeg").split("/")[-1].split(";")[0] or "jpg"
    key = f"conversations/{wa_id}/{int(time.time() * 1000)}-{message_id or 'img'}.{ext}"
    _client().put_object(
        Bucket=config.MEDIA_BUCKET, Key=key, Body=content,
        ContentType=content_type or "application/octet-stream",
        Metadata={"caption": (caption or "")[:500]},
    )
    return key


def fetch(key):
    """Read back a stored object. Returns (bytes, content_type), or None."""
    if not key or not config.MEDIA_BUCKET:
        return None
    resp = _client().get_object(Bucket=config.MEDIA_BUCKET, Key=key)
    return resp["Body"].read(), resp.get("ContentType", "application/octet-stream")
