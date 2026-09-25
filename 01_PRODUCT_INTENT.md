# 01 — Product Intent

## Product statement

SiloBreaker helps engineering teams identify evidence-backed candidate knowledge gaps, capture an expert-approved answer, and verify whether a successor can apply that knowledge in a realistic handoff exercise.

## Problem

Engineering knowledge is distributed across pull requests, issue trackers, runbooks, incident records and team conversations. Existing search/RAG systems are good at answering **“What do we already have?”** but a handoff also requires asking **“What important operating context appears not to be adequately captured?”**

The product therefore focuses on incomplete operational knowledge rather than generic enterprise search.

## Target users

### Primary

Engineering manager or team lead preparing a critical-service handoff.

### Supporting roles

- Experienced engineer: validates system interpretation and captures missing context.
- Successor: applies the approved knowledge in an exercise.

## Core workflow

```text
DETECT
  inspect unlabeled evidence
  → discover operational areas
  → compute transparent signals
  → show up to 3 supported candidate gaps

CAPTURE
  expert confirms/corrects/rejects
  → answers one targeted question
  → structures missing context
  → explicitly approves an immutable Knowledge Unit

VERIFY
  generate scenario from approved Knowledge Unit only
  → expert reviews scenario + rubric
  → successor answers
  → criterion-level assessment
  → retry if needed
```

## Product truth levels

| Level | Meaning | Example |
|---|---|---|
| Source observation | Directly inspectable evidence | An incident shows Alice performing a recovery action |
| System interpretation | Model/code inference | Recovery appears concentrated around Alice and procedural coverage is incomplete |
| Human-approved knowledge | Explicitly reviewed content | Alice approves the missing stop/escalation conditions |

SiloBreaker must keep these visually and structurally separate.

## Product language

Prefer:

- candidate knowledge gap;
- recorded activity is concentrated in this corpus;
- no adequate procedure was found in the supplied documentation;
- expert-approved Knowledge Unit;
- demonstrated in this exercise;
- insufficient evidence / more review needed.

Avoid absolute claims such as “only Alice knows this” or “the AI verified this is safe.”

## MVP scenario

Use one fictional `payment-platform` project with:

- Alice: experienced/transferring engineer;
- Bob: successor;
- evidence from GitHub-like activity, Jira-like issues/incidents, Slack-like engineering discussion and runbook documents;
- one primary candidate: settlement recovery;
- negative controls: well-documented activity, distributed recovery, sparse evidence.

## MVP scope

### Required

- import/reset one synthetic evidence bundle;
- select expert and successor;
- discover multiple operational areas from unlabeled evidence;
- deterministic review-priority score + separate evidence confidence;
- inspect citations;
- expert confirm/correct/reject/obsolete;
- structured capture and explicit approval;
- immutable Knowledge Unit versions;
- export approved knowledge as OKF;
- generate/review one application scenario;
- assess successor answer with critical-step handling;
- browser-level end-to-end demo.

### Stretch

- one real read-only GitHub adapter;
- second corpus;
- incremental source import.

### Out of scope

- autonomous operational remediation;
- employee performance scoring;
- departure prediction;
- production SSO/multi-tenancy;
- permission-complete enterprise connectors;
- knowledge graph/GraphRAG unless evidence shows it is necessary;
- production monitoring claims.

## Success criteria

The demo succeeds when a judge can see that:

1. the model did not receive hidden gap labels;
2. multiple areas are discovered;
3. the primary candidate is supported by inspectable evidence;
4. the expert adds genuinely new context;
5. only approved content becomes portable knowledge;
6. the successor must *apply* that knowledge rather than repeat text;
7. uncertainty and failure modes remain visible.
