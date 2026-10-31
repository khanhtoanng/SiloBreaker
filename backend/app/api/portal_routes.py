"""Signed-in overviews: my exercises and the approved-knowledge library."""

from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.auth.deps import current_user, handoff_role
from app.db import tx
from app.knowledge.service import library_versions
from app.models import (
    Analysis,
    AppUser,
    Attempt,
    Exercise,
    Finding,
    Handoff,
    HandoffCandidate,
    KnowledgeVersion,
)

router = APIRouter(prefix="/api", dependencies=[Depends(current_user)])


@router.get("/me/exercises")
def my_exercises(session: Session = Depends(tx), user: AppUser = Depends(current_user)) -> list:
    """Exercises in handoffs I take part in. As successor (or candidate of a selecting
    handoff) I see released ones only, and only my own attempts; the rubric is never part of
    this list."""
    if not user.person_id:
        return []
    candidate_of = select(HandoffCandidate.handoff_id).where(
        HandoffCandidate.person_id == user.person_id
    )
    rows = session.execute(
        select(Exercise, KnowledgeVersion, Finding, Handoff)
        .join(KnowledgeVersion, Exercise.knowledge_version_id == KnowledgeVersion.id)
        .join(Finding, KnowledgeVersion.finding_id == Finding.id)
        .join(Analysis, Finding.analysis_id == Analysis.id)
        .join(Handoff, Analysis.handoff_id == Handoff.id)
        .where(
            or_(
                Handoff.expert_id == user.person_id,
                Handoff.successor_id == user.person_id,
                (Handoff.status == "selecting") & Handoff.id.in_(candidate_of),
            )
        )
        .order_by(Exercise.created_at.desc())
    ).all()
    out = []
    for e, v, f, h in rows:
        r = handoff_role(user, h)
        if r == "successor" and e.status != "ready":
            continue
        attempts = select(Attempt).where(Attempt.exercise_id == e.id)
        if r == "successor":
            attempts = attempts.where(Attempt.successor_id == user.person_id)
        latest = session.scalar(attempts.order_by(Attempt.created_at.desc()).limit(1))
        out.append(
            {
                "id": str(e.id),
                "status": e.status,
                "viewer_role": r,
                "handoff_id": str(h.id),
                "project_key": h.project_key,
                "finding_id": str(f.id),
                "area_key": f.area_key,
                "title": f.title,
                "knowledge_version_id": str(v.id),
                "knowledge_version_no": v.version_no,
                "approved_at": e.approved_at,
                "latest_attempt": None
                if latest is None
                else {
                    "id": str(latest.id),
                    "assessment_status": latest.assessment_status,
                    "aggregate_result": latest.aggregate_result,
                    "created_at": latest.created_at,
                },
            }
        )
    return out


@router.get("/library")
def library(session: Session = Depends(tx)) -> list:
    """The newest approved version of every confirmed finding. Readable by everyone signed in;
    obsolete (retired) knowledge is left out."""
    return [
        {
            "version_id": str(v.id),
            "version_no": v.version_no,
            "finding_id": str(f.id),
            "area_key": f.area_key,
            "title": f.title,
            "project_key": h.project_key,
            "handoff_id": str(h.id),
            "approved_by": v.approved_by,
            "approved_at": v.approved_at,
        }
        for v, f, h in library_versions(session)
    ]
