# SiloBreaker Core Docs v4

This folder replaces one monolithic `Design.md` with smaller documents that act as explicit source-of-truth contracts for product, engineering, data, AI, and hackathon execution.

## Reading order

1. [`01_PRODUCT_INTENT.md`](01_PRODUCT_INTENT.md) — product problem, users, core flow, boundaries.
2. [`02_REQUIREMENTS.md`](02_REQUIREMENTS.md) — functional/non-functional requirements and acceptance criteria.
3. [`03_ARCHITECTURE.md`](03_ARCHITECTURE.md) — system boundaries, modules, runtime and end-to-end flow.
4. [`04_EVIDENCE_ADAPTERS.md`](04_EVIDENCE_ADAPTERS.md) — normalized evidence contract plus realistic mock GitHub/Slack/Jira payloads and official references.
5. [`05_DATA_MODEL_POSTGRES.md`](05_DATA_MODEL_POSTGRES.md) — PostgreSQL schema, field meanings, constraints and examples.
6. [`06_OKF_KNOWLEDGE_EXPORT.md`](06_OKF_KNOWLEDGE_EXPORT.md) — Knowledge Unit representation using Open Knowledge Format (OKF).
7. [`07_AI_DETECTION_AND_VERIFICATION.md`](07_AI_DETECTION_AND_VERIFICATION.md) — AI responsibilities, deterministic scoring, confidence, capture and verification.
8. [`08_CODEX_ENGINEERING_HARNESS.md`](08_CODEX_ENGINEERING_HARNESS.md) — intent-to-spec workflow, parallel agents, task contracts, testing and review.
9. [`09_BUILD_PLAN_AND_DEMO.md`](09_BUILD_PLAN_AND_DEMO.md) — D-Day build order, cut lines, verification and demo narrative.
10. [`10_DECISIONS_RISKS_ROADMAP.md`](10_DECISIONS_RISKS_ROADMAP.md) — product/architecture decisions, alternatives, risks and post-MVP roadmap.

`REGISTRATION_FORM_v4.md` is the revised hackathon submission copy.

## Core product invariant

> **Detect knowledge risk → Capture missing context → Verify transfer**

The detector may propose a candidate gap, but it must never pretend that an inference is already verified knowledge. Human approval is the boundary between system interpretation and approved knowledge.

## Important MVP principles

- The evidence bundle is **unlabeled input**. Target gaps, expected answers and evaluator labels remain outside model input.
- Every displayed finding must resolve to inspectable evidence.
- Numeric priority is a transparent heuristic, not a probability of knowledge loss or employee quality score.
- Expert approval and successor verification are separate states.
- Source integrations are adapters. The hackathon can run entirely from realistic JSON fixtures.
- PostgreSQL is the target persistence model in these docs.
- OKF is the canonical portable export for approved Knowledge Units; JSON/API representations remain useful internally.
- SiloBreaker itself is not a multi-agent product architecture. Multi-agent orchestration is used for **building the product with Codex**.
