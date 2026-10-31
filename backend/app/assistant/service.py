"""Help assistant: answers from curated help topics or approved knowledge, nothing else.

Who is asking comes from the session only. The sources are a whitelist: the topics in
app.assistant.topics, and the approved knowledge versions /library lists. The assistant
never reads drafts, exercise rubrics, attempts of anyone, evidence, the audit log or
settings, and it stores nothing: the question is neither logged nor saved.

Live data: a question that clearly matches one of app.assistant.intents gets mode "data", a
read-only answer from app.assistant.live_data under the same visibility rule as the app.

Assessment lock: while the user has a released exercise of their own still unanswered,
knowledge questions get mode "locked", so the assistant cannot answer the exercise for them.
"""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.service import ai_limits, openai_client, require_openai
from app.assistant import live_data
from app.assistant.intents import detect_intent
from app.assistant.retrieval import (
    KnowledgeHit,
    ReadableVersion,
    rank_knowledge,
    rank_topics,
    specificity,
    topic_allowed,
)
from app.assistant.topics import LIVE_DATA_TOPIC, TOPICS
from app.auth.deps import visible_handoffs
from app.config import get_settings
from app.errors import AppError
from app.knowledge.service import library_versions
from app.models import AppUser, Handoff, HandoffCandidate
from app.verify.contract import GUIDANCE_FIELDS
from app.verify.selection import (
    attempts_used,
    candidate_view,
    current_exercise,
    handoff_exercises,
)

log = logging.getLogger("silobreaker.assistant")

LOCKED_MESSAGE = (
    "Knowledge answers are paused while you have an exercise to complete. "
    "Read the approved knowledge yourself from the exercise page."
)
UNKNOWN_MESSAGE = (
    "I don't know that from the help guide or the approved knowledge, and I won't guess. "
    "Open the Library to read the approved knowledge yourself, or try one of the "
    "suggested questions."
)
FIELD_LABELS = {
    "prerequisites": "Preconditions",
    "steps": "Steps",
    "stop_and_escalate": "Stop and escalate",
    "success_checks": "Success checks",
}
SUGGESTIONS = 3


# ---------- who is asking ----------


def _role_in(handoff: Handoff, person_id: str) -> str | None:
    if person_id == handoff.expert_id:
        return "expert"
    if person_id == handoff.successor_id:
        return "successor"
    if handoff.candidate(person_id) is not None:
        return "candidate"
    return None


def role_context(session: Session, user: AppUser, handoff_id: str | None = None) -> set[str]:
    """The user's roles from the session and handoff memberships. With the id of a handoff
    the user takes part in, only their role in that handoff; any other id is ignored."""
    if user.role == "admin":
        return {"admin"}
    pid = user.person_id
    if not pid:
        return set()
    roles = {
        h.id: r for h in visible_handoffs(session, user) if (r := _role_in(h, pid)) is not None
    }
    try:
        wanted = uuid.UUID(handoff_id) if handoff_id else None
    except ValueError:
        wanted = None
    if wanted in roles:
        return {roles[wanted]}
    return set(roles.values())


def assessment_lock(session: Session, user: AppUser) -> bool:
    """True while the user has a released exercise of their own that is still unanswered:
    a successor with no counted attempt on a released exercise of their handoff, or a
    candidate of an open common assessment who has not used their official attempt."""
    pid = user.person_id
    if user.role == "admin" or not pid:
        return False
    for h in session.scalars(select(Handoff).where(Handoff.successor_id == pid)).all():
        for e in handoff_exercises(session, h):
            if e.status == "ready" and attempts_used(session, e.id, pid) == 0:
                return True
    selecting = session.scalars(
        select(Handoff)
        .join(HandoffCandidate, HandoffCandidate.handoff_id == Handoff.id)
        .where(HandoffCandidate.person_id == pid, Handoff.status == "selecting")
    ).all()
    for h in selecting:
        e = current_exercise(session, h)
        if e is None or e.status != "ready":
            continue
        view = candidate_view(session, h, e, pid)
        if view is not None and not view["closed"] and view["attempts_used"] == 0:
            return True
    return False


# ---------- sources ----------


def readable_versions(session: Session) -> list[ReadableVersion]:
    """Exactly the approved versions /library lists to every signed-in user."""
    return [
        ReadableVersion(str(v.id), v.version_no, f.title, v.approved_content)
        for v, f, _ in library_versions(session)
    ]


def suggestions(roles: set[str], page: str, exclude: str | None = None) -> list[str]:
    """Follow-up questions for this role and page: topics suggested on the most specific
    matching route first, then role-specific ones, in curated order."""

    allowed = [t for t in TOPICS if t.id != exclude and topic_allowed(t, roles, page)]
    # Topics pinned to this exact page (a role's home page) come first, whatever the role.
    pinned = [t for t in allowed if page in t.pin_on]
    rest = sorted((t for t in allowed if t not in pinned), key=lambda t: specificity(t, page))
    out: list[str] = []
    for t in [*pinned, *rest]:
        if t.suggest not in out:
            out.append(t.suggest)
        if len(out) == SUGGESTIONS:
            break
    return out


def knowledge_citation(hit: KnowledgeHit) -> dict:
    v = hit.version
    return {
        "kind": "knowledge_version",
        "id": v.version_id,
        "title": v.title,
        "version_no": v.version_no,
        "link": f"/library?open={v.version_id}",
    }


def offline_knowledge_answer(hit: KnowledgeHit) -> str:
    """Only quoted approved lines under fixed headings. Nothing is paraphrased or added."""
    v = hit.version
    out = [f'From the approved knowledge "{v.title}" v{v.version_no}:']
    for field in GUIDANCE_FIELDS:
        lines = [line for line in hit.lines if line.field == field]
        if lines:
            out.append(f"{FIELD_LABELS[field]}:")
            out.extend(f"- {line.text}" for line in sorted(lines, key=lambda x: x.index))
    return "\n".join(out)


# ---------- model (optional) ----------


def get_model():
    """The OpenAI assistant when SB_AI_PROVIDER=openai, else None. openai is never imported
    in offline mode."""
    settings = get_settings()
    if settings.ai_provider != "openai":
        return None
    from app.analysis.openai_extractor import StructuredCall
    from app.assistant.openai_assistant import OpenAIAssistant

    openai = require_openai()
    return OpenAIAssistant(
        StructuredCall(openai_client(openai), settings.openai_model, **ai_limits())
    )


def model_answer(question: str, hit: KnowledgeHit) -> str | None:
    """The model's answer if it cites only snippets it was given, else None (fall back)."""
    snippets = [{"id": line.id, "text": line.text} for line in hit.lines]
    given = {s["id"] for s in snippets}
    try:
        model = get_model()
        if model is None:
            return None
        out = model.answer(question, snippets)
    except AppError as exc:
        log.warning("assistant model unavailable (%s); offline answer used", exc.code)
        return None
    if not out.answer.strip() or not out.cited_ids or not set(out.cited_ids) <= given:
        log.warning("assistant model answer rejected: citations not in the provided snippets")
        return None
    return out.answer.strip()


# ---------- answer ----------


def answer(
    session: Session,
    user: AppUser,
    question: str,
    page: str,
    handoff_id: str | None = None,
) -> dict:
    if get_settings().assistant_provider == "local":
        from app.assistant.agent import run_agent

        return run_agent(session, user, question, page, handoff_id)
    return offline_answer(session, user, question, page, handoff_id)


def offline_answer(
    session: Session,
    user: AppUser,
    question: str,
    page: str,
    handoff_id: str | None = None,
    allow_model: bool = True,
) -> dict:
    """The lexical assistant. allow_model=False is the agent's fallback: a question meant for
    a local model must not move to SB_AI_PROVIDER's remote one because the local one failed."""
    roles = role_context(session, user, handoff_id)
    page = page if page.startswith("/") else ""
    # Live data first, but only for a question that clearly asks for it. No model is called
    # and the assessment lock is not consulted: these answers never contain knowledge.
    intent = detect_intent(question)
    if intent is not None:
        text, citations = live_data.ANSWERS[intent](session, user)
        return _out("data", text, citations, suggestions(roles, page, exclude=LIVE_DATA_TOPIC))
    topics = rank_topics(question, roles, page)
    best_topic = topics[0] if topics else None
    hit = rank_knowledge(question, readable_versions(session))
    # A question is about knowledge unless a help topic fits it strictly better.
    is_knowledge = hit is not None and (best_topic is None or hit.coverage >= best_topic.score)

    if is_knowledge and assessment_lock(session, user):
        return _out("locked", LOCKED_MESSAGE, [], suggestions(roles, page))
    if is_knowledge:
        assert hit is not None
        provider, text = "offline", None
        if allow_model and get_settings().ai_provider == "openai":
            text = model_answer(question, hit)
            provider = "openai" if text is not None else "offline_fallback"
        return _out(
            "knowledge",
            text or offline_knowledge_answer(hit),
            [knowledge_citation(hit)],
            suggestions(roles, page),
            provider,
        )
    if best_topic is not None:
        t = best_topic.topic
        return _out(
            "help",
            t.answer,
            [{"kind": "help_topic", "id": t.id, "title": t.title}],
            suggestions(roles, page, exclude=t.id),
        )
    return _out("unknown", UNKNOWN_MESSAGE, [], suggestions(roles, page))


def _out(
    mode: str, text: str, citations: list[dict], suggest: list[str], provider: str = "offline"
) -> dict:
    return {
        "mode": mode,
        "answer": text,
        "citations": citations,
        "suggestions": suggest,
        "provider": provider,
    }
