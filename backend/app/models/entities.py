from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid4())


location_sources = Table(
    "location_sources",
    Base.metadata,
    Column("location_id", ForeignKey("locations.id", ondelete="CASCADE"), primary_key=True),
    Column("source_id", ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True),
)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class Campus(Base, TimestampMixin):
    __tablename__ = "campuses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    address: Mapped[str] = mapped_column(String(255), default="")
    data_notice: Mapped[str] = mapped_column(Text, default="数据待完善")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class CampusMap(Base, TimestampMixin):
    __tablename__ = "campus_maps"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    campus_id: Mapped[str] = mapped_column(ForeignKey("campuses.id", ondelete="CASCADE"), index=True)
    image_url: Mapped[str] = mapped_column(String(500), default="")
    version: Mapped[str] = mapped_column(String(64), default="")
    license_note: Mapped[str] = mapped_column(Text, default="待核验")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class User(Base, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="uq_users_email"), UniqueConstraint("username", name="uq_users_username"))

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), index=True)
    username: Mapped[str] = mapped_column(String(50), index=True)
    nickname: Mapped[str] = mapped_column(String(80), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="user", index=True)
    campus_id: Mapped[str | None] = mapped_column(ForeignKey("campuses.id", ondelete="SET NULL"), nullable=True)
    grade: Mapped[str] = mapped_column(String(32), default="")
    major: Mapped[str] = mapped_column(String(100), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    campus: Mapped[Campus | None] = relationship()


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    jti: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Source(Base, TimestampMixin):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(String(1000), default="")
    publisher: Mapped[str] = mapped_column(String(255), default="")
    source_type: Mapped[str] = mapped_column(String(40), default="unverified")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    is_official: Mapped[bool] = mapped_column(Boolean, default=False)
    content_hash: Mapped[str] = mapped_column(String(64), default="")


class Location(Base, TimestampMixin):
    __tablename__ = "locations"
    __table_args__ = (Index("ix_locations_campus_category_active", "campus_id", "category", "is_active"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    campus_id: Mapped[str] = mapped_column(ForeignKey("campuses.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120), index=True)
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)
    category: Mapped[str] = mapped_column(String(50), index=True)
    sub_category: Mapped[str] = mapped_column(String(50), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    address: Mapped[str] = mapped_column(String(500), default="")
    area: Mapped[str] = mapped_column(String(255), default="")
    floor: Mapped[str] = mapped_column(String(100), default="")
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    map_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    map_y: Mapped[float | None] = mapped_column(Float, nullable=True)
    opening_hours: Mapped[str] = mapped_column(String(255), default="")
    phone: Mapped[str] = mapped_column(String(80), default="")
    services: Mapped[list[str]] = mapped_column(JSON, default=list)
    payment_methods: Mapped[list[str]] = mapped_column(JSON, default=list)
    verification_status: Mapped[str] = mapped_column(String(40), default="needs_verification", index=True)
    verification_method: Mapped[str] = mapped_column(String(80), default="unverified_seed")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_by: Mapped[str] = mapped_column(String(100), default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    freshness_status: Mapped[str] = mapped_column(String(40), default="needs_verification")
    data_status: Mapped[str] = mapped_column(String(40), default="demo_fixture")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    campus: Mapped[Campus] = relationship()
    sources: Mapped[list[Source]] = relationship(secondary=location_sources)


class Canteen(Base, TimestampMixin):
    __tablename__ = "canteens"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    campus_id: Mapped[str] = mapped_column(ForeignKey("campuses.id", ondelete="CASCADE"), index=True)
    location_id: Mapped[str | None] = mapped_column(ForeignKey("locations.id", ondelete="SET NULL"), nullable=True)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    floors: Mapped[list[str]] = mapped_column(JSON, default=list)
    opening_hours: Mapped[str] = mapped_column(String(255), default="")
    payment_methods: Mapped[list[str]] = mapped_column(JSON, default=list)
    verification_status: Mapped[str] = mapped_column(String(40), default="needs_verification")
    data_status: Mapped[str] = mapped_column(String(40), default="needs_verification", index=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    campus: Mapped[Campus] = relationship()
    location: Mapped[Location | None] = relationship()
    source: Mapped[Source | None] = relationship()
    stalls: Mapped[list[FoodStall]] = relationship(back_populates="canteen", cascade="all, delete-orphan")


class FoodStall(Base, TimestampMixin):
    __tablename__ = "food_stalls"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    canteen_id: Mapped[str] = mapped_column(ForeignKey("canteens.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    floor: Mapped[str] = mapped_column(String(80), default="")
    food_type: Mapped[str] = mapped_column(String(120), default="")
    common_items: Mapped[list[str]] = mapped_column(JSON, default=list)
    price_range: Mapped[str] = mapped_column(String(80), default="")
    meal_periods: Mapped[list[str]] = mapped_column(JSON, default=list)
    opening_hours: Mapped[str] = mapped_column(String(255), default="")
    payment_methods: Mapped[list[str]] = mapped_column(JSON, default=list)
    is_operating: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    verification_status: Mapped[str] = mapped_column(String(40), default="needs_verification")
    data_status: Mapped[str] = mapped_column(String(40), default="needs_verification", index=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    canteen: Mapped[Canteen] = relationship(back_populates="stalls")


class CampusProcess(Base, TimestampMixin):
    __tablename__ = "campus_processes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    campus_id: Mapped[str | None] = mapped_column(ForeignKey("campuses.id", ondelete="SET NULL"), nullable=True)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(180), index=True)
    category: Mapped[str] = mapped_column(String(80), default="other")
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    materials: Mapped[list[str]] = mapped_column(JSON, default=list)
    contact: Mapped[str] = mapped_column(String(255), default="")
    verification_status: Mapped[str] = mapped_column(String(40), default="needs_verification")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[Source | None] = relationship()


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"
    __table_args__ = (Index("ix_tasks_owner_status_deadline", "user_id", "status", "deadline"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text, default="")
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    location: Mapped[str] = mapped_column(String(255), default="")
    course: Mapped[str] = mapped_column(String(120), default="")
    task_type: Mapped[str] = mapped_column(String(80), default="general")
    materials: Mapped[list[str]] = mapped_column(JSON, default=list)
    submission_target: Mapped[str] = mapped_column(String(255), default="")
    submission_method: Mapped[str] = mapped_column(String(255), default="")
    file_naming: Mapped[str] = mapped_column(String(255), default="")
    source_text: Mapped[str] = mapped_column(Text, default="")
    source_url: Mapped[str] = mapped_column(String(1000), default="")
    status: Mapped[str] = mapped_column(String(30), default="pending")
    needs_confirmation: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reminders: Mapped[list[TaskReminder]] = relationship(back_populates="task", cascade="all, delete-orphan")


class TaskReminder(Base):
    __tablename__ = "task_reminders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    minutes_before: Mapped[int] = mapped_column(Integer)
    channel: Mapped[str] = mapped_column(String(30), default="ics")
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    task: Mapped[Task] = relationship(back_populates="reminders")


class Conversation(Base, TimestampMixin):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(180), default="新对话")
    campus_id: Mapped[str | None] = mapped_column(ForeignKey("campuses.id", ondelete="SET NULL"), nullable=True)
    messages: Mapped[list[Message]] = relationship(back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    intent: Mapped[str] = mapped_column(String(80), default="general_chat")
    tool_results: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class FeedbackSubmission(Base, TimestampMixin):
    __tablename__ = "feedback_submissions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    location_id: Mapped[str | None] = mapped_column(ForeignKey("locations.id", ondelete="SET NULL"), nullable=True)
    campus_id: Mapped[str] = mapped_column(ForeignKey("campuses.id", ondelete="CASCADE"))
    content: Mapped[str] = mapped_column(Text)
    evidence_url: Mapped[str] = mapped_column(String(1000), default="")
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str] = mapped_column(Text, default="")


class VerificationRecord(Base):
    __tablename__ = "verification_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    entity_type: Mapped[str] = mapped_column(String(50), index=True)
    entity_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(30))
    method: Mapped[str] = mapped_column(String(100), default="admin_review")
    evidence: Mapped[str] = mapped_column(Text, default="")
    note: Mapped[str] = mapped_column(Text, default="")
    verified_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    admin_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str] = mapped_column(String(50), default="")
    entity_id: Mapped[str] = mapped_column(String(64), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class DataRefreshLog(Base):
    __tablename__ = "data_refresh_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    changed: Mapped[bool] = mapped_column(Boolean, default=False)
    message: Mapped[str] = mapped_column(Text, default="")
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SystemLog(Base):
    __tablename__ = "system_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    level: Mapped[str] = mapped_column(String(20), index=True)
    event: Mapped[str] = mapped_column(String(120), index=True)
    message: Mapped[str] = mapped_column(Text)
    request_id: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
