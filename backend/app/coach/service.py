"""Learning coach: after an assessed attempt, what to re-read and a practice question.

Who is asking comes from the session only, and only the attempt's owner gets the coach. The
sources are a whitelist: the learner's own attempt (answer, criterion text, effective
verdict, evidence quote) and the approved knowledge version the exercise was built from.
The coach never reads drafts, other attempts, scores, fit, aliases, evidence or the audit
log, and it never returns a criterion's critical flag or source path.

The only write is one `coach.opened` audit event per attempt, holding no text. Practice is
not assessment: answers are checked with the offline assessor against the approved line and
are neither stored nor logged, so attempts_used, scores and selection never see them.
"""

import base64
import hashlib
import hmac
import logging
import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.service import ai_limits, openai_client, require_openai
from app.audit import audit
from app.config import get_settings
from app.errors import AppError
from app.models import AppUser, Attempt, AuditEvent, Exercise, Handoff
from app.verify import selection as Sel
from app.verify.contract import GUIDANCE_FIELDS, Criterion, CriterionMatch, resolve
from app.verify.offline import OfflineAssessor
from app.verify.service import exercise_context

log = logging.getLogger("silobreaker.coach")

OPENED = "coach.opened"
NOT_MET = ("partial", "unmet")
# The offline explanation is a fixed template over the criterion text the learner already sees.
EXPLANATION = {
    "unmet": "Your answer did not cover: {criterion}.",
    "partial": "Your answer only partly covered: {criterion}.",
}
# Keyed by the situation (what the learner's answer did), never by where the line came from.
PRACTICE_PROMPT = {
    "unmet": "In your own words: what does the approved knowledge say you should do here?",
    "partial": (
        "In your own words, and in full this time: what does the approved knowledge say you "
        "should do here?"
    ),
}
PRACTICE_FEEDBACK = {
    "met": "Your practice answer covers the approved line. Practice does not change your result.",
    "partial": (
        "Your practice answer covers part of the approved line. Compare it with the line and "
        "try another wording."
    ),
    "unmet": (
        "Your practice answer does not cover the approved line yet. Re-read it and try "
        "another wording."
    ),
}
DEMONSTRATED_MESSAGE = "Nothing to fix in this attempt."
UNCLEAR_MESSAGE = (
    "Nothing to coach in this attempt yet: an unclear judgment needs the expert's review."
)
COACH_MESSAGE = (
    "Re-read these lines of the approved knowledge and practise them. "
    "Practice does not change your result."
)
# A model explanation that says any of these is rejected: they would hint at the rubric.
FORBIDDEN_WORDS = re.compile(
    r"critical|important|safety|priority|rubric|score|source_path|"
    + "|".join(f.replace("_", "[ _]") for f in GUIDANCE_FIELDS),
    re.IGNORECASE,
)
MAX_EXPLANATION_SENTENCES = 2


# ---------- access ----------


def _uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError):
        return None


def owned_attempt(
    session: Session, user: AppUser, attempt_id: str
) -> tuple[Attempt, Exercise, Handoff]:
    """The attempt, if the signed-in user is its owner. Admins and the expert get 403 (the
    expert has the review flow); anyone else gets 404, as if the attempt did not exist."""
    key = _uuid(attempt_id)
    attempt = session.get(Attempt, key) if key else None
    if attempt is None:
        raise AppError(404, "not_found", "attempt not found")
    exercise = session.get(Exercise, attempt.exercise_id)
    _, _, handoff = exercise_context(session, exercise)
    if user.role == "admin" or (user.person_id and user.person_id == handoff.expert_id):
        raise AppError(403, "not_attempt_owner", "only the learner who answered may open the coach")
    if not user.person_id or attempt.successor_id != user.person_id:
        raise AppError(404, "not_found", "attempt not found")
    return attempt, exercise, handoff


def _require_assessed(attempt: Attempt) -> None:
    if attempt.assessment_status != "succeeded" or attempt.criterion_results is None:
        raise AppError(409, "not_assessed", "the coach opens after a successful assessment")


# ---------- approved lines ----------


def approved_lines(content: dict) -> list[tuple[str, str, str]]:
    """(line_id, source_path, text) for every line of the approved guidance. The line id is
    an opaque position, so it never names the section a line came from."""
    out = []
    for field in GUIDANCE_FIELDS:
        for i, text in enumerate(content.get(field) or []):
            out.append((f"L{len(out) + 1}", f"{field}[{i}]", text))
    return out


def _line_id(content: dict, source_path: str) -> str | None:
    return next((lid for lid, path, _ in approved_lines(content) if path == source_path), None)


def _line_text(content: dict, line_id: str) -> str | None:
    path = next((p for lid, p, _ in approved_lines(content) if lid == line_id), None)
    return resolve(content, path) if path else None


# ---------- practice token ----------


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(payload: bytes) -> bytes:
    secret = get_settings().coach_secret.encode()
    return hmac.new(secret, payload, hashlib.sha256).digest()


def practice_token(attempt_id: uuid.UUID, line_id: str) -> str:
    """An opaque, signed reference to one approved line of one attempt. No storage needed."""
    payload = f"{attempt_id}:{line_id}".encode()
    return f"{_b64(payload)}.{_b64(_sign(payload))}"


def read_token(token: str) -> tuple[str, str]:
    """(attempt_id, line_id) from a token this server signed, else 400."""
    try:
        body, sig = token.split(".")
        payload = _unb64(body)
        good = hmac.compare_digest(_unb64(sig), _sign(payload))
        attempt_id, line_id = payload.decode().split(":")
    except (ValueError, UnicodeDecodeError):
        good = False
    if not good:
        raise AppError(400, "invalid_practice_token", "this practice question is not valid")
    return attempt_id, line_id


# ---------- model (optional) ----------


def get_model():
    """The OpenAI coach when SB_AI_PROVIDER=openai, else None. openai is never imported in
    offline mode."""
    settings = get_settings()
    if settings.ai_provider != "openai":
        return None
    from app.analysis.openai_extractor import StructuredCall
    from app.coach.openai_coach import OpenAICoach

    openai = require_openai()
    return OpenAICoach(StructuredCall(openai_client(openai), settings.openai_model, **ai_limits()))


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]


def model_explanation(model, criterion: str, answer: str, line_id: str, text: str) -> str | None:
    """The model's explanation if it cites exactly the line it was given and stays plain,
    else None (fall back)."""
    try:
        out = model.explain(criterion, answer, {"id": line_id, "text": text})
    except AppError as exc:
        log.warning("coach model unavailable (%s); offline explanation used", exc.code)
        return None
    explanation = out.explanation.strip()
    if not explanation or set(out.cited_ids) != {line_id}:
        log.warning("coach model explanation rejected: citation is not the given line")
        return None
    if FORBIDDEN_WORDS.search(explanation) or len(_sentences(explanation)) > (
        MAX_EXPLANATION_SENTENCES
    ):
        log.warning("coach model explanation rejected: wording checks failed")
        return None
    return explanation


# ---------- coach ----------


def _next_step(session: Session, handoff: Handoff, exercise: Exercise, person_id: str) -> str:
    view = Sel.candidate_view(session, handoff, exercise, person_id)
    if view is not None:
        return "try_again" if view["attempts_left"] > 0 else "official_result_stands"
    return "try_again" if exercise.status == "ready" else "none"


def _audit_opened(session: Session, handoff: Handoff, attempt: Attempt, actor: str) -> None:
    seen = session.scalar(
        select(AuditEvent.id).where(AuditEvent.action == OPENED, AuditEvent.target_id == attempt.id)
    )
    if seen is None:
        audit(session, handoff.id, actor, OPENED, "attempt", attempt.id)


def coach_for_attempt(session: Session, user: AppUser, attempt_id: str) -> dict:
    attempt, exercise, handoff = owned_attempt(session, user, attempt_id)
    _require_assessed(attempt)
    version, finding, _ = exercise_context(session, exercise)
    content = version.approved_content
    review = Sel.review_of(session, attempt)
    overrides = review.overrides if review is not None and review.reviewed_at else None
    matches = Sel.effective_matches(attempt.criterion_results, overrides)
    verdicts = {m.criterion_id: m for m in matches}

    scenario = _sentences(exercise.scenario)
    situation = f" The situation: {scenario[0]}" if scenario else ""
    pending: list[tuple[Criterion, CriterionMatch, str, str]] = []
    for raw in exercise.rubric:  # rubric order, never by importance
        c = Criterion.model_validate(raw)
        m = verdicts.get(c.id)
        if m is None or m.verdict not in NOT_MET:
            continue
        line_id, text = _line_id(content, c.source_path), resolve(content, c.source_path)
        if line_id is None or text is None:  # validate_exercise makes this unreachable
            continue
        pending.append((c, m, line_id, text))

    explanations = [
        EXPLANATION[m.verdict].format(criterion=c.text.strip().rstrip(".")) for c, m, *_ in pending
    ]
    provider = "offline"
    if pending and get_settings().ai_provider == "openai":
        rephrased = None
        try:
            model = get_model()
        except AppError as exc:
            log.warning("coach model unavailable (%s); offline explanation used", exc.code)
            model = None
        if model is not None:
            rephrased = [
                model_explanation(model, c.text, attempt.answer, lid, text)
                for c, _, lid, text in pending
            ]
        if rephrased is not None and all(rephrased):
            explanations, provider = rephrased, "openai"
        else:
            provider = "offline_fallback"

    items = [
        {
            "criterion_id": c.id,
            "criterion_text": c.text,
            "verdict": m.verdict,
            "your_quote": m.evidence_quote or None,
            "explanation": explanation,
            "reread": {
                "version_id": str(version.id),
                "version_no": version.version_no,
                "title": finding.title,
                "line_id": line_id,
                "text": text,
                "link": f"/library?open={version.id}",
            },
            "practice": {
                "practice_id": practice_token(attempt.id, line_id),
                "prompt": PRACTICE_PROMPT[m.verdict] + situation,
            },
        }
        for (c, m, line_id, text), explanation in zip(pending, explanations, strict=True)
    ]
    result = Sel.effective_result(attempt, exercise, review)
    if items:
        message, next_step = COACH_MESSAGE, _next_step(session, handoff, exercise, user.person_id)
    else:
        message = DEMONSTRATED_MESSAGE if result == "demonstrated" else UNCLEAR_MESSAGE
        next_step = "none"
    _audit_opened(session, handoff, attempt, user.person_id)
    return {
        "attempt_id": str(attempt.id),
        "result": result,
        "met_count": sum(m.verdict == "met" for m in verdicts.values()),
        "total": len(exercise.rubric),
        "items": items,
        "message": message,
        "next_step": next_step,
        "provider": provider,
    }


# ---------- practice ----------


def check_practice(session: Session, user: AppUser, practice_id: str, answer: str) -> dict:
    """Checks a practice answer against one approved line. Nothing is stored or logged."""
    attempt_id, line_id = read_token(practice_id)
    attempt, exercise, _ = owned_attempt(session, user, attempt_id)
    _require_assessed(attempt)
    version, _, _ = exercise_context(session, exercise)
    text = _line_text(version.approved_content, line_id)
    if text is None:
        raise AppError(400, "line_not_in_version", "this line is not in the approved knowledge")
    # One ad-hoc criterion whose text is the approved line; built without the rubric's
    # length limits because an approved line is not a rubric criterion.
    line = Criterion.model_construct(id="practice", text=text, source_path="")
    match = OfflineAssessor().assess("", [line], answer).matches[0]
    return {
        "verdict": match.verdict,
        "feedback": PRACTICE_FEEDBACK[match.verdict],
        "reread_text": text,
    }
