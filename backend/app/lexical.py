"""Shared lexical tokenizer for the offline matchers (assessor and help assistant).

Lower-cases, drops stopwords, folds a plural "s", maps a small synonym table and turns
negations into the marker "NOT", so different wordings of the same idea overlap.
"""

import re

STOPWORDS = set(
    """a an the and or of to for in on at by with from as is are be been it its this that
    these those i i'd i'll i'm we our ours you your they their them he she his her if when
    then than so just also any all can could would should will shall do does did done has
    have had there here what which who whom how why where up out into about over more most
    very only first before after again via one's report reports say says shows show exactly
    use using already ensure make sure must""".split()
)
SYNONYMS = {
    "acmepay": "provider",
    "confirm": "check",
    "verify": "check",
    "look": "check",
    "inspect": "check",
    "settlement": "settle",
    "settled": "settle",
    "accepted": "accept",
    "pause": "stop",
    "halt": "stop",
    "raise": "escalate",
    "escalation": "escalate",
    "unclear": "unknown",
    "contradictory": "unknown",
    "contradicts": "unknown",
    "ambiguous": "unknown",
    "single": "one",
    "create": "submit",
    "trigger": "submit",
    "new": "another",
    "original": "existing",
    "status": "state",
    "happened": "state",
    "located": "locate",
    "find": "locate",
    "reconciled": "reconcile",
}
NEGATIONS = {"not", "never", "no", "without"}
NOT = "NOT"


def tokens(text: str) -> set[str]:
    text = text.lower().replace("won't", "will not").replace("n't", " not")
    out = set()
    for w in re.findall(r"[a-z0-9]+", text):
        if w in NEGATIONS:
            out.add(NOT)
            continue
        if w in STOPWORDS:
            continue
        if len(w) > 4 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.add(SYNONYMS.get(w, w))
    return out
