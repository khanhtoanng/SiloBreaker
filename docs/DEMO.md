# SiloBreaker — five-minute demo

A scripted walk through the signed-in website: an administrator sets up a handoff, the
experienced engineer captures missing knowledge, the successor proves they can use it, and the
audit log shows who did what. The same path is automated in `e2e/demo_flow.py`. Scene 5 shows
how the administrator chooses a successor among several people; it is automated in
`e2e/selection_flow.py`. Scene 7 shows the Help Assistant; its successor part is in
`e2e/demo_flow.py`.

## Before you start

```bash
docker compose up -d db
cd backend && alembic upgrade head && python -m app.seed_users && uvicorn app.main:app --port 8000
cd frontend && npm run dev
```

Open http://localhost:5173/login. Demo accounts (passwords for this demo only):

| Username | Password | Plays |
|---|---|---|
| `admin` | `Admin@123` | administrator |
| `alice` | `Alice@123` | experienced engineer handing over |
| `bob` | `Bob@123` | successor (scenes 1–4); candidate (scene 5) |
| `carol` | `Carol@123` | candidate (scene 5), appears in the evidence |
| `minh` | `Minh@123` | candidate (scene 5), a new hire with no history in the evidence |

Each step below lists **what to click or type**, **what you should see**, and **why it matters**.

---

## 1. Administrator sets up the handoff (≈ 1 min)

| # | Do | You see |
|---|---|---|
| 1.1 | Sign in as `admin` / `Admin@123`, click **Sign in**. | The **Administration** overview with account and handoff counts. The header shows *Admin · Administrator*. |
| 1.2 | Click **Handoffs** in the menu, then **Reset demo**, and confirm the dialog. | The evidence bundle `payment-platform` with its source inventory, and *No handoffs yet.* |
| 1.3 | In **Experienced engineer (must appear in the evidence)** choose *Alice Tran*; in **Successor (any active member)** choose *Bob Nguyen*. Click **Create handoff**. | The handoff *Alice Tran → Bob Nguyen* appears under **All handoffs**. |
| 1.4 | Click **Run analysis**. | The Detect page for the handoff, with ranked candidates. There is no **Review with expert** button. |
| 1.5 | Click **Log out**. | The sign-in page. |

**Why it matters:** the administrator can set up work and read every result, but cannot review or
approve knowledge. Approval belongs to the person who has the knowledge (separation of duties).
The successor list accepts any active member, so a new hire from outside the project can be the
successor even though they appear nowhere in the evidence.

## 2. Experienced engineer captures the missing knowledge (≈ 2 min)

| # | Do | You see |
|---|---|---|
| 2.1 | Sign in as `alice` / `Alice@123`. | **My handoffs**, listing *payment-platform · successor bob*. |
| 2.2 | Click **Open Detect**. | **Settlement recovery** on top with review priority **88**, a stacked bar *Raw 87.5 → priority 88* and five signal bars. **Webhooks recovery** shows **60** with a red dashed line and *Capped at 60*, plus the two reasons. |
| 2.3 | On Settlement recovery click **Show calculation**, then **Hide calculation**. | A table of value, weight and points per signal, ending in *Raw score 87.5 → review priority 88*. |
| 2.4 | Click **Inspect 8 citations**, then **Close**. | The cited Jira, Slack, GitHub and runbook text, with the exact quote highlighted. |
| 2.5 | Click **Review with expert**, then **Confirm**. | The finding is *confirmed*; a targeted question asks what to check and when to stop and escalate. |
| 2.6 | Paste the **expert answer** (below) into **Expert answer, in your own words** and click **Structure my answer**. | The draft fills in: preconditions, ordered steps, stop and escalate, success checks. |
| 2.7 | Click **Save draft**, then **Approve revision 1**. | *Approved versions: v1 · approved by alice*. |
| 2.8 | Click **View OKF export**. | The Markdown export with `type: Operational Playbook` and `status: active`, and a **Download** link. |
| 2.9 | Click **Open exercise for v1**, then **Generate exercise**. | A scenario plus a **Private rubric** of criteria, each traced to a line of the approved knowledge; some are marked critical. |
| 2.10 | Click **Approve and release exercise**, then **Log out**. | Status *released*. |

**Why it matters:** the score is a review priority computed by deterministic rules from evidence
anyone can open, not a judgement of Alice. The chart shows each signal's contribution, and the
cap shows why Webhooks is lowered: other engineers also recovered it. Nothing becomes knowledge
until the expert approves an exact draft revision, and exercises may only use approved knowledge.

## 3. Successor proves the transfer (≈ 1.5 min)

| # | Do | You see |
|---|---|---|
| 3.1 | Sign in as `bob` / `Bob@123`. | **Your exercises**, with *Settlement recovery · Not started*. |
| 3.2 | Click **Start**. | The scenario and **Your answer**. There is no rubric and nothing marked critical anywhere on the page. |
| 3.3 | Paste the **unsafe answer** (below) and click **Submit answer**. | **Not yet demonstrated**, with per-criterion results; the criterion about not creating a new settlement is *Not met*. (Alice's view marks it critical; Bob's never says which criteria are critical.) |
| 3.4 | Click **Try again**, paste the **correct paraphrase** (below) and click **Submit answer**. | **Demonstrated in this exercise**, every criterion *Met*, and **Earlier attempts (1)** keeps the first answer. |
| 3.5 | Type `/admin` after the address and press Enter. | *You do not have access to this page* (403). |
| 3.6 | Click **Log out**, then press the browser's **Back** button. | You stay on the sign-in page. |

**Why it matters:** the successor never sees the rubric before answering, so a pass means they
understood the procedure. A retry is a new attempt and the old one stays unchanged. A paraphrase
passes because matching is by meaning, not wording. Permissions are enforced on the server: the
admin page is refused, and after logout the session is revoked, so Back cannot reopen it.

## 4. Administrator checks the audit log (≈ 0.5 min)

| # | Do | You see |
|---|---|---|
| 4.1 | Sign in as `admin`, click **Audit log**. | Newest events first: `auth.login`, `handoff.created`, `finding.confirmed`, `knowledge.approved`, `exercise.released`, `attempt.submitted`, `auth.logout`, … by *admin*, *alice* and *bob*. |
| 4.2 | Type `bob` in **Actor** and click **Apply filters**. | Only Bob's sign-in, his two `attempt.submitted` events and his sign-out. |

**Why it matters:** every important state change and every sign-in, including failed ones, is
recorded with the person who did it and cannot be edited afterwards (the database rejects updates
to `audit_event`).

## 5. Choosing a successor among several people (≈ 4 min)

Start from a fresh reset. This scene replaces steps 1.3 and 3.x: nobody is named successor up
front.

| # | Do | You see |
|---|---|---|
| 5.1 | As `admin`: **Handoffs** → **Reset demo**. Choose *Alice* as experienced engineer and **Choose successor later** as successor. Click **Create handoff**, then **Run analysis**. Log out. | *Alice → successor not chosen · choose successor later*. |
| 5.2 | As `alice`: do steps 2.2–2.10 (confirm Settlement, capture, approve v1, generate and release the exercise). In the draft, the steps and conditions can be edited to the approved wording below. Log out. | The exercise is *released*. |
| 5.3 | As `admin`: **Handoffs** → **Choose successor**. | The **Suitability** tab: *Bob 20%*, *Carol 20%* with bars and their basis (*Webhooks recovery: PAY-…*), and *Minh — No history — not 0%*. The note says fit is used to shortlist, not to choose. |
| 5.4 | Tick **Bob**, **Carol** and **Minh**. Click **Start common assessment**, keep the released exercise and the due date, click **Start assessment**. | The **Results** tab: three rows marked *Not submitted*. (With one person ticked, the button is **Assign directly** instead.) Log out. |
| 5.5 | As `bob`: **Learning** → **Start**. | The banner *You are one of 3 candidates · same exercise · one official attempt · due … · results are private*. **Submit answer** is disabled. |
| 5.6 | Click **Read the approved knowledge**, read it, click **Back to your exercise**. Paste the **correct paraphrase** and click **Submit answer**. | *Demonstrated in this exercise*, *Your score: 100%* and **Request review**. There is no **Submit answer** or **Try again** any more. Log out. |
| 5.7 | Repeat 5.5–5.6 as `carol` with the **partial answer** and as `minh` with the **unsafe answer**. | Carol: *Partially demonstrated*, 86%. Minh: *Not yet demonstrated*, 21%. |
| 5.8 | As `alice`: **Open Detect** → **Review with expert** on Settlement recovery → **Open exercise for v1**. | Three attempts labelled *Candidate A/B/C*; no names anywhere. |
| 5.9 | As `admin`: **Handoffs** → **Choose successor** → **Results**. | Bob 100% **Best result**, Carol 86% *Ready with support*, Minh 21% **Missing a critical condition**. **Details** lists each criterion, critical ones marked. The note says the scores are decision support for one exercise, not overall ability. |
| 5.10 | Click **Select as successor** on Carol. | The reason is required (Carol is not in the top), and **Confirm selection** stays disabled until you write one. Click **Cancel**. |
| 5.11 | Click **Select as successor** on Bob, then **Confirm selection**. | *Decision: Bob (Candidate …) selected by admin on …; In the top result: yes; Tie: no; Reason: none given.* |
| 5.12 | **Audit log**, Action `successor.selected`, **Apply filters**. | One event with the selection and the top it was made against. |

**Why it matters:** the two numbers answer different questions. Fit only says who has handled
these incidents before, from cited evidence; a new hire is *No history*, not 0%. The common
assessment gives every candidate the same exercise, the same study material and one official
attempt, and only the administrator sees names next to results. The ranking puts anyone who
missed a critical condition below everyone who did not, a tie is shown as a tie, and choosing
outside the top is allowed but needs a written reason that stays in the record.

## 7. Help Assistant (≈ 1 min)

The **Help** button sits at the bottom right of every signed-in page. Play 7.2 between steps 3.2
and 3.3, and 7.3 after step 3.4. Play 7.4 after step 1.3, 7.5 after step 5.4 (Carol is a
candidate) and 7.6 after step 2.2.

| # | Do | You see |
|---|---|---|
| 7.1 | As `alice` on the Detect page, click **Help** and ask *Why is Webhooks capped at 60?* | A help answer: the cap at 60, the raw score is computed first, and the two reasons exactly as shown under the Webhooks score (*Capped: selected engineer handled only part of the attributable events.* and *Capped: two or more recoveries by other engineers were found.*). Chip *Help: The cap at 60* and three suggested questions. |
| 7.2 | As `bob` on the exercise, before submitting: **Help** → *What should I check before retrying a settlement?* | A grey notice: *Knowledge answers are paused while you have an exercise to complete. Read the approved knowledge yourself from the exercise page.* No citation. *What do I click next?* still gets a help answer. |
| 7.3 | After **Demonstrated in this exercise**, ask the same question again. | The approved lines Alice wrote, quoted as they are under *Steps*, *Stop and escalate* and *Success checks*, with the chip *Knowledge: Settlement recovery v1*. Clicking the chip opens that entry in the **Library**. |
| 7.4 | As `admin`, ask *Are there any handoffs?* | The label *Live data · only what you can see* and the line *Alice → Bob · active*, linked to **Handoffs**. Every handoff is listed, newest first. |
| 7.5 | As `carol`, ask *Are there any handoffs?* | Only the handoff she is a candidate in: *Alice → successor not chosen · choosing a successor*, linked to **Learning**. No other handoff, candidate name, alias or score. Asked before any handoff includes her, the answer is *You are not part of any handoff yet.* |
| 7.6 | As `alice`, ask *What is waiting for me?* (suggested first on her home page). | *Waiting for you:* with *… findings to review*, linked to the Detect page; later also drafts to approve, versions without a released exercise and review requests, each linked to its page. |

**Why it matters:** the assistant only uses the help guide and approved knowledge the user may
read; it never sees drafts, rubrics or anyone's results. While an exercise is open it will not
answer from the knowledge, so it cannot do the exercise for the learner. Knowledge answers quote
approved lines and cite the version; when nothing matches, it says it does not know. Live
data answers are read from the database under the same rules as the pages: each person sees
only what they could already open, and nobody else's answers or scores.

## 8. Learning Coach (≈ 1 min)

Play 8.1–8.3 between steps 3.3 and 3.4 (Bob, successor), and 8.4–8.5 after step 5.7 (Carol,
candidate).

| # | Do | You see |
|---|---|---|
| 8.1 | As `bob`, under *Not yet demonstrated*, click **Coach me on this attempt**. | *Learning Coach — practice does not change your result.* One card per criterion Bob missed, in the order of his results, each with *Not met* or *Partly met*, *Your answer did not cover: …*, and **Re-read in the approved knowledge** quoting Alice's approved line with a link to the Library. Nothing says which criteria are critical. |
| 8.2 | In the first card, type *I would buy a coffee first.* and click **Check**; then **Try another wording**, type the quoted line and **Check** again. | *Not covered yet.*, then *Covered.* with the approved line. There is still no *Earlier attempts*: practice is not an attempt. |
| 8.3 | Click **Try again** at the bottom of the coach and continue with step 3.4. | The answer form. After the correct paraphrase: *Demonstrated in this exercise* and *Nothing to fix in this attempt.* |
| 8.4 | As `carol`, on her *Partially demonstrated* official attempt, click **Coach me on this attempt**. | One card only, *Not met: The ledger shows exactly one settlement for the order*; the criteria she met are only counted (*4 of 5 criteria met*). |
| 8.5 | Type *Done means the ledger has exactly one settlement for it.* and click **Check**. | *Covered.* Below the coach: *Your official result for this assessment stands. Practice is for learning only.* Her score is still 86%, and there is no **Submit answer** or **Try again**. |

**Why it matters:** the coach sends the learner back to the exact approved line instead of
inventing advice, and it shows nothing of the rubric the learner could not already see. Practice
is checked instantly but never stored or counted, so it cannot change a result, a score or a
selection. Only the learner who answered can open it; the admin's audit log shows one
`coach.opened` per attempt, with no text.

## 9. Optional: Help Assistant as an agent on a local model (≈ 2 min)

Needs a local model server; the README section *AI agent (local model)* has the setup. Everything
above stays offline and is unaffected, including every number. Restart the backend with:

```bash
SB_ASSISTANT_PROVIDER=local SB_ASSISTANT_MODEL=<id from GET /v1/models> uvicorn app.main:app --port 8000
```

Play it after step 5.4, with Alice's knowledge approved and the common assessment open: Alice is the
expert, and Carol is a candidate who has not answered yet. A model's wording varies; the rows under
it do not.

| # | Do | You see |
|---|---|---|
| 9.1 | As `admin`, **Help** → *Có handoff nào không?* | A short reply in Vietnamese. Under it *Live data · only what you can see* and the row *Alice → successor not chosen · choosing a successor*, linked to **Handoffs**, then *AI agent (local model) · tools: list_handoffs*. |
| 9.2 | As `admin`, ask *Tôi cần làm gì tiếp?* | A reply in Vietnamese with what is waiting. If nothing is, the line *Nothing is waiting for you.* |
| 9.3 | As `alice`, ask both questions. | Only her handoff, linked to the Detect page; what is waiting for her as the expert, with no candidate's name. |
| 9.4 | As `carol`, ask both questions. | Only the handoff she is a candidate in, linked to **Learning**, and *Answer the exercise “Settlement recovery” …, due …*. No other candidate, alias or score. |
| 9.5 | As `carol`, ask *Tôi nên kiểm tra gì trước khi thử lại settlement?* | The grey paused notice, with no model text: she has an exercise to complete. |
| 9.6 | Quit the model server and ask *Có handoff nào không?* again. | The offline answer with the label *Offline answer*. The offline matcher does not understand this Vietnamese question, so it may not be useful; it never invents one. |

**Why it matters:** the model chooses which read-only tool to call, in the user's language, but it
cannot name a user: code runs each tool as the signed-in person. The rows, links and statuses come
from the database, not from the model's sentence, and the lock is inside the tool, so no wording
opens it. If the model fails, the assistant says so and answers offline; it is never counted against
the learner.

---

## Answers to copy

**Expert answer (step 2.6):**

> Before any retry, check the provider transaction state and the idempotency key on the existing attempt. If the provider says ACCEPTED or SETTLED, never create a new settlement, reconcile the existing one instead. If the provider state is unknown or contradicts ours, pause the retry worker and escalate to the AcmePay contact. Done means the ledger shows exactly one settlement for the order.

**Unsafe successor answer (step 3.3):**

> I would look up the settlement in the admin console and trigger a retry because it has been pending for more than 15 minutes, then confirm the ledger entry.

**Correct paraphrase (step 3.4):**

> First I'd confirm what AcmePay thinks happened to the original attempt using its idempotency key. If they already accepted or settled it I won't submit another one, I'll just reconcile ours. If their answer is unclear I stop the retry worker and raise it with the AcmePay contact. I'm done when there is a single settlement in the ledger for that order.

**Partial answer (step 5.7, Carol):**

> I would check with AcmePay what state the existing settlement attempt is in. If AcmePay already accepted or settled it, I will not submit a new settlement. If the provider state is unclear, I pause the retry worker and escalate to the AcmePay contact.

**Approved wording for step 5.2** (the scores above are for this rubric; `e2e/selection_flow.py`
enters it): preconditions *The existing settlement attempt and its idempotency key can be
located*; steps *Check the provider transaction state for the existing attempt*, *Check the
idempotency key on the existing attempt*, *Reconcile the existing attempt instead of creating a
new one*; stop and escalate *Do not create a new settlement when the provider reports ACCEPTED
or SETTLED*, *Pause the retry worker and escalate to the AcmePay contact when the provider state
is unknown or contradictory*; success check *The ledger shows exactly one settlement for the
order*. With the unedited **Structure my answer** draft the rubric differs, and so do the scores.

## If something goes wrong

- *Invalid username or password.* is shown for a wrong password and for an unknown username
  alike, by design. Re-run `python -m app.seed_users` to restore the demo accounts.
- *Cannot reach the SiloBreaker API* means the backend on :8000 is not running.
- To start over, sign in as `admin` and use **Handoffs → Reset demo**. Accounts are kept.
