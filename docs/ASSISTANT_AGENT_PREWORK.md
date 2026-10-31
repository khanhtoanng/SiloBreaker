# Assistant agent: prework notes

Branch `feature/assistant-local-agent` from `main` (`7fc2a94`, v1.5 with live data merged).
Baseline before any change: backend `pytest -q` 226 passed; frontend `npm test` 55 passed;
`ruff check .` 5 errors, all in `migrations/versions/0001` and `0002` (existing, not touched here).

## The local server

Tested on 2026-10-31 on one Windows 11 machine, with `openai` 3.29.0.

- **Server:** the Llama app, `http://localhost:9931/v1`.
- **Model:** `ggml-org/gemma-4-E4B-it-GGUF:Q4_0` (Gemma 4 E4B, 4.6 GB).
- **`GET /models`:** works, and lists the exact id above.
- **Tool calling:** works. Calls arrive as real `tool_calls`, with `arguments: "{}"` for a tool
  without arguments. No text tool calls were seen, in English or Vietnamese.
- **Live smoke test** (`tests/test_assistant_agent_live.py`): 2 passed, in English and Vietnamese.
- **Ollama:** not tested; no Ollama server was running on this machine. Only the base URL differs.

Nineteen further questions as admin, alice and carol, with a common assessment open. This was a
one-off check, not a committed test:

| Result | Count | Questions |
|---|---|---|
| Local, items cited | 12 | *Có handoff nào không?*, *Are there any handoffs?*, *What is waiting for me?*, *Tôi cần làm gì tiếp?*, a knowledge question as admin, a help question. Each user's rows were correct; Vietnamese questions got Vietnamese replies |
| Local, locked | 2 | carol, English and Vietnamese knowledge questions; no model text shown |
| Local, unknown | 2 | admin *Tôi cần làm gì tiếp?* with nothing pending (reply plus *Nothing is waiting for you.*); admin *Khi nào cần báo AcmePay?* (no line found, "Tôi không biết.") |
| Offline fallback | 3 | admin *What is waiting for me?* with nothing pending (cited an id no tool returned); carol *Who scored highest?* and *What is the capital of France?* (no tool called) |

Each fallback gave a correct or safe offline answer, and none leaked anything.

Quirks found:

1. **A model that is still downloading is already listed.** `GET /models` returned the id with a
   Llama-specific `status.value` of `downloading`, then `loading`. Chat calls then got `400 model name=…
   is not running`. The id check passes, the 400 goes to the fallback, and the WARNING says
   `BadRequestError (400)`. Code does not read `status`, because it is not part of the generic API.
2. **Cold start is slow.** The first request while the model was loading took 25 s, inside the 60 s
   budget. Later questions took 6 to 15 s each on this machine, and the panel shows *Looking it up…*
   meanwhile.
3. **`reasoning_content`.** Messages carry the model's reasoning in this extra field. It is ignored,
   never shown and never sent back, so only `content` can reach the user.
4. **Knowledge search depends on the model's translation.** *Khi nào cần báo AcmePay?* found no line
   here, so it said it did not know, while the English question finds lines. It failed safely; a
   stronger model may translate better.
5. **Empty results invite a bad citation.** With nothing to cite, the model sometimes still writes
   something in brackets, which is rejected. The user gets the offline answer, which is right but in
   English.

## Conflicts between the brief and the code, and what was done

1. **"The response schema must otherwise stay compatible" vs. a reply on top of rendered items.**
   v1.5 has one `answer` string, which the panel splits into a heading and rows paired with
   `citations`. Putting model text into it would break that pairing and mix model words with
   facts. **Done:** `answer` and `citations` stay code-rendered in the v1.5 format, so a client
   that ignores the new fields shows only facts from code. Agent answers add `reply` (the model's
   words, citations removed), `sections` and `tools_used`. Offline and fallback answers have
   exactly the v1.5 keys.

2. **Several kinds of item in one answer.** A model can cite a handoff row and a knowledge line
   together, and a data answer's rows pair up with its citations by position. **Done:** `sections`
   holds one `{mode, answer, citations}` block per tool (data), approved version (knowledge) or
   topic (help), each in its v1.5 shape, and the panel renders each one with the v1.5 code. The
   top-level `answer` is the blocks joined; `mode` follows the brief's order.

3. **A locked reply "that claims procedure without citing lines is rejected", but `mode: "locked"`
   is also a successful outcome.** With the lock on, no items come back, so the "no citation while
   items exist" rule does not catch it, and code cannot tell an honest "this is paused" from an
   invented procedure. **Done:** when `search_knowledge` returned locked and nothing else was
   cited, no model text is shown at all: `reply` is null, `answer` is the v1.5 locked message,
   `provider` is `"local"`. A reply citing lines the tool did not return goes to the fallback,
   which is locked too.

4. **A reply with no tool call.** The brief's rules cover citations, but a model that calls no tool
   and cites nothing passes them while saying anything ("Bob scored 100"). **Done:** rejected, with
   the offline fallback. So a greeting or an off-topic question from a model that skips the tools
   gets the offline answer; this follows "code renders every fact". It is stricter than the brief.

5. **Tools that found nothing.** "You are not part of any handoff yet." is a fact, but no item
   exists to cite. **Done:** the reply is accepted, `mode` is `"unknown"` as the brief says, and the
   tool's own message is rendered under it. A refusal ("not found") is not shown as a sentence;
   the user gets the v1.5 "I don't know" text instead.

6. **`live_data` gives rows, not ids.** Its answers carry a page link per row, and an admin's rows
   all link to `/admin/handoffs`. **Done:** no change to `live_data`. `list_handoffs` and
   `handoff_status` write one row per `visible_handoffs` entry in that order, so the tool pairs
   them (`handoff:<uuid>`, `status:<uuid>`; two prefixes because the two rows differ for the same
   handoff). Pending and due rows are not one per handoff: `pending:<hash>` and `due:<hash>` hash
   the row's link and title, with a counter for identical rows. They are stable while the row
   exists, whatever its counts say.

7. **Fallback with `SB_AI_PROVIDER=openai`.** The v1.5 path sends knowledge answers to that model.
   A question meant for a local model must not go to a remote one because the local one failed.
   **Done:** the fallback calls `offline_answer(..., allow_model=False)`. The default path is
   unchanged.

8. **Vietnamese and lexical tools.** `search_knowledge` and `help_topics` are lexical and English.
   **Done:** their descriptions ask for an English query; the reply stays in the user's language.

9. **Any text in square brackets counts as a citation.** The reply is rejected if one is not a
   returned id. This also rejects Markdown links, by design.

## What this does not guarantee

The model's reply is shown as written once its citations check out. Code verifies that the ids
exist, not that the sentence is true of them: a reply can misstate a status, and the rendered row
under it shows the true one (`test_facts_rendered_by_code`). The label says it is an AI agent.

## Test notes

- The migration in `tests/conftest.py` runs alembic's `fileConfig`, which disables every logger
  that already exists, including `silobreaker.assistant`, for the rest of the test run.
  `test_assistant_agent.py` re-enables it; otherwise its log assertions would pass on nothing.
- `VerifyPanel.test.tsx` failed once when run while the backend suite loaded the machine, and passed
  when re-run alone (8 of 8, twice). It is unrelated to this change.
