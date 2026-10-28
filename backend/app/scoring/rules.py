"""Deterministic review-priority rules, scoring version risk/1 (docs/07).

Pure functions only: no database, no model. Every number shown to a user is computed
here from counts that the user can open and check.

The score is a review-priority heuristic. It is not a probability of knowledge loss,
not an employee quality score and not a prediction that an incident will occur.
"""

from dataclasses import dataclass, field

SCORING_VERSION = "risk/1"
WEIGHTS = {"A": 25, "D": 25, "O": 20, "M": 15, "B": 15}
CAP = 60
MIN_ATTRIBUTABLE_EVENTS = 2
REQUIRED_DOC_FACETS = ("preconditions", "steps", "stop_and_escalate", "success_checks")
MAX_RANKED = 3
# Shown under a capped score; the help assistant quotes these same strings.
CAP_REASON_PARTICIPATION = "Capped: selected engineer handled only part of the attributable events."
CAP_REASON_ALTERNATE_RECOVERY = "Capped: two or more recoveries by other engineers were found."

Signal = float | None  # None means unknown


@dataclass(frozen=True)
class EventObs:
    """One distinct operational event, after linking records that describe it."""

    key: str
    resolver_id: str | None  # who performed the substantive recovery action, if attributable
    manual: bool
    record_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class AreaObs:
    key: str
    title: str
    events: tuple[EventObs, ...]
    doc_facets: tuple[frozenset[str], ...]  # facets found in each relevant document
    docs_family_included: bool
    record_count: int
    source_families: frozenset[str]
    contradiction: bool = False


@dataclass
class ScoreResult:
    signals: dict[str, Signal]
    counts: dict[str, int | float | None]
    raw: float | None
    review_priority: int | None
    eligibility_status: str
    evidence_confidence: str
    reasons: list[str] = field(default_factory=list)
    missing_facets: list[str] = field(default_factory=list)
    scoring_version: str = SCORING_VERSION


def three_level(count: int) -> float:
    return 0.0 if count == 0 else 0.5 if count == 1 else 1.0


def raw_score(s: dict[str, Signal]) -> float:
    return sum(WEIGHTS[k] * float(s[k]) for k in WEIGHTS)  # type: ignore[arg-type]


def round_half_up(x: float) -> int:
    return int(x + 0.5)


def participation(events: tuple[EventObs, ...], selected: str) -> tuple[Signal, Signal, dict]:
    attributable = [e for e in events if e.resolver_id]
    by_selected = sum(1 for e in attributable if e.resolver_id == selected)
    by_others = len(attributable) - by_selected
    counts = {
        "attributable_events": len(attributable),
        "events_by_selected": by_selected,
        "events_by_others": by_others,
        "participation_share": None,
    }
    if len(attributable) < MIN_ATTRIBUTABLE_EVENTS:
        return None, None, counts  # a proportion over too few events says almost nothing
    share = by_selected / len(attributable)
    counts["participation_share"] = round(share, 3)
    o = 1.0 if share >= 0.75 else 0.5 if share >= 0.5 else 0.0
    b = 0.0 if by_others >= 2 else 0.5 if by_others == 1 else 1.0
    return o, b, counts


def documentation(area: AreaObs) -> tuple[Signal, list[str]]:
    if not area.docs_family_included:
        return None, list(REQUIRED_DOC_FACETS)  # not imported is unknown, never "missing"
    if not area.doc_facets:
        return 1.0, list(REQUIRED_DOC_FACETS)
    best = max(area.doc_facets, key=lambda f: len(f & set(REQUIRED_DOC_FACETS)))
    missing = [f for f in REQUIRED_DOC_FACETS if f not in best]
    return (0.0 if not missing else 0.5), missing


def confidence(area: AreaObs, attributable: int) -> str:
    events = len(area.events)
    all_attributed = events > 0 and attributable == events
    if (
        area.record_count >= 4
        and len(area.source_families) >= 3
        and events >= 3
        and all_attributed
        and not area.contradiction
    ):
        return "high"
    if len(area.source_families) >= 2 and attributable >= MIN_ATTRIBUTABLE_EVENTS:
        return "medium"
    return "low"


def score_area(area: AreaObs, selected: str) -> ScoreResult:
    a = three_level(len(area.events))
    m = three_level(sum(1 for e in area.events if e.manual))
    o, b, counts = participation(area.events, selected)
    d, missing = documentation(area)
    signals: dict[str, Signal] = {"A": a, "D": d, "O": o, "M": m, "B": b}
    counts.update(
        {
            "distinct_events": len(area.events),
            "manual_events": sum(1 for e in area.events if e.manual),
            "linked_records": area.record_count,
            "relevant_documents": len(area.doc_facets),
        }
    )
    conf = confidence(area, counts["attributable_events"])  # type: ignore[arg-type]
    unknown = [k for k, v in signals.items() if v is None]
    raw = None if unknown else raw_score(signals)

    def result(status: str, priority: int | None, reasons: list[str]) -> ScoreResult:
        return ScoreResult(signals, counts, raw, priority, status, conf, reasons, missing)

    if area.contradiction:
        return result("review_required", None, ["Evidence contains a material contradiction."])
    if unknown:
        return result(
            "insufficient", None, [f"Unknown signal(s): {', '.join(unknown)}; no number is shown."]
        )
    if conf == "low":
        return result("insufficient", None, ["Evidence confidence is low; no number is shown."])
    if d == 0:
        return result(
            "adequately_covered",
            None,
            ["Supplied documentation covers the required procedural facets."],
        )
    if o == 0:
        return result(
            "not_prioritized",
            None,
            ["Selected engineer performed under half of the attributable events."],
        )
    reasons = []
    if o is not None and o < 1:
        reasons.append(CAP_REASON_PARTICIPATION)
    if b == 0:
        reasons.append(CAP_REASON_ALTERNATE_RECOVERY)
    assert raw is not None
    priority = round_half_up(min(raw, CAP) if reasons else raw)
    return result("ranked", priority, reasons)


def rank(results: dict[str, ScoreResult]) -> list[str]:
    ranked = [k for k, r in results.items() if r.eligibility_status == "ranked"]
    ranked.sort(key=lambda k: (-(results[k].review_priority or 0), k))
    return ranked[:MAX_RANKED]
