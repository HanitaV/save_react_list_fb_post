import hashlib
import json
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Lock
from urllib.parse import urlsplit

from botocore.exceptions import BotoCoreError, ClientError
from celery import Celery
from cloakbrowser import launch
from playwright.sync_api import Error as PlaywrightError
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from .browser_filter import filter_request
from .browser_session import proxy_config, storage_state
from .config import settings
from .db import SessionLocal
from .evidence import append_evidence, avatar_hashes, recent_snapshot
from .models import Actor, ProfileSnapshot, SystemState
from .storage import put_bytes

celery_app = Celery("evidence", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.task_routes = {"app.tasks.capture_profile": {"queue": "normal"}}
logger = logging.getLogger(__name__)


class JobFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        fields = {
            "event": record.getMessage(),
            "level": record.levelname,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        for key in (
            "correlation_id",
            "job_id",
            "actor",
            "post",
            "reason",
            "duration",
            "result",
            "error",
        ):
            value = getattr(record, key, None)
            if value is not None:
                fields[key] = value
        return json.dumps(fields, default=str)


_job_handler = logging.StreamHandler()
_job_handler.setFormatter(JobFormatter())
logger.addHandler(_job_handler)
logger.setLevel(logging.INFO)
logger.propagate = False
_native_executor = ThreadPoolExecutor(
    max_workers=1, thread_name_prefix="evidence-browser"
)
_pending: set[str] = set()
_pending_lock = Lock()


def queue_status() -> dict:
    if settings.queue_mode == "inline":
        with _pending_lock:
            return {"mode": "inline", "pending": len(_pending)}
    try:
        connection = Redis.from_url(settings.redis_url, socket_timeout=1)
        counts = {
            queue: connection.llen(queue)
            for queue in ("critical", "high", "normal", "low")
        }
        return {"mode": "celery", "pending": sum(counts.values()), "queues": counts}
    except RedisError:
        return {"mode": "celery", "pending": None, "status": "UNAVAILABLE"}


def priority_queue(
    score: int, threshold: int = 50, critical: bool = False, refresh: bool = False
) -> str | None:
    if critical:
        return "critical"
    if refresh:
        return "low"
    if score >= 70:
        return "high"
    if score >= threshold:
        return "normal"
    return None


def queue_capture(actor: Actor, reason: str, critical: bool = False) -> str | None:
    queue = priority_queue(
        actor.suspicion_score, settings.screenshot_threshold, critical
    )
    if queue:
        if settings.queue_mode == "inline":
            with _pending_lock:
                if actor.id in _pending:
                    return queue
                _pending.add(actor.id)

            def run() -> None:
                try:
                    capture_profile(actor.id, reason)
                finally:
                    with _pending_lock:
                        _pending.discard(actor.id)

            _native_executor.submit(run)
        else:
            capture_profile.apply_async(
                args=[actor.id, reason], queue=queue, task_id=f"capture-{actor.id}"
            )
    return queue


def set_health(state: str) -> None:
    with SessionLocal() as db:
        item = db.get(SystemState, "browser_health")
        if item is None:
            db.add(SystemState(key="browser_health", value=state))
        else:
            item.value = state
        db.commit()


_browser = None
_jobs = 0


def _capture(url: str) -> tuple[bytes, str, str | None, bytes | None]:
    global _browser, _jobs
    if _browser is None or _jobs >= settings.browser_max_jobs:
        if _browser is not None:
            _browser.close()
        _browser = launch(
            headless=True,
            proxy=proxy_config(),
            stealth_args=False,
            geoip=False,
            humanize=False,
        )
        _jobs = 0
    state = storage_state()
    context_options = {"viewport": {"width": 1280, "height": 900}}
    if state is not None:
        context_options["storage_state"] = state
    context = _browser.new_context(**context_options)
    try:
        page = context.new_page()

        page.route("**/*", filter_request)
        response = page.goto(url, wait_until="domcontentloaded", timeout=30000)
        if (urlsplit(page.url).hostname or "").lower() not in {
            "facebook.com",
            "www.facebook.com",
            "m.facebook.com",
            "fb.com",
            "www.fb.com",
        }:
            raise ManualReview("Unexpected redirect")
        final_path = urlsplit(page.url).path.lower()
        if any(
            segment in final_path for segment in ("/login", "/checkpoint", "/recover")
        ):
            raise ManualReview("Authentication flow")
        body = page.locator("body").inner_text(timeout=10000)[:4000].lower()
        if response and response.status in {403, 429}:
            raise ManualReview(f"HTTP {response.status}")
        if any(
            term in body
            for term in (
                "checkpoint",
                "log in to facebook",
                "temporarily blocked",
                "confirm your identity",
            )
        ):
            raise ManualReview("Authentication or restriction page")
        avatar = None
        candidate = page.locator('img[alt*="profile" i], img[alt*="avatar" i]').first
        if candidate.count() and candidate.is_visible():
            avatar = candidate.screenshot()
        heading = page.locator("h1").first
        display_name = (
            heading.inner_text()
            if heading.count() and heading.is_visible()
            else page.title()
        )
        return (
            page.screenshot(full_page=settings.capture_full_page),
            page.url,
            display_name,
            avatar,
        )
    finally:
        context.close()
        _jobs += 1


class ManualReview(Exception):
    pass


@celery_app.task(name="app.tasks.capture_profile", bind=True, acks_late=True)
def capture_profile(self, actor_id: str, reason: str) -> dict:
    correlation_id = str(uuid.uuid4())
    started = datetime.now(timezone.utc)
    logger.info(
        "capture_start",
        extra={
            "correlation_id": correlation_id,
            "job_id": self.request.id,
            "actor": actor_id,
            "reason": reason,
        },
    )
    with SessionLocal() as db:
        actor = db.get(Actor, actor_id)
        if actor is None or not actor.public_profile_url:
            return {"status": "UNAVAILABLE"}
        health = db.get(SystemState, "browser_health")
        if health and health.value == "NEEDS_MANUAL_REVIEW":
            return {"status": "NEEDS_MANUAL_REVIEW"}
        cached = recent_snapshot(db, actor)
        if cached:
            return {"status": "CACHED", "snapshot_id": cached.id}
        try:
            screenshot, final_url, title, avatar = _capture(actor.public_profile_url)
            captured_at = datetime.now(timezone.utc)
            path = f"actors/{actor.id}/{uuid.uuid4()}.png"
            put_bytes(path, screenshot)
            digest = hashlib.sha256(screenshot).hexdigest()
            hashes = avatar_hashes(avatar) if avatar else {}
            avatar_path = (
                f"actors/{actor.id}/{uuid.uuid4()}-avatar.png" if avatar else None
            )
            if avatar and avatar_path:
                put_bytes(avatar_path, avatar)
            db.add(
                ProfileSnapshot(
                    actor_id=actor.id,
                    profile_url=final_url,
                    display_name=title,
                    metadata_json={"reason": reason},
                    captured_at=captured_at,
                    screenshot_path=path,
                    screenshot_sha256=digest,
                    avatar_path=avatar_path,
                    avatar_phash=hashes.get("phash"),
                    avatar_ahash=hashes.get("average_hash"),
                    avatar_dhash=hashes.get("dhash"),
                    capture_status="CAPTURED",
                )
            )
            append_evidence(
                db, actor, final_url, path, screenshot, captured_at, {"reason": reason}
            )
            db.commit()
            set_health("NORMAL")
            logger.info(
                "capture_complete",
                extra={
                    "correlation_id": correlation_id,
                    "job_id": self.request.id,
                    "actor": actor_id,
                    "duration": (captured_at - started).total_seconds(),
                    "result": "CAPTURED",
                },
            )
            return {"status": "CAPTURED", "sha256": digest}
        except ManualReview as exc:
            set_health("NEEDS_MANUAL_REVIEW")
            db.add(
                ProfileSnapshot(
                    actor_id=actor.id,
                    profile_url=actor.public_profile_url,
                    capture_status="NEEDS_MANUAL_REVIEW",
                    metadata_json={"reason": str(exc)},
                )
            )
            db.commit()
            logger.warning(
                "capture_manual_review",
                extra={
                    "correlation_id": correlation_id,
                    "job_id": self.request.id,
                    "actor": actor_id,
                    "reason": reason,
                    "duration": (datetime.now(timezone.utc) - started).total_seconds(),
                    "result": "NEEDS_MANUAL_REVIEW",
                    "error": str(exc),
                },
            )
            return {"status": "NEEDS_MANUAL_REVIEW"}
        except (
            PlaywrightError,
            OSError,
            ValueError,
            BotoCoreError,
            ClientError,
            SQLAlchemyError,
        ) as exc:
            db.rollback()
            set_health("DEGRADED")
            logger.error(
                "capture_failed",
                extra={
                    "correlation_id": correlation_id,
                    "job_id": self.request.id,
                    "actor": actor_id,
                    "reason": reason,
                    "duration": (datetime.now(timezone.utc) - started).total_seconds(),
                    "result": "ERROR",
                    "error": type(exc).__name__,
                },
            )
            return {"status": "ERROR"}
