from datetime import datetime, timedelta, timezone
from io import BytesIO

from PIL import Image
from sqlalchemy import select

from app.analysis import analyze, cross_post_groups, detect_bursts, score_signals
from app.evidence import (
    avatar_hashes,
    phash_distance,
    recent_snapshot,
    record_hash,
    sha256,
    verify_evidence_chain,
)
from app.identity import actor_hash
from app.ingest import ingest_rows
from app.models import Actor, Interaction, ProfileSnapshot, Signal
from app.providers import ExtensionBundleProvider, InteractionRow
from app.tasks import priority_queue


def test_hashing_and_deduplication(db):
    assert actor_hash("https://www.facebook.com/A/") == actor_hash(
        "https://m.facebook.com/a"
    )
    row = InteractionRow(
        post_url="https://www.facebook.com/example/posts/1",
        profile_url="https://www.facebook.com/A",
        reaction_type="LIKE",
        observed_at=datetime.now(timezone.utc),
    )
    ingest_rows(db, [row, row], "test")
    assert len(list(db.scalars(select(Actor)))) == 1
    assert len(list(db.scalars(select(Interaction)))) == 1


def test_group_member_and_direct_profile_share_identity():
    assert actor_hash("https://www.facebook.com/groups/123/user/456/") == actor_hash(
        "https://www.facebook.com/profile.php?id=456"
    )


def test_extension_scan_time_is_not_a_reaction_burst(db):
    import json

    captured = datetime.now(timezone.utc).isoformat()
    bundle = {
        "scans": [
            {
                "post_url": "https://www.facebook.com/groups/123/posts/456",
                "captured_at": captured,
                "records": [
                    {
                        "profile_url": f"https://www.facebook.com/groups/123/user/{1000 + i}/",
                        "name": f"Person {i}",
                        "reaction": "Thích",
                    }
                    for i in range(12)
                ],
            }
        ]
    }
    rows = ExtensionBundleProvider().fetch_interactions(json.dumps(bundle))
    ingest_rows(db, rows, "extension_scan")
    analyze(db)
    assert (
        len(
            list(
                db.scalars(select(Signal).where(Signal.signal_type == "REACTION_BURST"))
            )
        )
        == 0
    )


def test_ttl_and_priority(db):
    actor = Actor(actor_hash="x" * 64, suspicion_score=75)
    db.add(actor)
    db.flush()
    db.add(
        ProfileSnapshot(
            actor_id=actor.id,
            profile_url="https://www.facebook.com/a",
            captured_at=datetime.now(timezone.utc),
            capture_status="CAPTURED",
        )
    )
    db.flush()
    assert recent_snapshot(db, actor) is not None
    assert (
        recent_snapshot(db, actor, datetime.now(timezone.utc) + timedelta(days=2))
        is None
    )
    assert priority_queue(75) == "high"
    assert priority_queue(55) == "normal"
    assert priority_queue(10) is None
    assert priority_queue(10, critical=True) == "critical"


def test_burst_and_clustering():
    now = datetime.now(timezone.utc)
    burst = detect_bursts(
        [(str(i), now + timedelta(seconds=i)) for i in range(12)], 60, 10
    )
    assert burst[-1]["actor_count"] == 12
    rows = [
        Interaction(
            actor_id=actor,
            post_id=post,
            interaction_type="LIKE",
            observed_at=now,
            collector_source="test",
        )
        for actor in ("a", "b", "c")
        for post in ("p", "q")
    ]
    clusters = cross_post_groups(rows)
    assert len(clusters) == 1
    assert set(clusters[0]["actor_ids"]) == {"a", "b", "c"}


def test_scoring():
    signals = [
        Signal(signal_type="CROSS_POST", score=25, confidence=0.8, details_json={}),
        Signal(signal_type="REACTION_BURST", score=20, confidence=0.7, details_json={}),
    ]
    assert score_signals(signals)[0] == 45


def test_large_shared_post_group_avoids_pairwise_explosion():
    now = datetime.now(timezone.utc)
    rows = [
        Interaction(
            actor_id=f"actor-{actor}",
            post_id=post,
            interaction_type="LIKE",
            observed_at=now,
            collector_source="test",
        )
        for actor in range(1000)
        for post in ("p", "q")
    ]
    groups = cross_post_groups(rows)
    assert len(groups) == 1
    assert len(groups[0]["actor_ids"]) == 1000
    assert len(groups[0]["edges"]) == 999


def test_image_hashes():
    image = Image.new("RGB", (32, 32), "red")
    output = BytesIO()
    image.save(output, format="PNG")
    hashes = avatar_hashes(output.getvalue())
    assert set(hashes) == {"average_hash", "phash", "dhash"}
    assert phash_distance(hashes["phash"], hashes["phash"]) == 0


def test_evidence_chain(db, monkeypatch):
    from app import evidence

    actor = Actor(actor_hash="a" * 64)
    db.add(actor)
    db.flush()
    data = b"image bytes"
    captured = datetime.now(timezone.utc)
    digest = sha256(data)
    from app.models import EvidenceRecord

    record = EvidenceRecord(
        actor_id=actor.id,
        source_url="https://www.facebook.com/a",
        captured_at=captured,
        screenshot_path="test.png",
        sha256=digest,
        previous_record_hash=None,
        record_hash=record_hash(
            actor.actor_hash, "https://www.facebook.com/a", captured, digest, None
        ),
    )
    db.add(record)
    db.flush()
    monkeypatch.setattr(evidence, "get_bytes", lambda path: data)
    db.expire_all()
    assert verify_evidence_chain(db, actor) == "VALID"
    record.sha256 = "bad"
    db.flush()
    assert verify_evidence_chain(db, actor) == "BROKEN"
