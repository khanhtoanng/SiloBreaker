# Assistant live data: prework notes

Branch `feature/assistant-live-data` from `main` (`b37049b`, v1.4 with the Learning Coach
merged). Baseline before any change: backend `pytest -q` 207 passed; frontend `npm test` 53
passed.

## How the code works today (read before coding)

| File | What matters for data mode |
|---|---|
| `app/api/routes.py` `list_handoffs` | Admin: every handoff. Member: expert or successor of it, or a candidate of it while it is `selecting`. Newest first. Each row is `S.handoff_out(h, role)` plus `viewer_role`. |
| `app/auth/deps.py` `handoff_role` | `admin`, `expert` or `successor` (a candidate of a selecting handoff acts as `successor`); anyone else 403. |
| `app/api/serializers.py` `handoff_out` | Person ids of the expert and successor and the status; candidate rows only for the admin and expert (aliases only for the expert while selecting). |
| `app/api/portal_routes.py` `my_exercises` | Released exercises only for a learner, with their own latest attempt. |
| `app/verify/selection.py` | `candidate_view` (own count, due time, attempts used/left, closed), `attempts_used` (failed attempts never count), `current_exercise`, `latest_analysis`, `selection_of`. |
| `app/assistant/service.py` | `answer` ranks help topics and knowledge, applies `assessment_lock` to knowledge only, and returns `_out(mode, answer, citations, suggestions, provider)`. |
| `app/lexical.py` | Folds plurals before synonyms ("status" -> `statu`, "analysis" -> `analysi`) and drops `how`, `why`, `who`, `any`, `which` as stopwords. |

## Conflicts between the brief and the code, and what was done

1. **"Never reveal that other handoffs exist" vs. two empty messages.** If a member saw *There
   are no handoffs yet.* when none exist and *You are not part of any handoff yet.* otherwise,
   the difference would reveal that other handoffs exist. **Done:** a member who sees none
   always gets *You are not part of any handoff yet.*; only an admin, who sees everything, gets
   *There are no handoffs yet.* Both brief examples hold (Carol; the admin after reset).

2. **Analysis status for learners.** `GET /handoffs/{id}` returns early for a successor or
   candidate, without analyses, so a learner cannot open "whether an analysis exists".
   **Done:** the status line shows analysis and the count of approved versions to the admin and
   expert only. A learner gets the status, the number of approved knowledge units of that
   handoff in the Library (which every signed-in user can read, `library_versions`), whether an
   exercise is released, and, as a candidate, their own state.

3. **Stopwords hide "how", "why" and "who".** "How do I run the analysis?" tokenizes to the
   same words as "Has the analysis run?". **Done:** `intents.py` uses the shared tokenizer for
   matching, plus a check of the raw words: a question with how, why or who is never a data
   intent. A blocker list (score, top, answer, result, create/submit, approve, …) keeps
   results and how-to questions out, and a question must hit an anchor word with at least 75%
   of its words in the intent's vocabulary.

4. **"What is waiting for me?" on every home page.** Suggestions sort role-specific topics on
   the page first, so an any-role topic never reached the top three on `/admin`, `/expert` or
   `/learn`, and a member in no handoff (Carol) has no role at all. **Done:** `Topic.pin_on`
   lists exact pages where a topic's question is suggested first; the new `live-data` topic is
   pinned on `/`, `/admin`, `/expert` and `/learn`. It is not suggested again right after a data
   answer. The existing "When is the assessment due?" suggestion now gets a live `my_due` answer.

5. **People's names.** `handoff_out` gives person ids, not names. **Done:** rows are labelled
   with the display names of that handoff's expert and successor only (people its participants
   already see; the Detect page shows names too). Candidates are never named or aliased.

6. **`my_exercises` repeats the visibility rule inline.** The brief asks to share the rule
   between `list_handoffs` and the assistant. **Done:** `visible_handoffs` in `app/auth/deps.py`
   is used by `list_handoffs`, the assistant's `role_context` and every live-data answer.
   `my_exercises` (a join over exercises) is unchanged to keep this change small; it applies
   the same three conditions.

7. **Lint.** `ruff check .` reports 5 existing errors in `migrations/versions/0001` and `0002`
   (unchanged files, not touched here); `ruff check app tests` and both format checks pass.

None of these blocked the work; each is covered by `backend/tests/test_assistant_live_data.py`.
