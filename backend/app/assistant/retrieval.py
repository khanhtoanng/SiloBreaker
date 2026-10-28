"""Lexical ranking of help topics and approved knowledge lines.

Both use the shared tokenizer (app.lexical) with its synonym table, plus a prefix match so
"retrying" meets "retry" and "approved" meets "approve". Thresholds are named constants;
anything below them is not an answer.
"""

from dataclasses import dataclass

from app.assistant.topics import ANY, TOPICS, Topic
from app.lexical import NOT, tokens
from app.verify.contract import GUIDANCE_FIELDS

# Forms the shared synonym table does not fold together, for help questions only.
HELP_SYNONYMS = {
    "capped": "cap",
    "capping": "cap",
    "login": "sign",
    "signin": "sign",
    "logged": "log",
    "logout": "log",
    "prioritized": "prioritised",
    "prioritize": "prioritise",
    "percentage": "percent",
    "approval": "approve",
    "escalating": "escalate",
    "escalated": "escalate",
}
# A word matches another if one is the other, or they share this much of a prefix.
MIN_PREFIX = 4
PREFIX_SLACK = 2

# A topic answers when it covers this share of the question's words.
TOPIC_MIN_SCORE = 0.3
# Knowledge answers need the question's words to appear in one approved version: at least
# this share of them, and at least this many different words (one shared word is chance).
KNOWLEDGE_MIN_COVERAGE = 0.6
KNOWLEDGE_MIN_TERMS = 2


def terms(text: str) -> set[str]:
    return {HELP_SYNONYMS.get(w, w) for w in tokens(text) if w != NOT and len(w) > 1}


def _match(a: str, b: str) -> bool:
    if a == b:
        return True
    if a.isdigit() or b.isdigit():
        return False
    n = 0
    for x, y in zip(a, b, strict=False):
        if x != y:
            break
        n += 1
    return n >= max(MIN_PREFIX, min(len(a), len(b)) - PREFIX_SLACK)


def _hits(question: set[str], doc: set[str]) -> set[str]:
    return {q for q in question if any(_match(q, d) for d in doc)}


def topic_allowed(topic: Topic, roles: set[str], page: str) -> bool:
    role_ok = ANY in topic.roles or bool(roles & set(topic.roles))
    page_ok = ANY in topic.pages or any(page.startswith(p) for p in topic.pages)
    return role_ok and page_ok


@dataclass(frozen=True)
class TopicHit:
    topic: Topic
    score: float


def rank_topics(question: str, roles: set[str], page: str) -> list[TopicHit]:
    """Topics allowed for these roles on this page, best first, above TOPIC_MIN_SCORE."""
    q = terms(question)
    if not q:
        return []
    out = []
    for t in TOPICS:
        if not topic_allowed(t, roles, page):
            continue
        keyword_hits = _hits(q, terms(" ".join(t.keywords)))
        title_hits = _hits(q, terms(t.title)) - keyword_hits
        score = (len(keyword_hits) + 0.5 * len(title_hits)) / len(q)
        if keyword_hits and score >= TOPIC_MIN_SCORE:
            out.append(TopicHit(t, score))
    out.sort(key=lambda h: (-h.score, *specificity(h.topic, page)))
    return out


def specificity(topic: Topic, page: str) -> tuple[int, int]:
    """Sort key among equals: topics suggested on this page first, then role-specific
    ones; a stable sort keeps the curated order after that."""
    here = max((len(p) for p in topic.suggest_on if page.startswith(p)), default=-1)
    return (-here, 1 if ANY in topic.roles else 0)


@dataclass(frozen=True)
class LineHit:
    id: str  # kv:<version_id>:<field>:<index>
    text: str
    field: str
    index: int
    version_id: str
    version_no: int
    title: str
    score: float


@dataclass(frozen=True)
class ReadableVersion:
    """One approved version the user may read: the same rows /library lists."""

    version_id: str
    version_no: int
    title: str
    content: dict


@dataclass(frozen=True)
class KnowledgeHit:
    version: ReadableVersion
    coverage: float
    lines: list[LineHit]


def line_id(version_id: str, field: str, index: int) -> str:
    return f"kv:{version_id}:{field}:{index}"


def rank_knowledge(question: str, readable: list[ReadableVersion]) -> KnowledgeHit | None:
    """The approved version that best covers the question, with its matching lines.

    Each line of preconditions, steps, stop-and-escalate and success checks is scored on
    its own; a version qualifies when its lines (and title) together cover the question
    above KNOWLEDGE_MIN_COVERAGE with at least KNOWLEDGE_MIN_TERMS different words.
    """
    q = terms(question)
    if not q:
        return None
    best: KnowledgeHit | None = None
    for v in readable:
        covered = _hits(q, terms(v.title))
        lines = []
        for field in GUIDANCE_FIELDS:
            for i, text in enumerate(v.content.get(field) or []):
                hits = _hits(q, terms(text))
                if not hits:
                    continue
                covered |= hits
                lines.append(
                    LineHit(
                        id=line_id(v.version_id, field, i),
                        text=text,
                        field=field,
                        index=i,
                        version_id=v.version_id,
                        version_no=v.version_no,
                        title=v.title,
                        score=len(hits) / len(q),
                    )
                )
        coverage = len(covered) / len(q)
        if (
            lines
            and len(covered) >= KNOWLEDGE_MIN_TERMS
            and coverage >= KNOWLEDGE_MIN_COVERAGE
            and (best is None or coverage > best.coverage)
        ):
            best = KnowledgeHit(v, coverage, lines)
    return best
