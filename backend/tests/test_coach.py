"""Learning coach: owner-only access, effective verdicts in rubric order, exact approved lines,
no rubric leak, practice that is never counted or stored, one text-free audit event, and the
OpenAI fallback (fake client)."""

import json
import uuid

import pytest
from sqlalchemy import text

from app.analysis.openai_extractor import StructuredCall
from app.coach import service as C
from app.coach.openai_coach import SYSTEM_PROMPT, OpenAICoach
from app.config import get_settings
from app.db import get_session
from app.errors import AppError
from app.models import Attempt
from app.verify import service as V
from app.verify.contract import GUIDANCE_FIELDS, resolve
from tests.conftest import login_as, make_handoff
from tests.test_openai_extractor import FakeClient
from tests.test_successor_selection import (
    create_unassigned,
    readiness,
    released_exercise,
    start,
    study,
    submit,
)

EXPERT = "alice"
POOL = ["bob", "carol", "minh"]
# Words that would tell a learner which criteria are critical or where they came from.
LEAKS = (
    "critical",
    "source_path",
    "important",
    "safety",
    "weight",
    *GUIDANCE_FIELDS,
    *(f.replace("_", " ") for f in GUIDANCE_FIELDS),
)
ITEM_KEYS = {
    "criterion_id",
    "criterion_text",
    "verdict",
    "your_quote",
    "explanation",
    "reread",
    "practice",
}


# ---------- helpers ----------


def coach(client, who, attempt_id):
    return login_as(client, who).get(f"/api/attempts/{attempt_id}/coach")


def coach_ok(client, who, attempt_id) -> dict:
    r = coach(client, who, attempt_id)
    assert r.status_code == 200, r.text
    out = r.json()
    assert set(out) == {
        "attempt_id",
        "result",
        "met_count",
        "total",
        "items",
        "message",
        "next_step",
        "provider",
    }
    for item in out["items"]:
        assert set(item) == ITEM_KEYS
        assert set(item["reread"]) == {
            "version_id",
            "version_no",
            "title",
            "line_id",
            "text",
            "link",
        }
        assert set(item["practice"]) == {"practice_id", "prompt"}
    return out


def practise(client, who, practice_id, answer):
    return login_as(client, who).post(
        "/api/coach/practice", json={"practice_id": practice_id, "answer": answer}
    )


def query(sql: str, **params):
    session = next(get_session())
    try:
        return session.execute(text(sql), params).all()
    finally:
        session.close()


def criteria(client, exercise_id) -> list[dict]:
    """The private rubric, as the expert sees it."""
    return login_as(client, EXPERT).get(f"/api/exercises/{exercise_id}").json()["criteria"]


def assert_no_leak(payload) -> None:
    dumped = json.dumps(payload).lower()
    for word in LEAKS:
        assert word not in dumped, word


@pytest.fixture
def assessed(client, oracle):
    """Common assessment alice -> {bob, carol, minh}: bob correct, carol partial, minh unsafe."""
    h = create_unassigned(client)
    v, ex = released_exercise(client, oracle, h)
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
    return {"handoff": h, "version": v, "exercise": ex, "attempts": attempts}


@pytest.fixture
def successor(client, oracle):
    """Plain handoff alice -> bob; bob answered unsafely once."""
    h = make_handoff(client)
    v, ex = released_exercise(client, oracle, h)
    r = submit(client, ex["id"], oracle["successor_answers"]["unsafe"], "bob")
    assert r.status_code == 201, r.text
    return {"handoff": h, "version": v, "exercise": ex, "attempt": r.json()}


class _FailingAssessor:
    model_id = "fake-failing"

    def assess(self, scenario, criteria, answer):
        raise AppError(502, "provider_error", "provider unavailable")


# ---------- access ----------


def test_only_owner_can_open_coach(client, assessed):
    carol = assessed["attempts"]["carol"]["id"]
    assert coach(client, "carol", carol).status_code == 200
    for who in ("admin", EXPERT):
        r = coach(client, who, carol)
        assert r.status_code == 403 and r.json()["error"]["code"] == "not_attempt_owner"
    for who in ("bob", "minh"):
        assert coach(client, who, carol).status_code == 404
    assert coach(client, "carol", str(uuid.uuid4())).status_code == 404
    assert coach(client, "carol", "not-a-uuid").status_code == 404
    client.cookies.clear()
    r = client.get(f"/api/attempts/{carol}/coach")
    assert r.status_code == 401 and r.json()["error"]["code"] == "not_authenticated"


def test_requires_assessed_attempt(client, successor, monkeypatch):
    ex = successor["exercise"]
    monkeypatch.setattr(V, "get_assessor", lambda: _FailingAssessor())
    failed = submit(client, ex["id"], "My answer", "bob")
    assert failed.status_code == 502
    failed_id = failed.json()["error"]["attempt_id"]

    session = next(get_session())
    try:
        pending = Attempt(
            exercise_id=uuid.UUID(ex["id"]),
            successor_id="bob",
            answer="Still being assessed",
            assessment_status="pending",
        )
        session.add(pending)
        session.commit()
        pending_id = str(pending.id)
    finally:
        session.close()

    for attempt_id in (failed_id, pending_id):
        r = coach(client, "bob", attempt_id)
        assert r.status_code == 409 and r.json()["error"]["code"] == "not_assessed"


# ---------- items ----------


def test_items_are_unmet_and_partial_only_in_rubric_order(client, assessed):
    carol = assessed["attempts"]["carol"]
    rubric = [c["id"] for c in criteria(client, assessed["exercise"]["id"])]
    verdicts = {r["criterion_id"]: r["verdict"] for r in carol["results"]}
    expected = [cid for cid in rubric if verdicts[cid] in ("partial", "unmet")]
    assert expected  # the partial answer misses something

    out = coach_ok(client, "carol", carol["id"])
    assert [i["criterion_id"] for i in out["items"]] == expected
    assert [i["verdict"] for i in out["items"]] == [verdicts[cid] for cid in expected]
    assert out["met_count"] == sum(v == "met" for v in verdicts.values())
    assert out["total"] == len(rubric)
    assert out["result"] == carol["effective_result"] == "partial"
    assert out["next_step"] == "official_result_stands"
    assert out["provider"] == "offline"
    texts = {r["criterion_id"]: r["text"] for r in carol["results"]}
    quotes = {r["criterion_id"]: r["evidence_quote"] for r in carol["results"]}
    for item in out["items"]:
        cid = item["criterion_id"]
        assert item["criterion_text"] == texts[cid]
        assert item["your_quote"] == (quotes[cid] or None)
        lead = "did not cover" if item["verdict"] == "unmet" else "only partly covered"
        assert item["explanation"] == f"Your answer {lead}: {texts[cid]}."
        assert item["practice"]["prompt"].startswith("In your own words")
        assert item["reread"]["text"] not in item["practice"]["prompt"]


def test_coach_never_reveals_critical(client, assessed, successor, oracle):
    answers = oracle["successor_answers"]
    outs = [coach_ok(client, who, a["id"]) for who, a in assessed["attempts"].items()]
    bob_ex = successor["exercise"]["id"]
    outs.append(coach_ok(client, "bob", successor["attempt"]["id"]))
    for key in ("correct_paraphrase", "partial_answer"):
        a = submit(client, bob_ex, answers[key], "bob").json()
        outs.append(coach_ok(client, "bob", a["id"]))
    assert sum(len(o["items"]) for o in outs) > 0
    for out in outs:
        assert_no_leak(out)
        for item in out["items"]:
            assert item["reread"]["line_id"].startswith("L")  # opaque, never a section name
    carol = coach_ok(client, "carol", assessed["attempts"]["carol"]["id"])
    for item in carol["items"]:
        r = practise(client, "carol", item["practice"]["practice_id"], answers["unsafe"])
        assert r.status_code == 200, r.text
        assert_no_leak(r.json())


def test_reread_is_exact_approved_line(client, assessed):
    ex = assessed["exercise"]
    version = login_as(client, "carol").get(f"/api/knowledge/{ex['knowledge_version_id']}").json()
    rubric = {c["id"]: c for c in criteria(client, ex["id"])}
    for who in ("carol", "minh"):
        out = coach_ok(client, who, assessed["attempts"][who]["id"])
        assert out["items"]
        for item in out["items"]:
            path = rubric[item["criterion_id"]]["source_path"]
            reread = item["reread"]
            assert reread["text"] == resolve(version["approved_content"], path)
            assert reread["version_id"] == ex["knowledge_version_id"] == version["id"]
            assert reread["version_no"] == version["version_no"]
            assert reread["link"] == f"/library?open={version['id']}"


def test_drafts_never_used(client, assessed, oracle):
    marker = "Rotate the zebra quartz rollback lever twice"
    content = oracle["expert_capture"]["content"]
    v = assessed["version"]
    alice = login_as(client, EXPERT)
    finding = alice.get(f"/api/findings/{v['finding_id']}").json()
    edited = {f: [marker for _ in content[f]] for f in GUIDANCE_FIELDS}
    r = alice.put(
        f"/api/findings/{finding['id']}/draft",
        json={"content": content | edited, "expected_revision": finding["draft"]["revision"]},
    )
    assert r.status_code == 200, r.text

    for who in ("carol", "minh"):
        out = coach_ok(client, who, assessed["attempts"][who]["id"])
        assert "zebra" not in json.dumps(out).lower()
        for item in out["items"]:
            r = practise(client, who, item["practice"]["practice_id"], marker)
            assert "zebra" not in r.json()["reread_text"].lower()


def test_review_overrides_are_respected(client, assessed):
    carol = assessed["attempts"]["carol"]
    before = coach_ok(client, "carol", carol["id"])
    target = before["items"][0]["criterion_id"]

    r = login_as(client, "carol").post(f"/api/attempts/{carol['id']}/review-request")
    assert r.status_code == 201, r.text
    # Requested but not yet reviewed: nothing changes.
    assert coach_ok(client, "carol", carol["id"])["items"] == before["items"]
    r = login_as(client, EXPERT).post(
        f"/api/attempts/{carol['id']}/review",
        json={"overrides": {target: "met"}, "reason": "The answer covers it in other words."},
    )
    assert r.status_code == 200, r.text

    after = coach_ok(client, "carol", carol["id"])
    assert target not in [i["criterion_id"] for i in after["items"]]
    assert [i["criterion_id"] for i in after["items"]] == [
        i["criterion_id"] for i in before["items"][1:]
    ]
    assert after["met_count"] == before["met_count"] + 1
    assert after["result"] == r.json()["effective_result"]


def test_demonstrated_has_no_items(client, assessed):
    bob = assessed["attempts"]["bob"]
    assert bob["effective_result"] == "demonstrated"
    out = coach_ok(client, "bob", bob["id"])
    assert out["items"] == []
    assert out["message"] == "Nothing to fix in this attempt."
    assert out["next_step"] == "none"
    assert out["met_count"] == out["total"]


def test_successor_is_sent_back_to_try_again(client, successor, oracle):
    a = successor["attempt"]
    assert a["effective_result"] == "not_yet"
    out = coach_ok(client, "bob", a["id"])
    assert out["items"] and out["next_step"] == "try_again"
    r = submit(
        client,
        successor["exercise"]["id"],
        oracle["successor_answers"]["correct_paraphrase"],
        "bob",
    )
    assert r.status_code == 201 and r.json()["effective_result"] == "demonstrated"


# ---------- practice ----------


def _counts() -> dict:
    tables = ("attempt", "attempt_review", "operation", "audit_event", "successor_selection")
    return {t: query(f"select count(*) from {t}")[0][0] for t in tables}


def test_practice_is_not_counted_or_stored(client, assessed, oracle):
    h, ex = assessed["handoff"], assessed["exercise"]
    carol = assessed["attempts"]["carol"]
    out = coach_ok(client, "carol", carol["id"])  # the one audit write happens here
    before_counts = _counts()
    before_ready = readiness(client, h["id"])
    before_ex = login_as(client, "carol").get(f"/api/exercises/{ex['id']}").json()
    before_attempts = query("select id, answer, criterion_results from attempt order by id")

    marker = "Walrus ledger practice phrase"
    for item in out["items"]:
        for answer in (
            f"{marker} {item['reread']['text']}",
            f"{marker} only",
            item["reread"]["text"],
        ):
            r = practise(client, "carol", item["practice"]["practice_id"], answer)
            assert r.status_code == 200, r.text

    assert _counts() == before_counts
    assert readiness(client, h["id"]) == before_ready
    after_ex = login_as(client, "carol").get(f"/api/exercises/{ex['id']}").json()
    assert after_ex["candidate"]["attempts_used"] == before_ex["candidate"]["attempts_used"] == 1
    assert after_ex["attempts"] == before_ex["attempts"]
    assert query("select id, answer, criterion_results from attempt order by id") == before_attempts
    # The official attempt is still used: no further submission.
    r = submit(client, ex["id"], oracle["successor_answers"]["correct_paraphrase"], "carol")
    assert r.status_code == 409 and r.json()["error"]["code"] == "attempt_limit"
    # No table holds the practice text anywhere.
    tables = [
        t
        for (t,) in query(
            "select table_name from information_schema.tables "
            "where table_schema = 'public' and table_type = 'BASE TABLE'"
        )
    ]
    for t in tables:
        hits = query(f'select count(*) from "{t}" r where r::text ilike :m', m=f"%{marker}%")
        assert hits[0][0] == 0, t


def test_practice_token_is_bound(client, assessed):
    carol = assessed["attempts"]["carol"]
    item = coach_ok(client, "carol", carol["id"])["items"][0]
    token = item["practice"]["practice_id"]
    answer = item["reread"]["text"]
    assert practise(client, "carol", token, answer).status_code == 200

    body, sig = token.split(".")
    other = C._b64(f"{carol['id']}:L1".encode())
    for bad in (token + "x", f"{other}.{sig}", f"{body}.{C._b64(b'forged')}", "nonsense", ""):
        r = practise(client, "carol", bad, answer)
        assert r.status_code in (400, 422), bad
        if r.status_code == 400:
            assert r.json()["error"]["code"] == "invalid_practice_token"

    # Another learner, the admin and the expert cannot use carol's token.
    r = practise(client, "bob", token, answer)
    assert r.status_code == 404
    for who in ("admin", EXPERT):
        r = practise(client, who, token, answer)
        assert r.status_code == 403 and r.json()["error"]["code"] == "not_attempt_owner"

    # A correctly signed token for a line that is not in the approved version.
    outside = C.practice_token(uuid.UUID(carol["id"]), "L99")
    r = practise(client, "carol", outside, answer)
    assert r.status_code == 400 and r.json()["error"]["code"] == "line_not_in_version"

    # The session decides who practises; body fields are ignored.
    r = login_as(client, "bob").post(
        "/api/coach/practice",
        json={"practice_id": token, "answer": answer, "actor_id": "carol", "user": "carol"},
    )
    assert r.status_code == 404
    # A write without the CSRF header is refused.
    r = login_as(client, "carol").post(
        "/api/coach/practice",
        json={"practice_id": token, "answer": answer},
        headers={"X-Requested-With": ""},
    )
    assert r.status_code == 403 and r.json()["error"]["code"] == "csrf_header_missing"


def test_practice_verdicts(client, assessed, oracle):
    carol = assessed["attempts"]["carol"]
    content = assessed["version"]["approved_content"]
    lines = {path: lid for lid, path, _ in C.approved_lines(content)}
    escalate = C.practice_token(uuid.UUID(carol["id"]), lines["stop_and_escalate[1]"])
    paraphrase = (
        "If the provider state is unclear, I pause the retry worker and escalate to the "
        "AcmePay contact."
    )
    r = practise(client, "carol", escalate, paraphrase)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["verdict"] == "met"
    assert out["reread_text"] == content["stop_and_escalate"][1]
    assert out["feedback"] == C.PRACTICE_FEEDBACK["met"]

    for answer in ("   ", "I would make a cup of coffee and read the news."):
        out = practise(client, "carol", escalate, answer).json()
        assert out["verdict"] == "unmet"
        assert out["feedback"] == C.PRACTICE_FEEDBACK["unmet"]
    for answer in ("", "x" * 1001):
        assert practise(client, "carol", escalate, answer).status_code == 422
    assert practise(client, "carol", escalate, "x" * 1000).status_code == 200


# ---------- audit ----------


def test_coach_opened_audited_once_without_text(client, assessed):
    carol = assessed["attempts"]["carol"]
    for _ in range(3):
        out = coach_ok(client, "carol", carol["id"])
    practise(client, "carol", out["items"][0]["practice"]["practice_id"], "Some practice text")
    rows = query(
        "select actor_id, target_type, target_id::text, metadata from audit_event "
        "where action = 'coach.opened'"
    )
    assert rows == [("carol", "attempt", carol["id"], {})]
    # Refused opens are not audited.
    coach(client, "admin", assessed["attempts"]["minh"]["id"])
    coach(client, "bob", assessed["attempts"]["minh"]["id"])
    assert len(query("select 1 from audit_event where action = 'coach.opened'")) == 1


# ---------- OpenAI mode (fake client, no network) ----------


@pytest.fixture
def openai_mode(monkeypatch):
    """Call with a fake client once setup is done: from then on the provider is openai."""

    def use(fake: FakeClient) -> OpenAICoach:
        monkeypatch.setattr(get_settings(), "ai_provider", "openai")
        model = OpenAICoach(
            StructuredCall(fake, "fake-model", timeout_seconds=5, max_retries=1, max_calls=2)
        )
        monkeypatch.setattr(C, "get_model", lambda: model)
        return model

    return use


def _reply(explanation: str, cited_ids: list[str]) -> str:
    return json.dumps({"explanation": explanation, "cited_ids": cited_ids})


def _offline(item: dict) -> str:
    lead = "did not cover" if item["verdict"] == "unmet" else "only partly covered"
    return f"Your answer {lead}: {item['criterion_text']}."


def test_openai_valid_citation_is_used(client, assessed, openai_mode):
    fake = FakeClient(_reply("unused", []))
    openai_mode(fake)

    def create(**body):
        line = json.loads(body["messages"][1]["content"])["line"]
        fake.outcomes = [_reply("Your answer did not say to check this first.", [line["id"]])]
        return FakeClient._create(fake, **body)

    fake.chat.completions.create = create
    out = coach_ok(client, "carol", assessed["attempts"]["carol"]["id"])
    assert out["provider"] == "openai"
    assert {i["explanation"] for i in out["items"]} == {
        "Your answer did not say to check this first."
    }
    for body, item in zip(fake.requests, out["items"], strict=True):
        assert body["messages"][0]["content"] == SYSTEM_PROMPT
        sent = json.loads(body["messages"][1]["content"])
        assert set(sent) == {"criterion", "answer", "line"}
        assert sent["criterion"] == item["criterion_text"]
        assert sent["line"] == {"id": item["reread"]["line_id"], "text": item["reread"]["text"]}
        assert sent["answer"] == assessed["attempts"]["carol"]["answer"]
        assert_no_leak(sent)


def test_openai_invalid_citation_falls_back(client, assessed, openai_mode):
    carol = assessed["attempts"]["carol"]["id"]
    for explanation, cited in (
        ("Retry the settlement three times.", ["L99"]),
        ("Retry the settlement three times.", []),
        ("", ["L1"]),
        ("This was the most critical safety line.", ["L1", "L2"]),
    ):
        openai_mode(FakeClient(_reply(explanation, cited)))
        out = coach_ok(client, "carol", carol)
        assert out["provider"] == "offline_fallback"
        assert "three times" not in json.dumps(out)
        assert [i["explanation"] for i in out["items"]] == [_offline(i) for i in out["items"]]
        assert_no_leak(out)


def test_openai_rejects_hinting_wording(client, assessed, openai_mode):
    fake = FakeClient(_reply("unused", []))
    openai_mode(fake)

    def create(**body):
        line = json.loads(body["messages"][1]["content"])["line"]
        fake.outcomes = [
            _reply("You missed the most important, safety-critical check.", [line["id"]])
        ]
        return FakeClient._create(fake, **body)

    fake.chat.completions.create = create
    out = coach_ok(client, "carol", assessed["attempts"]["carol"]["id"])
    assert out["provider"] == "offline_fallback"
    assert_no_leak(out)


def test_openai_timeout_falls_back(client, assessed, openai_mode):
    carol = assessed["attempts"]["carol"]["id"]
    for error in (TimeoutError("slow"), RuntimeError("provider down")):
        openai_mode(FakeClient(error))
        out = coach_ok(client, "carol", carol)
        assert out["provider"] == "offline_fallback"
        assert [i["explanation"] for i in out["items"]] == [_offline(i) for i in out["items"]]
    # Nothing to explain, so no model call.
    fake = FakeClient(TimeoutError("unused"))
    openai_mode(fake)
    assert coach_ok(client, "bob", assessed["attempts"]["bob"]["id"])["provider"] == "offline"
    assert fake.requests == []


# ---------- help ----------


def test_help_topic_learning_coach(client, successor):
    page = f"/learn/exercises/{successor['exercise']['id']}"
    r = login_as(client, "bob").post(
        "/api/assistant/ask", json={"question": "What is the learning coach?", "page": page}
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["mode"] == "help"
    assert out["citations"] == [
        {"kind": "help_topic", "id": "learning-coach", "title": "Learning Coach"}
    ]
    assert "never counted" in out["answer"] and "critical" not in out["answer"].lower()
    # Not offered to the expert or the admin.
    for who in (EXPERT, "admin"):
        r = login_as(client, who).post(
            "/api/assistant/ask", json={"question": "What is the learning coach?", "page": page}
        )
        assert all(c["id"] != "learning-coach" for c in r.json()["citations"])
