"""Capture flow: review, draft, explicit approval, immutable versions (FR-12 to FR-15)."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit import audit
from app.errors import AppError
from app.evidence.contract import sha256_json
from app.knowledge.content import KnowledgeContent
from app.models import Analysis, Finding, Handoff, KnowledgeDraft, KnowledgeVersion

REVIEW_TRANSITIONS = {
    "confirm": "confirmed",
    "correct": "confirmed",
    "reject": "rejected",
    "obsolete": "obsolete",
}


def _handoff_for(session: Session, finding: Finding) -> Handoff:
    analysis = session.get(Analysis, finding.analysis_id)
    handoff = session.get(Handoff, analysis.handoff_id) if analysis else None
    if handoff is None:
        raise AppError(404, "not_found", "handoff not found")
    return handoff


def get_finding(session: Session, finding_id: uuid.UUID, lock: bool = False) -> Finding:
    stmt = select(Finding).where(Finding.id == finding_id)
    if lock:
        stmt = stmt.with_for_update()
    finding = session.scalar(stmt)
    if finding is None:
        raise AppError(404, "not_found", "finding not found")
    return finding


def _require_expert(handoff: Handoff, actor: str) -> None:
    if actor != handoff.expert_id:
        raise AppError(403, "not_expert", "only the handoff's experienced engineer may do this")


def review_finding(
    session: Session,
    finding_id: uuid.UUID,
    action: str,
    reason: str,
    expected_revision: int,
    actor: str,
    corrected_summary: str | None = None,
) -> Finding:
    if action not in REVIEW_TRANSITIONS:
        raise AppError(422, "invalid_action", f"action must be one of {sorted(REVIEW_TRANSITIONS)}")
    finding = get_finding(session, finding_id, lock=True)
    handoff = _handoff_for(session, finding)
    _require_expert(handoff, actor)
    if finding.revision != expected_revision:
        raise AppError(
            409,
            "stale_revision",
            f"finding is at revision {finding.revision}, not {expected_revision}",
        )
    if finding.status in ("rejected", "obsolete"):
        raise AppError(409, "invalid_transition", f"finding is already {finding.status}")
    if action in ("reject", "obsolete", "correct") and not reason.strip():
        raise AppError(422, "reason_required", f"a reason is required to {action}")
    published = session.scalar(
        select(func.count()).where(KnowledgeVersion.finding_id == finding.id)
    )
    if action == "reject" and published:
        raise AppError(
            409,
            "invalid_transition",
            "this finding already has approved knowledge; mark it obsolete instead of rejecting",
        )
    metadata: dict = {"reason": reason}
    if action == "obsolete" and published:
        metadata["retired_versions"] = published  # every version now exports as retired
    finding.status = REVIEW_TRANSITIONS[action]
    finding.status_reason = reason.strip() or None
    if action == "correct" and corrected_summary:
        finding.summary = corrected_summary.strip()
    finding.revision += 1
    audit(
        session,
        handoff.id,
        actor,
        f"finding.{action}",
        "finding",
        finding.id,
        finding.revision,
        metadata,
    )
    session.flush()
    return finding


def get_draft(session: Session, finding_id: uuid.UUID) -> KnowledgeDraft | None:
    return session.scalar(select(KnowledgeDraft).where(KnowledgeDraft.finding_id == finding_id))


def save_draft(
    session: Session,
    finding_id: uuid.UUID,
    content: KnowledgeContent,
    expected_revision: int | None,
    author: str,
) -> KnowledgeDraft:
    """Saving never publishes (FR-14)."""
    finding = get_finding(session, finding_id, lock=True)
    handoff = _handoff_for(session, finding)
    _require_expert(handoff, author)
    if finding.status != "confirmed":
        raise AppError(409, "invalid_transition", "confirm or correct the finding before capture")
    draft = get_draft(session, finding_id)
    if draft is None:
        if expected_revision not in (None, 0):
            raise AppError(409, "stale_revision", "no draft exists yet")
        draft = KnowledgeDraft(
            finding_id=finding_id, revision=1, content=content.model_dump(), author_id=author
        )
        session.add(draft)
    else:
        if expected_revision != draft.revision:
            raise AppError(
                409,
                "stale_revision",
                f"draft is at revision {draft.revision}, not {expected_revision}",
            )
        draft.content = content.model_dump()
        draft.author_id = author
        draft.revision += 1
    session.flush()
    audit(
        session,
        handoff.id,
        author,
        "knowledge.draft_saved",
        "knowledge_draft",
        draft.id,
        draft.revision,
    )
    return draft


def publish(
    session: Session,
    finding_id: uuid.UUID,
    expected_finding_revision: int,
    draft_revision: int,
    approver: str,
) -> KnowledgeVersion:
    finding = get_finding(session, finding_id, lock=True)
    handoff = _handoff_for(session, finding)
    _require_expert(handoff, approver)
    if finding.status != "confirmed":
        raise AppError(409, "invalid_transition", f"cannot publish a {finding.status} finding")
    if finding.revision != expected_finding_revision:
        raise AppError(
            409,
            "stale_revision",
            f"finding is at revision {finding.revision}, not {expected_finding_revision}",
        )
    draft = get_draft(session, finding_id)
    if draft is None or draft.revision != draft_revision:
        raise AppError(409, "stale_revision", "approval must name the current draft revision")
    content = KnowledgeContent.model_validate(draft.content)  # re-validate at the boundary
    previous = session.scalar(
        select(KnowledgeVersion)
        .where(KnowledgeVersion.finding_id == finding_id)
        .order_by(KnowledgeVersion.version_no.desc())
        .limit(1)
    )
    if previous is not None and previous.draft_revision == draft.revision:
        raise AppError(409, "already_published", "this draft revision is already published")
    version_no = (
        session.scalar(
            select(func.max(KnowledgeVersion.version_no)).where(
                KnowledgeVersion.finding_id == finding_id
            )
        )
        or 0
    ) + 1
    approved = content.model_dump()
    version = KnowledgeVersion(
        finding_id=finding_id,
        version_no=version_no,
        draft_revision=draft.revision,
        approved_content=approved,
        source_refs=finding.evidence_refs,
        expert_added_context=True,
        approved_by=approver,
        content_hash=sha256_json(approved),
        supersedes_version_id=previous.id if previous else None,
    )
    session.add(version)
    session.flush()
    audit(
        session,
        handoff.id,
        approver,
        "knowledge.approved",
        "knowledge_version",
        version.id,
        version_no,
        {"draft_revision": draft.revision},
    )
    return version


def prior_knowledge(session: Session, finding: Finding) -> dict | None:
    """Latest approved version for the same area from an earlier finding of this handoff.

    A re-analysis creates new findings; this lets them point at knowledge that was already
    approved instead of asking the expert to start over. Obsolete or rejected findings
    never count. Computed by query, nothing is copied.
    """
    analysis = session.get(Analysis, finding.analysis_id)
    row = session.execute(
        select(KnowledgeVersion.id, KnowledgeVersion.version_no, Finding.id)
        .join(Finding, Finding.id == KnowledgeVersion.finding_id)
        .join(Analysis, Analysis.id == Finding.analysis_id)
        .where(
            Analysis.handoff_id == analysis.handoff_id,
            Finding.area_key == finding.area_key,
            Finding.id != finding.id,
            Finding.status == "confirmed",
        )
        .order_by(KnowledgeVersion.approved_at.desc(), KnowledgeVersion.version_no.desc())
        .limit(1)
    ).first()
    if row is None:
        return None
    return {"finding_id": str(row[2]), "version_id": str(row[0]), "version_no": row[1]}


def library_versions(session: Session) -> list[tuple[KnowledgeVersion, Finding, Handoff]]:
    """The newest approved version of every confirmed finding, newest approval first.

    This is the one rule for which approved knowledge a signed-in user may read: /library
    lists it and the help assistant answers from it. Obsolete (retired) knowledge is left out.
    """
    newest = (
        select(KnowledgeVersion.finding_id, func.max(KnowledgeVersion.version_no).label("n"))
        .group_by(KnowledgeVersion.finding_id)
        .subquery()
    )
    rows = session.execute(
        select(KnowledgeVersion, Finding, Handoff)
        .join(
            newest,
            (KnowledgeVersion.finding_id == newest.c.finding_id)
            & (KnowledgeVersion.version_no == newest.c.n),
        )
        .join(Finding, KnowledgeVersion.finding_id == Finding.id)
        .join(Analysis, Finding.analysis_id == Analysis.id)
        .join(Handoff, Analysis.handoff_id == Handoff.id)
        .where(Finding.status == "confirmed")
        .order_by(KnowledgeVersion.approved_at.desc())
    ).all()
    return [(v, f, h) for v, f, h in rows]
