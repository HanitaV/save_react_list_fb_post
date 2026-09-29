import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def now() -> datetime:
    return datetime.now(timezone.utc)


def uid() -> str:
    return str(uuid.uuid4())


class ActorStatus(str, enum.Enum):
    UNKNOWN = "UNKNOWN"
    NORMAL = "NORMAL"
    SUSPICIOUS = "SUSPICIOUS"
    HIGHLY_SUSPICIOUS = "HIGHLY_SUSPICIOUS"
    UNAVAILABLE = "UNAVAILABLE"


class InteractionType(str, enum.Enum):
    LIKE = "LIKE"
    LOVE = "LOVE"
    HAHA = "HAHA"
    WOW = "WOW"
    SAD = "SAD"
    ANGRY = "ANGRY"
    CARE = "CARE"
    COMMENT = "COMMENT"
    OTHER = "OTHER"


class Post(Base):
    __tablename__ = "posts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    platform: Mapped[str] = mapped_column(String(32), default="facebook")
    external_post_id: Mapped[str | None] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    page_name: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="CREATED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Actor(Base):
    __tablename__ = "actors"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    actor_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    public_profile_url: Mapped[str | None] = mapped_column(Text)
    display_name: Mapped[str | None] = mapped_column(String(255))
    raw_identifier: Mapped[str | None] = mapped_column(Text)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    status: Mapped[ActorStatus] = mapped_column(
        Enum(ActorStatus), default=ActorStatus.UNKNOWN
    )
    suspicion_score: Mapped[int] = mapped_column(Integer, default=0)


class Interaction(Base):
    __tablename__ = "interactions"
    __table_args__ = (
        UniqueConstraint("post_id", "actor_id", "interaction_type", "observed_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    post_id: Mapped[str] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"), index=True
    )
    actor_id: Mapped[str] = mapped_column(
        ForeignKey("actors.id", ondelete="CASCADE"), index=True
    )
    interaction_type: Mapped[InteractionType] = mapped_column(Enum(InteractionType))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    collector_source: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ProfileSnapshot(Base):
    __tablename__ = "profile_snapshots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    actor_id: Mapped[str] = mapped_column(
        ForeignKey("actors.id", ondelete="CASCADE"), index=True
    )
    profile_url: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str | None] = mapped_column(String(255))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    screenshot_path: Mapped[str | None] = mapped_column(Text)
    screenshot_sha256: Mapped[str | None] = mapped_column(String(64))
    avatar_path: Mapped[str | None] = mapped_column(Text)
    avatar_phash: Mapped[str | None] = mapped_column(String(64))
    avatar_ahash: Mapped[str | None] = mapped_column(String(64))
    avatar_dhash: Mapped[str | None] = mapped_column(String(64))
    page_content_hash: Mapped[str | None] = mapped_column(String(64))
    capture_status: Mapped[str] = mapped_column(String(32))


class Signal(Base):
    __tablename__ = "signals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    actor_id: Mapped[str | None] = mapped_column(
        ForeignKey("actors.id", ondelete="CASCADE"), index=True
    )
    post_id: Mapped[str | None] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"), index=True
    )
    signal_type: Mapped[str] = mapped_column(String(64))
    score: Mapped[int] = mapped_column(Integer)
    confidence: Mapped[float] = mapped_column(Float)
    details_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Cluster(Base):
    __tablename__ = "clusters"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    cluster_type: Mapped[str] = mapped_column(String(64))
    confidence: Mapped[float] = mapped_column(Float)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ClusterMember(Base):
    __tablename__ = "cluster_members"
    cluster_id: Mapped[str] = mapped_column(
        ForeignKey("clusters.id", ondelete="CASCADE"), primary_key=True
    )
    actor_id: Mapped[str] = mapped_column(
        ForeignKey("actors.id", ondelete="CASCADE"), primary_key=True
    )
    score: Mapped[int] = mapped_column(Integer, default=0)


class EvidenceRecord(Base):
    __tablename__ = "evidence_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    actor_id: Mapped[str] = mapped_column(
        ForeignKey("actors.id", ondelete="CASCADE"), index=True
    )
    post_id: Mapped[str | None] = mapped_column(
        ForeignKey("posts.id", ondelete="SET NULL")
    )
    source_url: Mapped[str] = mapped_column(Text)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    screenshot_path: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    previous_record_hash: Mapped[str | None] = mapped_column(String(64))
    record_hash: Mapped[str] = mapped_column(String(64))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class SystemState(Base):
    __tablename__ = "system_state"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(255))
