"""Help assistant data mode: live, read-only answers under the app's own visibility rule,
nothing about other people for non-admins, no model, and the assessment lock unchanged."""

from datetime import datetime

import pytest
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select

from app.api import serializers as S
from app.assistant import live_data as L
from app.assistant import service as A
from app.auth.deps import handoff_role
from app.config import get_settings
from app.db import get_session
from app.models import AppUser, Handoff, HandoffCandidate
from tests.conftest import analyze, login_as, make_handoff
from tests.test_assistant import KNOWLEDGE_Q, approved_lines
from tests.test_successor_selection import (
    create_unassigned,
    released_exercise,
    start,
    study,
    submit,
)

LIST_Q = "Are there any handoffs?"
STATUS_Q = "What is the status of my handoff?"
PENDING_Q = "What is waiting for me?"
DUE_Q = "When is my assessment due?"
DATA_QUESTIONS = (LIST_Q, "Which handoffs exist?", STATUS_Q, "Has the analysis run?", PENDING_Q,
                  "What do I need to do?", DUE_Q, "What is the deadline?")  # fmt: skip
OTHER_PEOPLE = ("Bob", "Minh", "Candidate", "%", "score", "fit")


# ---------- helpers ----------


def ask(client, who, question, page="/", **extra) -> dict:
    r = login_as(client, who).post(
        "/api/assistant/ask", json={"question": question, "page": page, **extra}
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert len(out["suggestions"]) == 3
    return out


def data(client, who, question, page="/") -> dict:
    out = ask(client, who, question, page)
    assert out["mode"] == "data", out
    assert out["provider"] == "offline"
    rows = out["answer"].split("\n")[1:]
    if out["citations"]:
        # One page link per row, in the same order.
        assert len(out["citations"]) == len(rows)
    for c in out["citations"]:
        assert set(c) == {"kind", "id", "title", "link"}
        assert c["kind"] == "page" and c["id"] == c["link"] and c["link"].startswith("/")
    return out


@pytest.fixture
def selecting(client, oracle):
    """Common assessment alice -> {bob, carol, minh}; bob and carol submitted, minh not."""
    h = create_unassigned(client)
    v, ex = released_exercise(client, oracle, h)
    assert start(client, h["id"], ex["id"]).status_code == 201
    answers = oracle["successor_answers"]
    attempts = {}
    for who, key in (("bob", "correct_paraphrase"), ("carol", "partial_answer")):
        study(client, h["id"], who)
        r = submit(client, ex["id"], answers[key], who)
        assert r.status_code == 201, r.text
        attempts[who] = r.json()
    return {"handoff": h, "version": v, "exercise": ex, "attempts": attempts}


# ---------- list_handoffs ----------


def test_list_handoffs_admin_sees_all(client):
    first = make_handoff(client)  # alice -> bob
    second = create_unassigned(client)  # alice, successor not chosen
    out = data(client, "admin", LIST_Q, "/admin")
    rows = out["answer"].split("\n")
    assert rows[0] == "2 handoffs you can see, newest first:"
    assert rows[1:] == [
        "Alice → successor not chosen · successor not chosen yet",
        "Alice → Bob · active",
    ]
    assert [c["link"] for c in out["citations"]] == ["/admin/handoffs", "/admin/handoffs"]
    assert first["id"] != second["id"]


def test_list_handoffs_member_sees_own_only(client):
    h = make_handoff(client)
    create_unassigned(client)
    bob = data(client, "bob", LIST_Q, "/learn")
    assert bob["answer"].split("\n")[1:] == ["Alice → Bob · active"]
    assert [c["link"] for c in bob["citations"]] == ["/learn"]

    alice = data(client, "alice", LIST_Q, "/expert")
    assert [c["link"] for c in alice["citations"]][1] == f"/expert/handoffs/{h['id']}/detect"

    for question in (LIST_Q, STATUS_Q):
        carol = data(client, "carol", question, "/learn")
        assert carol["answer"] == "You are not part of any handoff yet."
        assert carol["citations"] == []
        for word in ("Alice", "Bob", "active", "2", "handoffs exist"):
            assert word not in carol["answer"]


# ---------- handoff_status ----------


def test_candidate_sees_count_and_own_state_only(client, selecting):
    out = data(client, "carol", STATUS_Q, "/learn")
    (row,) = out["answer"].split("\n")[1:]
    assert row.startswith("Alice → successor not chosen · choosing a successor")
    assert "you are one of 3 candidates" in row
    assert "study material opened" in row and "official attempt used" in row
    assert "due " in row
    for word in OTHER_PEOPLE:
        assert word not in out["answer"], word
    assert "submitted" not in out["answer"]  # admin-only count
    assert "analysis" not in out["answer"]  # not something a learner can open

    minh = data(client, "minh", STATUS_Q, "/learn")["answer"]
    assert "study material not opened yet" in minh and "official attempt not used yet" in minh


def test_admin_status_counts_without_answers(client, selecting, oracle):
    out = data(client, "admin", STATUS_Q, "/admin")
    assert "2 of 3 candidates submitted" in out["answer"]
    assert "analysis done" in out["answer"] and "exercise released: yes" in out["answer"]
    assert "approved knowledge versions: 1" in out["answer"]
    for answer in oracle["successor_answers"].values():
        assert answer not in out["answer"]
    lines = approved_lines(selecting["version"])
    assert not any(line in out["answer"] for line in lines)
    assert "%" not in out["answer"] and "score" not in out["answer"].lower()
    assert "Candidate " not in out["answer"]


def test_expert_status_has_no_candidate_counts(client, selecting):
    out = data(client, "alice", STATUS_Q, "/expert")
    assert "analysis done" in out["answer"]
    for word in ("submitted", "Bob", "Carol", "Minh", "Candidate", "%"):
        assert word not in out["answer"], word


# ---------- my_pending ----------


def test_my_pending_per_role(client, oracle):
    # Admin: a handoff with no analysis yet.
    make_handoff(client)
    out = data(client, "admin", PENDING_Q, "/admin")
    assert out["answer"].split("\n")[1:] == ["Alice → Bob: run the analysis"]

    # Expert: findings to review once the analysis has run.
    h2 = create_unassigned(client)
    analyze(client, h2)
    alice = data(client, "alice", PENDING_Q, "/expert")
    assert any("findings to review" in r for r in alice["answer"].split("\n"))
    assert f"/expert/handoffs/{h2['id']}/detect" in [c["link"] for c in alice["citations"]]

    # Successor: a released exercise not answered yet.
    h3 = make_handoff(client)
    _, ex = released_exercise(client, oracle, h3)
    bob = data(client, "bob", PENDING_Q, "/learn")
    assert "Answer the exercise “Settlement recovery” (knowledge v1)" in bob["answer"]
    assert f"/learn/exercises/{ex['id']}" in [c["link"] for c in bob["citations"]]
    assert "due" not in bob["answer"]  # a successor has no due time
    # Answered: no longer waiting.
    assert submit(client, ex["id"], oracle["successor_answers"]["unsafe"], "bob").status_code == 201
    assert "Answer the exercise" not in data(client, "bob", PENDING_Q, "/learn")["answer"]

    # Nothing waiting.
    assert data(client, "carol", PENDING_Q, "/learn")["answer"] == "Nothing is waiting for you."


def test_my_pending_for_expert_reviews_and_candidate_due(client, selecting):
    minh = data(client, "minh", "What do I need to do?", "/learn")
    assert "Answer the exercise “Settlement recovery” (knowledge v1), due " in minh["answer"]
    assert data(client, "carol", PENDING_Q, "/learn")["answer"] == "Nothing is waiting for you."

    carol = selecting["attempts"]["carol"]["id"]
    assert (
        login_as(client, "carol").post(f"/api/attempts/{carol}/review-request").status_code == 201
    )
    alice = data(client, "alice", PENDING_Q, "/expert")
    assert "“Settlement recovery” v1: 1 review request waiting" in alice["answer"]
    assert "Carol" not in alice["answer"] and "Candidate" not in alice["answer"]


def test_admin_pending_after_due_without_decision(client, selecting):
    session = next(get_session())
    try:
        h = session.get(Handoff, selecting["handoff"]["id"])
        h.assessment_due_at = h.assessment_started_at
        session.commit()
    finally:
        session.close()
    out = data(client, "admin", PENDING_Q, "/admin")
    assert "the assessment is closed; select a successor" in out["answer"]
    assert f"/admin/handoffs/{selecting['handoff']['id']}" in [c["link"] for c in out["citations"]]


# ---------- my_due ----------


def test_my_due_for_candidate_and_others(client, selecting):
    minh = data(client, "minh", DUE_Q, "/learn")
    (row,) = minh["answer"].split("\n")[1:]
    assert row.startswith("Due ") and row.endswith("· your official attempt is not used yet")
    assert minh["citations"][0]["link"] == f"/learn/exercises/{selecting['exercise']['id']}"
    carol = data(client, "carol", "What is the deadline?", "/learn")
    assert carol["answer"].endswith("· your official attempt is used")
    for word in OTHER_PEOPLE:
        assert word not in carol["answer"]
    for who in ("admin", "alice"):
        assert data(client, who, DUE_Q)["answer"] == "You have no assessment with a due time."
    # A plain successor has no due time either.
    make_handoff(client, successor="bob")
    session = next(get_session())
    try:
        session.execute(
            HandoffCandidate.__table__.delete().where(HandoffCandidate.person_id == "bob")
        )
        session.commit()
    finally:
        session.close()
    assert data(client, "bob", DUE_Q)["answer"] == "You have no assessment with a due time."


# ---------- reset, routing, model, lock, identity ----------


def test_empty_after_reset(client):
    make_handoff(client)
    r = login_as(client, "admin").post("/api/demo/reset")
    assert r.status_code == 200, r.text
    out = data(client, "admin", LIST_Q, "/admin")
    assert out["answer"] == "There are no handoffs yet." and out["citations"] == []
    assert data(client, "admin", PENDING_Q, "/admin")["answer"] == "Nothing is waiting for you."


def test_results_questions_are_not_data_intents(client, selecting):
    for q in (
        "Who scored highest?",
        "What did Carol answer?",
        "Who is in the top?",
        "Is Carol in the top?",
        "What is Bob's status?",
        "What are the scores?",
        "What is my result?",
    ):
        for who in ("admin", "alice", "carol"):
            assert ask(client, who, q)["mode"] != "data", (who, q)


def test_help_question_still_routes_to_help(client):
    out = ask(client, "admin", "How do I create a handoff?", "/admin/handoffs")
    assert out["mode"] == "help"
    assert out["citations"][0]["id"] == "create-handoff"
    assert ask(client, "admin", "How do I run the analysis?", "/admin")["mode"] != "data"
    assert ask(client, "bob", "What do I click next?", "/learn")["mode"] != "data"


def test_waiting_question_is_suggested_on_every_home_page(client):
    make_handoff(client)  # alice expert, bob successor
    for who, home in (
        ("admin", "/admin"),
        ("alice", "/expert"),
        ("bob", "/learn"),
        ("carol", "/learn"),
    ):
        out = ask(client, who, "zzz unknown words", home)
        assert out["suggestions"][0] == PENDING_Q, (who, out["suggestions"])
    # Not repeated right after it was asked.
    assert PENDING_Q not in data(client, "bob", PENDING_Q, "/learn")["suggestions"]


def test_data_mode_never_calls_model(client, selecting, monkeypatch):
    monkeypatch.setattr(get_settings(), "ai_provider", "openai")

    def fail():
        pytest.fail("data mode must never call the model")

    monkeypatch.setattr(A, "get_model", fail)
    for who in ("admin", "alice", "carol", "minh"):
        for q in DATA_QUESTIONS:
            assert data(client, who, q)["provider"] == "offline"


def test_lock_unchanged(client, oracle):
    h = make_handoff(client)
    v, ex = released_exercise(client, oracle, h)
    locked = ask(client, "bob", KNOWLEDGE_Q, "/learn")
    assert locked["mode"] == "locked"

    out = data(client, "bob", PENDING_Q, "/learn")
    assert "Answer the exercise “Settlement recovery”" in out["answer"]
    assert ex["scenario"] not in out["answer"]
    content = login_as(client, "bob").get(f"/api/knowledge/{v['id']}").json()
    assert not any(line in out["answer"] for line in approved_lines(content))
    # Asking for live data never unlocks knowledge.
    assert ask(client, "bob", KNOWLEDGE_Q, "/learn")["mode"] == "locked"


def test_spoofed_role_ignored(client):
    make_handoff(client)
    create_unassigned(client)
    plain = data(client, "carol", LIST_Q, "/learn")
    spoofed = ask(
        client, "carol", LIST_Q, "/admin", role="admin", user="admin", actor_id="admin",
        username="admin", person_id="alice",
    )  # fmt: skip
    assert spoofed["mode"] == "data"
    assert spoofed["answer"] == plain["answer"] == "You are not part of any handoff yet."
    assert spoofed["citations"] == []


def test_questions_are_not_stored(client, selecting):
    from sqlalchemy import text

    def count() -> int:
        session = next(get_session())
        try:
            return session.execute(text("select count(*) from audit_event")).scalar_one()
        finally:
            session.close()

    login_as(client, "carol")
    before = count()
    for q in DATA_QUESTIONS:
        data(client, "carol", q)
    assert count() == before


# ---------- the shared visibility rule ----------


def _reference_list(user: AppUser) -> list:
    """GET /api/handoffs as it was written before visible_handoffs was factored out."""
    session = next(get_session())
    try:
        stmt = select(Handoff).order_by(Handoff.created_at.desc())
        if user.role != "admin":
            pid = user.person_id or ""
            candidate_of = select(HandoffCandidate.handoff_id).where(
                HandoffCandidate.person_id == pid
            )
            stmt = stmt.where(
                (Handoff.expert_id == pid)
                | (Handoff.successor_id == pid)
                | ((Handoff.status == "selecting") & Handoff.id.in_(candidate_of))
            )
        out = []
        for h in session.scalars(stmt):
            r = handoff_role(user, h)
            out.append(S.handoff_out(h, r) | {"viewer_role": r})
        return jsonable_encoder(out)
    finally:
        session.close()


def _same_times(value):
    """The API writes UTC as "Z", jsonable_encoder as "+00:00"; same instant either way."""
    if isinstance(value, list):
        return [_same_times(v) for v in value]
    if isinstance(value, dict):
        return {k: _same_times(v) for k, v in value.items()}
    if isinstance(value, str) and value.endswith(("Z", "+00:00")) and "T" in value:
        return datetime.fromisoformat(value)
    return value


def test_list_handoffs_route_unchanged(client, selecting):
    make_handoff(client)  # alice -> bob, active
    create_unassigned(client)
    session = next(get_session())
    try:
        users = {
            u.username: u
            for u in session.scalars(
                select(AppUser).where(AppUser.username.in_(["admin", "alice", "bob", "carol"]))
            )
        }
        for u in users.values():
            session.expunge(u)
    finally:
        session.close()
    seen = {}
    for name, user in users.items():
        r = login_as(client, name).get("/api/handoffs")
        assert r.status_code == 200, r.text
        assert _same_times(r.json()) == _same_times(_reference_list(user)), name
        seen[name] = len(r.json())
    assert seen == {"admin": 3, "alice": 3, "bob": 2, "carol": 1}
    # The assistant lists exactly the same handoffs.
    for name, n in seen.items():
        assert len(data(client, name, LIST_Q)["citations"]) == n


def test_live_data_functions_cover_every_intent():
    from app.assistant.intents import INTENTS

    assert set(L.ANSWERS) == {i.id for i in INTENTS}
