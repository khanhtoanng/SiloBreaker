# Sea × OpenAI Codex Hackathon — Registration Form Answers v4

## Which build direction does your idea align with?

**AI-Native Products & Operations**

## Problem: What problem are you solving?

Critical engineering knowledge is scattered across code reviews, tickets, runbooks, incidents, and team conversations.

Search tools help teams find what has already been captured. During a handoff, the harder problem is identifying important operational context that appears incomplete, undocumented, or concentrated around one engineer before that context is lost.

Recovery conditions, exceptions, escalation rules, workarounds, and design rationale often remain implicit. Teams may discover these gaps only after an engineer transfers or leaves.

SiloBreaker surfaces evidence-backed knowledge-continuity risks before they become handoff failures.

## Target users: Who is this for?
Engineering managers and team leads responsible for continuity of critical services during employee handoffs or internal transfers.

The workflow also involves:
- The experienced engineer who validates a candidate gap and captures missing context
- The successor engineer who must apply that knowledge in a realistic scenario

We initially focus on software teams where context is distributed across source-control activity, tickets, documentation, incidents, and engineering conversations.

## Solution: What will you build?

SiloBreaker — Detect knowledge risk → Capture missing context → Verify transfer.

It analyzes an unlabeled engineering evidence bundle and proposes candidate areas where signals such as these overlap:

- Repeated operational or incident activity
- Weak or incomplete procedural coverage in the supplied documentation
- Substantive activity concentrated around the selected engineer
- Limited evidence of successful recovery by other engineers.
- Every candidate is evidence-backed. The user can inspect the source records and the reasoning behind the finding.

SiloBreaker then asks the experienced engineer one targeted question. The expert can confirm, correct, reject, or mark the finding obsolete. Only explicitly approved content becomes a Knowledge Unit.

Approved knowledge is exported in an open, portable format and used to generate a realistic handoff exercise. The successor's answer is assessed against an expert-reviewed rubric so the system checks whether the knowledge can be applied, not merely retrieved.

Search helps teams find captured knowledge. SiloBreaker focuses on what may still be missing.

For the hackathon, we will prove one focused end-to-end handoff using a controlled, unlabeled evidence set. The target gap and correct answer are kept outside the inference payload so the system must infer candidate gaps from evidence rather than read labels.

Future direction — not part of the D-Day MVP: permission-aware live connectors, continuous knowledge-risk monitoring, freshness and re-verification, source ACL propagation, and alerts when important operational knowledge becomes stale or overly concentrated.

## Codex: How do you plan to use Codex in building your solution?

We will use Codex as the primary engineering workforce for the D-Day build, with humans defining product intent and Codex agents executing scoped work through a lightweight AI-native SDLC harness.

Human intent → AI-enriched requirements/design → task decomposition → parallel agents → test/review loops → integration → demo verification

Humans remain accountable for judgment-heavy decisions:
- Define the problem, target user, core Detect → Capture → Verify flow, and hackathon scope
- Brainstorm with GPT/Codex to expand that intent into functional requirements, non-functional requirements, acceptance criteria, risks, and design constraints
- Approve the resulting spec before implementation
- Review important architecture, scoring, safety, and integration decisions
- Make the final call on whether the demo is ready.

Engineering harness
The repository will carry the shared context agents need:

- INTENT.md — what we are building, why, non-goals, and demo success conditions
- SPEC.md / core design docs — requirements, contracts, data model, state transitions, scoring, and acceptance criteria
- AGENTS.md — architecture rules, commands, coding constraints, and required checks
scoped task contracts — owned files, inputs, expected outputs, tests, and stop conditions
- Skills — reusable workflows for implementation, fixture generation, API verification, browser testing, and review
machine feedback — lint, type-check, unit/integration tests, and repeatable test/fix loops
- Playwright for critical end-to-end browser verification
- Other open source on github to reduce token usage e.g. RTK

Concurrent multi-agent build
Frontend agent — React views, evidence inspection, capture flow, successor exercise
Backend agent — FastAPI contracts, PostgreSQL persistence, lifecycle/state rules
AI/data agent — evidence normalization, structured model outputs, scoring, OKF export
Reviewer/verifier agent — inspect diffs, run targeted tests and Playwright, check contracts, and report regressions.
Tasks that share the same files or schema are serialized behind an agreed contract; independent tasks run in parallel. Integration happens only after acceptance checks pass.

Build loop
Intent → Spec → Scoped task → Implement → Test → Inspect → Fix → Review → Integrate

This lets us demonstrate not only a product built with Codex, but an AI-native development process in which Codex is coordinated as a small engineering team rather than used as a single autocomplete tool.

