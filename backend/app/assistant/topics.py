"""Curated help topics: the only text the assistant may use in help mode.

Every number is built from the constant the code computes it with, so a topic cannot drift
from app.scoring or app.verify.selection. No topic names a real exercise, its criteria or
which of them are critical: help answers are the same for everyone with the same role.
"""

from dataclasses import dataclass

from app.scoring.rules import (
    CAP,
    CAP_REASON_ALTERNATE_RECOVERY,
    CAP_REASON_PARTICIPATION,
    MAX_RANKED,
    MIN_ATTRIBUTABLE_EVENTS,
    WEIGHTS,
)
from app.verify.selection import (
    COMMON_ASSESSMENT_ATTEMPTS,
    CREDIT,
    CRITICAL_WEIGHT,
    NORMAL_WEIGHT,
    experience,
)

ROLES = ("admin", "expert", "successor", "candidate")
ANY = "any"


@dataclass(frozen=True)
class Topic:
    id: str
    title: str
    roles: tuple[str, ...]  # who may get this topic; ("any",) for everyone signed in
    pages: tuple[str, ...]  # route prefixes it answers on; ("any",) for every page
    keywords: tuple[str, ...]
    answer: str
    # A question this topic answers, offered as a suggestion on these route prefixes.
    suggest: str
    suggest_on: tuple[str, ...] = ()


FORMULA = " + ".join(f"{w}{k}" for k, w in WEIGHTS.items())
ONE_ATTEMPT = "one official attempt" if COMMON_ASSESSMENT_ATTEMPTS == 1 else "official attempts"


def _num(x: float) -> str:
    return f"{x:g}"


TOPICS: tuple[Topic, ...] = (
    # ---------- everyone ----------
    Topic(
        id="sign-in-out",
        title="Signing in and out",
        roles=(ANY,),
        pages=(ANY,),
        keywords=(
            "sign",
            "login",
            "log",
            "logout",
            "password",
            "account",
            "tab",
            "switch",
            "session",
            "user",
            "changed",
            "another",
        ),
        answer=(
            "Sign in on the login page with your username and password; Log out is at the top "
            "right. Your session is one cookie shared by every tab of this browser. If you sign "
            "in as someone else in another tab, that new session replaces the cookie, so this "
            "tab acts as the other account on its next request. Use a private window or a second "
            "browser profile to be signed in as two people at once."
        ),
        suggest="Why did another tab switch my account?",
    ),
    Topic(
        id="library",
        title="The knowledge library",
        roles=(ANY,),
        pages=(ANY,),
        keywords=("library", "approved", "knowledge", "read", "where", "unit", "find"),
        answer=(
            "Library lists the newest approved version of every confirmed knowledge area. "
            "Anyone signed in can read it. Drafts and retired knowledge are never listed. "
            "Open an entry with Read to see its preconditions, steps, stop-and-escalate "
            "conditions and success checks, and download it as OKF."
        ),
        suggest="Where do I read approved knowledge?",
        suggest_on=("/library", "/learn"),
    ),
    Topic(
        id="assistant-sources",
        title="What this assistant can answer",
        roles=(ANY,),
        pages=(ANY,),
        keywords=(
            "assistant",
            "help",
            "answer",
            "paused",
            "locked",
            "source",
            "chat",
            "you",
            "knowledge",
            "guide",
        ),
        answer=(
            "This assistant answers from two sources only: this help guide, and approved "
            "knowledge you are allowed to read in the Library. Every knowledge answer quotes the "
            "approved lines and cites the version. It never uses drafts, private rubrics or other "
            "people's results, and it says so when it does not know. Knowledge answers are paused "
            "while you have a released exercise to complete, so the exercise stays fair. Nothing "
            "you ask is stored; the chat is gone when you reload."
        ),
        suggest="Why are knowledge answers paused?",
    ),
    Topic(
        id="okf-export",
        title="OKF export",
        roles=(ANY,),
        pages=(ANY,),
        keywords=("okf", "export", "download", "markdown", "file", "open", "format"),
        answer=(
            "OKF (Open Knowledge Format) is a Markdown file of one approved knowledge version: "
            "its applicability, preconditions, ordered steps, stop-and-escalate conditions, "
            "success checks, limitations, sources and who approved it. Its lifecycle is derived: "
            "active, superseded by a newer version, or retired. Use View OKF export after "
            "approval, or Download OKF in the Library."
        ),
        suggest="What is the OKF export?",
        suggest_on=("/library", "/expert/findings"),
    ),
    Topic(
        id="review-priority",
        title="Review priority formula",
        roles=(ANY,),
        pages=(ANY,),
        keywords=(
            "priority",
            "score",
            "formula",
            "number",
            "weight",
            "signal",
            "calculate",
            "computed",
            "rounding",
            "round",
            "88",
            "points",
            "ranked",
        ),
        answer=(
            f"Review priority = {FORMULA}. Each signal is 0, 0.5 or 1: A operational repetition, "
            "D documentation gap, O selected engineer participation, M manual intervention, "
            "B limited alternate recovery. O and B need at least "
            f"{MIN_ATTRIBUTABLE_EVENTS} attributable events; O is 1 from a 75% share, 0.5 from "
            "50%. B is 1 when nobody else recovered, 0.5 for one recovery by someone else, 0 for "
            "two or more. The result is rounded half up to a whole number, and at most "
            f"{MAX_RANKED} areas are ranked. It is a review-priority heuristic, not a probability "
            "of knowledge loss and not a score of anyone's quality."
        ),
        suggest="How is the review priority calculated?",
        suggest_on=("/expert/handoffs", "/expert"),
    ),
    Topic(
        id="cap",
        title=f"The cap at {CAP}",
        roles=(ANY,),
        pages=(ANY,),
        keywords=("cap", str(CAP), "limit", "webhook", "maximum", "lower", "why", "reason"),
        answer=(
            f"A ranked score is capped at {CAP} when the evidence shows the knowledge is not "
            "concentrated in the selected engineer. The raw score is computed first, then "
            f"min(raw, {CAP}) is rounded half up. Each cap shows its reason under the score: "
            f'"{CAP_REASON_PARTICIPATION}" (participation O below 1) or '
            f'"{CAP_REASON_ALTERNATE_RECOVERY}" (alternate recovery B = 0). In the demo, '
            f"Webhooks has both, so it shows {CAP} instead of its raw score."
        ),
        suggest=f"Why is Webhooks capped at {CAP}?",
        suggest_on=("/expert/handoffs",),
    ),
    Topic(
        id="coverage-states",
        title="Areas without a number",
        roles=(ANY,),
        pages=(ANY,),
        keywords=(
            "adequately",
            "covered",
            "insufficient",
            "evidence",
            "prioritised",
            "prioritized",
            "number",
            "missing",
            "state",
            "unranked",
        ),
        answer=(
            "Some areas get no number on purpose. Adequately covered: the supplied documentation "
            "already covers preconditions, steps, stop-and-escalate and success checks (D = 0). "
            "Not prioritised: the selected engineer performed under half of the attributable "
            "events (O = 0). Insufficient evidence: a signal is unknown, for example too few "
            "attributable events or no documentation imported, or evidence confidence is low. "
            "Review required: the evidence contradicts itself."
        ),
        suggest="What does insufficient evidence mean?",
        suggest_on=("/expert/handoffs",),
    ),
    Topic(
        id="citations",
        title="Citations",
        roles=(ANY,),
        pages=(ANY,),
        keywords=("citation", "cite", "source", "evidence", "inspect", "quote", "proof", "record"),
        answer=(
            "Every finding cites the evidence it is based on: a Jira ticket, Slack thread, "
            "GitHub pull request or runbook, with a quote copied from it. Code checks that each "
            "cited record and quote really exists before the finding is shown; an area whose "
            "citations fail is dropped. Use Inspect citations to open the original evidence."
        ),
        suggest="How do I check where a finding comes from?",
        suggest_on=("/expert/handoffs",),
    ),
    Topic(
        id="results",
        title="Not yet, Partial and Demonstrated",
        roles=(ANY,),
        pages=(ANY,),
        keywords=(
            "demonstrated",
            "partial",
            "partially",
            "result",
            "yet",
            "mean",
            "outcome",
            "met",
            "verdict",
            "label",
        ),
        answer=(
            "Results are computed by code from the verdict on each point of the exercise. "
            "Demonstrated in this exercise: every point met. Partially demonstrated: every "
            "critical condition met, some other point partly met or missed. Not yet "
            "demonstrated: a critical condition was clearly missed. Review required: a judgment "
            "was unclear, or a critical condition was only partly met, and the expert decides. "
            "A result is about one exercise, never about the person."
        ),
        suggest="What do Not yet, Partial and Demonstrated mean?",
        suggest_on=("/learn",),
    ),
    # ---------- admin ----------
    Topic(
        id="admin-next",
        title="What to do next (administrator)",
        roles=("admin",),
        pages=(ANY,),
        keywords=("click", "next", "start", "begin", "do", "step", "now", "workflow"),
        answer=(
            "Go to Handoffs. Use Reset demo for a clean start, then Create handoff with the "
            "expert and the successor (or Choose successor later), and Run analysis. Then the "
            "expert takes over: they review findings, approve knowledge and release an "
            "exercise. If the successor is chosen later, open the handoff for Suitability, "
            "start a common assessment and choose on Results. Audit log shows what everyone did."
        ),
        suggest="What do I click next?",
        suggest_on=("/admin",),
    ),
    Topic(
        id="create-handoff",
        title="Creating a handoff and running the analysis",
        roles=("admin",),
        pages=(ANY,),
        keywords=(
            "handoff",
            "create",
            "run",
            "analysis",
            "analyse",
            "analyze",
            "expert",
            "successor",
            "choose",
            "later",
        ),
        answer=(
            "On Handoffs, pick the expert (an active member who appears in the evidence) and the "
            "successor (any other active member, also a new hire), or Choose successor later. "
            "An admin can be neither. Create handoff, then Run analysis: the evidence is "
            "inspected, citations are checked and the review priority is computed by code."
        ),
        suggest="How do I create a handoff?",
        suggest_on=("/admin/handoffs",),
    ),
    Topic(
        id="reset-demo",
        title="Reset demo",
        roles=("admin",),
        pages=(ANY,),
        keywords=("reset", "demo", "clear", "start", "over", "fresh", "wipe"),
        answer=(
            "Reset demo clears all workflow data (handoffs, analyses, findings, knowledge, "
            "exercises, attempts and the audit log) and imports the fixture evidence again. "
            "Accounts and sign-ins are kept."
        ),
        suggest="What does Reset demo clear?",
        suggest_on=("/admin/handoffs",),
    ),
    Topic(
        id="separation-of-duties",
        title="Separation of duties",
        roles=("admin",),
        pages=(ANY,),
        keywords=(
            "approve",
            "approval",
            "review",
            "button",
            "admin",
            "separation",
            "duties",
            "missing",
            "publish",
            "release",
            "knowledge",
            "exercise",
        ),
        answer=(
            "An administrator sets things up and can read everything, but cannot review, approve "
            "or publish knowledge, author or release exercises, or answer them, and can never be "
            "the expert or the successor of a handoff. That is why there is no Review or Approve "
            "button for you: only the handoff's expert approves, and the backend refuses it from "
            "anyone else."
        ),
        suggest="Why is there no Review button for the admin?",
        suggest_on=("/admin", "/expert/handoffs"),
    ),
    Topic(
        id="fit",
        title="Suitability fit",
        roles=("admin",),
        pages=(ANY,),
        keywords=("fit", "suitability", "percent", "shortlist", "suitable", "experience", "20"),
        answer=(
            "Fit = sum(review priority x experience) / sum(review priority) x 100 over the "
            "ranked areas of the latest analysis, rounded half up. Experience is "
            f"{_num(experience(0))} if the person never recovered an incident in that area, "
            f"{_num(experience(1))} for one cited recovery and {_num(experience(2))} from two. "
            "So fit is priority-weighted: recoveries in high-priority areas count more. It comes "
            "from cited evidence only and is used to shortlist, never to choose."
        ),
        suggest="How is fit calculated?",
        suggest_on=("/admin/handoffs/",),
    ),
    Topic(
        id="no-history",
        title="No history is not 0%",
        roles=("admin",),
        pages=(ANY,),
        keywords=("history", "mean", "zero", "new", "hire", "0", "blank", "empty"),
        answer=(
            "No history means the evidence holds no cited recovery by that person in the ranked "
            "areas, for example a new hire. It is not a fit of 0%: the evidence simply says "
            "nothing about them, so no bar is drawn. Use the common assessment to learn more."
        ),
        suggest="What does No history mean?",
        suggest_on=("/admin/handoffs/",),
    ),
    Topic(
        id="assessment-score",
        title="Assessment score",
        roles=("admin", "candidate", "expert"),
        pages=(ANY,),
        keywords=(
            "score",
            "percent",
            "weight",
            "assessment",
            "double",
            "twice",
            "points",
            "count",
            "86",
            "21",
            "calculate",
        ),
        answer=(
            "Score = sum(weight x credit) / sum(weight) x 100, rounded half up. A critical "
            f"criterion weighs {CRITICAL_WEIGHT}, any other {NORMAL_WEIGHT}. Credit is "
            f"{_num(CREDIT['met'])} for met, {_num(CREDIT['partial'])} for partial and "
            f"{_num(CREDIT['unmet'])} for unmet. Expert review changes are applied first. The "
            "score supports the decision; it never makes it."
        ),
        suggest="How is the assessment score calculated?",
        suggest_on=("/admin/handoffs/",),
    ),
    Topic(
        id="top-tie",
        title="Top, tie and reasons",
        roles=("admin",),
        pages=(ANY,),
        keywords=(
            "top",
            "tie",
            "reason",
            "required",
            "nobody",
            "choose",
            "select",
            "decision",
            "rank",
            "best",
            "winner",
        ),
        answer=(
            "Results ranks by result first (demonstrated, then partial), then by score. Top is "
            "everyone with the highest score in the best group. A Not yet answer is never top, "
            "whatever its score. Tie: two or more share the top and you decide. Nobody in top: "
            "nobody reached demonstrated or partial; you may still choose. Choosing someone in "
            "the top needs no reason; anyone else needs one. The decision is recorded and "
            "cannot be changed."
        ),
        suggest="Why does choosing this person need a reason?",
        suggest_on=("/admin/handoffs/",),
    ),
    Topic(
        id="audit-log",
        title="The audit log",
        roles=("admin",),
        pages=(ANY,),
        keywords=("audit", "log", "who", "did", "event", "action", "history", "trail"),
        answer=(
            "Audit log lists important actions: sign-ins and sign-outs, handoffs, analyses, "
            "reviews, approvals, exercise releases, attempts, review requests and the successor "
            "decision, with who and when. Rows are never edited or deleted (a database trigger "
            "enforces it). Filter by actor, action or date."
        ),
        suggest="What does the audit log record?",
        suggest_on=("/admin/audit", "/admin"),
    ),
    # ---------- expert ----------
    Topic(
        id="expert-next",
        title="What to do next (expert)",
        roles=("expert",),
        pages=(ANY,),
        keywords=("click", "next", "start", "begin", "do", "step", "now", "workflow"),
        answer=(
            "Open My handoffs and then Open Detect. Read the ranked areas and Inspect citations. "
            "On an area, use Review with expert, Confirm it, write what is missing, Save draft "
            "and Approve. Then open the exercise for that version, Generate exercise, check the "
            "private rubric and Approve and release exercise."
        ),
        suggest="What do I click next?",
        suggest_on=("/expert",),
    ),
    Topic(
        id="review-confirm",
        title="Review with expert and Confirm",
        roles=("expert",),
        pages=(ANY,),
        keywords=(
            "review",
            "confirm",
            "correct",
            "reject",
            "obsolete",
            "finding",
            "wrong",
            "candidate",
        ),
        answer=(
            "A finding is a proposal until you review it. Review with expert lets you Confirm it, "
            "correct its summary, reject it or mark it obsolete, with a reason. Only a confirmed "
            "finding can get approved knowledge."
        ),
        suggest="What does Confirm do?",
        suggest_on=("/expert/findings", "/expert/handoffs"),
    ),
    Topic(
        id="approve-knowledge",
        title="Drafts, Approve and immutable versions",
        roles=("expert",),
        pages=(ANY,),
        keywords=(
            "approve",
            "approval",
            "draft",
            "save",
            "publish",
            "version",
            "immutable",
            "knowledge",
            "change",
            "edit",
        ),
        answer=(
            "Write what is missing in your own words, use the suggested structure, and Save "
            "draft; every save is a new revision. Approve publishes exactly that revision as an "
            "immutable knowledge version (v1, v2, ...). A version is never edited: to change "
            "it, save a new draft and approve again, which supersedes the old version. Only "
            "approved versions appear in the Library and can ground an exercise."
        ),
        suggest="How do I approve knowledge?",
        suggest_on=("/expert/findings",),
    ),
    Topic(
        id="generate-release",
        title="Generating and releasing an exercise",
        roles=("expert",),
        pages=(ANY,),
        keywords=(
            "generate",
            "release",
            "exercise",
            "rubric",
            "criteria",
            "scenario",
            "edit",
            "private",
        ),
        answer=(
            "Generate exercise builds a scenario and 3 to 5 criteria from one approved version; "
            "each criterion must point at an approved line. Check and edit them, then Approve "
            "and release exercise. Only then can the successor or the candidates see it. The "
            "rubric stays private to you and the admin."
        ),
        suggest="How do I release an exercise?",
        suggest_on=("/expert/knowledge",),
    ),
    Topic(
        id="expert-review-attempt",
        title="Reviewing an attempt",
        roles=("expert",),
        pages=(ANY,),
        keywords=(
            "review",
            "attempt",
            "override",
            "verdict",
            "change",
            "request",
            "reason",
            "appeal",
        ),
        answer=(
            "When a learner uses Request review, change the criterion verdicts you disagree with "
            "and give a reason. The attempt itself is never changed; its effective result and "
            "score are recomputed by code. While a successor is being selected you see aliases "
            "(Candidate A to D), never names."
        ),
        suggest="How do I review an attempt?",
        suggest_on=("/expert/knowledge",),
    ),
    # ---------- successor and candidate ----------
    Topic(
        id="successor-next",
        title="What to do next (successor)",
        roles=("successor",),
        pages=(ANY,),
        keywords=("click", "next", "start", "begin", "do", "step", "now", "workflow"),
        answer=(
            "Open Learning and the released exercise. Read the scenario, write what you would "
            "check, do, when you would stop and escalate, and how you confirm success, then "
            "Submit answer. You get a result per point, and Try again starts a new attempt."
        ),
        suggest="What do I click next?",
        suggest_on=("/learn",),
    ),
    Topic(
        id="candidate-next",
        title="What to do next (candidate)",
        roles=("candidate",),
        pages=(ANY,),
        keywords=("click", "next", "start", "begin", "do", "step", "now", "workflow"),
        answer=(
            "Open Learning and the common assessment. First use Read the approved knowledge; "
            "Submit answer stays locked until you do. Then answer before the due time. You have "
            f"{ONE_ATTEMPT}, and your result is private."
        ),
        suggest="What do I click next?",
        suggest_on=("/learn",),
    ),
    Topic(
        id="rubric-private",
        title="Why you never see the rubric",
        roles=("successor", "candidate"),
        pages=(ANY,),
        keywords=("rubric", "criteria", "hidden", "see", "private", "marking", "graded", "key"),
        answer=(
            "The rubric is private to the expert and the admin so the exercise tests what you "
            "know, not what you can copy. After you submit, you see a verdict per point with "
            "the quote from your answer that supports it. This assistant never describes the "
            "rubric or the expected answer either."
        ),
        suggest="Why can't I see the rubric?",
        suggest_on=("/learn",),
    ),
    Topic(
        id="attempts",
        title="Try again and the official attempt",
        roles=("successor", "candidate"),
        pages=(ANY,),
        keywords=(
            "try",
            "again",
            "retry",
            "attempt",
            "official",
            "limit",
            "once",
            "another",
            "second",
        ),
        answer=(
            "As a successor, Try again starts a new attempt; earlier attempts are kept unchanged. "
            f"In a common assessment each candidate has {ONE_ATTEMPT}, so Try again is not "
            "offered. An attempt that failed because of a system error does not count; use "
            "Assess again."
        ),
        suggest="Can I try again?",
        suggest_on=("/learn",),
    ),
    Topic(
        id="cannot-submit",
        title="Why Submit answer is not available",
        roles=("successor", "candidate"),
        pages=(ANY,),
        keywords=("submit", "cannot", "blocked", "disabled", "button", "grey", "locked", "work"),
        answer=(
            "Submit answer needs a non-empty answer. As a candidate it also stays locked until "
            "you use Read the approved knowledge, and it is closed after the due time or once "
            "your official attempt is used. If the expert has not released the exercise yet, "
            "there is nothing to submit."
        ),
        suggest="Why can't I submit?",
        suggest_on=("/learn/exercises",),
    ),
    Topic(
        id="study-due",
        title="Study first and the due time",
        roles=("candidate",),
        pages=(ANY,),
        keywords=("study", "read", "due", "deadline", "time", "closed", "late", "required"),
        answer=(
            "In a common assessment you must open the approved knowledge first (Read the "
            "approved knowledge); before that, submitting is refused with study required. "
            "Answers are accepted until the due time shown on the exercise; after it the "
            "assessment is closed."
        ),
        suggest="When is the assessment due?",
        suggest_on=("/learn/exercises",),
    ),
    Topic(
        id="request-review",
        title="Request review",
        roles=("successor", "candidate"),
        pages=(ANY,),
        keywords=(
            "request",
            "review",
            "appeal",
            "disagree",
            "wrong",
            "verdict",
            "unfair",
            "recheck",
        ),
        answer=(
            "If you think a verdict is wrong, use Request review on an assessed attempt, once. "
            "The expert may change verdicts and must give a reason. Your answer is never "
            "changed; your result and score are recomputed from the reviewed verdicts."
        ),
        suggest="What does Request review do?",
        suggest_on=("/learn/exercises",),
    ),
    Topic(
        id="learning-coach",
        title="Learning Coach",
        roles=("successor", "candidate"),
        pages=("/learn",),
        keywords=(
            "coach",
            "coaching",
            "learning",
            "practice",
            "practise",
            "missed",
            "missing",
            "improve",
            "reread",
        ),
        answer=(
            "After an assessed attempt that is not fully demonstrated, use Coach me on this "
            "attempt below its result. For each criterion your answer did not fully meet, the "
            "coach quotes the line of the approved knowledge it was built from, says in a "
            "sentence what your answer missed, and offers a practice question you can check "
            "right away. Only you see your coach. Practice is never counted as an attempt, "
            "never stored and never changes your result or score. A successor can then use "
            "Try again; in a common assessment the official result stands."
        ),
        suggest="What is the learning coach?",
    ),
)

BY_ID = {t.id: t for t in TOPICS}
