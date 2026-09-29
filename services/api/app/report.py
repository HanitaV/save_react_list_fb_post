import html
import io
import json
import zipfile

from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy import select
from sqlalchemy.orm import Session

from .evidence import verify_evidence_chain
from .models import (
    Actor,
    Cluster,
    ClusterMember,
    EvidenceRecord,
    Interaction,
    Post,
    Signal,
)
from .storage import get_bytes


def generate_report(db: Session, post: Post) -> bytes:
    interactions = list(
        db.scalars(select(Interaction).where(Interaction.post_id == post.id))
    )
    actor_ids = {item.actor_id for item in interactions}
    actors = (
        list(db.scalars(select(Actor).where(Actor.id.in_(actor_ids))))
        if actor_ids
        else []
    )
    signals = (
        list(db.scalars(select(Signal).where(Signal.actor_id.in_(actor_ids))))
        if actor_ids
        else []
    )
    evidence = (
        list(
            db.scalars(
                select(EvidenceRecord).where(EvidenceRecord.actor_id.in_(actor_ids))
            )
        )
        if actor_ids
        else []
    )
    members = (
        list(
            db.scalars(
                select(ClusterMember).where(ClusterMember.actor_id.in_(actor_ids))
            )
        )
        if actor_ids
        else []
    )
    cluster_ids = {member.cluster_id for member in members}
    clusters = (
        list(db.scalars(select(Cluster).where(Cluster.id.in_(cluster_ids))))
        if cluster_ids
        else []
    )
    data = {
        "post": {
            "id": post.id,
            "url": post.url,
            "last_scanned_at": str(post.last_scanned_at),
        },
        "methodology": "Authorized imports; deterministic signals indicate candidates, not conclusions.",
        "observed_facts": [
            {
                "actor_hash": actor.actor_hash,
                "display_name": actor.display_name,
                "interaction_count": sum(
                    item.actor_id == actor.id for item in interactions
                ),
            }
            for actor in actors
        ],
        "automated_heuristics": [
            {
                "actor_id": signal.actor_id,
                "type": signal.signal_type,
                "score": signal.score,
                "confidence": signal.confidence,
                "details": signal.details_json,
            }
            for signal in signals
        ],
        "clusters": [
            {
                "id": cluster.id,
                "type": cluster.cluster_type,
                "metadata": cluster.metadata_json,
            }
            for cluster in clusters
        ],
        "evidence": [
            {
                "actor_id": record.actor_id,
                "source_url": record.source_url,
                "captured_at": record.captured_at.isoformat(),
                "sha256": record.sha256,
                "record_hash": record.record_hash,
                "screenshot": f"screenshots/{record.id}.png",
            }
            for record in evidence
        ],
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("report.json", json.dumps(data, indent=2, default=str))
        rows = "".join(
            f"<tr><td>{html.escape(str(a.display_name or ''))}</td><td>{a.actor_hash}</td><td>{a.suspicion_score}</td></tr>"
            for a in actors
        )
        hashes = {}
        chains = {}
        for actor in actors:
            chains[actor.id] = verify_evidence_chain(db, actor)
        for record in evidence:
            name = f"screenshots/{record.id}.png"
            try:
                archive.writestr(name, get_bytes(record.screenshot_path))
                hashes[name] = record.sha256
            except (OSError, BotoCoreError, ClientError):
                hashes[name] = "MISSING"
        signal_rows = "".join(
            f"<li>{html.escape(s.signal_type)}: +{s.score} (confidence {s.confidence})</li>"
            for s in signals
        )
        cluster_rows = "".join(
            f"<li>{html.escape(c.cluster_type)}: {html.escape(c.id)}</li>"
            for c in clusters
        )
        evidence_rows = "".join(
            f"<li>{html.escape(r.captured_at.isoformat())}: "
            f"<a href='screenshots/{r.id}.png'>screenshot</a> "
            f"SHA-256 {html.escape(r.sha256)} "
            f"chain {html.escape(chains.get(r.actor_id, 'INCOMPLETE'))}</li>"
            for r in evidence
        )
        archive.writestr(
            "report.html",
            "<!doctype html><meta charset='utf-8'><title>Evidence report</title>"
            f"<h1>Post evidence report</h1><p>{html.escape(post.url)}</p>"
            f"<p>Last scan: {html.escape(str(post.last_scanned_at))}</p>"
            "<h2>Methodology</h2><p>Authorized imports and visible profile captures. "
            "Signals are automated heuristics, not proof of account authenticity.</p>"
            f"<h2>Observed facts</h2><table><tr><th>Actor</th><th>Hash</th><th>Heuristic score</th></tr>{rows}</table>"
            f"<h2>Automated heuristics</h2><ul>{signal_rows}</ul>"
            f"<h2>Clusters</h2><ul>{cluster_rows}</ul>"
            f"<h2>Evidence screenshots and hashes</h2><ul>{evidence_rows}</ul>",
        )
        archive.writestr("hashes.json", json.dumps(hashes, indent=2))
        archive.writestr("evidence_chain.json", json.dumps(chains, indent=2))
    return output.getvalue()
