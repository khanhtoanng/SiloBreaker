# 06 — Open Knowledge Format (OKF) Export

## Decision

Use **Open Knowledge Format (OKF) v0.2** as the canonical portable export for approved SiloBreaker Knowledge Units.

OKF represents a knowledge bundle as a directory of Markdown concept files with YAML frontmatter. The format is intentionally vendor-neutral and human/agent-readable. In v0.2, `type` is the only always-required frontmatter field, while provenance, trust and lifecycle metadata can be represented explicitly.

Official specification:

- https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md
- Repository/overview: https://github.com/GoogleCloudPlatform/open-knowledge-format

## Why OKF fits SiloBreaker

SiloBreaker is not only trying to store an answer. It needs to preserve:

- what knowledge was approved;
- where it came from;
- who approved it;
- which version is current;
- what remains unresolved;
- enough structure for both humans and agents to consume it later.

That aligns directly with OKF's goals around portable knowledge, provenance and lifecycle without forcing SiloBreaker to invent a proprietary external format.

## Internal vs portable representation

PostgreSQL remains the transactional source of truth for workflow state. OKF is a projection/export of an immutable approved `knowledge_version`.

```text
PostgreSQL knowledge_version
  → deterministic OKF renderer
  → validate required frontmatter/body rules
  → knowledge bundle directory
  → download / git / future knowledge system
```

Do not write back from an OKF export into approval state during the MVP.

## Proposed bundle layout

```text
silobreaker-okf/
  index.md
  payment-platform/
    index.md
    settlement-recovery-v1.md
```

## Concept example

```markdown
---
type: Operational Playbook
title: Settlement Recovery
description: Expert-approved handoff knowledge for a bounded fictional settlement recovery flow.
tags: [payment-platform, handoff, settlement]
resource: silobreaker://knowledge/KU-001/v1
silobreaker_finding_id: F-001
silobreaker_version: 1
silobreaker_status: approved
approved_by: alice
approved_at: 2026-10-31T05:15:00Z
sources:
  - uri: silobreaker://evidence/INC-03
    title: Settlement incident 03
  - uri: silobreaker://evidence/PR-1842
    title: Prevent duplicate settlement retry
lifecycle:
  status: active
---

# Applicability

Fictional AcmePay provider settlement flow.

# Preconditions

- Existing settlement attempt can be located.

# Procedure

1. Check provider transaction state.
2. Check the idempotency key associated with the existing attempt.

# Stop and escalate

- Do not create a new settlement when the provider confirms the original transaction was accepted or settled.
- Escalate when provider state is unknown or contradictory.

# Success checks

- Verify the final reconciliation outcome.

# Limitations and unresolved details

- None recorded for this approved version.

# Provenance note

The finding was derived from imported evidence; the operational stop/escalation conditions were added and explicitly approved by the experienced engineer during the Capture step.
```

## Conformance strategy

For D-Day:

1. Render one Markdown concept per approved Knowledge Unit version.
2. Always include required `type`.
3. Use standard/recommended frontmatter where the spec defines it.
4. Put SiloBreaker-specific fields under clearly namespaced extension keys.
5. Preserve unknown/extension fields if later implementing import/round-trip.
6. Validate frontmatter syntax and required fields in tests.
7. Label the export `OKF v0.2` only if the implementation is validated against the actual current spec used by the project.

## What not to export

- private exercise rubric;
- hidden evaluator/oracle labels;
- model chain-of-thought;
- secrets/tokens;
- unapproved drafts;
- unsupported claims that were rejected or marked obsolete.

## Future use

An OKF bundle can become the handoff artifact consumed by:

- a Git repository;
- a documentation site;
- an agent context loader;
- a search/indexing system;
- another team's knowledge-management tooling.

This makes the hackathon output useful beyond the demo UI without making SiloBreaker dependent on a proprietary runtime.
