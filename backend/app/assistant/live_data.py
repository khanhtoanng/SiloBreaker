"""Live-data answers: read-only, from the database, for the intents in app.assistant.intents.

Every row starts from app.auth.deps.visible_handoffs, the same rule as GET /api/handoffs, and
the user's role in it comes from handoff_role. A learner sees only their own state: a
candidate learns how many candidates there are, never who they are, their aliases, answers,
verdicts or scores. Only an admin sees counts across people ("2 of 3 submitted"), never answer
or rubric text. No model is involved and nothing is written.

Each function returns (answer, citations). The answer's first line is a heading; every other
line is one row, and citations hold exactly one page link per row, in the same order.
"""

from collections import Counter
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.deps import handoff_role, visible_handoffs
from app.knowledge.service import library_versions
from app.models import (
    Analysis,
    AppUser,
    Attempt,
    AttemptReview,
    Exercise,
    Finding,
    Handoff,
    KnowledgeDraft,
    KnowledgeVersion,
)
from app.verify import selection as Sel

NO_HANDOFFS = "There are no handoffs yet."
NOT_IN_HANDOFF = "You are not part of any handoff yet."
NOTHING_WAITING = "Nothing is waiting for you."
NO_DUE = "You have no assessment with a due time."
STATUS_LABEL = {
    "unassigned": "successor not chosen yet",
    "selecting": "choosing a successor",
    "active": "active",
}

Answer = tuple[str, list[dict]]


# ---------- shared ----------


def page(link: str, title: str) -> dict:
    return {"kind": "page", "id": link, "title": title, "link": link}


def _when(t: datetime) -> str:
    return f"{t.astimezone(UTC):%Y-%m-%d %H:%M} UTC"


def _label(h: Handoff, names: dict[str, str | None]) -> str:
    expert = names.get(h.expert_id) or h.expert_id
    successor = (names.get(h.successor_id) or h.successor_id) if h.successor_id else None
    return f"{expert} → {successor or 'successor not chosen'}"


def _names(session: Session, handoffs: list[Handoff]) -> dict[str, str | None]:
    """Display names of each handoff's expert and successor only: people the viewer already
    sees on that handoff. Candidates are never named here."""
    ids = {h.expert_id for h in handoffs} | {h.successor_id for h in handoffs if h.successor_id}
    return Sel._names(session, sorted(ids))


def _home(h: Handoff, role: str) -> str:
    """The page this user may open for the handoff."""
    if role == "admin":
        return "/admin/handoffs"
    if role == "expert":
        return f"/expert/handoffs/{h.id}/detect"
    return "/learn"


def _rows(heading: str, rows: list[tuple[str, dict]], empty: str) -> Answer:
    if not rows:
        return empty, []
    return "\n".join([heading, *(text for text, _ in rows)]), [c for _, c in rows]


def _title(session: Session, exercise: Exercise) -> tuple[str, int]:
    version = session.get(KnowledgeVersion, exercise.knowledge_version_id)
    return session.get(Finding, version.finding_id).title, version.version_no


def _released(session: Session, h: Handoff) -> list[Exercise]:
    return [e for e in Sel.handoff_exercises(session, h) if e.status == "ready"]


# ---------- list_handoffs ----------


def list_handoffs(session: Session, user: AppUser) -> Answer:
    handoffs = visible_handoffs(session, user)
    if not handoffs:
        # A member is never told whether other handoffs exist.
        return (NO_HANDOFFS if user.role == "admin" else NOT_IN_HANDOFF), []
    names = _names(session, handoffs)
    rows = []
    for h in handoffs:
        label = _label(h, names)
        link = _home(h, handoff_role(user, h))
        rows.append((f"{label} · {STATUS_LABEL[h.status]}", page(link, label)))
    noun = "handoff" if len(rows) == 1 else "handoffs"
    return _rows(f"{len(rows)} {noun} you can see, newest first:", rows, NO_HANDOFFS)


# ---------- handoff_status ----------


def _version_count(session: Session, h: Handoff) -> int:
    return session.scalar(
        select(func.count())
        .select_from(KnowledgeVersion)
        .join(Finding, KnowledgeVersion.finding_id == Finding.id)
        .join(Analysis, Finding.analysis_id == Analysis.id)
        .where(Analysis.handoff_id == h.id)
    )


def _candidate_state(session: Session, h: Handoff, person_id: str) -> str:
    """A candidate's own place: the count of candidates and nothing about anyone else."""
    parts = [f"you are one of {len(h.candidates)} candidates"]
    exercise = Sel.current_exercise(session, h)
    if exercise is None or exercise.status != "ready":
        return " · ".join([*parts, "no exercise released yet"])
    view = Sel.candidate_view(session, h, exercise, person_id)
    parts.append("study material " + ("opened" if view["study_opened"] else "not opened yet"))
    parts.append("official attempt " + ("used" if view["attempts_used"] else "not used yet"))
    if view["due_at"]:
        parts.append(("closed " if view["closed"] else "due ") + _when(view["due_at"]))
    return " · ".join(parts)


def _submitted(session: Session, h: Handoff) -> str:
    """Admin only: how many candidates have a counted attempt on the compared exercise."""
    exercise = Sel.current_exercise(session, h)
    done = 0
    if exercise is not None:
        done = sum(Sel.attempts_used(session, exercise.id, c.person_id) > 0 for c in h.candidates)
    return f"{done} of {len(h.candidates)} candidates submitted"


def handoff_status(session: Session, user: AppUser) -> Answer:
    handoffs = visible_handoffs(session, user)
    if not handoffs:
        return (NO_HANDOFFS if user.role == "admin" else NOT_IN_HANDOFF), []
    names = _names(session, handoffs)
    library = Counter(h.id for _, _, h in library_versions(session))
    rows = []
    for h in handoffs:
        role = handoff_role(user, h)
        label = _label(h, names)
        parts = [label, STATUS_LABEL[h.status]]
        released = "yes" if _released(session, h) else "no"
        if role in ("admin", "expert"):
            ran = Sel.latest_analysis(session, h) is not None
            parts.append("analysis done" if ran else "no analysis yet")
            parts.append(f"approved knowledge versions: {_version_count(session, h)}")
            parts.append(f"exercise released: {released}")
            if role == "admin" and h.status == "selecting":
                parts.append(_submitted(session, h))
        else:
            # A learner reads approved knowledge in the Library; analyses are not theirs.
            parts.append(f"approved knowledge in the Library: {library[h.id]}")
            parts.append(f"exercise released: {released}")
            if h.candidate(user.person_id) is not None:
                parts.append(_candidate_state(session, h, user.person_id))
        rows.append((" · ".join(parts), page(_home(h, role), label)))
    return _rows("Status of the handoffs you can see:", rows, NO_HANDOFFS)


# ---------- my_pending ----------


def _admin_pending(session: Session, h: Handoff, label: str) -> list[tuple[str, dict]]:
    rows = []
    if Sel.latest_analysis(session, h) is None:
        rows.append((f"{label}: run the analysis", page("/admin/handoffs", label)))
    if (
        h.status == "selecting"
        and h.assessment_due_at is not None
        and h.assessment_due_at < datetime.now(UTC)
        and Sel.selection_of(session, h) is None
    ):
        link = f"/admin/handoffs/{h.id}"
        rows.append((f"{label}: the assessment is closed; select a successor", page(link, label)))
    return rows


def _expert_pending(session: Session, h: Handoff, label: str) -> list[tuple[str, dict]]:
    rows = []
    analysis = Sel.latest_analysis(session, h)
    if analysis is not None:
        findings = session.scalars(
            select(Finding).where(Finding.analysis_id == analysis.id).order_by(Finding.title)
        ).all()
        unreviewed = sum(f.status == "candidate" for f in findings)
        if unreviewed:
            noun = "finding" if unreviewed == 1 else "findings"
            text = f"{label}: {unreviewed} {noun} to review"
            rows.append((text, page(f"/expert/handoffs/{h.id}/detect", label)))
        for f in findings:
            if f.status != "confirmed":
                continue
            draft = session.scalar(select(KnowledgeDraft).where(KnowledgeDraft.finding_id == f.id))
            newest = session.scalar(
                select(KnowledgeVersion)
                .where(KnowledgeVersion.finding_id == f.id)
                .order_by(KnowledgeVersion.version_no.desc())
                .limit(1)
            )
            if draft is not None and (newest is None or newest.draft_revision != draft.revision):
                link = f"/expert/findings/{f.id}"
                rows.append((f"“{f.title}”: the draft is not approved yet", page(link, f.title)))
            if newest is not None and not session.scalar(
                select(Exercise.id).where(
                    Exercise.knowledge_version_id == newest.id, Exercise.status == "ready"
                )
            ):
                link = f"/expert/knowledge/{newest.id}/exercise"
                text = f"“{f.title}” v{newest.version_no}: no exercise released yet"
                rows.append((text, page(link, f"{f.title} v{newest.version_no}")))
    for e in Sel.handoff_exercises(session, h):
        waiting = session.scalar(
            select(func.count())
            .select_from(AttemptReview)
            .join(Attempt, AttemptReview.attempt_id == Attempt.id)
            .where(Attempt.exercise_id == e.id, AttemptReview.reviewed_at.is_(None))
        )
        if waiting:
            title, no = _title(session, e)
            noun = "review request" if waiting == 1 else "review requests"
            link = f"/expert/knowledge/{e.knowledge_version_id}/exercise"
            text = f"“{title}” v{no}: {waiting} {noun} waiting"
            rows.append((text, page(link, f"{title} v{no}")))
    return rows


def _learner_pending(session: Session, user: AppUser, h: Handoff) -> list[tuple[str, dict]]:
    """Released exercises this learner has not answered yet. The title only; never the
    exercise's content."""
    rows = []
    for e in _released(session, h):
        due = None
        if h.candidate(user.person_id) is not None:
            view = Sel.candidate_view(session, h, e, user.person_id)
            if not view["is_assessment_exercise"] or view["closed"] or view["attempts_used"]:
                continue
            due = view["due_at"]
        elif Sel.attempts_used(session, e.id, user.person_id):
            continue
        title, no = _title(session, e)
        text = f"Answer the exercise “{title}” (knowledge v{no})"
        if due:
            text += f", due {_when(due)}"
        rows.append((text, page(f"/learn/exercises/{e.id}", title)))
    return rows


def my_pending(session: Session, user: AppUser) -> Answer:
    handoffs = visible_handoffs(session, user)
    names = _names(session, handoffs)
    rows = []
    for h in handoffs:
        role = handoff_role(user, h)
        label = _label(h, names)
        if role == "admin":
            rows += _admin_pending(session, h, label)
        elif role == "expert":
            rows += _expert_pending(session, h, label)
        else:
            rows += _learner_pending(session, user, h)
    return _rows("Waiting for you:", rows, NOTHING_WAITING)


# ---------- my_due ----------


def my_due(session: Session, user: AppUser) -> Answer:
    rows = []
    for h in visible_handoffs(session, user):
        if h.candidate(user.person_id) is None or h.assessment_due_at is None:
            continue
        exercise = Sel.current_exercise(session, h)
        view = Sel.candidate_view(session, h, exercise, user.person_id) if exercise else None
        used = bool(view and view["attempts_used"])
        state = "your official attempt is used" if used else "your official attempt is not used yet"
        verb = "Closed" if view and view["closed"] else "Due"
        link = f"/learn/exercises/{exercise.id}" if exercise else "/learn"
        title = _title(session, exercise)[0] if exercise else "Your assessment"
        rows.append((f"{verb} {_when(h.assessment_due_at)} · {state}", page(link, title)))
    return _rows("Your assessment:", rows, NO_DUE)


ANSWERS = {
    "list_handoffs": list_handoffs,
    "handoff_status": handoff_status,
    "my_pending": my_pending,
    "my_due": my_due,
}
