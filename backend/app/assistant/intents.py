"""Data intents: the few live-data questions the assistant answers from the database.

Detection is lexical, with the assistant's tokenizer (app.assistant.retrieval.terms). A
question matches an intent only when it hits one of the intent's anchor words and nearly all
of its words belong to that intent's vocabulary. Anything else ("How do I create a
handoff?", "Who scored highest?") falls through to knowledge and help as before.

The shared tokenizer drops "how", "why" and "who" as stopwords, so they are checked on the
raw words: a how-to, a why or a question about a person is never a data question.
"""

import re
from dataclasses import dataclass

from app.assistant.retrieval import terms

# Share of the question's words that must belong to the intent's vocabulary.
MIN_COVERAGE = 0.75
# Raw words that make a question a how-to, an explanation or about another person.
HOW_WHY_WHO = {"how", "why", "who", "whom", "whose"}
# Words about other people's results, rubrics or actions: never a data question.
BLOCKERS = {
    "score",
    "scored",
    "highest",
    "lowest",
    "top",
    "best",
    "worst",
    "answer",
    "answered",
    "fit",
    "rank",
    "ranked",
    "alias",
    "result",
    "verdict",
    "rubric",
    "critical",
    "password",
    "submit",  # also "create" (shared synonym table)
    "delete",
    "remove",
    "approve",
    "reason",
    "select",
    "selected",
    "cap",
    "mean",
    "explain",
}
# Words any data question may carry without changing what it asks.
FILLER = {
    "my",
    "me",
    "mine",
    "our",
    "us",
    "yet",
    "now",
    "right",
    "current",
    "currently",
    "still",
    "please",
    "tell",
    "know",
    "see",
    "list",
}


@dataclass(frozen=True)
class Intent:
    id: str
    anchors: frozenset[str]  # at least one must be in the question
    words: frozenset[str]  # the rest of the vocabulary


def _vocab(words: str) -> frozenset[str]:
    """Words as the tokenizer sees them ("status" -> "statu", "analysis" -> "analysi")."""
    return frozenset(t for w in words.split() for t in terms(w))


BLOCKED = _vocab(" ".join(BLOCKERS))
COMMON = _vocab(" ".join(FILLER))


def _intent(id: str, anchors: str, words: str) -> Intent:
    return Intent(id, _vocab(anchors), _vocab(words) | COMMON)


# Order breaks ties: the more specific questions first.
INTENTS = (
    _intent("my_due", "due deadline closed close", "assessment exercise time when official"),
    _intent(
        "my_pending",
        "waiting wait pending need todo outstanding",
        "need do task thing work handoff",
    ),
    _intent(
        "handoff_status",
        "status state analysis progress",
        "handoff run ran analysis project stand going",
    ),
    _intent("list_handoffs", "handoff", "exist existing system open have"),
)


def _raw_words(question: str) -> set[str]:
    return set(re.findall(r"[a-z]+", question.lower()))


def detect_intent(question: str) -> str | None:
    """The data intent the question clearly asks for, else None."""
    if _raw_words(question) & HOW_WHY_WHO:
        return None
    q = terms(question)
    if not q or q & BLOCKED:
        return None
    best: tuple[float, int, int] | None = None
    found = None
    for rank, intent in enumerate(INTENTS):
        anchors = q & intent.anchors
        if not anchors:
            continue
        coverage = len(q & (intent.anchors | intent.words)) / len(q)
        if coverage < MIN_COVERAGE:
            continue
        key = (coverage, len(anchors), -rank)
        if best is None or key > best:
            best, found = key, intent.id
    return found
