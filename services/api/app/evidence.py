import hashlib
import io
from datetime import datetime, timedelta, timezone

import imagehash
from botocore.exceptions import BotoCoreError, ClientError
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .models import Actor, EvidenceRecord, ProfileSnapshot
from .storage import get_bytes


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def record_hash(
    actor_hash: str,
    source_url: str,
    captured_at: datetime,
    screenshot_sha256: str,
    previous_record_hash: str | None,
) -> str:
    utc_time = (
        captured_at.astimezone(timezone.utc).replace(tzinfo=None)
        if captured_at.tzinfo
        else captured_at
    )
    payload = (
        actor_hash
        + source_url
        + utc_time.isoformat(timespec="microseconds")
        + screenshot_sha256
        + (previous_record_hash or "")
    )
    return sha256(payload.encode())


def avatar_hashes(data: bytes) -> dict[str, str]:
    with Image.open(io.BytesIO(data)) as image:
        rgb = image.convert("RGB")
        return {
            "average_hash": str(imagehash.average_hash(rgb)),
            "phash": str(imagehash.phash(rgb)),
            "dhash": str(imagehash.dhash(rgb)),
        }


def phash_distance(left: str, right: str) -> int:
    return imagehash.hex_to_hash(left) - imagehash.hex_to_hash(right)


def recent_snapshot(
    db: Session, actor: Actor, now: datetime | None = None
) -> ProfileSnapshot | None:
    latest = db.scalar(
        select(ProfileSnapshot)
        .where(
            ProfileSnapshot.actor_id == actor.id,
            ProfileSnapshot.capture_status == "CAPTURED",
        )
        .order_by(ProfileSnapshot.captured_at.desc())
    )
    if latest is None:
        return None
    days = (
        settings.high_risk_profile_ttl_days
        if actor.suspicion_score >= 70
        else settings.suspicious_profile_ttl_days
        if actor.suspicion_score >= settings.screenshot_threshold
        else settings.normal_profile_ttl_days
    )
    captured = (
        latest.captured_at.replace(tzinfo=timezone.utc)
        if latest.captured_at.tzinfo is None
        else latest.captured_at
    )
    return (
        latest
        if captured >= (now or datetime.now(timezone.utc)) - timedelta(days=days)
        else None
    )


def append_evidence(
    db: Session,
    actor: Actor,
    source_url: str,
    screenshot_path: str,
    screenshot_bytes: bytes,
    captured_at: datetime,
    metadata: dict | None = None,
) -> EvidenceRecord:
    previous = db.scalar(
        select(EvidenceRecord)
        .where(EvidenceRecord.actor_id == actor.id)
        .order_by(EvidenceRecord.captured_at.desc(), EvidenceRecord.id.desc())
    )
    digest = sha256(screenshot_bytes)
    prior = previous.record_hash if previous else None
    record = EvidenceRecord(
        actor_id=actor.id,
        source_url=source_url,
        captured_at=captured_at,
        screenshot_path=screenshot_path,
        sha256=digest,
        previous_record_hash=prior,
        record_hash=record_hash(
            actor.actor_hash, source_url, captured_at, digest, prior
        ),
        metadata_json=metadata or {},
    )
    db.add(record)
    db.flush()
    return record


def verify_evidence_chain(db: Session, actor: Actor) -> str:
    records = list(
        db.scalars(
            select(EvidenceRecord)
            .where(EvidenceRecord.actor_id == actor.id)
            .order_by(EvidenceRecord.captured_at, EvidenceRecord.id)
        )
    )
    if not records:
        return "INCOMPLETE"
    previous = None
    for record in records:
        if record.previous_record_hash != previous:
            return "BROKEN"
        expected = record_hash(
            actor.actor_hash,
            record.source_url,
            record.captured_at,
            record.sha256,
            previous,
        )
        if expected != record.record_hash:
            return "BROKEN"
        try:
            if sha256(get_bytes(record.screenshot_path)) != record.sha256:
                return "BROKEN"
        except (OSError, BotoCoreError, ClientError):
            return "INCOMPLETE"
        previous = record.record_hash
    return "VALID"
