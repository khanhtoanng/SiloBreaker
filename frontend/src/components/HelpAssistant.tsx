import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { api, describeError } from "../api";
import type { AssistantAnswer, AssistantCitation } from "../types";

type Message = { id: number; question: string; reply?: AssistantAnswer; error?: string };

// Routes whose :id is a handoff id; other ids (findings, knowledge, exercises) are not sent.
const HANDOFF_ROUTES = [/^\/admin\/handoffs\/([^/]+)\/?$/, /^\/expert\/handoffs\/([^/]+)\//];

export function handoffIdOf(pathname: string): string | undefined {
  for (const r of HANDOFF_ROUTES) {
    const m = pathname.match(r);
    if (m) return m[1];
  }
  return undefined;
}

// Shown before the first answer. Afterwards the backend's suggestions, scoped to the
// signed-in role and this page, replace them.
function starterQuestions(pathname: string): string[] {
  if (pathname.startsWith("/admin")) return ["What do I click next?", "Why is Webhooks capped at 60?", "What does No history mean?"];
  if (pathname.startsWith("/learn")) return ["What do I click next?", "Why can't I submit?", "Can I try again?"];
  if (pathname.startsWith("/expert"))
    return ["What do I click next?", "How is the review priority calculated?", "How do I approve knowledge?"];
  return ["Where do I read approved knowledge?", "What is the OKF export?", "Why did another tab switch my account?"];
}

function CitationChip({ c }: { c: AssistantCitation }) {
  if (c.kind === "knowledge_version")
    return (
      <Link className="chip chip-knowledge" to={c.link ?? `/library?open=${c.id}`}>
        Knowledge: {c.title} v{c.version_no}
      </Link>
    );
  if (c.kind === "page")
    return (
      <Link className="chip chip-page" to={c.link ?? c.id}>
        {c.title}
      </Link>
    );
  return <span className="chip">Help: {c.title}</span>;
}

/** A live-data answer: a heading line, then one row per line, each linking to the page the
 *  signed-in user may open for it. Every row and link comes from the backend. */
function DataAnswer({ reply }: { reply: AssistantAnswer }) {
  const [heading, ...rows] = reply.answer.split("\n");
  const paired = rows.length > 0 && rows.length === reply.citations.length;
  return (
    <>
      <p className="assistant-data-label small">Live data · only what you can see</p>
      <p>{heading}</p>
      {paired ? (
        <ul className="assistant-rows">
          {rows.map((row, i) => (
            <li key={i}>
              <Link to={reply.citations[i].link ?? reply.citations[i].id}>{row}</Link>
            </li>
          ))}
        </ul>
      ) : (
        rows.map((row, i) => <p key={i}>{row}</p>)
      )}
    </>
  );
}

/** Answers only from the help guide and approved knowledge. History lives in this
 *  component's state and is gone on reload; nothing is stored anywhere. */
export default function HelpAssistant() {
  const { pathname } = useLocation();
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [suggestions, setSuggestions] = useState<string[]>(() => starterQuestions(pathname));
  const nextId = useRef(1);
  const listEnd = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);

  // Block bodies: an effect must return nothing or a cleanup function.
  useEffect(() => {
    setSuggestions(starterQuestions(pathname));
  }, [pathname]);
  useEffect(() => {
    listEnd.current?.scrollIntoView?.({ block: "end" });
  }, [messages, busy]);
  useEffect(() => {
    if (open) input.current?.focus();
  }, [open]);

  const send = async (text: string) => {
    const q = text.trim();
    if (!q || busy) return;
    const id = nextId.current++;
    setMessages((m) => [...m, { id, question: q }]);
    setQuestion("");
    setBusy(true);
    try {
      const reply = await api.ask({ question: q, page: pathname, handoff_id: handoffIdOf(pathname) });
      setMessages((m) => m.map((x) => (x.id === id ? { ...x, reply } : x)));
      if (reply.suggestions.length) setSuggestions(reply.suggestions);
    } catch (e) {
      setMessages((m) => m.map((x) => (x.id === id ? { ...x, error: describeError(e).message } : x)));
    } finally {
      setBusy(false);
    }
  };

  const clear = () => {
    setMessages([]);
    setSuggestions(starterQuestions(pathname));
  };

  return (
    <div className="assistant">
      {open && (
        <section
          className="assistant-panel"
          role="dialog"
          aria-labelledby="assistant-title"
          onKeyDown={(e) => {
            if (e.key === "Escape") setOpen(false);
          }}
        >
          <header className="assistant-head">
            <div>
              <h2 id="assistant-title">SiloBreaker Assistant</h2>
              <p className="muted small">Answers come only from the help guide and approved knowledge.</p>
            </div>
            <div className="row gap-s">
              <button className="ghost small" onClick={clear} disabled={busy || messages.length === 0}>
                Clear
              </button>
              <button className="ghost small" aria-label="Close assistant" onClick={() => setOpen(false)}>
                ×
              </button>
            </div>
          </header>
          <div className="assistant-messages" aria-live="polite">
            {messages.length === 0 && <p className="muted small">Ask how to use SiloBreaker or about approved knowledge.</p>}
            {messages.map((m) => (
              <div key={m.id} className="assistant-turn">
                <p className="assistant-question">{m.question}</p>
                {m.error && (
                  <p className="banner small" role="alert">
                    {m.error}
                  </p>
                )}
                {m.reply &&
                  (m.reply.mode === "locked" ? (
                    <p className="assistant-locked" role="status">
                      {m.reply.answer}
                    </p>
                  ) : (
                    <div className={`assistant-answer mode-${m.reply.mode}`}>
                      {m.reply.mode === "data" ? <DataAnswer reply={m.reply} /> : <p>{m.reply.answer}</p>}
                      {m.reply.mode !== "data" && m.reply.citations.length > 0 && (
                        <div className="row wrap gap-s" aria-label="Sources">
                          {m.reply.citations.map((c) => (
                            <CitationChip key={`${c.kind}:${c.id}`} c={c} />
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
              </div>
            ))}
            {busy && (
              <p className="busy" role="status">
                Looking it up…
              </p>
            )}
            <div ref={listEnd} />
          </div>
          {suggestions.length > 0 && (
            <div className="assistant-suggestions" aria-label="Suggested questions">
              {suggestions.map((s) => (
                <button key={s} className="secondary small" disabled={busy} onClick={() => send(s)}>
                  {s}
                </button>
              ))}
            </div>
          )}
          <form
            className="assistant-form"
            onSubmit={(e) => {
              e.preventDefault();
              send(question);
            }}
          >
            <input
              ref={input}
              aria-label="Your question"
              placeholder="Ask a question"
              maxLength={500}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
            />
            <button type="submit" disabled={busy || !question.trim()}>
              Send
            </button>
          </form>
        </section>
      )}
      <button
        className="assistant-toggle"
        aria-expanded={open}
        aria-label={open ? "Close help" : "Open help"}
        onClick={() => setOpen((o) => !o)}
      >
        {open ? "Close" : "Help"}
      </button>
    </div>
  );
}
