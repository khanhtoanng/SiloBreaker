"""Successor selection phase 2: unassigned handoffs, Suitability (fit), direct assignment,
the common assessment (one official attempt, due time), score-based top and tie, and the
selection snapshot. Expected scores are recomputed from the assessor's own verdicts."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.db import get_session
from app.errors import AppError
from app.verify import selection as Sel
from app.verify import service as V
from app.verify.offline import OfflineAssessor
from tests.conftest import analyze, by_area, create_member, login_as

EXPERT = "alice"
POOL = ["bob", "carol", "minh"]


# ---------- helpers ----------


def create_unassigned(client):
    r = login_as(client, "admin").post(
        "/api/handoffs", json={"bundle_id": client.bundle["id"], "expert_id": EXPERT}
    )
    assert r.status_code == 201, r.text
    return r.json()


def due(hours=24):
    return (datetime.now(UTC) + timedelta(hours=hours)).isoformat()


def start(client, handoff_id, exercise_id, candidates=POOL, due_at=None):
    return login_as(client, "admin").post(
        f"/api/handoffs/{handoff_id}/assessment",
        json={"candidate_ids": candidates, "exercise_id": exercise_id, "due_at": due_at or due()},
    )


def submit(client, ex_id, answer, actor):
    return login_as(client, actor).post(
        f"/api/exercises/{ex_id}/attempts",
        json={"answer": answer},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )


def study(client, handoff_id, actor):
    r = login_as(client, actor).post(f"/api/handoffs/{handoff_id}/study-opened")
    assert r.status_code == 200, r.text


def readiness(client, handoff_id):
    r = login_as(client, "admin").get(f"/api/handoffs/{handoff_id}/readiness")
    assert r.status_code == 200, r.text
    return r.json()


def released_exercise(client, oracle, handoff):
    """Alice confirms settlement, approves v1 and releases an exercise. Leaves alice signed in."""
    f = by_area(analyze(client, handoff))["settlement"]
    f = client.post(
        f"/api/findings/{f['id']}/review",
        json={"action": "confirm", "expected_revision": f["revision"]},
    ).json()
    d = client.put(
        f"/api/findings/{f['id']}/draft", json={"content": oracle["expert_capture"]["content"]}
    ).json()
    v = client.post(
        f"/api/findings/{f['id']}/publish",
        json={"expected_finding_revision": f["revision"], "draft_revision": d["revision"]},
    ).json()
    ex = client.post(f"/api/knowledge/{v['id']}/exercises").json()
    ex = client.post(
        f"/api/exercises/{ex['id']}/approve", json={"expected_revision": ex["revision"]}
    ).json()
    return v, ex


def expected_score(exercise: dict, attempt: dict) -> int:
    """The documented formula, applied to the assessor's verdicts as the expert sees them:
    critical weight 2, other 1; met 1, partial 0.5, unmet 0; rounded half up."""
    critical = {c["id"]: c["critical"] for c in exercise["criteria"]}
    credit = {"met": 1.0, "partial": 0.5, "unmet": 0.0, "uncertain": 0.0}
    weights = {cid: 2 if crit else 1 for cid, crit in critical.items()}
    got = sum(weights[r["criterion_id"]] * credit[r["verdict"]] for r in attempt["results"])
    return int(100 * got / sum(weights.values()) + 0.5)


@pytest.fixture
def unassigned(client, oracle):
    h = create_unassigned(client)
    v, ex = released_exercise(client, oracle, h)
    return {"handoff": h, "version": v, "exercise": ex}


@pytest.fixture
def assessed(client, unassigned, oracle):
    """Common assessment for bob (correct), carol (partial_answer), minh (unsafe)."""
    h, ex = unassigned["handoff"], unassigned["exercise"]
    assert start(client, h["id"], ex["id"]).status_code == 201
    answers = oracle["successor_answers"]
    attempts = {}
    for who, key in (
        ("bob", "correct_paraphrase"),
        ("carol", "partial_answer"),
        ("minh", "unsafe"),
    ):
        study(client, h["id"], who)
        r = submit(client, ex["id"], answers[key], who)
        assert r.status_code == 201, r.text
        attempts[who] = r.json()
    return unassigned | {"attempts": attempts}


# ---------- unassigned handoff ----------


def test_handoff_can_be_created_without_a_successor(client):
    h = create_unassigned(client)
    assert h["status"] == "unassigned" and h["successor_id"] is None
    assert login_as(client, EXPERT).get(f"/api/handoffs/{h['id']}").json()["viewer_role"] == (
        "expert"
    )
    assert login_as(client, "bob").get(f"/api/handoffs/{h['id']}").status_code == 403
    session = next(get_session())
    try:
        with pytest.raises(Exception, match="ck_handoff_successor_when_active"):
            session.execute(text("update handoff set status='active' where id=:i"), {"i": h["id"]})
        session.rollback()
    finally:
        session.close()


# ---------- suitability (fit) ----------


def test_fit_formula():
    assert [Sel.experience(n) for n in (0, 1, 2, 5)] == [0.0, 0.5, 1.0, 1.0]
    priorities = {"settlement": 88, "webhooks": 60}
    assert Sel.fit_pct(priorities, {"webhooks": 1}) == 20  # 60 x 0.5 / 148 = 20.27
    assert Sel.fit_pct(priorities, {"settlement": 2, "webhooks": 1}) == 80  # 118 / 148 = 79.7
    assert Sel.fit_pct(priorities, {}) is None
    assert Sel.fit_pct(priorities, {"certificates": 3}) is None  # not a ranked area
    assert Sel.fit_pct({}, {"webhooks": 1}) is None


def test_suitability_fits_bob_carol_and_no_history_for_minh(client):
    h = create_unassigned(client)
    r = login_as(client, "admin").get(f"/api/handoffs/{h['id']}/suitability")
    assert r.status_code == 409 and r.json()["error"]["code"] == "analysis_required"
    analyze(client, h)
    s = login_as(client, "admin").get(f"/api/handoffs/{h['id']}/suitability").json()
    assert [(a["area_key"], a["review_priority"]) for a in s["ranked_areas"]] == [
        ("settlement", 88),
        ("webhooks", 60),
    ]
    assert s["total_priority"] == 148
    fit = {m["person_id"]: m for m in s["members"]}
    assert EXPERT not in fit
    assert (fit["bob"]["fit_pct"], fit["carol"]["fit_pct"], fit["minh"]["fit_pct"]) == (
        20,
        20,
        None,
    )
    assert fit["minh"]["fit_status"] == "no_history" and fit["minh"]["basis"] == []
    basis = fit["bob"]["basis"]
    assert [(b["area_key"], b["experience"], len(b["incidents"])) for b in basis] == [
        ("webhooks", 0.5, 1)
    ]
    assert basis[0]["incidents"][0].startswith("PAY-")
    assert [m["person_id"] for m in s["members"]][-1] == "minh"  # no history sorts last
    assert "not to choose" in s["note"]
    assert s["released_exercises"] == []


def test_suitability_lists_released_exercises_for_the_assessment(client, unassigned):
    h, ex = unassigned["handoff"], unassigned["exercise"]
    # A draft exercise is not offered.
    login_as(client, EXPERT).post(f"/api/knowledge/{unassigned['version']['id']}/exercises")
    s = login_as(client, "admin").get(f"/api/handoffs/{h['id']}/suitability").json()
    assert [
        (e["id"], e["area_key"], e["knowledge_version_no"]) for e in s["released_exercises"]
    ] == [(ex["id"], "settlement", 1)]


def test_only_admin_reads_suitability(client):
    h = create_unassigned(client)
    analyze(client, h)
    for user in (EXPERT, "bob"):
        assert login_as(client, user).get(f"/api/handoffs/{h['id']}/suitability").status_code == (
            403
        )


# ---------- direct assignment ----------


def test_assign_directly(client):
    h = create_unassigned(client)
    admin = login_as(client, "admin")
    r = admin.post(f"/api/handoffs/{h['id']}/assign", json={"successor_id": EXPERT})
    assert r.status_code == 422 and r.json()["error"]["code"] == "same_person"
    r = admin.post(f"/api/handoffs/{h['id']}/assign", json={"successor_id": "minh"})
    assert r.status_code == 200 and r.json()["status"] == "active"
    assert r.json()["successor_id"] == "minh"
    r = admin.post(f"/api/handoffs/{h['id']}/assign", json={"successor_id": "bob"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "invalid_transition"
    events = admin.get("/api/admin/audit", params={"action": "successor.assigned"}).json()
    assert [e["metadata"]["successor_id"] for e in events["items"]] == ["minh"]
    assert login_as(client, "bob").post(
        f"/api/handoffs/{h['id']}/assign", json={"successor_id": "bob"}
    ).status_code == (403)


# ---------- starting the common assessment ----------


def test_start_assessment_validation(client, unassigned, oracle):
    h, ex = unassigned["handoff"], unassigned["exercise"]
    r = start(client, h["id"], ex["id"], ["bob"])
    assert r.status_code == 422 and r.json()["error"]["code"] == "candidate_count"
    r = start(client, h["id"], ex["id"], ["bob", EXPERT])
    assert r.status_code == 422 and r.json()["error"]["code"] == "same_person"
    r = start(client, h["id"], ex["id"], due_at=due(-1))
    assert r.status_code == 422 and r.json()["error"]["code"] == "due_in_past"
    # A draft exercise is not released yet.
    draft = login_as(client, EXPERT).post(f"/api/knowledge/{unassigned['version']['id']}/exercises")
    r = start(client, h["id"], draft.json()["id"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "exercise_not_ready"
    # An exercise of another handoff.
    other = create_unassigned(client)
    _, other_ex = released_exercise(client, oracle, other)
    r = start(client, h["id"], other_ex["id"])
    assert r.status_code == 422 and r.json()["error"]["code"] == "exercise_not_in_handoff"
    for user in (EXPERT, "bob"):
        r = login_as(client, user).post(
            f"/api/handoffs/{h['id']}/assessment",
            json={"candidate_ids": POOL, "exercise_id": ex["id"], "due_at": due()},
        )
        assert r.status_code == 403


def test_start_assessment_opens_a_one_attempt_selection(client, unassigned):
    h, ex = unassigned["handoff"], unassigned["exercise"]
    r = start(client, h["id"], ex["id"])
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["status"] == "selecting" and out["max_attempts"] == 1
    assert {c["person_id"] for c in out["candidates"]} == set(POOL)
    assert start(client, h["id"], ex["id"]).status_code == 409  # already started
    events = (
        login_as(client, "admin")
        .get("/api/admin/audit", params={"action": "assessment.started"})
        .json()
    )
    assert events["items"][0]["metadata"]["exercise_id"] == ex["id"]

    view = login_as(client, "carol").get(f"/api/exercises/{ex['id']}").json()
    c = view["candidate"]
    assert (c["candidate_count"], c["max_attempts"], c["attempts_left"]) == (3, 1, 1)
    assert c["study_opened"] is False and c["is_assessment_exercise"] is True
    assert c["due_at"] is not None and "Candidate" in c["alias"]
    assert "criteria" not in view and "critical" not in str(view)
    detail = client.get(f"/api/handoffs/{h['id']}").json()
    assert detail["candidate_count"] == 3 and detail["assessment_exercise_id"] == ex["id"]


class _FailingAssessor:
    model_id = "failing/1"

    def assess(self, *_):
        raise AppError(502, "provider_error", "provider unavailable")


def test_one_official_attempt_and_failed_does_not_count(client, unassigned, oracle, monkeypatch):
    h, ex = unassigned["handoff"], unassigned["exercise"]
    start(client, h["id"], ex["id"])
    study(client, h["id"], "bob")
    answer = oracle["successor_answers"]["correct_paraphrase"]
    monkeypatch.setattr(V, "get_assessor", lambda: _FailingAssessor())
    assert submit(client, ex["id"], answer, "bob").status_code == 502
    monkeypatch.setattr(V, "get_assessor", lambda: OfflineAssessor())
    ok = submit(client, ex["id"], answer, "bob")
    assert ok.status_code == 201 and ok.json()["score_pct"] == 100
    r = submit(client, ex["id"], answer, "bob")
    assert r.status_code == 409 and r.json()["error"]["code"] == "attempt_limit"
    view = login_as(client, "bob").get(f"/api/exercises/{ex['id']}").json()
    assert view["candidate"]["attempts_left"] == 0 and view["candidate"]["attempts_used"] == 1


def test_candidates_answer_only_the_assessment_exercise_before_it_is_due(
    client, unassigned, oracle
):
    h, ex = unassigned["handoff"], unassigned["exercise"]
    start(client, h["id"], ex["id"])
    # A second released exercise on the same knowledge is not the common assessment.
    other = login_as(client, EXPERT).post(f"/api/knowledge/{unassigned['version']['id']}/exercises")
    other = client.post(
        f"/api/exercises/{other.json()['id']}/approve",
        json={"expected_revision": other.json()["revision"]},
    ).json()
    study(client, h["id"], "minh")
    r = submit(client, other["id"], oracle["successor_answers"]["unsafe"], "minh")
    assert r.status_code == 409 and r.json()["error"]["code"] == "not_assessment_exercise"

    session = next(get_session())
    try:
        session.execute(
            text("update handoff set assessment_due_at = now() - interval '1 minute' where id=:i"),
            {"i": h["id"]},
        )
        session.commit()
    finally:
        session.close()
    r = submit(client, ex["id"], oracle["successor_answers"]["unsafe"], "minh")
    assert r.status_code == 409 and r.json()["error"]["code"] == "assessment_closed"
    view = login_as(client, "minh").get(f"/api/exercises/{ex['id']}").json()
    assert view["candidate"]["closed"] is True and view["candidate"]["attempts_left"] == 0


# ---------- results: score, top, tie ----------


def test_scores_top_and_critical_flags_come_from_the_assessor(client, assessed):
    h, ex = assessed["handoff"], assessed["exercise"]
    out = readiness(client, h["id"])
    rows = {c["person_id"]: c for c in out["candidates"]}
    for who in POOL:
        # Each score recomputed from the assessor's verdicts as the expert sees them.
        attempt = login_as(client, EXPERT).get(f"/api/attempts/{assessed['attempts'][who]['id']}")
        assert rows[who]["score_pct"] == expected_score(ex, attempt.json())
        assert assessed["attempts"][who]["score_pct"] == rows[who]["score_pct"]
    assert rows["bob"]["score_pct"] == 100
    assert rows["bob"]["score_pct"] > rows["carol"]["score_pct"] > rows["minh"]["score_pct"]
    assert [c["person_id"] for c in out["candidates"]] == ["bob", "carol", "minh"]
    assert out["top_ids"] == ["bob"] and out["tie"] is False
    assert [rows[p]["is_top"] for p in POOL] == [True, False, False]
    assert [rows[p]["missing_critical"] for p in POOL] == [False, False, True]
    assert all(rows[p]["ranked"] for p in POOL)
    assert out["warnings"] == []
    minh_c1 = next(c for c in rows["minh"]["criteria"] if c["criterion_id"] == "C1")
    assert minh_c1["critical"] is True and minh_c1["weight"] == 2 and minh_c1["text"]


def test_tie_lets_the_admin_pick_either_without_reason(client, unassigned, oracle):
    h, ex = unassigned["handoff"], unassigned["exercise"]
    start(client, h["id"], ex["id"], ["bob", "carol"])
    for who in ("bob", "carol"):
        study(client, h["id"], who)
        submit(client, ex["id"], oracle["successor_answers"]["correct_paraphrase"], who)
    out = readiness(client, h["id"])
    assert out["top_ids"] == ["bob", "carol"] and out["tie"] is True
    r = login_as(client, "admin").post(
        f"/api/handoffs/{h['id']}/selection", json={"selected_person_id": "carol"}
    )
    assert r.status_code == 201, r.text
    assert (r.json()["is_top"], r.json()["tie"], r.json()["top_ids"]) == (
        True,
        True,
        ["bob", "carol"],
    )
    assert r.json()["reason"] is None


def test_nobody_top_when_everyone_misses_a_critical_condition(client, unassigned, oracle):
    h, ex = unassigned["handoff"], unassigned["exercise"]
    start(client, h["id"], ex["id"], ["bob", "carol"])
    for who in ("bob", "carol"):
        study(client, h["id"], who)
        submit(client, ex["id"], oracle["successor_answers"]["unsafe"], who)
    out = readiness(client, h["id"])
    assert out["top_ids"] == [] and out["tie"] is False
    assert {"person_id": None, "code": "no_candidate_meets_all_critical"} in out["warnings"]
    admin = login_as(client, "admin")
    r = admin.post(f"/api/handoffs/{h['id']}/selection", json={"selected_person_id": "bob"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "reason_required"
    r = admin.post(
        f"/api/handoffs/{h['id']}/selection",
        json={"selected_person_id": "bob", "reason": "Only Bob is available on the rota."},
    )
    assert r.status_code == 201 and r.json()["is_top"] is False and r.json()["top_ids"] == []


def test_unsubmitted_and_review_required_are_not_ranked(client, unassigned, oracle):
    h, ex = unassigned["handoff"], unassigned["exercise"]
    start(client, h["id"], ex["id"])
    study(client, h["id"], "bob")
    submit(client, ex["id"], oracle["successor_answers"]["partial_answer"], "bob")
    # Carol's answer leaves the critical C1 only partly stated: review_required.
    c1_partial = oracle["successor_answers"]["correct_paraphrase"].replace(
        "If they already accepted or settled it I won't submit another one, I'll just "
        "reconcile ours.",
        "If AcmePay already accepted it, I just reconcile ours.",
    )
    study(client, h["id"], "carol")
    assert submit(client, ex["id"], c1_partial, "carol").json()["aggregate_result"] == (
        "review_required"
    )
    out = readiness(client, h["id"])
    rows = {c["person_id"]: c for c in out["candidates"]}
    assert out["top_ids"] == ["bob"]
    assert rows["carol"]["ranked"] is False and rows["carol"]["is_top"] is False
    assert rows["minh"]["ranked"] is False and rows["minh"]["submitted"] is False
    assert out["candidates"][0]["person_id"] == "bob"
    codes = {(w["person_id"], w["code"]) for w in out["warnings"]}
    assert {("carol", "pending"), ("minh", "no_result")} <= codes


# ---------- selection snapshot ----------


def test_selection_stores_top_snapshot_and_requires_reason_outside_top(client, assessed):
    h = assessed["handoff"]
    admin = login_as(client, "admin")
    r = admin.post(f"/api/handoffs/{h['id']}/selection", json={"selected_person_id": "carol"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "reason_required"
    reason = "Carol is staying on the payments team; Bob moves next month."
    r = admin.post(
        f"/api/handoffs/{h['id']}/selection",
        json={"selected_person_id": "carol", "reason": reason},
    )
    assert r.status_code == 201, r.text
    sel = r.json()
    assert (sel["top_ids"], sel["tie"], sel["is_top"], sel["reason"]) == (
        ["bob"],
        False,
        False,
        reason,
    )
    out = readiness(client, h["id"])
    assert out["decision"]["selected_person_id"] == "carol"
    assert out["decision"]["decided_by"] == "admin" and out["decision"]["decided_at"]
    meta = admin.get("/api/admin/audit", params={"action": "successor.selected"}).json()
    assert meta["items"][0]["metadata"]["is_top"] is False


def test_reset_clears_assessment_but_keeps_accounts(client, assessed):
    r = login_as(client, "admin").post("/api/demo/reset")
    assert r.status_code == 200
    assert client.get("/api/handoffs").json() == []
    assert login_as(client, "minh").get("/api/auth/me").status_code == 200


def test_new_member_without_history_appears_in_suitability(client):
    create_member(client, "erin")
    h = create_unassigned(client)
    analyze(client, h)
    s = login_as(client, "admin").get(f"/api/handoffs/{h['id']}/suitability").json()
    erin = next(m for m in s["members"] if m["person_id"] == "erin")
    assert erin["fit_pct"] is None and erin["fit_status"] == "no_history"
