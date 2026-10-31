"""Verify flow (docs/03 'Verify flow', FR-17 to FR-22).

1. Generate a draft from one approved, current knowledge version of a live finding.
2. Code checks every criterion maps to approved content.
3. The expert edits and releases it.
4. The successor's answer is committed before any assessment runs.
5. The assessor proposes criterion matches; code validates them and derives the result.
6. A provider failure leaves the attempt `failed` with no result; it can be reassessed.
   A retry by the learner is a new attempt.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.service import ai_limits, openai_client, require_openai
from app.audit import audit
from app.config import get_settings
from app.errors import AppError
from app.evidence.contract import sha256_json
from app.models import Analysis, Attempt, Exercise, Finding, Handoff, KnowledgeVersion, Operation
from app.verify.contract import (
    Assessor,
    Criterion,
    ExerciseDraft,
    ExerciseGenerator,
    validate_exercise,
    validate_matches,
)
from app.verify.offline import OfflineAssessor, OfflineGenerator
from app.verify.rules import aggregate
from app.verify.selection import check_can_attempt, check_can_reassess


def _openai_call():
    from app.analysis.openai_extractor import StructuredCall

    openai = require_openai()
    return StructuredCall(openai_client(openai), get_settings().openai_model, **ai_limits())


def get_generator() -> ExerciseGenerator:
    provider = get_settings().ai_provider
    if provider == "offline":
        return OfflineGenerator()
    if provider == "openai":
        from app.verify.openai_verify import OpenAIGenerator

        return OpenAIGenerator(_openai_call())
    raise AppError(503, "provider_not_configured", f"AI provider '{provider}' is not configured")


def get_assessor() -> Assessor:
    provider = get_settings().ai_provider
    if provider == "offline":
        return OfflineAssessor()
    if provider == "openai":
        from app.verify.openai_verify import OpenAIAssessor

        return OpenAIAssessor(_openai_call())
    raise AppError(503, "provider_not_configured", f"AI provider '{provider}' is not configured")


# ---------- context and roles ----------


def version_context(session: Session, version: KnowledgeVersion) -> tuple[Finding, Handoff]:
    finding = session.get(Finding, version.finding_id)
    analysis = session.get(Analysis, finding.analysis_id)
    return finding, session.get(Handoff, analysis.handoff_id)


def exercise_context(
    session: Session, exercise: Exercise
) -> tuple[KnowledgeVersion, Finding, Handoff]:
    version = session.get(KnowledgeVersion, exercise.knowledge_version_id)
    return version, *version_context(session, version)


def role(handoff: Handoff, viewer: str | None) -> str:
    """The viewer's role in this handoff. Anyone else sees nothing."""
    if viewer and viewer == handoff.expert_id:
        return "expert"
    if viewer and viewer == handoff.successor_id:
        return "successor"
    if handoff.candidate(viewer) is not None:
        return "successor"
    raise AppError(403, "not_participant", "viewer is not the expert or successor of this handoff")


def _require(handoff: Handoff, actor: str, wanted: str) -> None:
    if role(handoff, actor) != wanted:
        raise AppError(403, f"not_{wanted}", f"only the handoff's {wanted} may do this")


def require_live(session: Session, version: KnowledgeVersion, finding: Finding) -> None:
    if finding.status != "confirmed":
        raise AppError(
            409, "invalid_transition", f"knowledge of a {finding.status} finding cannot be tested"
        )
    newer = session.scalar(
        select(KnowledgeVersion.id).where(KnowledgeVersion.supersedes_version_id == version.id)
    )
    if newer is not None:
        raise AppError(
            409, "superseded_version", "a newer approved version exists; create exercises from it"
        )


def _check_revision(exercise: Exercise, expected: int) -> None:
    if exercise.revision != expected:
        raise AppError(
            409,
            "stale_revision",
            f"exercise is at revision {exercise.revision}, not {expected}",
        )


# ---------- exercise lifecycle ----------


def _store_draft(exercise: Exercise, draft: ExerciseDraft, content: dict, code: str) -> None:
    problems = validate_exercise(draft, content)
    if problems:
        status = 502 if code == "provider_error" else 422
        raise AppError(status, code, "; ".join(problems))
    exercise.scenario = draft.scenario.strip()
    exercise.rubric = [c.model_dump() for c in draft.criteria]


def create_exercise(
    session: Session,
    version: KnowledgeVersion,
    actor: str,
    generator: ExerciseGenerator | None = None,
) -> Exercise:
    finding, handoff = version_context(session, version)
    _require(handoff, actor, "expert")
    require_live(session, version, finding)
    generator = generator or get_generator()
    try:
        draft = generator.generate(finding.title, version.approved_content)
    except AppError:
        raise
    except Exception as exc:  # a generator failure is a system error
        raise AppError(502, "provider_error", f"exercise generation failed: {exc}") from exc
    exercise = Exercise(
        knowledge_version_id=version.id,
        status="draft",
        revision=1,
        generator_id=generator.model_id,
    )
    # A generated draft that is not grounded is the generator's fault (502), not the user's.
    code = "insufficient_content" if isinstance(generator, OfflineGenerator) else "provider_error"
    _store_draft(exercise, draft, version.approved_content, code)
    session.add(exercise)
    session.flush()
    audit(
        session,
        handoff.id,
        actor,
        "exercise.generated",
        "exercise",
        exercise.id,
        exercise.revision,
        {"generator": generator.model_id, "knowledge_version": str(version.id)},
    )
    return exercise


def save_exercise_draft(
    session: Session, exercise: Exercise, draft: ExerciseDraft, expected_revision: int, actor: str
) -> Exercise:
    version, _, handoff = exercise_context(session, exercise)
    _require(handoff, actor, "expert")
    _check_revision(exercise, expected_revision)
    if exercise.status != "draft":
        raise AppError(409, "invalid_transition", f"a {exercise.status} exercise cannot be edited")
    _store_draft(exercise, draft, version.approved_content, "invalid_exercise")
    exercise.revision += 1
    session.flush()
    audit(session, handoff.id, actor, "exercise.edited", "exercise", exercise.id, exercise.revision)
    return exercise


def approve_exercise(
    session: Session, exercise: Exercise, expected_revision: int, actor: str
) -> Exercise:
    version, finding, handoff = exercise_context(session, exercise)
    _require(handoff, actor, "expert")
    _check_revision(exercise, expected_revision)
    if exercise.status != "draft":
        raise AppError(409, "invalid_transition", f"exercise is already {exercise.status}")
    require_live(session, version, finding)
    exercise.status = "ready"
    exercise.approved_by = actor
    exercise.approved_at = datetime.now(UTC)
    exercise.revision += 1
    session.flush()
    audit(
        session, handoff.id, actor, "exercise.released", "exercise", exercise.id, exercise.revision
    )
    return exercise


# ---------- attempts and assessment ----------


def submit_attempt(
    session: Session,
    exercise: Exercise,
    answer: str,
    actor: str,
    idempotency_key: str | None,
    assessor: Assessor | None = None,
) -> tuple[Attempt, bool]:
    """Returns (attempt, replayed). Raises 502/504 after storing a failed attempt."""
    if not idempotency_key:
        raise AppError(
            422, "idempotency_key_required", "submitting an answer needs Idempotency-Key"
        )
    _, finding, handoff = exercise_context(session, exercise)
    _require(handoff, actor, "successor")
    if exercise.status != "ready":
        raise AppError(409, "exercise_not_ready", "the expert has not released this exercise")
    if finding.status != "confirmed":
        raise AppError(409, "invalid_transition", f"knowledge of a {finding.status} finding")
    if not answer.strip():
        raise AppError(422, "empty_answer", "the answer is empty")

    request_hash = sha256_json({"exercise": str(exercise.id), "actor": actor, "answer": answer})
    existing = session.scalar(
        select(Operation).where(
            Operation.kind == "attempt", Operation.idempotency_key == idempotency_key
        )
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise AppError(
                409, "idempotency_key_reused", "this Idempotency-Key was used with another answer"
            )
        if existing.result_id is None:
            raise AppError(409, "operation_in_progress", f"operation is {existing.state}")
        return session.get(Attempt, existing.result_id), True

    check_can_attempt(session, handoff, exercise, actor)
    attempt = Attempt(
        exercise_id=exercise.id, successor_id=actor, answer=answer, assessment_status="pending"
    )
    session.add(attempt)
    session.flush()
    op = Operation(
        handoff_id=handoff.id,
        kind="attempt",
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        state="running",
        result_type="attempt",
        result_id=attempt.id,
        started_at=datetime.now(UTC),
    )
    session.add(op)
    audit(session, handoff.id, actor, "attempt.submitted", "attempt", attempt.id)
    session.commit()  # the answer is durable before any model call (FR-21, FR-22)
    assess(session, attempt, exercise, handoff, op, assessor or get_assessor())
    return attempt, False


def reassess_attempt(
    session: Session, attempt: Attempt, actor: str, assessor: Assessor | None = None
) -> Attempt:
    exercise = session.get(Exercise, attempt.exercise_id)
    _, _, handoff = exercise_context(session, exercise)
    role(handoff, actor)  # expert or successor
    if attempt.assessment_status == "succeeded":
        raise AppError(
            409, "invalid_transition", "this attempt is already assessed; submit a new attempt"
        )
    check_can_reassess(session, handoff, attempt)
    op = Operation(
        handoff_id=handoff.id,
        kind="reassess",
        idempotency_key=f"reassess:{uuid.uuid4()}",
        request_hash=sha256_json({"attempt": str(attempt.id)}),
        state="running",
        result_type="attempt",
        result_id=attempt.id,
        started_at=datetime.now(UTC),
    )
    session.add(op)
    session.commit()
    assess(session, attempt, exercise, handoff, op, assessor or get_assessor())
    return attempt


def assess(
    session: Session,
    attempt: Attempt,
    exercise: Exercise,
    handoff: Handoff,
    op: Operation,
    assessor: Assessor,
) -> None:
    criteria = [Criterion.model_validate(c) for c in exercise.rubric]
    try:
        proposal = assessor.assess(exercise.scenario, criteria, attempt.answer)
    except Exception as exc:
        err = (
            exc
            if isinstance(exc, AppError)
            else AppError(502, "provider_error", f"assessment failed ({type(exc).__name__})")
        )
        attempt.assessment_status = "failed"
        attempt.assessment_error = err.code
        attempt.assessor_id = assessor.model_id
        op.state, op.error_code, op.error_detail = "failed", err.code, err.detail
        op.finished_at = datetime.now(UTC)
        audit(
            session,
            handoff.id,
            "system",
            "attempt.assessment_failed",
            "attempt",
            attempt.id,
            metadata={"error": err.code, "assessor": assessor.model_id},
        )
        session.commit()  # the failure is recorded; it is never a learner result
        raise AppError(
            err.status,
            err.code,
            err.detail,
            {"attempt_id": str(attempt.id), "operation_id": str(op.id)},
        ) from exc
    matches, notes = validate_matches(criteria, proposal, attempt.answer)
    attempt.criterion_results = [m.model_dump() for m in matches]
    attempt.aggregate_result = aggregate(criteria, matches)
    attempt.assessment_status = "succeeded"
    attempt.assessment_error = None
    attempt.assessor_id = assessor.model_id
    attempt.assessed_at = datetime.now(UTC)
    op.state, op.finished_at = "succeeded", datetime.now(UTC)
    audit(
        session,
        handoff.id,
        "system",
        "attempt.assessed",
        "attempt",
        attempt.id,
        metadata={"result": attempt.aggregate_result, "notes": notes},
    )
    session.flush()
