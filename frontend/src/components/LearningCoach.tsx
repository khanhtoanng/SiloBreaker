import { useState } from "react";
import { api } from "../api";
import type { Coach, CoachItem, PracticeResult } from "../types";
import ErrorNotice from "./ErrorNotice";

// Labels only. Items, verdicts, explanations and practice feedback all come from the backend;
// nothing is scored here and practice never changes a result.
const VERDICT_LABEL: Record<CoachItem["verdict"], string> = { unmet: "Not met", partial: "Partly met" };
const PRACTICE_LABEL: Record<PracticeResult["verdict"], string> = {
  met: "Covered",
  partial: "Partly covered",
  unmet: "Not covered yet",
};
const OFFICIAL_RESULT_STANDS = "Your official result for this assessment stands. Practice is for learning only.";

export type LearningCoachProps = {
  attemptId: string;
  // The existing Try again action of the exercise page (successors only).
  onTryAgain?: () => void;
};

export default function LearningCoach({ attemptId, onTryAgain }: LearningCoachProps) {
  const [coach, setCoach] = useState<Coach | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const open = async () => {
    setBusy(true);
    setError(null);
    try {
      setCoach(await api.getCoach(attemptId));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  if (!coach)
    return (
      <div className="stack">
        <ErrorNotice error={error} />
        <div>
          <button className="secondary" disabled={busy} onClick={open}>
            {busy ? "Opening the coach…" : "Coach me on this attempt"}
          </button>
        </div>
      </div>
    );

  return (
    <section className="coach" aria-labelledby={`coach-${attemptId}`}>
      <h3 id={`coach-${attemptId}`}>Learning Coach — practice does not change your result.</h3>
      <p className="muted small">
        {coach.met_count} of {coach.total} criteria met. {coach.message}
      </p>
      {coach.items.map((item) => (
        <CoachCard key={item.criterion_id} item={item} />
      ))}
      {coach.next_step === "try_again" && onTryAgain && (
        <div>
          <button onClick={onTryAgain}>Try again</button>
        </div>
      )}
      {coach.next_step === "official_result_stands" && (
        <p className="notice" role="note">
          {OFFICIAL_RESULT_STANDS}
        </p>
      )}
    </section>
  );
}

function CoachCard({ item }: { item: CoachItem }) {
  const [answer, setAnswer] = useState("");
  const [result, setResult] = useState<PracticeResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const check = async () => {
    setBusy(true);
    setError(null);
    try {
      setResult(await api.checkPractice({ practice_id: item.practice.practice_id, answer }));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  const reset = () => {
    setAnswer("");
    setResult(null);
    setError(null);
  };

  return (
    <article className="coach-card" aria-label={`Coach: ${item.criterion_text}`}>
      <p className={`coach-criterion verdict verdict-${item.verdict}`}>
        <span className="chip verdict-label">{VERDICT_LABEL[item.verdict]}</span> {item.criterion_text}
      </p>
      {item.your_quote && (
        <p className="small">
          Your answer said: <q className="muted">{item.your_quote}</q>
        </p>
      )}
      <p>{item.explanation}</p>
      <div className="coach-reread">
        <strong className="small">Re-read in the approved knowledge</strong>
        <blockquote>{item.reread.text}</blockquote>
        <a className="small" href={item.reread.link}>
          Open “{item.reread.title}” v{item.reread.version_no} in the Library
        </a>
      </div>
      <form
        className="stack coach-practice"
        onSubmit={(e) => {
          e.preventDefault();
          if (answer.trim()) check();
        }}
      >
        <label className="field">
          <span>Practice: {item.practice.prompt}</span>
          <textarea
            rows={3}
            maxLength={1000}
            value={answer}
            onChange={(e) => {
              setAnswer(e.target.value);
              setResult(null);
            }}
          />
        </label>
        <div className="row gap-s wrap">
          <button type="submit" className="secondary" disabled={busy || !answer.trim()}>
            Check
          </button>
          {(answer || result) && (
            <button type="button" className="secondary" onClick={reset}>
              Try another wording
            </button>
          )}
        </div>
        <ErrorNotice error={error} />
        {result && (
          <div className={`coach-feedback practice-${result.verdict}`} role="status">
            <p>
              <strong>{PRACTICE_LABEL[result.verdict]}.</strong> {result.feedback}
            </p>
            <p className="small muted">
              The approved line: <q>{result.reread_text}</q>
            </p>
          </div>
        )}
      </form>
    </article>
  );
}
