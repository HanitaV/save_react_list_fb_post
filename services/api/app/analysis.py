from collections import defaultdict
from datetime import datetime, timedelta

import networkx as nx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .config import settings
from .evidence import phash_distance
from .models import (
    Actor,
    ActorStatus,
    Cluster,
    ClusterMember,
    Interaction,
    ProfileSnapshot,
    Signal,
)

WEIGHTS = {
    "CROSS_POST": 25,
    "REACTION_BURST": 20,
    "AVATAR_SIMILARITY": 20,
    "NAME_PATTERN": 10,
    "REPEATED_CLUSTER": 20,
    "LOW_METADATA": 5,
}


def detect_bursts(
    items: list[tuple[str, datetime]], window_seconds: int = 60, min_actors: int = 10
) -> list[dict]:
    ordered = sorted(items, key=lambda item: item[1])
    found: list[dict] = []
    left = 0
    for right, (_, end) in enumerate(ordered):
        while end - ordered[left][1] > timedelta(seconds=window_seconds):
            left += 1
        actors = {actor for actor, _ in ordered[left : right + 1]}
        if len(actors) >= min_actors:
            candidate = {
                "start_time": ordered[left][1].isoformat(),
                "end_time": end.isoformat(),
                "actor_count": len(actors),
                "duration": (end - ordered[left][1]).total_seconds(),
                "actor_ids": sorted(actors),
            }
            if found and set(candidate["actor_ids"]) >= set(found[-1]["actor_ids"]):
                found[-1] = candidate
            else:
                found.append(candidate)
    return found


def cross_post_groups(
    interactions: list[Interaction],
    minimum_shared: int = 2,
    minimum_jaccard: float = 0.6,
) -> list[dict]:
    actor_posts: dict[str, set[str]] = defaultdict(set)
    graph = nx.Graph()
    for interaction in interactions:
        actor_posts[interaction.actor_id].add(interaction.post_id)
        graph.add_edge(f"a:{interaction.actor_id}", f"p:{interaction.post_id}")
    projection = nx.Graph()
    for actor in actor_posts:
        projection.add_node(actor)
    signatures: dict[frozenset[str], list[str]] = defaultdict(list)
    for actor, posts in actor_posts.items():
        if len(posts) >= minimum_shared:
            signatures[frozenset(posts)].append(actor)
    for posts, members in signatures.items():
        if len(members) >= 3:
            representative = members[0]
            for member in members[1:]:
                projection.add_edge(
                    representative, member, weight=len(posts), jaccard=1.0
                )
    post_actors: dict[str, set[str]] = defaultdict(set)
    for actor, posts in actor_posts.items():
        for post in posts:
            post_actors[post].add(actor)
    pairs: set[tuple[str, str]] = set()
    for members in post_actors.values():
        if len(members) > settings.max_pairwise_post_actors:
            continue
        ordered = sorted(members)
        for i, left in enumerate(ordered):
            for right in ordered[i + 1 :]:
                pairs.add((left, right))
    for left, right in pairs:
        shared = actor_posts[left] & actor_posts[right]
        union = actor_posts[left] | actor_posts[right]
        similarity = len(shared) / len(union)
        if len(shared) >= minimum_shared and similarity >= minimum_jaccard:
            projection.add_edge(left, right, weight=len(shared), jaccard=similarity)
    return [
        {
            "actor_ids": sorted(component),
            "post_ids": sorted(set.union(*(actor_posts[a] for a in component))),
            "actor_degrees": {actor: graph.degree[f"a:{actor}"] for actor in component},
            "post_degrees": {
                post: graph.degree[f"p:{post}"]
                for post in set.union(*(actor_posts[a] for a in component))
            },
            "edges": [
                {
                    "source": a,
                    "target": b,
                    "weight": projection[a][b]["weight"],
                    "jaccard": projection[a][b]["jaccard"],
                    "shared_post_ids": sorted(actor_posts[a] & actor_posts[b]),
                }
                for a, b in list(projection.subgraph(component).edges)[
                    : settings.max_cluster_edges
                ]
            ],
        }
        for component in nx.connected_components(projection)
        if len(component) >= 3
    ]


def score_signals(signals: list[Signal]) -> tuple[int, list[dict]]:
    strongest: dict[str, Signal] = {}
    for signal in signals:
        if (
            signal.signal_type not in strongest
            or signal.score > strongest[signal.signal_type].score
        ):
            strongest[signal.signal_type] = signal
    reasons = [
        {
            "type": key,
            "points": min(value.score, WEIGHTS.get(key, 0)),
            "confidence": value.confidence,
            "details": value.details_json,
        }
        for key, value in strongest.items()
    ]
    return min(100, sum(reason["points"] for reason in reasons)), reasons


def analyze(db: Session) -> dict:
    interactions = list(db.scalars(select(Interaction)))
    affected = {row.actor_id for row in interactions}
    if not affected:
        return {"actors": 0, "clusters": 0, "bursts": 0}
    db.execute(delete(Signal).where(Signal.actor_id.in_(affected)))
    db.execute(delete(ClusterMember))
    db.execute(delete(Cluster))
    actor_posts: dict[str, set[str]] = defaultdict(set)
    by_post: dict[str, list[tuple[str, datetime]]] = defaultdict(list)
    for row in interactions:
        actor_posts[row.actor_id].add(row.post_id)
        if row.collector_source != "extension_scan":
            by_post[row.post_id].append((row.actor_id, row.observed_at))
    for actor_id in affected:
        count = len(actor_posts[actor_id])
        if count >= 2:
            db.add(
                Signal(
                    actor_id=actor_id,
                    signal_type="CROSS_POST",
                    score=min(25, count * 5),
                    confidence=min(0.95, 0.5 + count * 0.05),
                    details_json={"post_count": count},
                )
            )
    bursts = 0
    for pid, items in by_post.items():
        for burst in detect_bursts(
            items, settings.burst_window_seconds, settings.burst_min_actors
        ):
            bursts += 1
            for actor_id in burst["actor_ids"]:
                db.add(
                    Signal(
                        actor_id=actor_id,
                        post_id=pid,
                        signal_type="REACTION_BURST",
                        score=20,
                        confidence=0.7,
                        details_json={
                            k: v for k, v in burst.items() if k != "actor_ids"
                        },
                    )
                )
    clusters = cross_post_groups(interactions)
    for group in clusters:
        cluster = Cluster(
            cluster_type="CROSS_POST",
            confidence=0.8,
            metadata_json={
                "post_ids": group["post_ids"],
                "edges": group["edges"],
                "actor_degrees": group["actor_degrees"],
                "post_degrees": group["post_degrees"],
            },
        )
        db.add(cluster)
        db.flush()
        for actor_id in group["actor_ids"]:
            db.add(ClusterMember(cluster_id=cluster.id, actor_id=actor_id, score=20))
            db.add(
                Signal(
                    actor_id=actor_id,
                    signal_type="REPEATED_CLUSTER",
                    score=20,
                    confidence=0.8,
                    details_json={"cluster_id": cluster.id},
                )
            )
    snapshots = list(
        db.scalars(
            select(ProfileSnapshot)
            .where(ProfileSnapshot.avatar_phash.is_not(None))
            .order_by(ProfileSnapshot.captured_at.desc())
        )
    )
    latest = {}
    for snapshot in snapshots:
        latest.setdefault(snapshot.actor_id, snapshot.avatar_phash)
    avatar_graph = nx.Graph()
    for actor_id in latest:
        avatar_graph.add_node(actor_id)
    hashes = list(latest.items())
    for index, (left, left_hash) in enumerate(hashes):
        for right, right_hash in hashes[index + 1 :]:
            distance = phash_distance(left_hash, right_hash)
            if distance <= settings.avatar_phash_distance_possible:
                avatar_graph.add_edge(left, right, distance=distance)
    for component in nx.connected_components(avatar_graph):
        if len(component) < 2:
            continue
        cluster = Cluster(
            cluster_type="AVATAR_SIMILARITY",
            confidence=0.65,
            metadata_json={"threshold": settings.avatar_phash_distance_possible},
        )
        db.add(cluster)
        db.flush()
        for actor_id in component:
            db.add(ClusterMember(cluster_id=cluster.id, actor_id=actor_id, score=20))
            db.add(
                Signal(
                    actor_id=actor_id,
                    signal_type="AVATAR_SIMILARITY",
                    score=20,
                    confidence=0.65,
                    details_json={"cluster_id": cluster.id},
                )
            )
    db.flush()
    for actor in db.scalars(select(Actor).where(Actor.id.in_(affected))):
        score, _ = score_signals(
            list(db.scalars(select(Signal).where(Signal.actor_id == actor.id)))
        )
        actor.suspicion_score = score
        actor.status = (
            ActorStatus.HIGHLY_SUSPICIOUS
            if score >= 70
            else ActorStatus.SUSPICIOUS
            if score >= settings.screenshot_threshold
            else ActorStatus.NORMAL
        )
    db.commit()
    return {"actors": len(affected), "clusters": len(clusters), "bursts": bursts}
