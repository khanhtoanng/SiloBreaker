# 07 — AI Detection, Scoring, Capture and Verification

## Responsibility split

### AI proposes

- operational areas/concepts;
- actor/action relationships;
- links between records that may represent the same event;
- documentation-coverage observations;
- evidence-backed explanations;
- one targeted expert question;
- draft exercise + rubric from approved knowledge;
- criterion-level semantic matches for successor answers.

### Application code controls

- validated references and quote membership;
- event de-duplication rules;
- counts/denominators;
- numeric scoring;
- gates/caps;
- confidence rules;
- lifecycle transitions;
- approval/versioning;
- aggregate exercise outcome;
- provider budgets/retries/timeouts.

The model must never directly set authoritative application state.

## Candidate scoring

Initial review-priority heuristic:

```text
raw_score = 25*A + 25*D + 20*O + 15*M + 15*B
```

Each signal is `0`, `0.5` or `1`.

| Signal | 0 | 0.5 | 1 |
|---|---|---|---|
| A — operational repetition | no relevant event | one distinct event | at least two distinct events |
| D — documentation gap | relevant facets covered | partially covered | procedure not found in examined supplied documentation |
| O — selected engineer participation | <50% | 50% to <75% | >=75% |
| M — manual intervention/exception | none | one event | >=2 distinct events |
| B — limited alternate recovery evidence | >=2 successful recovery events by others | one | none found in examined records |

### Important constraints

- O requires enough attributable events to make a proportion meaningful.
- Authorship/name mention alone does not count as operational participation.
- Multiple artifacts about one incident should not inflate A/M/O/B as separate events.
- Missing relevant documentation input is **unknown**, not automatically `D=1`.
- Documentation coverage and operational action are separate signals.

## Gates and abstention

Before displaying a ranked score:

1. require valid supporting references;
2. require a specific incomplete operational facet;
3. `D=0` → adequately covered for this model, not a gap;
4. `O=0` → not prioritized for this selected handoff;
5. unknown required signals → insufficient evidence, no numeric ranking;
6. material contradiction → review required;
7. cap a result that lacks strong selected-engineer concentration or has strong alternate-recovery evidence;
8. explain any cap to the user.

## Score interpretation

The score is a **review-priority heuristic**, not:

- probability of knowledge loss;
- employee risk/quality score;
- prediction that an incident will occur.

## Evidence confidence

Keep confidence independent of risk priority.

Example initial rules:

- **High:** >=4 records, >=3 source types, >=3 distinct events, reliable attribution, no material contradiction.
- **Medium:** >=2 source types and enough attributable events to compute required signals.
- **Low:** sparse, ambiguous, incomplete or contradictory evidence.

Low-confidence areas should not receive a confidently ranked numeric score.

## Capture contract

Approved Knowledge Unit fields:

```text
project/service
topic
applicability
preconditions
ordered actions
stop/escalation conditions
success checks
limitations
unresolved details
source references
expert-added context
approver + timestamp
immutable version
```

Unknown information remains unresolved. The structuring model may reorganize the expert's words but must not invent operational facts.

## Exercise generation

Rules:

- use one approved Knowledge Unit version only;
- generate a realistic decision/sequence/exception scenario;
- 3–5 rubric criteria;
- map each criterion to approved guidance;
- mark critical criteria only when the approved guidance supports it;
- do not invent commands, thresholds or roles;
- require expert review before release;
- keep rubric private until submission.

## Assessment

AI proposes criterion matches; code derives aggregate status.

| Condition | Result |
|---|---|
| all required criteria met; no critical contradiction | demonstrated in this exercise |
| critical criteria met; some non-critical partial | partially demonstrated |
| any critical criterion clearly unmet | not yet demonstrated |
| ambiguous/unsupported/contradictory judgment | review required |

A provider failure is a system failure, not evidence that the successor failed.
