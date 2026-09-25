# 09 — Build Plan, Verification and Demo

## D-Day constraints

The public hackathon FAQ states that building must take place on the event day and that projects are judged on problem framing, quality of build, depth of thinking and effective Codex usage.

Reference: https://codexhackathon.sea.com/

Therefore these docs are planning/specification artifacts. Do not bring pre-built submission code if event rules prohibit it.

## Build order

| Step | Deliverable | Completion check |
|---|---|---|
| 1 | Freeze intent/contracts | Team agrees on scope, evidence schema, scoring version, DB model and critical flow |
| 2 | Scaffold React/FastAPI/PostgreSQL | Browser can call API; migration runs |
| 3 | Create fixture corpus + isolated oracle | Runtime payload contains no evaluator labels |
| 4 | Normalize/chunk/display evidence | Stable citations open real stored text |
| 5 | Area discovery + structured extraction | Multiple areas emerge from unlabeled evidence |
| 6 | Scoring/confidence/gates | Negative controls behave correctly |
| 7 | Candidate explanation/question | Top finding is understandable and evidence-backed |
| 8 | Expert review/capture/versioning | Reject/stale actions are safe; approve creates immutable version |
| 9 | OKF export | Approved content produces validated Markdown/frontmatter |
| 10 | Exercise generation/review | Criteria map to approved knowledge |
| 11 | Assessment/retry | Correct paraphrase, partial and critical omission produce different outcomes |
| 12 | Full Playwright flow | Judged path passes repeatedly |
| 13 | Optional live GitHub adapter | Same canonical evidence contract |
| 14 | Freeze/rehearse | Reset/demo repeatable |

## Suggested parallel streams

### Stream A — backend/database

FastAPI, PostgreSQL migrations, lifecycle, idempotency, state transitions.

### Stream B — AI/data

Evidence normalization, structured output, citations, scoring, OKF, exercise/assessment.

### Stream C — frontend

Setup/results/evidence/capture/exercise/export flow.

### Stream D — verification/integration (if fourth member or rotating role)

Fixtures, negative controls, API contract verification, Playwright, demo stability.

## Cut lines

- First complete vertical slice: **Detect** with real citations.
- Next: **Capture** through immutable approval + OKF export.
- Next: **Verify** with one scenario and retry.
- Live source adapters are cut before any core flow element.
- Do not cut citation integrity, explicit approval, oracle isolation or critical-condition handling.

## Verification matrix

| Test | Expected result |
|---|---|
| Label isolation | Model input has no `target_gap`, expected answer, desired rank or expert script |
| Multiple areas | System discovers multiple operational areas |
| Primary finding | Settlement recovery is supported above controls for Alice |
| Strong docs | Adequate procedural coverage prevents promotion as missing-context risk |
| Distributed recovery | Strong alternate recovery evidence prevents misleading concentration claim |
| Sparse evidence | No confident numeric ranking |
| Actor change | Alice/Bob selection changes actor-sensitive signals from same extraction |
| Duplicate event | Multiple records about one incident do not multiply event count |
| Invalid citation | Finding is rejected/invalid rather than displayed as grounded |
| Expert rejection | Rejected finding cannot publish knowledge |
| Stale approval | Old revision returns conflict |
| New knowledge version | Old attempts remain attached to old version |
| Rubric leakage | Successor API/UI never contains private rubric pre-submission |
| Correct paraphrase | Semantically equivalent answer can pass |
| Critical omission | Unsafe/blind retry cannot pass |
| Provider timeout | Honest system error, retry allowed |
| Export | OKF contains exact approved version + provenance, no rubric |
| Full browser flow | Detect → Capture → Verify → export passes |

## Four-minute demo narrative

### 0:00–0:25 — Problem

“Search can find what a team already wrote down. SiloBreaker looks for operational context that appears important but incompletely captured during a handoff.”

### 0:25–1:10 — Detect

- choose Payment Platform / Alice → Bob;
- analyze fixture evidence;
- show settlement recovery candidate;
- open GitHub/Jira/Slack/runbook evidence;
- contrast with one negative control.

### 1:10–2:00 — Capture

- expert confirms/corrects the finding;
- answer targeted question;
- approve structured Knowledge Unit;
- show immutable version and OKF export.

### 2:00–3:05 — Verify

- generate/review scenario;
- successor submits plausible but critically incomplete answer;
- show criterion-level failure;
- retry with correct paraphrase;
- show demonstrated result.

### 3:05–4:00 — Codex build story

Show the harness briefly:

- `INTENT.md`/core specs;
- FE/BE/AI/reviewer tasks running in parallel worktrees;
- automated tests/Playwright feedback;
- verifier output;
- explain that humans own intent and gates while Codex executes/iterates.

This ending directly connects the product quality to the hackathon's Codex criterion.
