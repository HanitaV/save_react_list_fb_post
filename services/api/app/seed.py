"""Generate deterministic synthetic development data."""

import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from .analysis import analyze
from .db import SessionLocal
from .ingest import ingest_rows
from .models import Actor, ProfileSnapshot
from .providers import InteractionRow


def seed() -> dict:
    rng = random.Random(42)
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    posts = [f"https://www.facebook.com/example/posts/{i + 1}" for i in range(20)]
    actors = [
        f"https://www.facebook.com/fake-development-actor-{i + 1}" for i in range(600)
    ]
    combinations: set[tuple[int, int]] = set()
    for actor in range(50):
        for post in range(4):
            combinations.add((post, actor))
    for actor in range(72):
        combinations.add((5, actor))
    for actor in range(600):
        combinations.add((actor % 20, actor))
    while len(combinations) < 2000:
        combinations.add((rng.randrange(20), rng.randrange(600)))
    rows = []
    for post, actor in sorted(combinations):
        seconds = actor if post == 5 and actor < 72 else rng.randrange(1, 86400)
        rows.append(
            InteractionRow(
                post_url=posts[post],
                profile_url=actors[actor],
                display_name=f"Synthetic Actor {actor + 1}",
                reaction_type="LIKE",
                observed_at=base + timedelta(days=post, seconds=seconds),
            )
        )
    with SessionLocal() as db:
        result = ingest_rows(db, rows, "development_seed")
        for actor in list(
            db.scalars(select(Actor).order_by(Actor.actor_hash).limit(12))
        ):
            db.add(
                ProfileSnapshot(
                    actor_id=actor.id,
                    profile_url=actor.public_profile_url,
                    capture_status="SYNTHETIC_AVATAR_ONLY",
                    avatar_phash="0000000000000000",
                )
            )
        db.commit()
        result["analysis"] = analyze(db)
        return result


if __name__ == "__main__":
    print(seed())
