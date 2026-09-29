from collections import Counter
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .analysis import analyze, score_signals
from .config import settings
from .db import get_db
from .evidence import recent_snapshot, verify_evidence_chain
from .identity import canonical_post_url
from .ingest import ingest_rows
from .models import (
    Actor,
    Cluster,
    ClusterMember,
    EvidenceRecord,
    Interaction,
    Post,
    ProfileSnapshot,
    Signal,
    SystemState,
)
from .providers import ExtensionBundleProvider, JSONImportProvider, ManualCSVProvider
from .report import generate_report
from .security import issue_token, require_role
from .storage import delete_object
from .tasks import queue_capture, queue_status

app = FastAPI(title="Facebook Engagement Evidence System")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", include_in_schema=False)
def native_dashboard():
    return FileResponse(Path(__file__).with_name("native.html"))


class PostInput(BaseModel):
    urls: list[str]


class LoginInput(BaseModel):
    password: str


@app.post("/api/auth/login")
def login(body: LoginInput):
    import hmac

    for role, password in (
        ("ADMIN", settings.admin_password),
        ("ANALYST", settings.analyst_password),
        ("VIEWER", settings.viewer_password),
    ):
        if password and hmac.compare_digest(body.password, password):
            return {
                "access_token": issue_token(role),
                "token_type": "bearer",
                "role": role,
            }
    raise HTTPException(401, "Invalid credentials")


@app.post("/api/posts")
def create_posts(
    body: PostInput,
    db: Session = Depends(get_db),
    user=Depends(require_role("ADMIN", "ANALYST")),
):
    result = []
    for raw_url in body.urls:
        try:
            url = canonical_post_url(raw_url)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        post = db.scalar(select(Post).where(Post.url == url))
        if post is None:
            post = Post(url=url)
            db.add(post)
            db.flush()
        result.append({"id": post.id, "url": post.url, "status": post.status})
    db.commit()
    return result


@app.get("/api/posts")
def list_posts(
    db: Session = Depends(get_db),
    user=Depends(require_role("ADMIN", "ANALYST", "VIEWER")),
):
    return [
        {
            "id": p.id,
            "url": p.url,
            "status": p.status,
            "last_scanned_at": p.last_scanned_at,
            "interaction_count": db.scalar(
                select(func.count())
                .select_from(Interaction)
                .where(Interaction.post_id == p.id)
            ),
        }
        for p in db.scalars(select(Post).order_by(Post.created_at.desc()))
    ]


@app.get("/api/posts/{post_id}")
def get_post(
    post_id: str,
    db: Session = Depends(get_db),
    user=Depends(require_role("ADMIN", "ANALYST", "VIEWER")),
):
    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(404, "Post not found")
    rows = list(db.scalars(select(Interaction).where(Interaction.post_id == post_id)))
    actors = (
        {
            a.id: a
            for a in db.scalars(
                select(Actor).where(Actor.id.in_({r.actor_id for r in rows}))
            )
        }
        if rows
        else {}
    )
    return {
        "id": post.id,
        "url": post.url,
        "status": post.status,
        "last_scanned_at": post.last_scanned_at,
        "interaction_count": len(rows),
        "unique_actors": len(actors),
        "reaction_distribution": dict(Counter(r.interaction_type.value for r in rows)),
        "interactions": [
            {
                "id": r.id,
                "actor_id": r.actor_id,
                "actor_name": actors[r.actor_id].display_name,
                "type": r.interaction_type.value,
                "observed_at": r.observed_at,
                "timestamp_basis": "SCAN_TIME"
                if r.collector_source == "extension_scan"
                else "REACTION_TIME",
                "collector_source": r.collector_source,
                "score": actors[r.actor_id].suspicion_score,
            }
            for r in rows
        ],
    }


@app.post("/api/import/csv")
async def import_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(require_role("ADMIN", "ANALYST")),
):
    content = (await file.read(10_000_001)).decode("utf-8-sig")
    if len(content) > 10_000_000:
        raise HTTPException(413, "CSV too large")
    try:
        return ingest_rows(
            db, ManualCSVProvider().fetch_interactions(content), "manual_csv"
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/import/json")
async def import_json(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(require_role("ADMIN", "ANALYST")),
):
    try:
        return ingest_rows(
            db,
            JSONImportProvider().fetch_interactions(
                (await file.read(10_000_001)).decode()
            ),
            "json_import",
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/import/extension")
async def import_extension(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(require_role("ADMIN", "ANALYST")),
):
    raw = await file.read(10_000_001)
    if len(raw) > 10_000_000:
        raise HTTPException(413, "Extension bundle too large")
    try:
        content = raw.decode("utf-8-sig")
        provider = ExtensionBundleProvider()
        metadata = provider.fetch_post_metadata(content)
        result = ingest_rows(db, provider.fetch_interactions(content), "extension_scan")
        return {**result, **metadata}
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/actors")
def list_actors(
    min_score: int = 0,
    db: Session = Depends(get_db),
    user=Depends(require_role("ADMIN", "ANALYST", "VIEWER")),
):
    return [
        {
            "id": a.id,
            "display_name": a.display_name,
            "actor_hash": a.actor_hash,
            "status": a.status.value,
            "suspicion_score": a.suspicion_score,
            "public_profile_url": a.public_profile_url,
        }
        for a in db.scalars(
            select(Actor)
            .where(Actor.suspicion_score >= min_score)
            .order_by(Actor.suspicion_score.desc())
            .limit(1000)
        )
    ]


@app.get("/api/actors/{actor_id}")
def get_actor(
    actor_id: str,
    db: Session = Depends(get_db),
    user=Depends(require_role("ADMIN", "ANALYST", "VIEWER")),
):
    actor = db.get(Actor, actor_id)
    if not actor:
        raise HTTPException(404, "Actor not found")
    signals = list(db.scalars(select(Signal).where(Signal.actor_id == actor_id)))
    score, reasons = score_signals(signals)
    interactions = list(
        db.scalars(select(Interaction).where(Interaction.actor_id == actor_id))
    )
    snapshots = list(
        db.scalars(select(ProfileSnapshot).where(ProfileSnapshot.actor_id == actor_id))
    )
    members = list(
        db.scalars(select(ClusterMember).where(ClusterMember.actor_id == actor_id))
    )
    return {
        "id": actor.id,
        "actor_hash": actor.actor_hash,
        "display_name": actor.display_name,
        "public_profile_url": actor.public_profile_url,
        "first_seen": actor.first_seen,
        "last_seen": actor.last_seen,
        "status": actor.status.value,
        "suspicion_score": score,
        "reasons": reasons,
        "post_ids": sorted({r.post_id for r in interactions}),
        "timeline": [
            {
                "post_id": r.post_id,
                "type": r.interaction_type.value,
                "observed_at": r.observed_at,
                "timestamp_basis": "SCAN_TIME"
                if r.collector_source == "extension_scan"
                else "REACTION_TIME",
                "collector_source": r.collector_source,
            }
            for r in interactions
        ],
        "cluster_ids": [m.cluster_id for m in members],
        "snapshots": [
            {
                "id": s.id,
                "captured_at": s.captured_at,
                "capture_status": s.capture_status,
                "sha256": s.screenshot_sha256,
            }
            for s in snapshots
        ],
        "evidence_verification": verify_evidence_chain(db, actor),
    }


@app.delete("/api/actors/{actor_id}")
def delete_actor(
    actor_id: str, db: Session = Depends(get_db), user=Depends(require_role("ADMIN"))
):
    actor = db.get(Actor, actor_id)
    if not actor:
        raise HTTPException(404, "Actor not found")
    paths = [
        r.screenshot_path
        for r in db.scalars(
            select(EvidenceRecord).where(EvidenceRecord.actor_id == actor_id)
        )
    ]
    for snapshot in db.scalars(
        select(ProfileSnapshot).where(ProfileSnapshot.actor_id == actor_id)
    ):
        paths.extend(
            path for path in (snapshot.screenshot_path, snapshot.avatar_path) if path
        )
    db.delete(actor)
    db.commit()
    for path in set(paths):
        delete_object(path)
    return {"deleted": actor_id}


@app.post("/api/analyze/post/{post_id}")
def analyze_post(
    post_id: str,
    db: Session = Depends(get_db),
    user=Depends(require_role("ADMIN", "ANALYST")),
):
    if not db.get(Post, post_id):
        raise HTTPException(404, "Post not found")
    result = analyze(db)
    actor_ids = set(
        db.scalars(select(Interaction.actor_id).where(Interaction.post_id == post_id))
    )
    result["queued"] = queue_candidates(db, actor_ids)
    return result


@app.post("/api/analyze/all")
def analyze_all(db: Session = Depends(get_db), user=Depends(require_role("ADMIN"))):
    result = analyze(db)
    result["queued"] = queue_candidates(db)
    return result


def queue_candidates(db: Session, actor_ids: set[str] | None = None) -> int:
    statement = select(Actor).where(
        Actor.suspicion_score >= settings.screenshot_threshold
    )
    if actor_ids is not None:
        statement = statement.where(Actor.id.in_(actor_ids))
    queued = 0
    for actor in db.scalars(statement):
        if actor.public_profile_url and recent_snapshot(db, actor) is None:
            if queue_capture(actor, "analysis_threshold"):
                queued += 1
    return queued


@app.post("/api/evidence/capture/{actor_id}")
def capture(
    actor_id: str,
    db: Session = Depends(get_db),
    user=Depends(require_role("ADMIN", "ANALYST")),
):
    actor = db.get(Actor, actor_id)
    if not actor:
        raise HTTPException(404, "Actor not found")
    cached = recent_snapshot(db, actor)
    if cached:
        return {"status": "CACHED", "snapshot_id": cached.id}
    queue = queue_capture(actor, "operator_requested")
    return {"status": "QUEUED" if queue else "BELOW_THRESHOLD", "queue": queue}


@app.get("/api/evidence/{actor_id}")
def list_evidence(
    actor_id: str,
    db: Session = Depends(get_db),
    user=Depends(require_role("ADMIN", "ANALYST", "VIEWER")),
):
    return [
        {
            "id": r.id,
            "source_url": r.source_url,
            "captured_at": r.captured_at,
            "sha256": r.sha256,
            "record_hash": r.record_hash,
        }
        for r in db.scalars(
            select(EvidenceRecord).where(EvidenceRecord.actor_id == actor_id)
        )
    ]


@app.get("/api/evidence/verify/{actor_id}")
def verify(
    actor_id: str,
    db: Session = Depends(get_db),
    user=Depends(require_role("ADMIN", "ANALYST", "VIEWER")),
):
    actor = db.get(Actor, actor_id)
    if not actor:
        raise HTTPException(404, "Actor not found")
    return {"status": verify_evidence_chain(db, actor)}


@app.get("/api/clusters")
def list_clusters(
    db: Session = Depends(get_db),
    user=Depends(require_role("ADMIN", "ANALYST", "VIEWER")),
):
    return [
        {
            "id": c.id,
            "type": c.cluster_type,
            "confidence": c.confidence,
            "member_count": db.scalar(
                select(func.count())
                .select_from(ClusterMember)
                .where(ClusterMember.cluster_id == c.id)
            ),
        }
        for c in db.scalars(select(Cluster))
    ]


@app.get("/api/clusters/{cluster_id}")
def get_cluster(
    cluster_id: str,
    db: Session = Depends(get_db),
    user=Depends(require_role("ADMIN", "ANALYST", "VIEWER")),
):
    cluster = db.get(Cluster, cluster_id)
    if not cluster:
        raise HTTPException(404, "Cluster not found")
    members = list(
        db.scalars(select(ClusterMember).where(ClusterMember.cluster_id == cluster_id))
    )
    return {
        "id": cluster.id,
        "type": cluster.cluster_type,
        "confidence": cluster.confidence,
        "metadata": cluster.metadata_json,
        "members": [{"actor_id": m.actor_id, "score": m.score} for m in members],
    }


@app.post("/api/reports/post/{post_id}")
def report(
    post_id: str,
    db: Session = Depends(get_db),
    user=Depends(require_role("ADMIN", "ANALYST")),
):
    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(404, "Post not found")
    return Response(
        generate_report(db, post),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="report-{post_id}.zip"'},
    )


@app.get("/api/system/status")
def system_status(
    db: Session = Depends(get_db),
    user=Depends(require_role("ADMIN", "ANALYST", "VIEWER")),
):
    health = db.get(SystemState, "browser_health")
    return {
        "posts": db.scalar(select(func.count()).select_from(Post)),
        "interactions": db.scalar(select(func.count()).select_from(Interaction)),
        "actors": db.scalar(select(func.count()).select_from(Actor)),
        "suspicious_actors": db.scalar(
            select(func.count())
            .select_from(Actor)
            .where(Actor.suspicion_score >= settings.screenshot_threshold)
        ),
        "clusters": db.scalar(select(func.count()).select_from(Cluster)),
        "evidence_records": db.scalar(select(func.count()).select_from(EvidenceRecord)),
        "browser_health": health.value if health else "NORMAL",
        "browser_backend": "CLOAKBROWSER",
        "proxy_enabled": bool(settings.browser_proxy_server),
        "session_file_ready": bool(
            settings.browser_storage_state_path
            and Path(settings.browser_storage_state_path).is_file()
        ),
        "queue": queue_status(),
    }


@app.post("/api/system/resume")
def resume_capture(db: Session = Depends(get_db), user=Depends(require_role("ADMIN"))):
    health = db.get(SystemState, "browser_health")
    if health is None:
        health = SystemState(key="browser_health", value="NORMAL")
        db.add(health)
    else:
        health.value = "NORMAL"
    db.commit()
    return {"browser_health": "NORMAL"}
