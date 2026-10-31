# Help Assistant: prework notes

Branch `feature/help-assistant` from `main` (`c8d44da`). Baseline before any change: backend
`pytest -q` 174 passed; frontend `npm test` 40 passed.

## How the code works today (read before coding)

| File | What matters for the assistant |
|---|---|
| `app/api/portal_routes.py` `/library` | Every signed-in user reads the newest approved version of every **confirmed** finding; retired (obsolete) knowledge is left out. `/me/exercises` shows a successor (or candidate of a `selecting` handoff) released (`status = 'ready'`) exercises only, with their own attempts. |
| `app/api/routes.py` `/knowledge/{version_id}` | Any signed-in user may read any version by id, including superseded or retired ones. Broader than `/library`. |
| `app/verify/offline.py` | `_tokens` (stopwords, plural fold, synonyms, negation → `NOT`) and `SYNONYMS`. |
| `app/verify/selection.py` | `attempts_used` counts attempts that did not fail; `candidate_view` gives `attempts_used` and `closed` (past `assessment_due_at`); a common assessment has `max_attempts = 1`. |
| `app/auth/deps.py` | `current_user` resolves the session cookie (401 otherwise). The CSRF check is a middleware in `app/main.py`; it runs before authentication, so a write without `X-Requested-With: silobreaker` is 403 even when signed out. |
| `frontend/src/components/Layout.tsx`, `api.ts` | Layout renders only for a signed-in user; `call()` adds the CSRF header on every write. |

## Conflicts between the brief and the code, and what was done

1. **Rubric criteria are approved lines.** The offline generator copies approved sentences
   into criteria verbatim (`PLAN` in `verify/offline.py`), and those same sentences are readable
   by every signed-in user in `/library`. A knowledge answer that quotes approved lines can
   therefore contain text equal to a criterion's text. "No answer contains rubric criterion
   text" cannot hold literally without hiding Library content.
   **Done:** the assistant never reads `exercise.rubric`. `test_rubric_never_leaks` asserts:
   rubric-only text (a criterion the expert edited) never appears; criterion text appears only
   in a knowledge answer, quoted from the approved version, to a user who is not locked; help
   answers never contain it; knowledge answers never contain the word "critical"; a locked
   learner never gets it.

2. **"Read the approved knowledge yourself from the exercise page."** Only candidates have a
   *Read the approved knowledge* button on the exercise page. A plain successor reads it from
   **Library** in the menu. **Done:** the message is kept verbatim as specified.

3. **Phase-1 candidate handoffs** (created with `candidate_ids`, `max_attempts = 2`, no due
   time) have no single "official attempt". **Done:** a candidate is locked while the handoff
   is `selecting`, the exercise (the assessment's, else the latest released one) is released,
   the assessment is not closed and `attempts_used == 0`. A successor is locked while any
   released exercise of a handoff they are the successor of has no counted attempt. A failed
   attempt (system error) does not count, so it does not unlock.

4. **Mode precedence.** The brief says "knowledge if a knowledge line scores above the
   threshold". Short help questions share words with approved content (for example "submit"
   is a synonym of "create"). **Done:** knowledge needs at least two different question words
   and 60% coverage in one approved version, and a help topic that fits strictly better wins.

5. **Readable knowledge.** `/knowledge/{id}` is broader than `/library`. **Done:** the
   assistant uses the `/library` rule only, factored into `knowledge.service.library_versions`
   and shared by both.

6. **OpenAI mode** is used for knowledge answers only. Help answers are curated text and are
   returned as written; sending them to a model adds risk and no information.

7. **Lint commands.** The brief says `ruff check .`; `AGENTS.md` says `ruff check app tests`.
   Both are run.

None of these blocked the work; each is covered by a test.
