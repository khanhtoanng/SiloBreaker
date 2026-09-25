# 02 — Requirements

## Functional requirements

| ID | Requirement | Acceptance criterion |
|---|---|---|
| FR-01 | Create handoff | Project, evidence bundle, expert and successor persist with stable IDs |
| FR-02 | Import evidence | Invalid records return actionable errors; duplicate external IDs are rejected or deterministically de-duplicated |
| FR-03 | Freeze analysis snapshot | Every analysis stores bundle hash, selected engineer, model/prompt/scoring versions |
| FR-04 | Show source coverage | Included, excluded, unavailable and incomplete source families are distinguishable |
| FR-05 | Discover areas | At least several operational areas can emerge without target labels in model input |
| FR-06 | Rank supported candidates | Up to 3 candidates; each has valid supporting evidence and a specific incomplete operational facet |
| FR-07 | Validate citations | Displayed quote/chunk references resolve to stored source text |
| FR-08 | Deterministic score | Signal values, counts, gates, caps and scoring version are inspectable |
| FR-09 | Separate confidence | Evidence confidence is independent from review-priority score |
| FR-10 | Actor-sensitive analysis | Changing selected engineer recomputes ownership/backup signals from the same extraction snapshot |
| FR-11 | Abstain | Sparse/contradictory/missing required evidence cannot become a confident numeric finding |
| FR-12 | Review finding | Expert can confirm, correct, reject or mark obsolete with reason |
| FR-13 | Capture structured knowledge | Applicability, prerequisites, steps, stop/escalation conditions, success checks and unresolved details can be saved |
| FR-14 | Explicit approval | Saving a draft or confirming a finding never publishes knowledge |
| FR-15 | Immutable versioning | Editing approved knowledge creates a new draft/version; history remains readable |
| FR-16 | OKF export | Approved knowledge exports as a valid OKF concept with provenance/lifecycle metadata |
| FR-17 | Generate exercise | Exercise can only reference an approved Knowledge Unit version |
| FR-18 | Review exercise | Expert approves public scenario and private rubric before release |
| FR-19 | Semantic assessment | Equivalent paraphrases can satisfy criteria |
| FR-20 | Critical omission handling | Missing a critical condition blocks “demonstrated” result |
| FR-21 | Preserve attempts | Each answer is immutable; retry creates another attempt |
| FR-22 | Provider failure handling | AI/provider errors remain system errors, never learner failures or fake successful results |
| FR-23 | Persist/recover | Approved versions, exercises and attempts survive refresh/restart |
| FR-24 | Reset demo | A full run can be replayed without manual database editing |

## Non-functional requirements

| Area | MVP target |
|---|---|
| Evidence size | 16–20 short records; bounded payload size |
| Latency | Prefer <30 s per AI stage; hard deadline 60 s |
| Provider usage | Bounded retries and call budget per stage |
| Persistence | PostgreSQL with transactional state transitions |
| Integrity | Foreign keys, unique constraints, revision checks, idempotency keys |
| Privacy | Synthetic evidence for hackathon; API keys server-side; no evidence body in routine logs |
| Safety | Model receives no shell/browser/write tools; evidence treated as untrusted data |
| UX | Explicit loading, empty, insufficient-evidence, rejected, obsolete, stale and provider-error states |
| Accessibility | Labeled controls, keyboard flow, text equivalents for status |
| Observability | operation ID, stage, duration, model/config version, input hash, error code |
| Reproducibility | Save extraction/config versions and hashes needed to explain a run |

## Negative controls

The evaluator corpus must contain controls that make superficial heuristics fail:

- **Strong documentation:** Alice appears frequently but relevant procedure is adequately documented.
- **Distributed recovery:** incidents are frequent but successful recovery is demonstrated by Bob/Carol too.
- **Sparse evidence:** a single weak mention must produce insufficient evidence rather than a confident claim.
- **Duplicate event representation:** ticket + chat + PR about one incident must count as one underlying event where appropriate.
- **Actor change:** changing the selected expert should change actor-sensitive signals without re-labeling the corpus.

## Acceptance rule

A feature is not complete because an agent reports “done.” Completion means its automated checks pass and its observable behavior matches the relevant acceptance criterion.
