"""Fair successor selection: candidate pool, attempt rules, anonymity, readiness, the admin's
selection and expert review. Every rule is enforced by the backend."""

import json
import uuid

import pytest
from sqlalchemy import text

from app.db import get_session
from app.errors import AppError
from app.verify import selection as Sel
from app.verify import service as V
from app.verify.contract import Criterion, CriterionMatch, validate_matches
from app.verify.offline import OfflineAssessor, OfflineGenerator
from app.verify.rules import aggregate
from tests.conftest import ORACLE, analyze, by_area, create_member, login_as

EXPERT = "alice"
POOL = ["bob", "carol", "minh"]
# The correct paraphrase with the "do not create a new settlement" condition only half
# stated: the critical criterion C1 is partial, so the result needs review.
C1_PARTIAL = (
    "First I'd confirm what AcmePay thinks happened to the original attempt using its "
    "idempotency key. If AcmePay already accepted it, I just reconcile ours. If their answer "
    "is unclear I stop the retry worker and raise it with the AcmePay contact. I'm done when "
    "there is a single settlement in the ledger for that order."
)


# ---------- helpers ----------


def create_pool(client, candidates=POOL, expert=EXPERT, **extra):
    return login_as(client, "admin").post(
        "/api/handoffs",
        json={
            "bundle_id": client.bundle["id"],
            "expert_id": expert,
            "candidate_ids": candidates,
            **extra,
        },
    )


def submit(client, ex_id, answer, actor):
    return login_as(client, actor).post(
        f"/api/exercises/{ex_id}/attempts",
        json={"answer": answer},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )


def open_study(client, handoff_id, actor):
    return login_as(client, actor).post(f"/api/handoffs/{handoff_id}/study-opened")


def readiness(client, handoff_id):
    r = login_as(client, "admin").get(f"/api/handoffs/{handoff_id}/readiness")
    assert r.status_code == 200, r.text
    return {c["person_id"]: c for c in r.json()["candidates"]}, r.json()


@pytest.fixture
def pool(client, oracle):
    """A selecting handoff alice -> {bob, carol, minh} with a released settlement exercise."""
    r = create_pool(client)
    assert r.status_code == 201, r.text
    h = r.json()
    f = by_area(analyze(client, h))["settlement"]
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
    assert ex["status"] == "ready"
    return {"handoff": h, "exercise": ex}


@pytest.fixture
def answered(client, pool, oracle):
    """Bob correct, Carol partial, Minh unsafe; each opened the study material first."""
    answers = oracle["successor_answers"]
    h, ex = pool["handoff"], pool["exercise"]
    attempts = {}
    for who, key in (
        ("bob", "correct_paraphrase"),
        ("carol", "partial_answer"),
        ("minh", "unsafe"),
    ):
        assert open_study(client, h["id"], who).status_code == 200
        r = submit(client, ex["id"], answers[key], who)
        assert r.status_code == 201, r.text
        attempts[who] = r.json()
    return pool | {"attempts": attempts}


# ---------- pool ----------


def test_valid_pool_is_selecting_with_repeatable_aliases(client):
    h = create_pool(client).json()
    assert h["status"] == "selecting" and h["successor_id"] is None
    assert h["max_attempts"] == 2
    aliases = {c["person_id"]: c["alias"] for c in h["candidates"]}
    assert set(aliases) == set(POOL)
    assert set(aliases.values()) == {"Candidate A", "Candidate B", "Candidate C"}
    # Same pool in another order: same aliases (seeded, and the typed order does not leak).
    again = create_pool(client, list(reversed(POOL))).json()
    assert {c["person_id"]: c["alias"] for c in again["candidates"]} == aliases
    assert Sel.assign_aliases(POOL, "seed") == Sel.assign_aliases(POOL, "seed")


def test_single_successor_still_creates_an_active_handoff(client):
    r = login_as(client, "admin").post(
        "/api/handoffs",
        json={"bundle_id": client.bundle["id"], "expert_id": EXPERT, "successor_id": "minh"},
    )
    assert r.status_code == 201 and r.json()["status"] == "active"
    assert r.json()["successor_id"] == "minh" and "candidates" not in r.json()


@pytest.mark.parametrize(
    ("candidates", "code"),
    [
        (["bob"], "candidate_count"),
        ([], "candidate_count"),
        (["bob", "bob"], "duplicate_candidate"),
        (["bob", "alice"], "same_person"),
        (["bob", "nobody"], "unknown_person"),
    ],
)
def test_invalid_pool_is_rejected(client, candidates, code):
    r = create_pool(client, candidates)
    assert r.status_code == 422 and r.json()["error"]["code"] == code


def test_pool_of_five_inactive_or_admin_is_rejected(client):
    for name in ("dave", "erin"):
        create_member(client, name)
    r = create_pool(client, [*POOL, "dave", "erin"])
    assert r.status_code == 422 and r.json()["error"]["code"] == "candidate_count"

    users = {u["username"]: u for u in client.get("/api/admin/users").json()["items"]}
    client.patch(f"/api/admin/users/{users['dave']['id']}", json={"is_active": False})
    r = create_pool(client, ["bob", "dave"])
    assert r.status_code == 422 and r.json()["error"]["code"] == "inactive_account"

    client.patch(f"/api/admin/users/{users['erin']['id']}", json={"role": "admin"})
    r = create_pool(client, ["bob", "erin"])
    assert r.status_code == 422 and r.json()["error"]["code"] == "admin_not_participant"

    r = create_pool(client, POOL, successor_id="bob")
    assert r.status_code == 422 and r.json()["error"]["code"] == "successor_or_candidates"


# ---------- attempt rules ----------


def test_new_hire_outside_the_evidence_can_answer(client, pool, oracle):
    assert "minh" not in {p["id"] for p in client.bundle["people"]}
    ex = login_as(client, "minh").get(f"/api/exercises/{pool['exercise']['id']}")
    assert ex.status_code == 200 and "criteria" not in ex.json()
    assert "rubric" not in ex.text and "critical" not in ex.text
    mine = client.get("/api/me/exercises").json()
    assert [e["id"] for e in mine] == [pool["exercise"]["id"]]
    open_study(client, pool["handoff"]["id"], "minh")
    r = submit(client, pool["exercise"]["id"], oracle["successor_answers"]["unsafe"], "minh")
    assert r.status_code == 201 and r.json()["assessment_status"] == "succeeded"


def test_submitting_before_opening_study_is_409(client, pool, oracle):
    h, ex = pool["handoff"], pool["exercise"]
    r = submit(client, ex["id"], oracle["successor_answers"]["unsafe"], "carol")
    assert r.status_code == 409 and r.json()["error"]["code"] == "study_required"
    first = open_study(client, h["id"], "carol").json()["study_opened_at"]
    assert open_study(client, h["id"], "carol").json()["study_opened_at"] == first
    assert (
        submit(client, ex["id"], oracle["successor_answers"]["unsafe"], "carol").status_code == 201
    )
    # Only candidates of the handoff record study.
    assert open_study(client, h["id"], EXPERT).status_code == 403
    assert open_study(client, h["id"], "admin").status_code == 403


class _FailingAssessor:
    model_id = "failing/1"

    def assess(self, *_):
        raise AppError(502, "provider_error", "provider unavailable")


def test_attempt_limit_ignores_failed_attempts(client, pool, oracle, monkeypatch):
    h, ex = pool["handoff"], pool["exercise"]
    answer = oracle["successor_answers"]["unsafe"]
    open_study(client, h["id"], "carol")
    monkeypatch.setattr(V, "get_assessor", lambda: _FailingAssessor())
    failed = submit(client, ex["id"], answer, "carol")
    assert failed.status_code == 502
    failed_id = failed.json()["error"]["attempt_id"]
    monkeypatch.setattr(V, "get_assessor", lambda: OfflineAssessor())
    assert submit(client, ex["id"], answer, "carol").status_code == 201
    assert submit(client, ex["id"], answer, "carol").status_code == 201
    third = submit(client, ex["id"], answer, "carol")
    assert third.status_code == 409 and third.json()["error"]["code"] == "attempt_limit"
    # Reassessing the failed one would be a third result: refused too.
    r = login_as(client, "carol").post(f"/api/attempts/{failed_id}/reassess")
    assert r.status_code == 409 and r.json()["error"]["code"] == "attempt_limit"
    by_person, _ = readiness(client, h["id"])
    assert by_person["carol"]["attempts_used"] == 2 and by_person["carol"]["max_attempts"] == 2


def test_candidate_cannot_read_another_candidates_attempt(client, answered):
    bob_attempt = answered["attempts"]["bob"]["id"]
    r = login_as(client, "carol").get(f"/api/attempts/{bob_attempt}")
    assert r.status_code == 403 and r.json()["error"]["code"] == "not_owner"
    ex = login_as(client, "carol").get(f"/api/exercises/{answered['exercise']['id']}").json()
    assert [a["id"] for a in ex["attempts"]] == [answered["attempts"]["carol"]["id"]]
    r = login_as(client, "carol").post(f"/api/attempts/{bob_attempt}/review-request")
    assert r.status_code == 403


# ---------- anonymity ----------


def test_expert_sees_aliases_until_selection(client, answered):
    h, ex = answered["handoff"], answered["exercise"]
    names = ("bob", "carol", "minh", "Bob", "Carol", "Minh")
    expert = login_as(client, EXPERT)
    views = [
        expert.get(f"/api/exercises/{ex['id']}"),
        expert.get(f"/api/attempts/{answered['attempts']['bob']['id']}"),
        expert.get(f"/api/handoffs/{h['id']}"),
        expert.get("/api/handoffs"),
    ]
    for v in views:
        assert v.status_code == 200, v.text
        for n in names:
            assert n not in v.text, n
    labels = {a["successor_id"] for a in views[0].json()["attempts"]}
    assert labels == {"Candidate A", "Candidate B", "Candidate C"}
    assert [c.keys() for c in views[2].json()["candidates"]] == [{"alias"}] * 3

    r = login_as(client, "admin").post(
        f"/api/handoffs/{h['id']}/selection", json={"selected_person_id": "bob"}
    )
    assert r.status_code == 201, r.text
    after = login_as(client, EXPERT).get(f"/api/exercises/{ex['id']}").json()
    assert {a["successor_id"] for a in after["attempts"]} == set(POOL)


# ---------- readiness ----------


def test_readiness_groups_and_recommendation(client, answered):
    by_person, out = readiness(client, answered["handoff"]["id"])
    assert by_person["bob"]["group"] == "ready" and by_person["bob"]["group_label"] == "Ready"
    assert by_person["carol"]["group"] == "ready_with_support"
    assert by_person["carol"]["group_label"] == "Ready with support"
    assert by_person["minh"]["group"] == "not_yet"
    assert out["recommended"] == ["bob"]
    assert out["warnings"] == []
    bob = by_person["bob"]
    assert bob["display_name"] == "Bob" and bob["alias"].startswith("Candidate ")
    assert bob["attempts_used"] == 1 and bob["study_opened"] is True
    assert {c["verdict"] for c in bob["criteria"]} == {"met"}
    # Context comes from the stored extraction and is marked as not scored.
    assert by_person["minh"]["context"]["recovered_incidents"] == 0
    assert all(c["context"]["scored"] is False for c in by_person.values())
    assert by_person["bob"]["context"]["recovered_incidents"] >= 1


def test_readiness_picks_the_best_attempt_and_warns(client, pool, oracle):
    h, ex = pool["handoff"], pool["exercise"]
    answers = oracle["successor_answers"]
    open_study(client, h["id"], "bob")
    submit(client, ex["id"], answers["correct_paraphrase"], "bob")
    submit(client, ex["id"], answers["unsafe"], "bob")
    by_person, out = readiness(client, h["id"])
    assert by_person["bob"]["group"] == "ready" and by_person["bob"]["attempts_used"] == 2
    assert by_person["carol"]["group"] == "pending"
    assert {(w["person_id"], w["code"]) for w in out["warnings"]} == {
        ("carol", "no_result"),
        ("minh", "no_result"),
    }


def test_context_never_changes_group_or_recommendation(client, answered, monkeypatch):
    before, out = readiness(client, answered["handoff"]["id"])
    real = Sel.candidate_context

    def inflated(session, handoff):
        ctx = real(session, handoff)
        ctx["minh"] = ctx["minh"] | {"recovered_incidents": 99, "by_area": {"settlement": 99}}
        return ctx

    monkeypatch.setattr(Sel, "candidate_context", inflated)
    after, out2 = readiness(client, answered["handoff"]["id"])
    assert after["minh"]["context"]["recovered_incidents"] == 99
    assert {p: c["group"] for p, c in after.items()} == {p: c["group"] for p, c in before.items()}
    assert out2["recommended"] == out["recommended"] == ["bob"]


def test_only_admin_reads_readiness_and_selects(client, answered):
    h = answered["handoff"]
    for user in ("bob", EXPERT):
        r = login_as(client, user).get(f"/api/handoffs/{h['id']}/readiness")
        assert r.status_code == 403
        r = client.post(f"/api/handoffs/{h['id']}/selection", json={"selected_person_id": "bob"})
        assert r.status_code == 403


# ---------- selection ----------


def test_selection_outside_recommendation_needs_reason(client, answered):
    h = answered["handoff"]
    admin = login_as(client, "admin")
    r = admin.post(f"/api/handoffs/{h['id']}/selection", json={"selected_person_id": "carol"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "reason_required"
    r = admin.post(
        f"/api/handoffs/{h['id']}/selection",
        json={"selected_person_id": "carol", "reason": "   "},
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "reason_required"
    r = admin.post(f"/api/handoffs/{h['id']}/selection", json={"selected_person_id": "dan"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "not_candidate"

    reason = "Carol owns the webhook rota next quarter; Bob is moving teams."
    r = admin.post(
        f"/api/handoffs/{h['id']}/selection",
        json={"selected_person_id": "carol", "reason": reason},
    )
    assert r.status_code == 201, r.text
    sel = r.json()
    assert sel["in_recommended"] is False and sel["recommended"] == ["bob"]
    assert sel["reason"] == reason and sel["decided_by"] == "admin"
    assert sel["handoff"]["status"] == "active" and sel["handoff"]["successor_id"] == "carol"

    again = admin.post(f"/api/handoffs/{h['id']}/selection", json={"selected_person_id": "bob"})
    assert again.status_code == 409 and again.json()["error"]["code"] == "already_selected"

    events = admin.get("/api/admin/audit", params={"action": "successor.selected"}).json()
    assert [e["metadata"]["selected_person_id"] for e in events["items"]] == ["carol"]

    # The selected successor keeps access; the others no longer act in this handoff.
    assert login_as(client, "carol").get(f"/api/handoffs/{h['id']}").status_code == 200
    assert login_as(client, "bob").get(f"/api/handoffs/{h['id']}").status_code == 403


def test_recommended_selection_needs_no_reason(client, answered):
    r = login_as(client, "admin").post(
        f"/api/handoffs/{answered['handoff']['id']}/selection",
        json={"selected_person_id": "bob"},
    )
    assert r.status_code == 201 and r.json()["in_recommended"] is True
    assert r.json()["reason"] is None


def test_database_forbids_changing_a_selection(client, answered):
    h = answered["handoff"]
    login_as(client, "admin").post(
        f"/api/handoffs/{h['id']}/selection", json={"selected_person_id": "bob"}
    )
    session = next(get_session())
    try:
        with pytest.raises(Exception, match="immutable"):
            session.execute(
                text(
                    "update successor_selection set selected_person_id='carol' where handoff_id=:h"
                ),
                {"h": h["id"]},
            )
        session.rollback()
        with pytest.raises(Exception, match="immutable"):
            session.execute(
                text("delete from successor_selection where handoff_id=:h"), {"h": h["id"]}
            )
        session.rollback()
    finally:
        session.close()


# ---------- review ----------


def test_review_override_recomputes_group_without_touching_the_attempt(client, answered):
    h, ex = answered["handoff"], answered["exercise"]
    second = submit(client, ex["id"], C1_PARTIAL, "minh").json()
    assert second["aggregate_result"] == "review_required"
    by_person, out = readiness(client, h["id"])
    assert by_person["minh"]["group"] == "pending"
    assert ("minh", "pending") in {(w["person_id"], w["code"]) for w in out["warnings"]}

    # Only an assessed attempt's owner may ask, once.
    r = login_as(client, "minh").post(f"/api/attempts/{second['id']}/review-request")
    assert r.status_code == 201 and r.json()["review"]["reviewed_at"] is None
    r = client.post(f"/api/attempts/{second['id']}/review-request")
    assert r.status_code == 409 and r.json()["error"]["code"] == "review_already_requested"
    _, out = readiness(client, h["id"])
    assert ("minh", "review_pending") in {(w["person_id"], w["code"]) for w in out["warnings"]}

    expert = login_as(client, EXPERT)
    url = f"/api/attempts/{second['id']}/review"
    r = expert.post(url, json={"overrides": {"C1": "met"}})
    assert r.status_code == 422 and r.json()["error"]["code"] == "reason_required"
    r = expert.post(url, json={"overrides": {"C1": "met"}, "reason": " "})
    assert r.status_code == 422 and r.json()["error"]["code"] == "reason_required"
    r = expert.post(url, json={"overrides": {"C9": "met"}, "reason": "x"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_overrides"
    r = expert.post(url, json={"overrides": {"C1": "uncertain"}, "reason": "x"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_overrides"
    assert (
        login_as(client, "minh")
        .post(url, json={"overrides": {"C1": "met"}, "reason": "x"})
        .status_code
        == 403
    )

    reason = "'If AcmePay already accepted it, I just reconcile ours' rules out a new settlement."
    r = login_as(client, EXPERT).post(url, json={"overrides": {"C1": "met"}, "reason": reason})
    assert r.status_code == 200, r.text
    reviewed = r.json()
    assert reviewed["successor_id"].startswith("Candidate ")  # still anonymous
    assert reviewed["aggregate_result"] == "review_required"  # the attempt is unchanged

    # Expected result recomputed independently with aggregate() on the overridden verdicts.
    criteria = [Criterion.model_validate(c) for c in ex["criteria"]]
    verdicts = {x["criterion_id"]: x["verdict"] for x in second["results"]} | {"C1": "met"}
    expected = aggregate(
        criteria, [CriterionMatch(criterion_id=c.id, verdict=verdicts[c.id]) for c in criteria]
    )
    assert expected == "demonstrated" and reviewed["effective_result"] == expected

    again = login_as(client, EXPERT).post(url, json={"overrides": {"C1": "met"}, "reason": reason})
    assert again.status_code == 409 and again.json()["error"]["code"] == "already_reviewed"

    by_person, out = readiness(client, h["id"])
    assert by_person["minh"]["group"] == "ready"
    assert by_person["minh"]["best_attempt_id"] == second["id"]
    c1 = next(c for c in by_person["minh"]["criteria"] if c["criterion_id"] == "C1")
    assert (c1["verdict"], c1["overridden"], c1["critical"]) == ("met", True, True)
    assert out["recommended"] == ["bob", "minh"]

    mine = login_as(client, "minh").get(f"/api/attempts/{second['id']}").json()
    assert mine["effective_result"] == "demonstrated" and mine["review"]["reason"] == reason

    session = next(get_session())
    try:
        row = session.execute(
            text("select aggregate_result, criterion_results from attempt where id=:i"),
            {"i": second["id"]},
        ).one()
    finally:
        session.close()
    assert row[0] == "review_required"
    assert next(m for m in row[1] if m["criterion_id"] == "C1")["verdict"] == "partial"

    actions = [
        e["action"]
        for e in login_as(client, "admin").get("/api/admin/audit").json()["items"]
        if e["target_id"] == second["id"]
    ]
    assert "attempt.review_requested" in actions and "attempt.reviewed" in actions


def test_review_needs_an_assessed_attempt_and_a_request(client, answered, monkeypatch):
    ex = answered["exercise"]
    bob = answered["attempts"]["bob"]["id"]
    r = login_as(client, EXPERT).post(
        f"/api/attempts/{bob}/review", json={"overrides": {"C1": "met"}, "reason": "x"}
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "review_not_requested"
    monkeypatch.setattr(V, "get_assessor", lambda: _FailingAssessor())
    failed = submit(client, ex["id"], "x y z", "carol").json()["error"]["attempt_id"]
    r = login_as(client, "carol").post(f"/api/attempts/{failed}/review-request")
    assert r.status_code == 409 and r.json()["error"]["code"] == "not_assessed"


# ---------- oracle ----------


def test_partial_answer_is_partial_with_offline_assessor():
    """fixtures/oracle partial_answer meets every critical criterion and misses a normal one."""
    content = json.loads((ORACLE / "expert_capture.json").read_text())["content"]
    answer = json.loads((ORACLE / "successor_answers.json").read_text())["partial_answer"]
    draft = OfflineGenerator().generate("Settlement recovery", content)
    proposal = OfflineAssessor().assess(draft.scenario, draft.criteria, answer)
    matches, _ = validate_matches(draft.criteria, proposal, answer)
    verdict = {m.criterion_id: m.verdict for m in matches}
    assert all(verdict[c.id] == "met" for c in draft.criteria if c.critical)
    assert any(verdict[c.id] != "met" for c in draft.criteria if not c.critical)
    assert aggregate(draft.criteria, matches) == "partial"
