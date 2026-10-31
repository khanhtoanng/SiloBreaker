import { Fragment, useState, type FormEvent } from "react";
import type { Readiness, ReadinessCandidate, ReadinessWarning, Verdict } from "../types";
import Modal from "./Modal";
import PctBar from "./PctBar";

// Labels only. Scores, the top, ties and critical misses all come from the backend.
export const RESULTS_NOTE = "Decision support only. Scores reflect one exercise on this knowledge area, not overall ability.";

const VERDICT_LABEL: Record<Verdict, string> = { met: "Met", partial: "Partly met", unmet: "Not met", uncertain: "Unclear" };

const who = (c: ReadinessCandidate) => `${c.display_name ?? c.person_id} (${c.alias})`;

export function badges(c: ReadinessCandidate, tie: boolean): { text: string; kind: string }[] {
  const out: { text: string; kind: string }[] = [];
  if (!c.submitted) out.push({ text: "Not submitted", kind: "muted" });
  if (c.is_top) out.push(tie ? { text: "Tie — admin decides", kind: "tie" } : { text: "Best result", kind: "best" });
  if (c.missing_critical) out.push({ text: "Missing a critical condition", kind: "critical" });
  if (c.submitted && !c.ranked) out.push({ text: "Waiting for expert review", kind: "pending" });
  return out;
}

function warningText(w: ReadinessWarning, name: (pid: string) => string): string {
  const n = w.person_id ? name(w.person_id) : "";
  switch (w.code) {
    case "no_result":
      return `${n} has not submitted an assessed answer.`;
    case "pending":
      return `${n} needs an expert review before the result can be ranked.`;
    case "review_pending":
      return `${n} asked for a review that is still open.`;
    case "no_candidate_meets_all_critical":
      return "No candidate met every critical condition. You can still select someone, with a reason.";
    case "no_released_exercise":
      return "No released exercise yet.";
    default:
      return n ? `${n}: ${w.code}` : w.code;
  }
}

export default function ResultsTable({
  data,
  busy,
  onSelect,
}: {
  data: Readiness;
  busy: boolean;
  onSelect: (personId: string, reason: string) => Promise<void> | void;
}) {
  const [open, setOpen] = useState<string | null>(null);
  const [choosing, setChoosing] = useState<ReadinessCandidate | null>(null);
  const [reason, setReason] = useState("");
  const byId = new Map(data.candidates.map((c) => [c.person_id, c]));
  const name = (pid: string) => {
    const c = byId.get(pid);
    return c ? who(c) : pid;
  };
  const canSelect = data.status === "selecting" && !data.decision;
  const needsReason = choosing !== null && !data.top_ids.includes(choosing.person_id);

  const confirm = async (e: FormEvent) => {
    e.preventDefault();
    if (!choosing || (needsReason && !reason.trim())) return;
    await onSelect(choosing.person_id, reason.trim());
    setChoosing(null);
    setReason("");
  };

  const d = data.decision;
  return (
    <div className="stack">
      <p className="note" role="note">
        {RESULTS_NOTE}
      </p>
      {data.assessment.due_at && (
        <p className="muted small">
          One common exercise · {data.assessment.max_attempts} official attempt
          {data.assessment.max_attempts === 1 ? "" : "s"} · due {new Date(data.assessment.due_at).toLocaleString()}
        </p>
      )}
      {data.warnings.length > 0 && (
        <ul className="warnings" aria-label="Warnings">
          {data.warnings.map((w, i) => (
            <li key={`${w.code}-${w.person_id}-${i}`}>{warningText(w, name)}</li>
          ))}
        </ul>
      )}

      <div className="table-wrap">
        <table className="data stack-table" aria-label="Results">
          <thead>
            <tr>
              <th scope="col">Candidate</th>
              <th scope="col">Score</th>
              <th scope="col">Status</th>
              <th scope="col">Actions</th>
            </tr>
          </thead>
          <tbody>
            {data.candidates.map((c) => (
              <Fragment key={c.person_id}>
                <tr aria-label={who(c)}>
                  <td data-label="Candidate">
                    <strong>{c.display_name ?? c.person_id}</strong> <span className="muted small">{c.alias}</span>
                  </td>
                  <td data-label="Score" className="fit-cell">
                    {c.score_pct === null ? (
                      <span className="muted">—</span>
                    ) : (
                      <PctBar value={c.score_pct} label={`Score for ${c.display_name ?? c.person_id}`} />
                    )}
                  </td>
                  <td data-label="Status">
                    <span className="badges">
                      {badges(c, data.tie).map((b) => (
                        <span key={b.text} className={`badge badge-${b.kind}`}>
                          {b.text}
                        </span>
                      ))}
                      {c.ranked && <span className="muted small">{c.group_label}</span>}
                    </span>
                  </td>
                  <td data-label="Actions">
                    <span className="row gap-s wrap">
                      {c.criteria && (
                        <button
                          className="ghost small"
                          aria-expanded={open === c.person_id}
                          onClick={() => setOpen(open === c.person_id ? null : c.person_id)}
                        >
                          {open === c.person_id ? "Hide details" : "Details"}
                        </button>
                      )}
                      {canSelect && (
                        <button className="small" disabled={busy} onClick={() => setChoosing(c)}>
                          Select as successor
                        </button>
                      )}
                    </span>
                  </td>
                </tr>
                {open === c.person_id && c.criteria && (
                  <tr className="details-row">
                    <td colSpan={4}>
                      <ul className="criteria-results" aria-label={`Criteria for ${c.display_name ?? c.person_id}`}>
                        {c.criteria.map((r) => (
                          <li key={r.criterion_id} className={`verdict verdict-${r.verdict}`}>
                            <span className="verdict-label">{VERDICT_LABEL[r.verdict]}</span> {r.criterion_id} · {r.text}
                            {r.critical && <span className="chip chip-critical">critical</span>}
                            {r.overridden && <span className="chip">changed on review</span>}
                          </li>
                        ))}
                      </ul>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>

      {d && (
        <section className="decision" aria-label="Decision">
          <h4>Decision</h4>
          <p>
            <strong>{name(d.selected_person_id)}</strong> selected by {d.decided_by} on{" "}
            {new Date(d.decided_at).toLocaleString()}.
          </p>
          <ul className="plain-list small">
            <li>In the top result: {d.is_top === null ? "not recorded" : d.is_top ? "yes" : "no"}</li>
            <li>Tie: {d.tie === null ? "not recorded" : d.tie ? "yes" : "no"}</li>
            <li>Reason: {d.reason ?? "none given"}</li>
          </ul>
        </section>
      )}

      {choosing && (
        <Modal title="Select as successor" onClose={() => setChoosing(null)}>
          <form className="stack" onSubmit={confirm}>
            <p>
              Select <strong>{who(choosing)}</strong> as the successor? The decision is final and recorded.
            </p>
            <p className="small muted">
              {data.top_ids.length === 0
                ? "Nobody is in the top result."
                : needsReason
                  ? `Not in the top result (top: ${data.top_ids.map(name).join(", ")}).`
                  : "In the top result."}
            </p>
            <label className="field">
              <span>{needsReason ? "Reason (required: outside the top result)" : "Reason (optional)"}</span>
              <textarea rows={3} required={needsReason} value={reason} onChange={(e) => setReason(e.target.value)} />
            </label>
            <div className="row gap-s wrap">
              <button type="submit" disabled={busy || (needsReason && !reason.trim())}>
                Confirm selection
              </button>
              <button type="button" className="ghost" onClick={() => setChoosing(null)}>
                Cancel
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
