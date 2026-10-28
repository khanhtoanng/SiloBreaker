"""Browser-level check of successor selection (README "Successor selection", docs/DEMO.md):

a. admin: Reset demo -> handoff Alice with "Choose successor later" -> Run analysis
b. alice: confirm Settlement, capture, approve v1, generate and release the exercise
c. admin: Suitability shows Bob 20%, Carol 20%, Minh "No history - not 0%" -> select all
          three -> Start common assessment (released exercise, due date)
d. bob (correct), carol (partial_answer), minh (unsafe): Submit locked -> Read the approved
          knowledge -> back -> submit the one official attempt -> own score shown. Carol
          opens the Learning Coach: only her missed items, the approved line to re-read, one
          practice check -> "official result stands", still no Submit or Try again (also at
          a 360px width)
e. alice: the exercise lists attempts by alias only, no names
f. admin: Results shows Bob 100% Best result, Carol and Minh with the scores the backend
          computed from the assessor's verdicts (re-checked here from those verdicts), Minh
          "Missing a critical condition" -> selecting Carol without a reason is blocked ->
          select Bob -> decision shown -> audit log has successor.selected

Run with the API on :8000 (demo accounts seeded: python -m app.seed_users) and the Vite dev
server on :5173:
    python e2e/selection_flow.py [screenshot_dir] [--runs N]

Set SB_E2E_BROWSER_CHANNEL=chrome (or msedge) to use an installed browser instead of the
Playwright-managed Chromium. Each run uses a fresh browser context and starts with Reset demo.
"""

import argparse
import json
import os
import re
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright

BASE = os.environ.get("SB_E2E_BASE_URL", "http://localhost:5173")
ROOT = Path(__file__).resolve().parents[1]
ORACLE = ROOT / "fixtures" / "oracle"
EXPERT_CAPTURE = json.loads((ORACLE / "expert_capture.json").read_text())
EXPERT_ANSWER, EXPERT_CONTENT = EXPERT_CAPTURE["answer"], EXPERT_CAPTURE["content"]
SUCCESSOR = json.loads((ORACLE / "successor_answers.json").read_text())
# Demo-only accounts created by `python -m app.seed_users`.
ACCOUNTS = {
    "admin": "Admin@123",
    "alice": "Alice@123",
    "bob": "Bob@123",
    "carol": "Carol@123",
    "minh": "Minh@123",
}
NAMES = {"bob": "Bob", "carol": "Carol", "minh": "Minh"}
ANSWERS = {
    "bob": SUCCESSOR["correct_paraphrase"],
    "carol": SUCCESSOR["partial_answer"],
    "minh": SUCCESSOR["unsafe"],
}

parser = argparse.ArgumentParser()
parser.add_argument("shots", nargs="?", type=Path)
parser.add_argument("--runs", type=int, default=1)
args = parser.parse_args()


def shot(page: Page, run: int, name: str) -> None:
    if args.shots:
        args.shots.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(args.shots / f"selection-run{run}-{name}.png"), full_page=True)


def at(page: Page, path: str) -> None:
    expect(page).to_have_url(re.compile("^" + re.escape(BASE) + path + "$"))


def nav(page: Page, label: str) -> None:
    page.get_by_role("navigation", name="Main").get_by_role("link", name=label, exact=True).click()


def login(page: Page, user: str) -> None:
    page.goto(f"{BASE}/login")
    page.get_by_label("Username").fill(user)
    page.get_by_label("Password").fill(ACCOUNTS[user])
    page.get_by_role("button", name="Sign in").click()
    expect(page.get_by_role("button", name="Log out")).to_be_visible()


def logout(page: Page) -> None:
    page.get_by_role("button", name="Log out").click()
    at(page, "/login")


def no_horizontal_scroll(page: Page, where: str, viewport: int = 390) -> None:
    """At phone width nothing may scroll sideways."""
    page.set_viewport_size({"width": viewport, "height": 844})
    width = page.evaluate("document.documentElement.scrollWidth")
    page.set_viewport_size({"width": 1360, "height": 900})
    assert width <= viewport, f"{where}: page is {width}px wide at a {viewport}px viewport"


def open_selection(page: Page) -> None:
    nav(page, "Handoffs")
    at(page, "/admin/handoffs")
    page.get_by_role("link", name="Choose successor").click()
    at(page, "/admin/handoffs/[^/]+")


def set_list(page: Page, label: str, items: list[str]) -> None:
    group = page.get_by_role("group", name=label, exact=True)
    rows = group.get_by_role("textbox")
    while rows.count() < len(items):
        group.get_by_role("button", name="+ Add").click()
    while rows.count() > len(items):
        group.get_by_role("button", name="Remove").last.click()
    for i, text in enumerate(items, start=1):
        group.get_by_label(f"{label} {i}", exact=True).fill(text)


def admin_setup(page: Page, run: int) -> None:
    login(page, "admin")
    nav(page, "Handoffs")
    at(page, "/admin/handoffs")
    page.get_by_role("button", name="Reset demo").click()  # confirm dialog is accepted
    expect(page.get_by_text("No handoffs yet.")).to_be_visible(timeout=30_000)
    page.get_by_label("Experienced engineer (must appear in the evidence)").select_option("alice")
    page.get_by_label("Successor (any active member)").select_option(
        label="Choose successor later"
    )
    page.get_by_role("button", name="Create handoff").click()
    expect(page.get_by_role("region", name="All handoffs")).to_contain_text(
        "Alice → successor not chosen"
    )
    page.get_by_role("button", name="Run analysis").click()
    at(page, "/expert/handoffs/[^/]+/detect")
    expect(page.get_by_role("article", name="Settlement recovery")).to_be_visible()
    shot(page, run, "1-admin-detect")
    logout(page)


def expert_capture(page: Page, run: int) -> None:
    login(page, "alice")
    page.get_by_role("link", name="Open Detect").click()
    first = page.get_by_role("article", name="Settlement recovery")
    first.get_by_role("button", name="Review with expert").click()
    at(page, "/expert/findings/[^/]+")
    page.get_by_role("button", name="Confirm", exact=True).click()
    page.get_by_label("Expert answer, in your own words").fill(EXPERT_ANSWER)
    page.get_by_role("button", name="Structure my answer").click()
    expect(page.get_by_label("Stop and escalate 1")).not_to_have_value("")
    # The expert edits the suggestion into the approved wording of the scenario
    # (fixtures/oracle/expert_capture.json), so the exercise grades the same rubric as the
    # backend tests: Carol's partial_answer is partial, not a critical miss.
    for label, field in (
        ("Preconditions", "prerequisites"),
        ("Ordered steps", "steps"),
        ("Stop and escalate", "stop_and_escalate"),
        ("Success checks", "success_checks"),
    ):
        set_list(page, label, EXPERT_CONTENT[field])
    page.get_by_role("button", name="Save draft").click()
    page.get_by_role("button", name="Approve revision 1").click()
    expect(page.locator(".versions")).to_contain_text("v1")
    page.get_by_role("link", name="Open exercise for v1").click()
    verify = page.locator(".verify")
    verify.get_by_role("button", name="Generate exercise").click()
    verify.get_by_role("button", name="Approve and release exercise").click()
    expect(verify).to_contain_text("released")
    shot(page, run, "2-exercise-released")
    logout(page)


def admin_suitability(page: Page, run: int) -> None:
    login(page, "admin")
    open_selection(page)
    expect(page.get_by_role("tab", name="Suitability")).to_have_attribute("aria-selected", "true")
    table = page.get_by_role("table", name="Suitability")
    expect(table.get_by_role("img", name="Fit for Bob 20%")).to_be_visible()
    expect(table.get_by_role("img", name="Fit for Carol 20%")).to_be_visible()
    minh = table.get_by_role("row").filter(has_text="Minh")
    expect(minh).to_contain_text("No history — not 0%")
    expect(minh.get_by_role("img")).to_have_count(0)  # no bar, so never a 0% bar
    expect(page.get_by_role("note")).to_have_text(
        "Fit is based on cited recoveries in the evidence only. It is used to shortlist, "
        "not to choose."
    )
    no_horizontal_scroll(page, "Suitability")
    shot(page, run, "3-suitability")

    for name in NAMES.values():
        page.get_by_label(f"Select {name}").check()
    expect(page.get_by_role("button", name="Assign directly")).to_have_count(0)
    page.get_by_role("button", name="Start common assessment").click()
    dialog = page.get_by_role("dialog", name="Start common assessment")
    expect(dialog.get_by_label("Released exercise")).to_contain_text("Settlement recovery")
    expect(dialog.get_by_label("Due")).not_to_have_value("")
    dialog.get_by_role("button", name="Start assessment").click()
    expect(page.get_by_role("tab", name="Results")).to_have_attribute("aria-selected", "true")
    expect(page.get_by_role("table", name="Results").get_by_text("Not submitted")).to_have_count(3)
    logout(page)


def candidate_answers(page: Page, run: int, who: str) -> None:
    login(page, who)
    at(page, "/learn")
    page.get_by_role("link", name="Start").click()
    at(page, "/learn/exercises/[^/]+")
    exercise_url = page.url
    verify = page.locator(".verify")
    expect(verify.get_by_role("note")).to_have_text(
        re.compile(
            r"^You are one of 3 candidates · same exercise · one official attempt · due .+ · "
            r"results are private$"
        )
    )
    expect(verify).not_to_contain_text("rubric")
    verify.get_by_label("Your answer").fill("draft")
    expect(verify.get_by_role("button", name="Submit answer")).to_be_disabled()

    verify.get_by_role("button", name="Read the approved knowledge").click()
    at(page, r"/library\?open=.+")
    expect(page.get_by_role("heading", name="Stop and escalate")).to_be_visible()
    page.get_by_role("link", name="Back to your exercise").click()
    expect(page).to_have_url(exercise_url)

    verify.get_by_label("Your answer").fill(ANSWERS[who])
    submit = verify.get_by_role("button", name="Submit answer")
    expect(submit).to_be_enabled()
    submit.click()
    expect(verify.get_by_text(re.compile(r"^Your score: \d+%"))).to_be_visible()
    expect(verify.get_by_role("button", name="Request review")).to_be_visible()
    expect(verify.get_by_role("button", name="Submit answer")).to_have_count(0)
    expect(verify.get_by_role("button", name="Try again")).to_have_count(0)
    if who == "bob":
        no_horizontal_scroll(page, "Learn")
        expect(verify.get_by_text("Nothing to fix in this attempt.")).to_be_visible()
        expect(verify.get_by_role("button", name="Coach me on this attempt")).to_have_count(0)
    shot(page, run, f"4-{who}-scored")
    if who == "carol":
        carol_coach(page, run, verify)
    logout(page)


def carol_coach(page: Page, run: int, verify) -> None:
    """Carol's partial official attempt: the coach shows only what she missed; practice is
    checked but never changes the result, and she still cannot submit again."""
    verify.get_by_role("button", name="Coach me on this attempt").click()
    coach = verify.get_by_role(
        "region", name="Learning Coach — practice does not change your result."
    )
    cards = coach.get_by_role("article")
    expect(cards).to_have_count(1)
    card = cards.first
    line = "The ledger shows exactly one settlement for the order"
    expect(card).to_contain_text("Not met")
    expect(card.locator("blockquote")).to_have_text(line)
    expect(card.get_by_role("link", name=re.compile("in the Library$"))).to_have_attribute(
        "href", re.compile(r"^/library\?open=")
    )
    card.get_by_role("textbox").fill("Done means the ledger has exactly one settlement for it.")
    card.get_by_role("button", name="Check").click()
    expect(card.get_by_role("status")).to_contain_text("Covered.")
    expect(coach.get_by_role("note")).to_have_text(
        "Your official result for this assessment stands. Practice is for learning only."
    )
    expect(verify).not_to_contain_text("ritical")
    expect(verify.get_by_role("button", name="Submit answer")).to_have_count(0)
    expect(verify.get_by_role("button", name="Try again")).to_have_count(0)
    no_horizontal_scroll(page, "Learning Coach", viewport=360)
    shot(page, run, "4a-carol-coach")
    # The score did not move.
    expect(verify.get_by_text(re.compile(r"^Your score: \d+%"))).to_be_visible()


def expert_sees_aliases(page: Page, run: int) -> None:
    login(page, "alice")
    version = page.request.get(f"{BASE}/api/library").json()[0]["version_id"]
    page.goto(f"{BASE}/expert/knowledge/{version}/exercise")
    verify = page.locator(".verify")
    attempts = verify.get_by_role("article", name=re.compile(r"^Attempt \d by Candidate [A-D]$"))
    expect(attempts).to_have_count(3)
    for name in NAMES.values():
        expect(verify).not_to_contain_text(re.compile(name, re.IGNORECASE))
    shot(page, run, "5-expert-aliases")
    logout(page)


def expected_score(attempt: dict) -> int:
    """README formula on the assessor's verdicts: critical weight 2, other 1; met 1,
    partial 0.5, unmet 0; rounded half up. A check on the backend, not a replacement."""
    credit = {"met": 1.0, "partial": 0.5, "unmet": 0.0, "uncertain": 0.0}
    weights = {r["criterion_id"]: 2 if r["critical"] else 1 for r in attempt["results"]}
    got = sum(weights[r["criterion_id"]] * credit[r["verdict"]] for r in attempt["results"])
    return int(100 * got / sum(weights.values()) + 0.5)


def admin_results(page: Page, run: int) -> dict[str, int]:
    login(page, "admin")
    open_selection(page)
    handoff_id = page.url.rsplit("/", 1)[1]
    readiness = page.request.get(f"{BASE}/api/handoffs/{handoff_id}/readiness").json()
    scores = {}
    for c in readiness["candidates"]:
        attempt = page.request.get(f"{BASE}/api/attempts/{c['best_attempt_id']}").json()
        assert c["score_pct"] == expected_score(attempt), (c["person_id"], c["score_pct"])
        scores[c["person_id"]] = c["score_pct"]
    assert scores["bob"] == 100, scores

    table = page.get_by_role("table", name="Results")
    rows = {who: table.get_by_role("row", name=re.compile(f"^{n} ")) for who, n in NAMES.items()}
    for who, name in NAMES.items():
        expect(rows[who].get_by_role("img", name=f"Score for {name} {scores[who]}%")).to_be_visible()
    expect(rows["bob"]).to_contain_text("Best result")
    expect(rows["carol"]).not_to_contain_text("Best result")
    expect(rows["carol"]).to_contain_text("Ready with support")
    expect(rows["carol"]).not_to_contain_text("Missing a critical condition")
    assert [c["person_id"] for c in readiness["candidates"]] == ["bob", "carol", "minh"]
    expect(rows["minh"]).to_contain_text("Missing a critical condition")
    expect(page.get_by_role("note")).to_have_text(
        "Decision support only. Scores reflect one exercise on this knowledge area, "
        "not overall ability."
    )
    rows["bob"].get_by_role("button", name="Details").click()
    expect(page.get_by_role("list", name="Criteria for Bob").get_by_text("critical")).not_to_have_count(0)
    no_horizontal_scroll(page, "Results")
    shot(page, run, "6-results")

    # Carol is outside the top: no reason, no selection.
    rows["carol"].get_by_role("button", name="Select as successor").click()
    dialog = page.get_by_role("dialog", name="Select as successor")
    expect(dialog.get_by_label(re.compile(r"^Reason \(required"))).to_be_visible()
    expect(dialog.get_by_role("button", name="Confirm selection")).to_be_disabled()
    refused = page.request.post(
        f"{BASE}/api/handoffs/{handoff_id}/selection",
        data={"selected_person_id": "carol"},
        headers={"X-Requested-With": "silobreaker"},
    )
    assert refused.status == 422 and refused.json()["error"]["code"] == "reason_required"
    dialog.get_by_role("button", name="Cancel").click()

    rows["bob"].get_by_role("button", name="Select as successor").click()
    dialog = page.get_by_role("dialog", name="Select as successor")
    expect(dialog.get_by_label("Reason (optional)")).to_be_visible()
    dialog.get_by_role("button", name="Confirm selection").click()
    decision = page.get_by_role("region", name="Decision")
    expect(decision).to_contain_text(re.compile(r"Bob \(Candidate [A-D]\) selected by admin"))
    expect(decision).to_contain_text("In the top result: yes")
    expect(decision).to_contain_text("Tie: no")
    expect(page.get_by_role("button", name="Select as successor")).to_have_count(0)
    shot(page, run, "7-decision")

    nav(page, "Audit log")
    page.get_by_label("Action").fill("successor.selected")
    page.get_by_role("button", name="Apply filters").click()
    expect(page.locator("table.data tbody tr")).to_have_count(1)
    expect(page.locator("table.data tbody")).to_contain_text("successor.selected")
    shot(page, run, "8-audit")
    logout(page)
    return scores


with sync_playwright() as p:
    channel = os.environ.get("SB_E2E_BROWSER_CHANNEL") or None
    browser = p.chromium.launch(channel=channel)
    for run in range(1, args.runs + 1):
        context = browser.new_context(viewport={"width": 1360, "height": 900})
        page = context.new_page()
        page.on("dialog", lambda d: d.accept())
        admin_setup(page, run)
        expert_capture(page, run)
        admin_suitability(page, run)
        for who in ("bob", "carol", "minh"):
            candidate_answers(page, run, who)
        expert_sees_aliases(page, run)
        scores = admin_results(page, run)
        context.close()
        print(f"run {run}/{args.runs} passed · scores {scores}")
    browser.close()
print("e2e selection flow passed")
