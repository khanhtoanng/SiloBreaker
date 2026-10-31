import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api";
import type { AggregateResult, Attempt, Criterion, Exercise, HandoffRole, Verdict } from "../types";
import ErrorNotice from "./ErrorNotice";
import LearningCoach from "./LearningCoach";

// Labels only. Every verdict and result comes from the backend; nothing is scored here.
const RESULT_LABEL: Record<AggregateResult, string> = {
  demonstrated: "Demonstrated in this exercise",
  partial: "Partially demonstrated",
  not_yet: "Not yet demonstrated",
  review_required: "Review required by the expert",
};
const ROLE_VIEW: Record<HandoffRole, string> = {
  expert: "You are the experienced engineer",
  successor: "You are the successor",
  admin: "Administrator view (read only)",
};
const VERDICT_LABEL: Record<Verdict, string> = {
  met: "Met",
  partial: "Partly met",
  unmet: "Not met",
  uncertain: "Unclear",
};

export type VerifyPanelProps = {
  versionId: string;
  versionNo: number;
  // The view the page expects before any exercise exists. Once one exists, the backend's
  // viewer_role for the signed-in account decides (expert, successor or read-only admin).
  expectedRole: HandoffRole;
  // Show this exercise of the version (e.g. a common assessment) instead of the newest.
  exerciseId?: string;
  // Called after a candidate records opening the study material, to show the knowledge.
  onOpenKnowledge?: () => void;
  // Offer the learning coach under the latest assessed attempt (the learner's exercise page).
  coach?: boolean;
};

export default function VerifyPanel({
  versionId,
  versionNo,
  expectedRole,
  exerciseId,
  onOpenKnowledge,
  coach = false,
}: VerifyPanelProps) {
  const [exercise, setExercise] = useState<Exercise | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const role: HandoffRole = exercise?.viewer_role ?? expectedRole;

  const load = useCallback(async () => {
    const list = await api.listExercises(versionId);
    const chosen = exerciseId ? list.find((e) => e.id === exerciseId) : undefined;
    setExercise(chosen ?? (list.length ? list[list.length - 1] : null));
    setLoaded(true);
  }, [versionId, exerciseId]);

  useEffect(() => {
    setLoaded(false);
    setExercise(null);
    setError(null);
    load().catch(setError);
  }, [load]);

  const run = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(label);
    setError(null);
    try {
      await fn();
      await load();
    } catch (e) {
      setError(e);
      // A provider failure still stored the attempt; reload so it appears as failed.
      if (e instanceof ApiError && e.extra.attempt_id) await load().catch(() => undefined);
    } finally {
      setBusy(null);
    }
  };

  const reload = () => {
    setError(null);
    load().catch(setError);
  };

  return (
    <section className="panel verify" aria-labelledby="verify-title">
      <header className="panel-head">
        <div>
          <p className="eyebrow">Step 3 · Verify</p>
          <h2 id="verify-title">Exercise for knowledge v{versionNo}</h2>
        </div>
        <span className="acting">{ROLE_VIEW[role]}</span>
      </header>

      <ErrorNotice error={error} onReload={reload} />
      {busy && (
        <p className="busy" role="status">
          {busy}…
        </p>
      )}
      {!loaded && !error && <p role="status">Loading exercise…</p>}

      {loaded && role !== "successor" && (
        <ExpertView
          exercise={exercise}
          busy={!!busy}
          readOnly={role === "admin"}
          onGenerate={() => run("Generating exercise", () => api.createExercise(versionId))}
          onSave={(scenario, criteria) =>
            run("Saving exercise", () =>
              api.saveExerciseDraft(exercise!.id, { scenario, criteria, expected_revision: exercise!.revision! }),
            )
          }
          onApprove={() =>
            run("Releasing exercise", () => api.approveExercise(exercise!.id, { expected_revision: exercise!.revision! }))
          }
          onReview={(attemptId, overrides, reason) =>
            run("Saving the review", () => api.reviewAttempt(attemptId, { overrides, reason }))
          }
        />
      )}

      {loaded && role === "successor" && (
        <SuccessorView
          exercise={exercise}
          busy={!!busy}
          coach={coach}
          onSubmit={(answer) => run("Assessing your answer", () => api.submitAttempt(exercise!.id, { answer }))}
          onReassess={(attemptId) => run("Re-assessing", () => api.reassess(attemptId))}
          onRequestReview={(attemptId) => run("Requesting a review", () => api.requestReview(attemptId))}
          onReadKnowledge={() =>
            run("Opening the approved knowledge", async () => {
              await api.studyOpened(exercise!.candidate!.handoff_id);
              onOpenKnowledge?.();
            })
          }
        />
      )}
    </section>
  );
}

function ExpertView({
  exercise,
  busy,
  readOnly,
  onGenerate,
  onSave,
  onApprove,
  onReview,
}: {
  exercise: Exercise | null;
  busy: boolean;
  readOnly: boolean;
  onGenerate: () => void;
  onSave: (scenario: string, criteria: Criterion[]) => void;
  onApprove: () => void;
  onReview: (attemptId: string, overrides: Record<string, Verdict>, reason: string) => void;
}) {
  const [scenario, setScenario] = useState("");
  const [criteria, setCriteria] = useState<Criterion[]>([]);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    setScenario(exercise?.scenario ?? "");
    setCriteria(exercise?.criteria ?? []);
    setDirty(false);
  }, [exercise]);

  if (!exercise)
    return (
      <div className="stack">
        <p className="notice">No exercise exists for this approved version yet.</p>
        {!readOnly && (
          <button disabled={busy} onClick={onGenerate}>
            Generate exercise
          </button>
        )}
      </div>
    );

  const editable = exercise.status === "draft" && !readOnly;
  const waiting = exercise.attempts.filter((a) => a.review && !a.review.reviewed_at);
  const patch = (i: number, p: Partial<Criterion>) => {
    setCriteria((cs) => cs.map((c, j) => (j === i ? { ...c, ...p } : c)));
    setDirty(true);
  };

  return (
    <div className="stack">
      <p className="muted small">
        Status: <strong>{exercise.status === "ready" ? "released" : exercise.status}</strong> · revision{" "}
        {exercise.revision} · generated by {exercise.generator_id}
        {exercise.approved_by && ` · released by ${exercise.approved_by}`}
      </p>
      <label className="field">
        <span>Scenario (visible to the successor)</span>
        <textarea
          rows={4}
          value={scenario}
          readOnly={!editable}
          onChange={(e) => {
            setScenario(e.target.value);
            setDirty(true);
          }}
        />
      </label>
      <fieldset className="list-editor">
        <legend>Private rubric (never shown to the successor before assessment)</legend>
        {criteria.map((c, i) => (
          <div key={c.id} className="criterion">
            <label className="field">
              <span>
                {c.id} · from <code>{c.source_path}</code>
              </span>
              <textarea
                rows={2}
                value={c.text}
                readOnly={!editable}
                onChange={(e) => patch(i, { text: e.target.value })}
              />
            </label>
            <label className="check">
              <input
                type="checkbox"
                checked={c.critical}
                disabled={!editable}
                onChange={(e) => patch(i, { critical: e.target.checked })}
              />
              Critical: missing it blocks “demonstrated”
            </label>
          </div>
        ))}
      </fieldset>
      {editable && (
        <div className="row gap-s wrap">
          <button className="secondary" disabled={busy || !dirty} onClick={() => onSave(scenario, criteria)}>
            Save exercise draft
          </button>
          <button
            disabled={busy || dirty}
            title={dirty ? "Save first; release names an exact revision" : undefined}
            onClick={onApprove}
          >
            Approve and release exercise
          </button>
        </div>
      )}
      {!readOnly && waiting.length > 0 && (
        <section className="attempts" aria-labelledby="review-queue-title">
          <h3 id="review-queue-title">Review requests ({waiting.length})</h3>
          {waiting.map((a) => (
            <ReviewForm key={a.id} attempt={a} busy={busy} onSave={(o, r) => onReview(a.id, o, r)} />
          ))}
        </section>
      )}
      {exercise.attempts.length > 0 && (
        <div className="attempts">
          <h3>Successor attempts</h3>
          {exercise.attempts.map((a, i) => (
            <AttemptCard key={a.id} attempt={a} index={i + 1} showCritical showLearner />
          ))}
        </div>
      )}
    </div>
  );
}

/** The expert's answer to a review request: new verdicts for some criteria and a reason.
 * The backend recomputes the result; the original attempt is never changed. */
function ReviewForm({
  attempt: a,
  busy,
  onSave,
}: {
  attempt: Attempt;
  busy: boolean;
  onSave: (overrides: Record<string, Verdict>, reason: string) => void;
}) {
  const [verdicts, setVerdicts] = useState<Record<string, Verdict>>({});
  const [reason, setReason] = useState("");
  const results = a.results ?? [];
  const overrides = Object.fromEntries(
    Object.entries(verdicts).filter(([cid, v]) => results.find((r) => r.criterion_id === cid)?.verdict !== v),
  );
  const changed = Object.keys(overrides).length > 0;

  return (
    <form
      className="attempt review-form"
      aria-label={`Review of ${a.successor_id}`}
      onSubmit={(e) => {
        e.preventDefault();
        if (changed && reason.trim()) onSave(overrides, reason.trim());
      }}
    >
      <strong>{a.successor_id} asked for a review</strong>
      <details>
        <summary>Answer</summary>
        <p className="answer">{a.answer}</p>
      </details>
      {results.map((r) => (
        <label key={r.criterion_id} className="field">
          <span>
            Verdict for {r.criterion_id}
            {r.critical ? " (critical)" : ""}: {r.text}
          </span>
          <select
            value={verdicts[r.criterion_id] ?? r.verdict}
            onChange={(e) => setVerdicts((v) => ({ ...v, [r.criterion_id]: e.target.value as Verdict }))}
          >
            {r.verdict === "uncertain" && <option value="uncertain">Unclear (assessor)</option>}
            <option value="met">Met</option>
            <option value="partial">Partly met</option>
            <option value="unmet">Not met</option>
          </select>
        </label>
      ))}
      <label className="field">
        <span>Reason for the change (required)</span>
        <textarea rows={2} required value={reason} onChange={(e) => setReason(e.target.value)} />
      </label>
      <button type="submit" disabled={busy || !changed || !reason.trim()}>
        Save review
      </button>
    </form>
  );
}

function SuccessorView({
  exercise,
  busy,
  coach,
  onSubmit,
  onReassess,
  onRequestReview,
  onReadKnowledge,
}: {
  exercise: Exercise | null;
  busy: boolean;
  coach: boolean;
  onSubmit: (answer: string) => void;
  onReassess: (attemptId: string) => void;
  onRequestReview: (attemptId: string) => void;
  onReadKnowledge: () => void;
}) {
  const [answer, setAnswer] = useState("");
  const [answering, setAnswering] = useState(true);
  // While the coach is open it offers Try again itself, so the row below does not repeat it.
  const [coaching, setCoaching] = useState(false);
  const attempts = exercise?.attempts ?? [];
  const last: Attempt | undefined = attempts[attempts.length - 1];
  const candidate = exercise?.candidate ?? null;
  // Every limit comes from the backend: a candidate with no attempt left cannot submit.
  const outOfAttempts = candidate !== null && candidate.attempts_left === 0;

  useEffect(() => {
    // Show the form until there is an attempt; afterwards show its result first.
    setAnswering(attempts.length === 0 && !outOfAttempts);
    setAnswer("");
    setCoaching(false);
  }, [exercise?.id, attempts.length, outOfAttempts]);

  if (!exercise) return <p className="notice">The expert has not released an exercise yet.</p>;

  const mustRead = candidate !== null && !candidate.study_opened;

  return (
    <div className="stack">
      {candidate && (
        <p className="candidate-banner" role="note">
          You are one of {candidate.candidate_count} candidates · same exercise ·{" "}
          {candidate.max_attempts === 1 ? "one official attempt" : `${candidate.max_attempts} official attempts`} ·{" "}
          {candidate.due_at ? `due ${new Date(candidate.due_at).toLocaleString()}` : "no due date"} · results are
          private
        </p>
      )}
      {candidate && (
        <div className="row gap-s wrap">
          <button className={mustRead ? "" : "secondary"} disabled={busy} onClick={onReadKnowledge}>
            Read the approved knowledge
          </button>
          {mustRead && <span className="muted small">Read it before you answer; Submit answer stays locked until then.</span>}
        </div>
      )}
      <blockquote className="question">
        <span className="truth truth-system">Scenario</span>
        {exercise.scenario}
      </blockquote>
      {answering && !outOfAttempts ? (
        <form
          className="stack"
          onSubmit={(e) => {
            e.preventDefault();
            if (answer.trim() && !mustRead) onSubmit(answer);
          }}
        >
          <label className="field">
            <span>Your answer</span>
            <textarea rows={6} value={answer} onChange={(e) => setAnswer(e.target.value)} />
          </label>
          <button type="submit" disabled={busy || !answer.trim() || mustRead}>
            Submit answer
          </button>
        </form>
      ) : (
        last && (
          <>
            <AttemptCard attempt={last} index={attempts.length} showScore={candidate !== null} />
            {coach &&
              last.assessment_status === "succeeded" &&
              ((last.effective_result ?? last.aggregate_result) === "demonstrated" ? (
                <p className="muted small">Nothing to fix in this attempt.</p>
              ) : (
                <LearningCoach
                  key={last.id}
                  attemptId={last.id}
                  onTryAgain={() => setAnswering(true)}
                  onOpen={() => setCoaching(true)}
                />
              ))}
            {last.assessment_status === "failed" ? (
              <button className="secondary" disabled={busy} onClick={() => onReassess(last.id)}>
                Assess again
              </button>
            ) : (
              <div className="row gap-s wrap">
                {last.assessment_status === "succeeded" && !last.review && (
                  <button className="secondary" disabled={busy} onClick={() => onRequestReview(last.id)}>
                    Request review
                  </button>
                )}
                {!outOfAttempts && !coaching && (
                  <button className="secondary" disabled={busy} onClick={() => setAnswering(true)}>
                    Try again
                  </button>
                )}
              </div>
            )}
          </>
        )
      )}
      {outOfAttempts && (
        <p className="notice" role="status">
          {!candidate!.is_assessment_exercise
            ? "This exercise is not the common assessment; answer the one you were assigned."
            : candidate!.closed
              ? "The common assessment is closed."
              : "You have used your official attempt. There is no further submission."}
        </p>
      )}
      {attempts.length > 1 && (
        <details className="controls">
          <summary>Earlier attempts ({attempts.length - 1})</summary>
          {attempts.slice(0, -1).map((a, i) => (
            <AttemptCard key={a.id} attempt={a} index={i + 1} />
          ))}
        </details>
      )}
    </div>
  );
}


function AttemptCard({
  attempt: a,
  index,
  showCritical = false,
  showLearner = false,
  showScore = false,
}: {
  attempt: Attempt;
  index: number;
  showCritical?: boolean;
  // Expert view: who answered (an alias while the successor is being selected).
  showLearner?: boolean;
  // Candidate view: the learner's own score, computed by the backend.
  showScore?: boolean;
}) {
  const reviewed = a.review?.reviewed_at ? a.effective_result : null;
  return (
    <article className="attempt" aria-label={showLearner ? `Attempt ${index} by ${a.successor_id}` : `Attempt ${index}`}>
      <header className="row between wrap">
        <strong>
          Attempt {index}
          {showLearner && ` · ${a.successor_id}`}
        </strong>
        <span className="muted small">
          on knowledge v{a.knowledge_version_no} · {new Date(a.created_at).toLocaleString()}
        </span>
      </header>
      {a.assessment_status === "pending" && <p role="status">Assessment pending…</p>}
      {a.assessment_status === "failed" && (
        <p className="error error-provider" role="alert">
          Assessment failed because of a system error ({a.assessment_error}). Your answer is saved; this is not a result.
        </p>
      )}
      {a.aggregate_result && (
        <p className={`result result-${a.aggregate_result}`} role="status">
          {RESULT_LABEL[a.aggregate_result]}
        </p>
      )}
      {showScore && a.score_pct !== null && a.score_pct !== undefined && (
        <p className="score-line">
          Your score: <strong>{a.score_pct}%</strong>
          {reviewed ? " (after expert review)" : ""}
        </p>
      )}
      {a.review && (
        <p className="small muted">
          {a.review.reviewed_at
            ? `Reviewed by the expert: ${reviewed ? RESULT_LABEL[reviewed] : ""}. Reason: ${a.review.reason}`
            : "Review requested; waiting for the expert."}
        </p>
      )}
      {a.results && (
        <ul className="criteria-results">
          {a.results.map((r) => (
            <li key={r.criterion_id} className={`verdict verdict-${r.verdict}`}>
              <span className="verdict-label">{VERDICT_LABEL[r.verdict]}</span> {r.text}
              {showCritical && r.critical && <span className="chip">critical</span>}
              {r.evidence_quote && <q className="muted small">{r.evidence_quote}</q>}
            </li>
          ))}
        </ul>
      )}
      <details>
        <summary>Answer</summary>
        <p className="answer">{a.answer}</p>
      </details>
    </article>
  );
}
