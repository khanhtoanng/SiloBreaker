"""Fair successor selection among 2-4 candidates of one handoff.

Every rule here is application code: the assessor only proposes criterion verdicts, the
group of a candidate comes from app.verify.rules.aggregate over (verdicts + expert review
overrides), and only the admin selects. Two numbers support the admin, neither decides:

- Fit (Suitability, before any assessment): how much of the handoff's ranked review
  priority a person has recovered before, from cited events in the stored extraction.
  It is used to shortlist, never to choose.
- Score (Results, after the common assessment): weighted criterion credit of the best
  effective attempt. The top is ranked by aggregate result first, then by score.
"""

import random
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit import audit
from app.errors import AppError
from app.models import (
    Analysis,
    AppUser,
    Attempt,
    AttemptReview,
    Exercise,
    Finding,
    Handoff,
    HandoffCandidate,
    KnowledgeVersion,
    SuccessorSelection,
)
from app.scoring.rules import round_half_up
from app.verify.contract import Criterion, CriterionMatch
from app.verify.rules import aggregate

MIN_CANDIDATES, MAX_CANDIDATES = 2, 4
ALIASES = ("Candidate A", "Candidate B", "Candidate C", "Candidate D")
OVERRIDE_VERDICTS = ("met", "partial", "unmet")

# Best attempt first: a result that still needs review beats a clear not_yet.
RESULT_ORDER = {"demonstrated": 3, "partial": 2, "review_required": 1, "not_yet": 0}
GROUPS = {"demonstrated": "ready", "partial": "ready_with_support", "not_yet": "not_yet"}
GROUP_LABELS = {
    "ready": "Ready",
    "ready_with_support": "Ready with support",
    "not_yet": "Not yet",
    "pending": "Pending",
}
GROUP_RANK = {"ready": 3, "ready_with_support": 2, "not_yet": 1}

# Score: critical criteria weigh twice as much; partial earns half the credit.
CRITICAL_WEIGHT, NORMAL_WEIGHT = 2, 1
CREDIT = {"met": 1.0, "partial": 0.5, "unmet": 0.0, "uncertain": 0.0}
# Only these results are ranked; review_required and "not submitted" are warnings instead.
RANKED_RESULTS = ("demonstrated", "partial", "not_yet")
# The top comes from the best of these groups; nobody who missed a critical condition is top.
TOP_RESULTS = ("demonstrated", "partial")
COMMON_ASSESSMENT_ATTEMPTS = 1


# ---------- pure rules ----------


def assign_aliases(person_ids: list[str], seed: str) -> dict[str, str]:
    """A seeded shuffle of the pool. Sorting first means the order the admin typed the
    candidates in does not leak into who becomes Candidate A."""
    order = sorted(person_ids)
    random.Random(f"{seed}:{','.join(order)}").shuffle(order)
    return {pid: ALIASES[i] for i, pid in enumerate(order)}


def effective_matches(
    criterion_results: list[dict], overrides: dict[str, str] | None
) -> list[CriterionMatch]:
    """The assessor's verdicts with the expert's review overrides applied."""
    overrides = overrides or {}
    return [
        CriterionMatch.model_validate(
            m | {"verdict": overrides.get(m["criterion_id"], m["verdict"])}
        )
        for m in criterion_results
    ]


def group_of(result: str | None) -> str:
    return GROUPS.get(result or "", "pending")


def recommend(groups: dict[str, str]) -> list[str]:
    """Everyone in the highest group anyone reached; pending is not a group to rank."""
    ranked = {pid: GROUP_RANK[g] for pid, g in groups.items() if g in GROUP_RANK}
    if not ranked:
        return []
    top = max(ranked.values())
    return sorted(pid for pid, r in ranked.items() if r == top)


def experience(incidents: int) -> float:
    """0 if never the resolver, 0.5 for one cited recovery, 1 from two."""
    return 0.0 if incidents <= 0 else 0.5 if incidents == 1 else 1.0


def fit_pct(priorities: dict[str, int], incidents: dict[str, int]) -> int | None:
    """sum(review_priority x experience) / sum(review_priority) x 100 over ranked areas.
    None means no history in those areas, which is not the same as 0%."""
    total = sum(priorities.values())
    got = sum(rp * experience(incidents.get(area, 0)) for area, rp in priorities.items())
    if total <= 0 or got <= 0:
        return None
    return round_half_up(100 * got / total)


def score_pct(criteria: list[Criterion], matches: list[CriterionMatch]) -> int:
    weight = {c.id: CRITICAL_WEIGHT if c.critical else NORMAL_WEIGHT for c in criteria}
    total = sum(weight.values())
    got = sum(
        weight[m.criterion_id] * CREDIT[m.verdict] for m in matches if m.criterion_id in weight
    )
    return round_half_up(100 * got / total) if total else 0


def top_of(entries: dict[str, tuple[str | None, int | None]]) -> tuple[list[str], bool]:
    """(top_ids, tie) from {person: (effective result, score)}: the best result group among
    demonstrated > partial, then the highest score in it. Empty if nobody reached partial."""
    group = next((r for r in TOP_RESULTS if any(res == r for res, _ in entries.values())), None)
    if group is None:
        return [], False
    scores = {pid: score or 0 for pid, (res, score) in entries.items() if res == group}
    best = max(scores.values())
    top = sorted(pid for pid, sc in scores.items() if sc == best)
    return top, len(top) >= 2


# ---------- reads ----------


def handoff_exercises(session: Session, handoff: Handoff) -> list[Exercise]:
    return list(
        session.scalars(
            select(Exercise)
            .join(KnowledgeVersion, Exercise.knowledge_version_id == KnowledgeVersion.id)
            .join(Finding, KnowledgeVersion.finding_id == Finding.id)
            .join(Analysis, Finding.analysis_id == Analysis.id)
            .where(Analysis.handoff_id == handoff.id)
        ).all()
    )


def current_exercise(session: Session, handoff: Handoff) -> Exercise | None:
    """The exercise candidates are compared on: the common assessment's, or else the most
    recently released one."""
    if handoff.assessment_exercise_id is not None:
        return session.get(Exercise, handoff.assessment_exercise_id)
    ready = [e for e in handoff_exercises(session, handoff) if e.status == "ready"]
    return max(ready, key=lambda e: e.approved_at, default=None)


def review_of(session: Session, attempt: Attempt) -> AttemptReview | None:
    return session.scalar(select(AttemptReview).where(AttemptReview.attempt_id == attempt.id))


def effective_result(
    attempt: Attempt, exercise: Exercise, review: AttemptReview | None
) -> str | None:
    """The attempt's result after an expert review, recomputed by aggregate()."""
    if attempt.assessment_status != "succeeded":
        return None
    if review is None or review.reviewed_at is None:
        return attempt.aggregate_result
    criteria = [Criterion.model_validate(c) for c in exercise.rubric]
    return aggregate(criteria, effective_matches(attempt.criterion_results, review.overrides))


def effective_score(
    attempt: Attempt, exercise: Exercise, review: AttemptReview | None
) -> int | None:
    if attempt.assessment_status != "succeeded":
        return None
    overrides = review.overrides if review is not None and review.reviewed_at else None
    criteria = [Criterion.model_validate(c) for c in exercise.rubric]
    return score_pct(criteria, effective_matches(attempt.criterion_results, overrides))


def latest_analysis(session: Session, handoff: Handoff) -> Analysis | None:
    return session.scalar(
        select(Analysis)
        .where(Analysis.handoff_id == handoff.id, Analysis.status == "succeeded")
        .order_by(Analysis.created_at.desc())
        .limit(1)
    )


def resolved_incidents(analysis: Analysis, area_keys: set[str]) -> dict[str, dict[str, set]]:
    """{person: {area: event keys}} for cited events of kept areas (findings exist only for
    areas whose citations passed validation)."""
    out: dict[str, dict[str, set]] = {}
    for area in analysis.extraction.get("proposal", {}).get("areas", []):
        if area["key"] not in area_keys:
            continue
        for e in area.get("events", []):
            if e.get("resolver_id"):
                out.setdefault(e["resolver_id"], {}).setdefault(area["key"], set()).add(e["key"])
    return out


def attempts_used(session: Session, exercise_id, person_id: str) -> int:
    """Attempts that count toward the limit. A failed one (a system error) never counts."""
    return session.scalar(
        select(func.count()).where(
            Attempt.exercise_id == exercise_id,
            Attempt.successor_id == person_id,
            Attempt.assessment_status != "failed",
        )
    )


# ---------- candidate rules for attempts ----------


def check_can_attempt(session: Session, handoff: Handoff, exercise: Exercise, actor: str) -> None:
    """Candidates answer the common assessment's exercise before it is due, after opening
    the study material, and get max_attempts results."""
    candidate = handoff.candidate(actor)
    if candidate is None:
        return
    if handoff.assessment_exercise_id and exercise.id != handoff.assessment_exercise_id:
        raise AppError(
            409, "not_assessment_exercise", "candidates answer the common assessment's exercise"
        )
    if handoff.assessment_due_at and datetime.now(UTC) > handoff.assessment_due_at:
        raise AppError(409, "assessment_closed", "the common assessment is past its due time")
    if candidate.study_opened_at is None:
        raise AppError(409, "study_required", "open the study material before answering")
    if attempts_used(session, exercise.id, actor) >= handoff.max_attempts:
        raise AppError(
            409, "attempt_limit", f"each candidate has {handoff.max_attempts} assessed attempts"
        )


def check_can_reassess(session: Session, handoff: Handoff, attempt: Attempt) -> None:
    """Reassessing a failed attempt must not give a candidate one result too many."""
    if handoff.candidate(attempt.successor_id) is None:
        return
    if attempts_used(session, attempt.exercise_id, attempt.successor_id) >= handoff.max_attempts:
        raise AppError(
            409, "attempt_limit", f"each candidate has {handoff.max_attempts} assessed attempts"
        )


def open_study(session: Session, handoff: Handoff, actor: str) -> HandoffCandidate:
    candidate = handoff.candidate(actor)
    if candidate is None:
        raise AppError(403, "not_candidate", "only a candidate of a selecting handoff may do this")
    if candidate.study_opened_at is None:
        candidate.study_opened_at = datetime.now(UTC)
        session.flush()
        audit(session, handoff.id, actor, "study.opened", "handoff_candidate", candidate.id)
    return candidate


# ---------- review (phúc khảo) ----------


def request_review(
    session: Session, attempt: Attempt, handoff: Handoff, actor: str
) -> AttemptReview:
    if attempt.successor_id != actor:
        raise AppError(403, "not_owner", "this attempt belongs to someone else")
    if attempt.assessment_status != "succeeded":
        raise AppError(409, "not_assessed", "only an assessed attempt can be reviewed")
    if review_of(session, attempt) is not None:
        raise AppError(409, "review_already_requested", "a review was already requested")
    review = AttemptReview(attempt_id=attempt.id, requested_at=datetime.now(UTC))
    session.add(review)
    session.flush()
    audit(session, handoff.id, actor, "attempt.review_requested", "attempt", attempt.id)
    return review


def review_attempt(
    session: Session,
    attempt: Attempt,
    exercise: Exercise,
    handoff: Handoff,
    overrides: dict[str, str],
    reason: str,
    actor: str,
) -> AttemptReview:
    if not reason.strip():
        raise AppError(422, "reason_required", "a review needs a reason")
    known = {c["id"] for c in exercise.rubric}
    if not overrides:
        raise AppError(422, "invalid_overrides", "a review changes at least one criterion")
    for cid, verdict in overrides.items():
        if cid not in known:
            raise AppError(422, "invalid_overrides", f"unknown criterion {cid}")
        if verdict not in OVERRIDE_VERDICTS:
            raise AppError(
                422, "invalid_overrides", f"{cid}: verdict must be one of met, partial, unmet"
            )
    review = review_of(session, attempt)
    if review is None:
        raise AppError(409, "review_not_requested", "the learner has not requested a review")
    if review.reviewed_at is not None:
        raise AppError(409, "already_reviewed", "this attempt was already reviewed")
    review.overrides = dict(overrides)
    review.reason = reason.strip()
    review.reviewed_by = actor
    review.reviewed_at = datetime.now(UTC)
    session.flush()
    audit(
        session,
        handoff.id,
        actor,
        "attempt.reviewed",
        "attempt",
        attempt.id,
        metadata={
            "overrides": review.overrides,
            "original_result": attempt.aggregate_result,
            "effective_result": effective_result(attempt, exercise, review),
        },
    )
    return review


# ---------- readiness and selection ----------


def candidate_context(session: Session, handoff: Handoff) -> dict[str, dict]:
    """Incidents each person recovered in the handoff's areas, from the stored extraction
    of the latest analysis. Shown for context only: it is never part of the group."""
    analysis = latest_analysis(session, handoff)
    by_person: dict[str, dict[str, set]] = {}
    if analysis is not None:
        keys = set(
            session.scalars(select(Finding.area_key).where(Finding.analysis_id == analysis.id))
        )
        by_person = resolved_incidents(analysis, keys)
    out = {}
    for c in handoff.candidates:
        areas = {k: len(v) for k, v in sorted(by_person.get(c.person_id, {}).items())}
        out[c.person_id] = {
            "recovered_incidents": sum(areas.values()),
            "by_area": areas,
            "analysis_id": str(analysis.id) if analysis else None,
            "scored": False,
            "note": "context only; not part of the group or the recommendation",
        }
    return out


def _names(session: Session, person_ids: list[str]) -> dict[str, str | None]:
    return dict(
        session.execute(
            select(AppUser.person_id, AppUser.display_name).where(AppUser.person_id.in_(person_ids))
        ).all()
    )


def decision_out(sel: SuccessorSelection | None) -> dict | None:
    if sel is None:
        return None
    return {
        "id": str(sel.id),
        "selected_person_id": sel.selected_person_id,
        "recommended": sel.recommended,
        "in_recommended": sel.in_recommended,
        "top_ids": sel.top_ids,
        "tie": sel.tie,
        "is_top": sel.is_top,
        "reason": sel.reason,
        "decided_by": sel.decided_by,
        "decided_at": sel.decided_at,
    }


def selection_of(session: Session, handoff: Handoff) -> SuccessorSelection | None:
    return session.scalar(
        select(SuccessorSelection).where(SuccessorSelection.handoff_id == handoff.id)
    )


def readiness(session: Session, handoff: Handoff) -> dict:
    if not handoff.candidates:
        raise AppError(409, "no_candidates", "this handoff has no candidate pool")
    exercise = current_exercise(session, handoff)
    context = candidate_context(session, handoff)
    names = _names(session, [c.person_id for c in handoff.candidates])
    rubric = {c["id"]: c for c in exercise.rubric} if exercise is not None else {}
    rows, warnings, groups, entries = [], [], {}, {}
    for c in handoff.candidates:
        best, used, review_open = None, 0, False
        if exercise is not None:
            attempts = session.scalars(
                select(Attempt)
                .where(Attempt.exercise_id == exercise.id, Attempt.successor_id == c.person_id)
                .order_by(Attempt.created_at)
            ).all()
            used = sum(a.assessment_status != "failed" for a in attempts)
            scored = []
            for a in attempts:
                review = review_of(session, a)
                review_open = review_open or (review is not None and review.reviewed_at is None)
                result = effective_result(a, exercise, review)
                if result is not None:
                    scored.append((a, result, review))
            # Highest result, then highest score; among equals the earliest (max keeps the first).
            best = max(
                scored,
                key=lambda s: (RESULT_ORDER[s[1]], effective_score(s[0], exercise, s[2])),
                default=None,
            )
        result = best[1] if best else None
        group = group_of(result)
        groups[c.person_id] = group
        criteria, score = None, None
        if best is not None:
            a, _, review = best
            score = effective_score(a, exercise, review)
            overrides = (review.overrides or {}) if review and review.reviewed_at else {}
            criteria = []
            for m in effective_matches(a.criterion_results, overrides):
                crit = rubric.get(m.criterion_id, {})
                critical = crit.get("critical", False)
                criteria.append(
                    {
                        "criterion_id": m.criterion_id,
                        "text": crit.get("text", ""),
                        "critical": critical,
                        "weight": CRITICAL_WEIGHT if critical else NORMAL_WEIGHT,
                        "verdict": m.verdict,
                        "overridden": m.criterion_id in overrides,
                    }
                )
        ranked = result in RANKED_RESULTS
        if ranked:
            entries[c.person_id] = (result, score)
        rows.append(
            {
                "person_id": c.person_id,
                "display_name": names.get(c.person_id),
                "alias": c.alias,
                "group": group,
                "group_label": GROUP_LABELS[group],
                "best_attempt_id": str(best[0].id) if best else None,
                "best_result": result,
                "score_pct": score,
                "ranked": ranked,
                "submitted": used > 0,
                "missing_critical": result == "not_yet",
                "criteria": criteria,
                "attempts_used": used,
                "max_attempts": handoff.max_attempts,
                "study_opened": c.study_opened_at is not None,
                "review_pending": review_open,
                "context": context[c.person_id],
            }
        )
        if best is None:
            warnings.append({"person_id": c.person_id, "code": "no_result"})
        elif group == "pending":
            warnings.append({"person_id": c.person_id, "code": "pending"})
        if review_open:
            warnings.append({"person_id": c.person_id, "code": "review_pending"})
    top_ids, tie = top_of(entries)
    if not top_ids and entries:
        warnings.append({"person_id": None, "code": "no_candidate_meets_all_critical"})
    if exercise is None:
        warnings.insert(0, {"person_id": None, "code": "no_released_exercise"})
    for row in rows:
        row["is_top"] = row["person_id"] in top_ids
    # Ranked first (result, then score), then everyone who cannot be ranked yet.
    rows.sort(
        key=lambda r: (
            not r["ranked"],
            -RESULT_ORDER.get(r["best_result"] or "", -1) if r["ranked"] else 0,
            -(r["score_pct"] or 0) if r["ranked"] else 0,
            r["alias"],
        )
    )
    return {
        "handoff_id": str(handoff.id),
        "status": handoff.status,
        "exercise_id": str(exercise.id) if exercise else None,
        "assessment": {
            "exercise_id": str(handoff.assessment_exercise_id)
            if handoff.assessment_exercise_id
            else None,
            "due_at": handoff.assessment_due_at,
            "started_at": handoff.assessment_started_at,
            "max_attempts": handoff.max_attempts,
        },
        "weights": {"critical": CRITICAL_WEIGHT, "normal": NORMAL_WEIGHT},
        "candidates": rows,
        "recommended": recommend(groups),
        "top_ids": top_ids,
        "tie": tie,
        "warnings": warnings,
        "decision": decision_out(selection_of(session, handoff)),
    }


def select_successor(
    session: Session, handoff: Handoff, person_id: str, reason: str | None, actor: str
) -> SuccessorSelection:
    if selection_of(session, handoff) is not None or handoff.status != "selecting":
        raise AppError(409, "already_selected", "a successor has already been selected")
    if handoff.candidate(person_id) is None:
        raise AppError(422, "not_candidate", f"'{person_id}' is not a candidate of this handoff")
    ready = readiness(session, handoff)
    recommended, top_ids, tie = ready["recommended"], ready["top_ids"], ready["tie"]
    is_top = person_id in top_ids
    reason = (reason or "").strip() or None
    # Anyone in the top needs no reason; anyone else (or anyone when nobody is top) does.
    if not is_top and reason is None:
        raise AppError(
            422, "reason_required", "selecting someone outside the top result needs a reason"
        )
    selection = SuccessorSelection(
        handoff_id=handoff.id,
        selected_person_id=person_id,
        recommended=recommended,
        in_recommended=person_id in recommended,
        top_ids=top_ids,
        tie=tie,
        is_top=is_top,
        reason=reason,
        decided_by=actor,
        decided_at=datetime.now(UTC),
    )
    session.add(selection)
    handoff.successor_id = person_id
    handoff.status = "active"
    session.flush()
    audit(
        session,
        handoff.id,
        actor,
        "successor.selected",
        "handoff",
        handoff.id,
        metadata={
            "selected_person_id": person_id,
            "recommended": recommended,
            "in_recommended": selection.in_recommended,
            "top_ids": top_ids,
            "tie": tie,
            "is_top": is_top,
            "reason": reason,
        },
    )
    return selection


# ---------- suitability, direct assignment, common assessment ----------


def suitability(session: Session, handoff: Handoff) -> dict:
    """Fit of every active member (except the expert) for the handoff's ranked areas."""
    analysis = latest_analysis(session, handoff)
    if analysis is None:
        raise AppError(409, "analysis_required", "run an analysis before checking suitability")
    findings = session.scalars(
        select(Finding).where(
            Finding.analysis_id == analysis.id,
            Finding.eligibility_status == "ranked",
            Finding.review_priority.is_not(None),
        )
    ).all()
    priorities = {f.area_key: f.review_priority for f in findings}
    titles = {f.area_key: f.title for f in findings}
    incidents = resolved_incidents(analysis, set(priorities))
    members = session.scalars(
        select(AppUser).where(
            AppUser.role == "member",
            AppUser.is_active.is_(True),
            AppUser.person_id.is_not(None),
            AppUser.person_id != handoff.expert_id,
        )
    ).all()
    rows = []
    for m in members:
        mine = incidents.get(m.person_id, {})
        fit = fit_pct(priorities, {a: len(keys) for a, keys in mine.items()})
        rows.append(
            {
                "person_id": m.person_id,
                "display_name": m.display_name,
                "fit_pct": fit,
                "fit_status": "scored" if fit is not None else "no_history",
                "basis": [
                    {
                        "area_key": area,
                        "title": titles[area],
                        "review_priority": priorities[area],
                        "incidents": sorted(mine[area]),
                        "experience": experience(len(mine[area])),
                    }
                    for area in sorted(priorities, key=lambda a: -priorities[a])
                    if mine.get(area)
                ],
            }
        )
    rows.sort(key=lambda r: (r["fit_pct"] is None, -(r["fit_pct"] or 0), r["person_id"]))
    released = []
    for e in handoff_exercises(session, handoff):
        if e.status != "ready":
            continue
        version = session.get(KnowledgeVersion, e.knowledge_version_id)
        finding = session.get(Finding, version.finding_id)
        released.append(
            {
                "id": str(e.id),
                "title": finding.title,
                "area_key": finding.area_key,
                "knowledge_version_no": version.version_no,
                "approved_at": e.approved_at,
            }
        )
    released.sort(key=lambda e: e["approved_at"], reverse=True)
    return {
        "handoff_id": str(handoff.id),
        "status": handoff.status,
        "analysis_id": str(analysis.id),
        "ranked_areas": [
            {"area_key": a, "title": titles[a], "review_priority": rp}
            for a, rp in sorted(priorities.items(), key=lambda kv: -kv[1])
        ],
        "total_priority": sum(priorities.values()),
        "members": rows,
        # What a common assessment can use: released exercises of this handoff, newest first.
        "released_exercises": released,
        "note": "Fit is based on cited recoveries in the evidence only. "
        "It is used to shortlist, not to choose.",
    }


def _require_unassigned(handoff: Handoff) -> None:
    if handoff.status != "unassigned":
        raise AppError(
            409, "invalid_transition", f"a {handoff.status} handoff already has its successor path"
        )


def assign_directly(session: Session, handoff: Handoff, person_id: str, actor: str) -> Handoff:
    _require_unassigned(handoff)
    handoff.successor_id = person_id
    handoff.status = "active"
    session.flush()
    audit(
        session,
        handoff.id,
        actor,
        "successor.assigned",
        "handoff",
        handoff.id,
        metadata={"successor_id": person_id},
    )
    return handoff


def start_assessment(
    session: Session,
    handoff: Handoff,
    candidate_ids: list[str],
    exercise: Exercise,
    due_at: datetime,
    seed: str,
    actor: str,
) -> Handoff:
    """Every candidate answers the same released exercise once, before due_at."""
    _require_unassigned(handoff)
    if exercise.status != "ready":
        raise AppError(409, "exercise_not_ready", "only a released exercise can be assessed")
    if due_at.tzinfo is None:
        raise AppError(422, "invalid_due_at", "due_at needs a time zone")
    now = datetime.now(UTC)
    if due_at <= now:
        raise AppError(422, "due_in_past", "the due time must be in the future")
    aliases = assign_aliases(candidate_ids, seed)
    session.add_all(
        HandoffCandidate(handoff_id=handoff.id, person_id=pid, alias=aliases[pid])
        for pid in candidate_ids
    )
    handoff.status = "selecting"
    handoff.max_attempts = COMMON_ASSESSMENT_ATTEMPTS
    handoff.assessment_exercise_id = exercise.id
    handoff.assessment_due_at = due_at
    handoff.assessment_started_at = now
    session.flush()
    session.expire(handoff, ["candidates"])
    audit(
        session,
        handoff.id,
        actor,
        "assessment.started",
        "handoff",
        handoff.id,
        metadata={
            "candidate_ids": candidate_ids,
            "exercise_id": str(exercise.id),
            "due_at": due_at.isoformat(),
            "max_attempts": COMMON_ASSESSMENT_ATTEMPTS,
        },
    )
    return handoff


def candidate_view(
    session: Session, handoff: Handoff, exercise: Exercise, person_id: str | None
) -> dict | None:
    """What a candidate sees about their own place in the selection. Never other people."""
    c = handoff.candidate(person_id)
    if c is None:
        return None
    used = attempts_used(session, exercise.id, c.person_id)
    is_assessment = handoff.assessment_exercise_id in (None, exercise.id)
    closed = bool(handoff.assessment_due_at and datetime.now(UTC) > handoff.assessment_due_at)
    return {
        "handoff_id": str(handoff.id),
        "alias": c.alias,
        "candidate_count": len(handoff.candidates),
        "due_at": handoff.assessment_due_at,
        "max_attempts": handoff.max_attempts,
        "attempts_used": used,
        "attempts_left": max(0, handoff.max_attempts - used) if is_assessment and not closed else 0,
        "study_opened": c.study_opened_at is not None,
        "is_assessment_exercise": is_assessment,
        "closed": closed,
    }
