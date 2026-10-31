"""PostgreSQL schema, one class per table in docs/05_DATA_MODEL_POSTGRES.md."""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _id() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _now() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class EvidenceBundle(Base):
    __tablename__ = "evidence_bundle"
    id: Mapped[uuid.UUID] = _id()
    project_key: Mapped[str] = mapped_column(Text, nullable=False)
    schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    source_inventory: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    coverage_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    coverage_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    import_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = _now()

    items: Mapped[list["EvidenceItem"]] = relationship(back_populates="bundle")


class EvidenceItem(Base):
    __tablename__ = "evidence_item"
    __table_args__ = (
        UniqueConstraint("bundle_id", "source", "external_id"),
        Index("idx_evidence_item_bundle_source_time", "bundle_id", "source", "occurred_at"),
    )
    id: Mapped[uuid.UUID] = _id()
    bundle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evidence_bundle.id"), nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    parent_external_id: Mapped[str | None] = mapped_column(Text)
    author_id: Mapped[str | None] = mapped_column(Text)
    author_display_name: Mapped[str | None] = mapped_column(Text)
    participants: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    title: Mapped[str | None] = mapped_column(Text)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    payload_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _now()

    bundle: Mapped[EvidenceBundle] = relationship(back_populates="items")
    chunks: Mapped[list["EvidenceChunk"]] = relationship(
        back_populates="item", order_by="EvidenceChunk.ordinal"
    )


class EvidenceChunk(Base):
    __tablename__ = "evidence_chunk"
    __table_args__ = (UniqueConstraint("evidence_item_id", "ordinal"),)
    id: Mapped[uuid.UUID] = _id()
    evidence_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evidence_item.id"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    line_start: Mapped[int | None] = mapped_column(Integer)
    line_end: Mapped[int | None] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    text_hash: Mapped[str] = mapped_column(Text, nullable=False)

    item: Mapped[EvidenceItem] = relationship(back_populates="chunks")


class Handoff(Base):
    __tablename__ = "handoff"
    __table_args__ = (
        CheckConstraint("status in ('unassigned','selecting','active')", name="ck_handoff_status"),
        CheckConstraint(
            "status in ('unassigned','selecting') or successor_id is not null",
            name="ck_handoff_successor_when_active",
        ),
        CheckConstraint("max_attempts >= 1", name="ck_handoff_max_attempts"),
    )
    id: Mapped[uuid.UUID] = _id()
    project_key: Mapped[str] = mapped_column(Text, nullable=False)
    bundle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evidence_bundle.id"), nullable=False)
    expert_id: Mapped[str] = mapped_column(Text, nullable=False)
    # Null while 'unassigned' or 'selecting'; set by direct assignment or the admin's selection.
    successor_id: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    max_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=2, server_default="2"
    )
    # Common assessment: the one released exercise every candidate answers, and its due time.
    # use_alter breaks the handoff -> exercise -> ... -> handoff foreign-key cycle.
    assessment_exercise_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("exercise.id", use_alter=True)
    )
    assessment_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    assessment_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _now()

    candidates: Mapped[list["HandoffCandidate"]] = relationship(
        order_by="HandoffCandidate.alias", viewonly=True
    )

    def candidate(self, person_id: str | None) -> "HandoffCandidate | None":
        """The candidate row for `person_id` while the successor is still being selected."""
        if self.status != "selecting" or not person_id:
            return None
        return next((c for c in self.candidates if c.person_id == person_id), None)


class HandoffCandidate(Base):
    __tablename__ = "handoff_candidate"
    __table_args__ = (
        UniqueConstraint("handoff_id", "person_id"),
        UniqueConstraint("handoff_id", "alias"),
    )
    id: Mapped[uuid.UUID] = _id()
    handoff_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("handoff.id"), nullable=False)
    person_id: Mapped[str] = mapped_column(Text, nullable=False)
    # "Candidate A".."Candidate D": what the expert sees while selecting.
    alias: Mapped[str] = mapped_column(Text, nullable=False)
    study_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SuccessorSelection(Base):
    """Immutable. The admin's decision with the recommendation it was made against."""

    __tablename__ = "successor_selection"
    id: Mapped[uuid.UUID] = _id()
    handoff_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("handoff.id"), nullable=False, unique=True
    )
    selected_person_id: Mapped[str] = mapped_column(Text, nullable=False)
    recommended: Mapped[list] = mapped_column(JSONB, nullable=False)
    in_recommended: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # Score-based top at decision time (phase 2). Null on rows decided before it existed.
    top_ids: Mapped[list | None] = mapped_column(JSONB)
    tie: Mapped[bool | None] = mapped_column(Boolean)
    is_top: Mapped[bool | None] = mapped_column(Boolean)
    reason: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[str] = mapped_column(Text, nullable=False)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Analysis(Base):
    __tablename__ = "analysis"
    __table_args__ = (
        Index("idx_analysis_handoff_created", "handoff_id", "created_at"),
        CheckConstraint("status in ('pending','running','succeeded','failed')"),
    )
    id: Mapped[uuid.UUID] = _id()
    handoff_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("handoff.id"), nullable=False)
    bundle_hash: Mapped[str] = mapped_column(Text, nullable=False)
    selected_engineer_id: Mapped[str] = mapped_column(Text, nullable=False)
    model_id: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    scoring_version: Mapped[str] = mapped_column(Text, nullable=False)
    extraction: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    created_at: Mapped[datetime] = _now()

    findings: Mapped[list["Finding"]] = relationship(back_populates="analysis")


class Finding(Base):
    __tablename__ = "finding"
    __table_args__ = (
        CheckConstraint("status in ('candidate','confirmed','rejected','obsolete')"),
        CheckConstraint(
            "eligibility_status in "
            "('ranked','adequately_covered','not_prioritized','insufficient','review_required')"
        ),
        CheckConstraint("evidence_confidence in ('high','medium','low')"),
        CheckConstraint("review_priority is null or review_priority between 0 and 100"),
    )
    id: Mapped[uuid.UUID] = _id()
    analysis_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analysis.id"), nullable=False)
    area_key: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    question: Mapped[str | None] = mapped_column(Text)
    signal_values: Mapped[dict] = mapped_column(JSONB, nullable=False)
    review_priority: Mapped[int | None] = mapped_column(SmallInteger)
    evidence_confidence: Mapped[str] = mapped_column(Text, nullable=False)
    eligibility_status: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="candidate")
    status_reason: Mapped[str | None] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    evidence_refs: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    analysis: Mapped[Analysis] = relationship(back_populates="findings")


Index(
    "idx_finding_analysis_priority",
    Finding.analysis_id,
    Finding.eligibility_status,
    Finding.review_priority.desc().nulls_last(),
)


class KnowledgeDraft(Base):
    __tablename__ = "knowledge_draft"
    __table_args__ = (UniqueConstraint("finding_id"),)
    id: Mapped[uuid.UUID] = _id()
    finding_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("finding.id"), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    author_id: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class KnowledgeVersion(Base):
    """Immutable. Rows are inserted, never updated (enforced by a trigger in the migration)."""

    __tablename__ = "knowledge_version"
    __table_args__ = (
        UniqueConstraint("finding_id", "version_no"),
        Index("idx_knowledge_version_finding_version", "finding_id", "version_no"),
    )
    id: Mapped[uuid.UUID] = _id()
    finding_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("finding.id"), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    draft_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    approved_content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    source_refs: Mapped[list] = mapped_column(JSONB, nullable=False)
    expert_added_context: Mapped[bool] = mapped_column(Boolean, nullable=False)
    approved_by: Mapped[str] = mapped_column(Text, nullable=False)
    approved_at: Mapped[datetime] = _now()
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    supersedes_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("knowledge_version.id")
    )


class Exercise(Base):
    __tablename__ = "exercise"
    __table_args__ = (CheckConstraint("status in ('draft','ready','obsolete')"),)
    id: Mapped[uuid.UUID] = _id()
    knowledge_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_version.id"), nullable=False
    )
    scenario: Mapped[str] = mapped_column(Text, nullable=False)
    rubric: Mapped[list] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="draft")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    approved_by: Mapped[str | None] = mapped_column(Text)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    generator_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _now()


class Attempt(Base):
    __tablename__ = "attempt"
    __table_args__ = (
        Index("idx_attempt_exercise_created", "exercise_id", "created_at"),
        CheckConstraint("assessment_status in ('pending','succeeded','failed')"),
        CheckConstraint(
            "aggregate_result is null or aggregate_result in "
            "('demonstrated','partial','not_yet','review_required')"
        ),
        CheckConstraint(
            "(assessment_status = 'succeeded') = (aggregate_result is not null)",
            name="ck_attempt_result_only_when_succeeded",
        ),
    )
    id: Mapped[uuid.UUID] = _id()
    exercise_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("exercise.id"), nullable=False)
    successor_id: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    assessment_status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    criterion_results: Mapped[list | None] = mapped_column(JSONB)
    aggregate_result: Mapped[str | None] = mapped_column(Text)
    assessor_id: Mapped[str | None] = mapped_column(Text)
    assessment_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _now()
    assessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AttemptReview(Base):
    """A learner's review request; the expert fills overrides, reason and reviewer once.
    The attempt row is never changed: the effective result is derived from both."""

    __tablename__ = "attempt_review"
    id: Mapped[uuid.UUID] = _id()
    attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("attempt.id"), nullable=False, unique=True
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    overrides: Mapped[dict | None] = mapped_column(JSONB)
    reason: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Operation(Base):
    __tablename__ = "operation"
    __table_args__ = (
        UniqueConstraint("kind", "idempotency_key"),
        Index("idx_operation_state_created", "state", "created_at"),
        CheckConstraint("state in ('pending','running','succeeded','failed','interrupted')"),
    )
    id: Mapped[uuid.UUID] = _id()
    handoff_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("handoff.id"))
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    request_hash: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    result_type: Mapped[str | None] = mapped_column(Text)
    result_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    error_code: Mapped[str | None] = mapped_column(Text)
    error_detail: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _now()


class AuditEvent(Base):
    __tablename__ = "audit_event"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    handoff_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("handoff.id"))
    actor_id: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    target_revision: Mapped[int | None] = mapped_column(Integer)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = _now()


class AppUser(Base):
    """Login identity. Survives demo reset. Only an argon2 hash of the password is stored."""

    __tablename__ = "app_user"
    __table_args__ = (
        CheckConstraint("role in ('admin','member')", name="ck_app_user_role"),
        Index(
            "uq_app_user_person_id",
            "person_id",
            unique=True,
            postgresql_where=text("person_id is not null"),
        ),
    )
    id: Mapped[uuid.UUID] = _id()
    username: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    display_name: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    # Evidence actor ID this account speaks for (e.g. "alice"); null for admins.
    person_id: Mapped[str | None] = mapped_column(Text)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = _now()
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserSession(Base):
    """Server-side session. Stores a SHA-256 hash of the cookie token, never the token."""

    __tablename__ = "user_session"
    __table_args__ = (Index("idx_user_session_user", "user_id"),)
    id: Mapped[uuid.UUID] = _id()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    created_at: Mapped[datetime] = _now()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
