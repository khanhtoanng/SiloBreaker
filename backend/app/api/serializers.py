from app.models import (
    Analysis,
    Attempt,
    AttemptReview,
    EvidenceBundle,
    EvidenceChunk,
    EvidenceItem,
    Exercise,
    Finding,
    Handoff,
    KnowledgeDraft,
    KnowledgeVersion,
    Operation,
)
from app.scoring.rules import CAP, WEIGHTS

# Viewers who may see the private rubric and assessor details.
FULL_VIEW = ("expert", "admin")


def bundle_out(
    b: EvidenceBundle, people: list[dict] | None = None, item_count: int | None = None
) -> dict:
    return {
        "id": str(b.id),
        "project_key": b.project_key,
        "content_hash": b.content_hash,
        "schema_version": b.schema_version,
        "source_inventory": b.source_inventory,
        "coverage_start": b.coverage_start,
        "coverage_end": b.coverage_end,
        "import_complete": b.import_complete,
        "item_count": item_count,
        "people": people or [],
    }


def handoff_out(h: Handoff, viewer: str | None = None) -> dict:
    out = {
        "id": str(h.id),
        "project_key": h.project_key,
        "bundle_id": str(h.bundle_id),
        "expert_id": h.expert_id,
        "successor_id": h.successor_id,
        "status": h.status,
        "max_attempts": h.max_attempts,
        "created_at": h.created_at,
    }
    if viewer in FULL_VIEW and h.candidates:
        # The expert sees aliases only until the admin has selected.
        hide = viewer == "expert" and h.status == "selecting"
        out["candidates"] = [
            {"alias": c.alias}
            if hide
            else {
                "alias": c.alias,
                "person_id": c.person_id,
                "study_opened_at": c.study_opened_at,
            }
            for c in h.candidates
        ]
    return out


def contributions(signals: dict) -> dict:
    """Per-signal points (value x weight) for display; unknown signals stay null."""
    return {
        k: None if signals.get(k) is None else w * float(signals[k]) for k, w in WEIGHTS.items()
    }


def finding_out(f: Finding, prior: dict | None = None) -> dict:
    sv = f.signal_values
    return {
        "id": str(f.id),
        "analysis_id": str(f.analysis_id),
        "area_key": f.area_key,
        "title": f.title,
        "summary": f.summary,
        "question": f.question,
        "signals": sv["signals"],
        "counts": sv["counts"],
        "raw_score": sv["raw"],
        "weights": dict(WEIGHTS),
        "contributions": contributions(sv["signals"]),
        "cap": CAP,
        "reasons": sv["reasons"],
        "missing_facets": sv["missing_facets"],
        "top_candidate": sv.get("top_candidate", False),
        "review_priority": f.review_priority,
        "evidence_confidence": f.evidence_confidence,
        "eligibility_status": f.eligibility_status,
        "status": f.status,
        "status_reason": f.status_reason,
        "revision": f.revision,
        "evidence_refs": f.evidence_refs,
        "prior_knowledge": prior,
    }


def analysis_out(
    a: Analysis, findings: list[Finding], priors: dict[str, dict | None] | None = None
) -> dict:
    priors = priors or {}
    order = {
        "ranked": 0,
        "review_required": 1,
        "adequately_covered": 2,
        "not_prioritized": 3,
        "insufficient": 4,
    }
    findings = sorted(
        findings,
        key=lambda f: (order.get(f.eligibility_status, 9), -(f.review_priority or 0), f.area_key),
    )
    return {
        "id": str(a.id),
        "handoff_id": str(a.handoff_id),
        "bundle_hash": a.bundle_hash,
        "selected_engineer_id": a.selected_engineer_id,
        "model_id": a.model_id,
        "prompt_version": a.prompt_version,
        "schema_version": a.schema_version,
        "scoring_version": a.scoring_version,
        "status": a.status,
        "rejected_areas": a.extraction.get("rejected", []),
        "reused_extraction_from": a.extraction.get("reused_from_analysis"),
        "created_at": a.created_at,
        "findings": [finding_out(f, priors.get(str(f.id))) for f in findings],
    }


def chunk_out(c: EvidenceChunk, item: EvidenceItem) -> dict:
    return {
        "chunk_id": str(c.id),
        "ordinal": c.ordinal,
        "line_start": c.line_start,
        "line_end": c.line_end,
        "text": c.text,
        "text_hash": c.text_hash,
        "item": item_out(item),
    }


def item_out(i: EvidenceItem) -> dict:
    return {
        "id": str(i.id),
        "source": i.source,
        "source_type": i.source_type,
        "external_id": i.external_id,
        "parent_external_id": i.parent_external_id,
        "author_id": i.author_id,
        "author_display_name": i.author_display_name,
        "occurred_at": i.occurred_at,
        "title": i.title,
        "text": i.normalized_text,
        "url": i.source_url,
    }


def draft_out(d: KnowledgeDraft | None) -> dict | None:
    if d is None:
        return None
    return {
        "id": str(d.id),
        "finding_id": str(d.finding_id),
        "revision": d.revision,
        "content": d.content,
        "author_id": d.author_id,
        "updated_at": d.updated_at,
    }


def version_out(v: KnowledgeVersion) -> dict:
    return {
        "id": str(v.id),
        "finding_id": str(v.finding_id),
        "version_no": v.version_no,
        "draft_revision": v.draft_revision,
        "approved_content": v.approved_content,
        "approved_by": v.approved_by,
        "approved_at": v.approved_at,
        "content_hash": v.content_hash,
        "supersedes_version_id": str(v.supersedes_version_id) if v.supersedes_version_id else None,
        "source_refs": v.source_refs,
    }


# ---------- verify ----------
# The successor view is built from an allow-list of fields. It never includes the rubric;
# criterion-level feedback appears only on an attempt whose assessment has completed.


def _results(attempt: Attempt, rubric: list[dict], expert: bool) -> list[dict] | None:
    if attempt.assessment_status != "succeeded" or attempt.criterion_results is None:
        return None
    by_id = {c["id"]: c for c in rubric}
    out = []
    for m in attempt.criterion_results:
        c = by_id.get(m["criterion_id"], {})
        row = {
            "criterion_id": m["criterion_id"],
            "text": c.get("text", ""),
            "verdict": m["verdict"],
            "evidence_quote": m["evidence_quote"],
        }
        if expert:
            row |= {"critical": c.get("critical", False), "source_path": c.get("source_path")}
        out.append(row)
    return out


def review_out(r: AttemptReview | None) -> dict | None:
    if r is None:
        return None
    return {
        "requested_at": r.requested_at,
        "overrides": r.overrides,
        "reason": r.reason,
        "reviewed_by": r.reviewed_by,
        "reviewed_at": r.reviewed_at,
    }


def attempt_out(
    a: Attempt,
    exercise: Exercise,
    version: KnowledgeVersion,
    viewer: str,
    label: str | None = None,
    review: AttemptReview | None = None,
    effective_result: str | None = None,
    score_pct: int | None = None,
) -> dict:
    """`label` replaces the learner's person_id (a candidate alias for the expert)."""
    out = {
        "id": str(a.id),
        "exercise_id": str(a.exercise_id),
        "knowledge_version_id": str(version.id),
        "knowledge_version_no": version.version_no,
        "successor_id": label or a.successor_id,
        "answer": a.answer,
        "assessment_status": a.assessment_status,
        "assessment_error": a.assessment_error,
        "aggregate_result": a.aggregate_result,
        "effective_result": effective_result or a.aggregate_result,
        # Weighted criterion credit computed by app.verify.selection; null until assessed.
        "score_pct": score_pct,
        "review": review_out(review),
        "results": _results(a, exercise.rubric, viewer in FULL_VIEW),
        "created_at": a.created_at,
        "assessed_at": a.assessed_at,
    }
    if viewer in FULL_VIEW:
        out["assessor_id"] = a.assessor_id
    return out


def exercise_out(
    e: Exercise,
    version: KnowledgeVersion,
    viewer: str,
    attempts: list[Attempt],
    extras: dict | None = None,
    candidate: dict | None = None,
) -> dict:
    """`extras` maps an attempt id to the keyword arguments of attempt_out. `candidate` is the
    viewer's own place in a successor selection (count, due time, attempts left)."""
    extras = extras or {}
    out = {
        "id": str(e.id),
        "knowledge_version_id": str(version.id),
        "knowledge_version_no": version.version_no,
        "status": e.status,
        "scenario": e.scenario,
        "approved_at": e.approved_at,
        "viewer_role": viewer,
        "attempts": [attempt_out(a, e, version, viewer, **extras.get(a.id, {})) for a in attempts],
        "candidate": candidate,
    }
    if viewer in FULL_VIEW:
        out |= {
            "revision": e.revision,
            "approved_by": e.approved_by,
            "generator_id": e.generator_id,
            "criteria": e.rubric,
        }
    return out


def operation_out(o: Operation) -> dict:
    return {
        "id": str(o.id),
        "kind": o.kind,
        "state": o.state,
        "result_type": o.result_type,
        "result_id": str(o.result_id) if o.result_id else None,
        "error_code": o.error_code,
        "error_detail": o.error_detail,
        "started_at": o.started_at,
        "finished_at": o.finished_at,
    }
