"""Verify endpoints (docs/03 'API shape'). The signed-in account decides the view:
the handoff's expert and admins see the rubric; the successor sees released exercises and
their own attempts only. Admins read everything but never author or answer exercises.
"""

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import serializers as S
from app.api.routes import _get
from app.auth.deps import current_user, handoff_role, require_handoff_role
from app.db import tx
from app.errors import AppError
from app.models import AppUser, Attempt, Exercise, Handoff, KnowledgeVersion, Operation
from app.operations import run_idempotent
from app.verify import selection as Sel
from app.verify import service as V
from app.verify.contract import Criterion, ExerciseDraft

router = APIRouter(prefix="/api", dependencies=[Depends(current_user)])


def _attempts(session: Session, exercise: Exercise, viewer_role: str, viewer: AppUser) -> list:
    stmt = select(Attempt).where(Attempt.exercise_id == exercise.id)
    if viewer_role == "successor":
        stmt = stmt.where(Attempt.successor_id == viewer.person_id)
    return list(session.scalars(stmt.order_by(Attempt.created_at)).all())


def _attempt_extras(
    session: Session, attempt: Attempt, exercise: Exercise, handoff: Handoff, viewer_role: str
) -> dict:
    """Review, effective result and, for the expert of a selecting handoff, the alias that
    stands in for the learner's identity."""
    review = Sel.review_of(session, attempt)
    label = None
    if viewer_role == "expert" and handoff.status == "selecting":
        c = next(c for c in handoff.candidates if c.person_id == attempt.successor_id)
        label = c.alias
    return {
        "label": label,
        "review": review,
        "effective_result": Sel.effective_result(attempt, exercise, review),
        "score_pct": Sel.effective_score(attempt, exercise, review),
    }


def _exercise_view(session: Session, exercise: Exercise, user: AppUser) -> dict:
    version, _, handoff = V.exercise_context(session, exercise)
    r = handoff_role(user, handoff)
    if r == "successor" and exercise.status != "ready":
        raise AppError(403, "not_released", "this exercise has not been released yet")
    attempts = _attempts(session, exercise, r, user)
    extras = {a.id: _attempt_extras(session, a, exercise, handoff, r) for a in attempts}
    candidate = Sel.candidate_view(session, handoff, exercise, user.person_id)
    return S.exercise_out(exercise, version, r, attempts, extras, candidate)


def _attempt_view(session: Session, attempt: Attempt, user: AppUser) -> dict:
    exercise = session.get(Exercise, attempt.exercise_id)
    version, _, handoff = V.exercise_context(session, exercise)
    r = handoff_role(user, handoff)
    if r == "successor" and attempt.successor_id != user.person_id:
        raise AppError(403, "not_owner", "this attempt belongs to someone else")
    return S.attempt_out(
        attempt, exercise, version, r, **_attempt_extras(session, attempt, exercise, handoff, r)
    )


@router.post("/knowledge/{version_id}/exercises", status_code=201)
def create_exercise(
    version_id: str,
    session: Session = Depends(tx),
    user: AppUser = Depends(current_user),
    idempotency_key: str | None = Header(default=None),
) -> dict:
    v = _get(session, KnowledgeVersion, version_id, "knowledge version")
    require_handoff_role(user, V.version_context(session, v)[1], "expert")
    eid, _ = run_idempotent(
        session,
        "generate_exercise",
        idempotency_key,
        {"version": version_id, "actor": user.person_id},
        None,
        "exercise",
        lambda: V.create_exercise(session, v, user.person_id).id,
    )
    return _exercise_view(session, session.get(Exercise, eid), user)


@router.get("/knowledge/{version_id}/exercises")
def list_exercises(
    version_id: str, session: Session = Depends(tx), user: AppUser = Depends(current_user)
) -> list[dict]:
    v = _get(session, KnowledgeVersion, version_id, "knowledge version")
    _, handoff = V.version_context(session, v)
    r = handoff_role(user, handoff)
    stmt = select(Exercise).where(Exercise.knowledge_version_id == v.id)
    if r == "successor":
        stmt = stmt.where(Exercise.status == "ready")
    rows = session.scalars(stmt.order_by(Exercise.created_at)).all()
    return [_exercise_view(session, e, user) for e in rows]


def _expert_exercise(session: Session, exercise_id: str, user: AppUser) -> Exercise:
    e = _get(session, Exercise, exercise_id, "exercise")
    require_handoff_role(user, V.exercise_context(session, e)[2], "expert")
    return e


class ExerciseDraftIn(BaseModel):
    scenario: str
    criteria: list[Criterion]
    expected_revision: int


@router.put("/exercises/{exercise_id}/draft")
def put_exercise_draft(
    exercise_id: str,
    body: ExerciseDraftIn,
    session: Session = Depends(tx),
    user: AppUser = Depends(current_user),
) -> dict:
    e = _expert_exercise(session, exercise_id, user)
    draft = ExerciseDraft(scenario=body.scenario, criteria=body.criteria)
    V.save_exercise_draft(session, e, draft, body.expected_revision, user.person_id)
    return _exercise_view(session, e, user)


class ApproveIn(BaseModel):
    expected_revision: int


@router.post("/exercises/{exercise_id}/approve")
def approve_exercise(
    exercise_id: str,
    body: ApproveIn,
    session: Session = Depends(tx),
    user: AppUser = Depends(current_user),
) -> dict:
    e = _expert_exercise(session, exercise_id, user)
    V.approve_exercise(session, e, body.expected_revision, user.person_id)
    return _exercise_view(session, e, user)


@router.get("/exercises/{exercise_id}")
def get_exercise(
    exercise_id: str, session: Session = Depends(tx), user: AppUser = Depends(current_user)
) -> dict:
    return _exercise_view(session, _get(session, Exercise, exercise_id, "exercise"), user)


class AttemptIn(BaseModel):
    answer: str


@router.post("/exercises/{exercise_id}/attempts", status_code=201)
def submit_attempt(
    exercise_id: str,
    body: AttemptIn,
    session: Session = Depends(tx),
    user: AppUser = Depends(current_user),
    idempotency_key: str | None = Header(default=None),
) -> dict:
    e = _get(session, Exercise, exercise_id, "exercise")
    require_handoff_role(user, V.exercise_context(session, e)[2], "successor")
    attempt, _ = V.submit_attempt(session, e, body.answer, user.person_id, idempotency_key)
    return _attempt_view(session, attempt, user)


@router.get("/attempts/{attempt_id}")
def get_attempt(
    attempt_id: str, session: Session = Depends(tx), user: AppUser = Depends(current_user)
) -> dict:
    return _attempt_view(session, _get(session, Attempt, attempt_id, "attempt"), user)


@router.post("/attempts/{attempt_id}/reassess")
def reassess(
    attempt_id: str, session: Session = Depends(tx), user: AppUser = Depends(current_user)
) -> dict:
    a = _get(session, Attempt, attempt_id, "attempt")
    handoff = V.exercise_context(session, session.get(Exercise, a.exercise_id))[2]
    r = require_handoff_role(user, handoff, "expert", "successor")
    if r == "successor" and a.successor_id != user.person_id:
        raise AppError(403, "not_owner", "this attempt belongs to someone else")
    V.reassess_attempt(session, a, user.person_id)
    return _attempt_view(session, a, user)


@router.get("/operations/{operation_id}")
def get_operation(
    operation_id: str, session: Session = Depends(tx), user: AppUser = Depends(current_user)
) -> dict:
    op = _get(session, Operation, operation_id, "operation")
    if op.handoff_id is not None:
        handoff_role(user, session.get(Handoff, op.handoff_id))
    return S.operation_out(op)


@router.post("/attempts/{attempt_id}/review-request", status_code=201)
def request_review(
    attempt_id: str, session: Session = Depends(tx), user: AppUser = Depends(current_user)
) -> dict:
    """The learner who made an assessed attempt asks the expert to review it, once."""
    a = _get(session, Attempt, attempt_id, "attempt")
    handoff = V.exercise_context(session, session.get(Exercise, a.exercise_id))[2]
    require_handoff_role(user, handoff, "successor")
    Sel.request_review(session, a, handoff, user.person_id)
    return _attempt_view(session, a, user)


class AttemptReviewIn(BaseModel):
    overrides: dict[str, str]  # checked in Sel.review_attempt: met, partial or unmet
    reason: str = ""


@router.post("/attempts/{attempt_id}/review")
def review_attempt(
    attempt_id: str,
    body: AttemptReviewIn,
    session: Session = Depends(tx),
    user: AppUser = Depends(current_user),
) -> dict:
    """The expert overrides criterion verdicts with a reason. The attempt is not changed;
    its effective result is recomputed by aggregate()."""
    a = _get(session, Attempt, attempt_id, "attempt")
    exercise = session.get(Exercise, a.exercise_id)
    handoff = V.exercise_context(session, exercise)[2]
    require_handoff_role(user, handoff, "expert")
    Sel.review_attempt(session, a, exercise, handoff, body.overrides, body.reason, user.person_id)
    return _attempt_view(session, a, user)
