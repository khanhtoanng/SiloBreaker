# 08 — Codex Engineering Harness

## Goal

Use Codex as a coordinated engineering team, not a single chat that accumulates the entire project context.

The harness should make each agent's job small, testable and compatible with parallel work.

## AI-native SDLC used for the hackathon

```text
Human idea/core flow
  ↓
INTENT.md
  ↓  GPT/Codex brainstorm + requirement enrichment
Functional requirements + non-functional requirements + risks + acceptance criteria
  ↓  human review gate
Core design/spec docs
  ↓
Task decomposition + ownership boundaries
  ↓
Parallel Codex agents in isolated worktrees
  ↓
Machine feedback: lint / type-check / unit / integration / Playwright
  ↓
Reviewer/verifier agent
  ↓
Human integration gate
  ↓
Demo rehearsal + fix loop
```

This is inspired by AI-native SDLC patterns that move human attention toward intent, constraints and review while agents expand intent into requirements/design and execute scoped implementation work.

References:

- Claude Academy AI-native SDLC overview: https://academy.claude.com/courses/ai-native-sdlc-playbook
- Capture intent: https://academy.claude.com/courses/ai-native-sdlc-playbook/capture-intent
- Requirements/design: https://academy.claude.com/courses/ai-native-sdlc-playbook/requirements-and-design
- Parallel sessions/subagents: https://academy.claude.com/courses/ai-native-sdlc-playbook/parallel-sessions-and-subagents
- OpenAI Codex multi-agent/worktree positioning: https://openai.com/codex/
- Codex app parallel agents: https://openai.com/index/introducing-the-codex-app/

## Human responsibilities

Humans own the decisions that need judgment:

- product hypothesis and target user;
- core Detect → Capture → Verify flow;
- scope/non-goals;
- risk scoring intent;
- safety and trust boundaries;
- acceptance criteria;
- schema/API changes that affect several agents;
- final integration/demo decision.

GPT/Codex may challenge or enrich these decisions, but does not silently replace them.

## Repository knowledge

```text
INTENT.md
README.md
AGENTS.md
SPEC/
  PRODUCT.md
  REQUIREMENTS.md
  ARCHITECTURE.md
  EVIDENCE.md
  DATA_MODEL.md
  AI.md
  OKF.md
TASKS/
  FE-001.md
  BE-001.md
  AI-001.md
  QA-001.md
```

### `AGENTS.md` should contain

- architecture boundaries;
- commands to run app/tests;
- style/type/lint requirements;
- migration rules;
- forbidden shortcuts (e.g. do not read oracle fixtures from runtime);
- files generated vs hand-maintained;
- mandatory acceptance checks;
- integration etiquette.

## Agent roles

### 1. Frontend agent

Owns:

- React pages/components;
- typed API client usage;
- evidence drawer;
- finding review/capture UX;
- successor exercise UX;
- loading/error/empty states.

Must not:

- invent backend response fields;
- duplicate scoring logic in the browser;
- read oracle fixtures.

### 2. Backend agent

Owns:

- FastAPI routes;
- application services;
- PostgreSQL models/migrations;
- state transitions;
- idempotency/revision handling;
- public response schemas.

### 3. AI/data agent

Owns:

- evidence normalization/chunking;
- structured AI schemas/prompts;
- citation validation;
- event linking/dedup support;
- deterministic scoring implementation;
- exercise/assessment AI contracts;
- OKF renderer.

### 4. Reviewer/verifier agent

Owns verification, not feature implementation by default:

- inspect diff against task contract;
- run targeted tests;
- run critical Playwright flow;
- inspect API contract mismatch;
- check for leakage of oracle/rubric/private fields;
- report failures and scope regressions.

### Optional 5. Integration agent/human driver

Owns:

- resolving cross-agent contract changes;
- merging worktrees/branches;
- running full-stack checks;
- preventing simultaneous edits to shared schema files.

## Parallelization policy

Parallelize only when ownership boundaries are clear.

Good parallel tasks:

- FE builds static view against frozen API types while BE implements endpoint;
- AI agent implements scoring pure function while BE builds lifecycle persistence;
- QA builds Playwright against agreed selectors/flow.

Serialize or coordinate first when tasks modify:

- OpenAPI/Pydantic contract shared by FE and BE;
- database migration touching the same entities;
- canonical evidence schema;
- scoring-version contract;
- shared fixture manifest.

Use isolated worktrees/branches for concurrent agents. The objective is to prevent one agent from seeing a half-written tree from another agent.

## Task contract template

```markdown
# BE-003 — Publish Knowledge Version

## Intent
Publish one immutable Knowledge Unit version from an explicitly approved draft revision.

## Inputs
- finding ID
- expected finding revision
- draft revision
- approver ID

## Allowed files
- backend/app/knowledge/**
- backend/app/db/models/knowledge.py
- backend/tests/knowledge/**

## Must not change
- scoring formula
- evidence schema
- frontend

## Acceptance
- stale draft revision returns 409
- duplicate idempotency key is safe
- approved content cannot be updated in place
- version number increments once
- tests pass

## Stop condition
If the current DB schema cannot support immutable versions without changing a shared migration, stop and report the required contract change.
```

## Feedback loop

Every implementation agent should execute:

```text
implement
→ format/lint
→ type-check
→ targeted unit tests
→ nearest integration test
→ inspect failures
→ fix
→ rerun
→ report exact checks run
```

The verifier then independently checks the behavior.

## Browser verification

Use Playwright for the judged path:

```text
reset
→ create handoff
→ analyze
→ inspect evidence
→ confirm finding
→ capture + approve
→ generate + approve exercise
→ submit unsafe answer
→ see blocked result
→ retry with correct paraphrase
→ export OKF
```

## Context-efficiency tools

RTK or similar tools can reduce noisy output from Git, tests, lint and terminal commands. Treat these as developer aids, not product dependencies.

## Why this Codex story is strong for judging

The hackathon explicitly evaluates effective Codex usage. This harness demonstrates:

- Codex expanding scoped implementation work from human-approved specs;
- multiple agents working concurrently;
- isolation through worktrees;
- reusable project knowledge/skills;
- automated machine feedback;
- agentic review plus human integration gates.

It shows Codex changing the **development operating model**, not merely producing snippets.
