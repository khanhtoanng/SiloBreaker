# Learning Coach: prework notes

Branch `feature/learning-coach` from `main` (`f8ba2df`). Baseline before any change: backend
`pytest -q` 189 passed; frontend `npm test` 46 passed.

## How the code works today (read before coding)

| File | What matters for the coach |
|---|---|
| `app/verify/contract.py` | `Criterion` has `id`, `text`, `critical`, `source_path` (`field[index]`). `resolve(content, source_path)` returns the approved sentence or `None`. `CRITICAL_FIELDS` lists the fields whose criteria *may* be critical; `critical` itself is per criterion. |
| `app/verify/offline.py` | `OfflineAssessor.assess(scenario, criteria, answer)` is a lexical matcher: coverage ≥ 0.6 is met, ≥ 0.34 partial, else unmet; a negated line described without the prohibition is unmet. It ignores the scenario. |
| `app/api/serializers.py` | `_results` gives learners `criterion_id`, `text`, `verdict`, `evidence_quote` only; `critical` and `source_path` are added for the expert and admin (`FULL_VIEW`). |
| `app/api/verify_routes.py` | `GET /attempts/{id}`: a non-participant gets 403 `not_participant` (from `handoff_role`); another learner of the same handoff gets 403 `not_owner`. |
| `app/verify/selection.py` | `effective_matches` applies review overrides; overrides only count once `reviewed_at` is set (`effective_result`, `effective_score`). `candidate_view` gives `attempts_left` (0 once the official attempt is used or the assessment is closed). `Handoff.candidate()` only returns a row while the handoff is `selecting`. |
| `frontend/.../LearnExercisePage.tsx`, `VerifyPanel.tsx` | The page only renders `VerifyPanel`; `SuccessorView` shows the latest attempt with Request review and Try again (hidden for a candidate with no attempt left). |

## Conflicts between the brief and the code, and what was done

1. **"Other learners get 404, as for attempts today."** Today another learner gets 403
   (`not_owner` or `not_participant`) from `GET /attempts/{id}`, not 404.
   **Done:** the coach follows the stated rule, not the existing one: any signed-in user who
   is not the owner, the admin or the handoff's expert gets 404 `not_found` for both
   `GET /attempts/{id}/coach` and `POST /coach/practice`. Existing attempt routes are unchanged.

2. **`uncertain` verdicts.** The brief lists items for criteria "not fully met" but gives
   templates and chips only for unmet and partial. An `uncertain` judgment is not a fact about
   the answer; it is settled by an expert review.
   **Done:** items are built for `unmet` and `partial` only. An attempt whose only non-met
   verdicts are `uncertain` returns `items: []` with a message pointing to the expert's review;
   only a `demonstrated` attempt gets "Nothing to fix in this attempt."

3. **Empty practice answer.** The body is `answer` 1–1000 chars, so `""` is 422, yet a test
   asks that "an empty answer is unmet". **Done:** `""` is 422 (body rule); a whitespace-only
   answer passes validation and is `unmet`. Both are tested.

4. **Line ids and the Library.** The re-read line is quoted exactly and linked to the Library,
   where every signed-in user can already see it under its section heading. The coach never
   names the section, but the Library does. **Done:** `line_id` is an opaque position (`L1`,
   `L2`, …) over the approved guidance, never a field name; no response contains a field name,
   `critical` or `source_path` (tested for every fixture answer). The section heading in the
   Library is existing, public behaviour and is not changed.

5. **Library link to a superseded version.** `/library` lists only the newest approved version.
   If the exercise's version has been superseded, `?open=<version_id>` will not find it. The
   quoted text in the coach is still the exercise's own version (exact `resolve`). Not changed.

6. **Next step for a phase-1 candidate** (`max_attempts = 2`, no common assessment): it can
   still have an attempt left. **Done:** a candidate with `attempts_left > 0` gets
   `try_again`; with none (official attempt used, or closed) `official_result_stands`. A
   successor gets `try_again` while the exercise is released, else `none`.

7. **Audit "store only the attempt id".** **Done:** `coach.opened` has `target_type =
   'attempt'`, `target_id = <attempt id>`, empty metadata and the actor (person id), and keeps
   `handoff_id` like every other event so the per-handoff audit view lists it. No text. Two
   truly simultaneous first opens could both write it; this was accepted rather than adding
   a lock or a table (no new tables allowed).

8. **OpenAI wording checks.** Besides citing exactly the given line id, a model explanation is
   rejected (offline template, `provider: "offline_fallback"`) when it is empty, longer than two
   sentences, or mentions critical, important, safety, priority, rubric, score, a field name or
   `source_path`. If any item falls back, all items use the offline template, so one response
   never mixes providers.

9. **Lint commands.** The brief says `ruff check .`; `AGENTS.md` says `ruff check app tests`.
   Both are run.

None of these blocked the work; each is covered by a test in `backend/tests/test_coach.py`.
