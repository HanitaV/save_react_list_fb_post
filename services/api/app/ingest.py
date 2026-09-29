from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .identity import actor_hash, normalize_identifier
from .models import Actor, Interaction, Post, now
from .providers import InteractionRow


def ingest_rows(db: Session, rows: list[InteractionRow], source: str) -> dict:
    inserted = 0
    actor_ids: set[str] = set()
    post_ids: set[str] = set()
    for row in rows:
        post = db.scalar(select(Post).where(Post.url == row.post_url))
        if post is None:
            post = Post(url=row.post_url)
            db.add(post)
            db.flush()
        digest = actor_hash(row.profile_url)
        actor = db.scalar(select(Actor).where(Actor.actor_hash == digest))
        if actor is None:
            actor = Actor(
                actor_hash=digest,
                public_profile_url=row.profile_url,
                display_name=row.display_name,
                raw_identifier=normalize_identifier(row.profile_url)
                if settings.store_raw_identifiers
                else None,
            )
            db.add(actor)
            db.flush()
        else:
            actor.last_seen = now()
            if row.display_name:
                actor.display_name = row.display_name
        exists = db.scalar(
            select(Interaction.id).where(
                Interaction.post_id == post.id,
                Interaction.actor_id == actor.id,
                Interaction.interaction_type == row.reaction_type,
                Interaction.observed_at == row.observed_at,
            )
        )
        if exists is None:
            db.add(
                Interaction(
                    post_id=post.id,
                    actor_id=actor.id,
                    interaction_type=row.reaction_type,
                    observed_at=row.observed_at,
                    collector_source=source,
                )
            )
            inserted += 1
        post.last_scanned_at = now()
        post.status = "IMPORTED"
        actor_ids.add(actor.id)
        post_ids.add(post.id)
    db.commit()
    return {"inserted": inserted, "actors": len(actor_ids), "posts": len(post_ids)}
