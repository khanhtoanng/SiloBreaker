import { useState, type FormEvent } from "react";
import type { Suitability, SuitabilityMember } from "../types";
import Modal from "./Modal";
import PctBar from "./PctBar";

export const FIT_NOTE = "Fit is based on cited recoveries in the evidence only. It is used to shortlist, not to choose.";
export const NO_HISTORY = "No history — not 0%";

export type StartAssessment = { candidate_ids: string[]; exercise_id: string; due_at: string };

/** Value for a datetime-local input, `days` from now in the viewer's time zone. */
function localInput(days: number): string {
  const d = new Date(Date.now() + days * 86_400_000);
  d.setSeconds(0, 0);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

const memberName = (m: SuitabilityMember) => m.display_name ?? m.person_id;

export default function SuitabilityTable({
  data,
  locked,
  busy,
  onAssign,
  onStart,
}: {
  data: Suitability;
  // True once the successor path is chosen: the table is then read-only.
  locked: boolean;
  busy: boolean;
  onAssign: (personId: string) => Promise<void> | void;
  onStart: (b: StartAssessment) => Promise<void> | void;
}) {
  const [picked, setPicked] = useState<string[]>([]);
  const [dialog, setDialog] = useState(false);
  const [exerciseId, setExerciseId] = useState(data.released_exercises[0]?.id ?? "");
  const [dueLocal, setDueLocal] = useState(localInput(3));

  const toggle = (pid: string) => setPicked((p) => (p.includes(pid) ? p.filter((x) => x !== pid) : [...p, pid]));
  const name = (pid: string) => memberName(data.members.find((m) => m.person_id === pid)!);

  const start = async (e: FormEvent) => {
    e.preventDefault();
    await onStart({ candidate_ids: picked, exercise_id: exerciseId, due_at: new Date(dueLocal).toISOString() });
    setDialog(false);
  };

  return (
    <div className="stack">
      <p className="note" role="note">
        {FIT_NOTE}
      </p>
      <p className="muted small">
        Ranked areas: {data.ranked_areas.map((a) => `${a.title} (priority ${a.review_priority})`).join(", ") || "none"}
      </p>
      <div className="table-wrap">
        <table className="data stack-table" aria-label="Suitability">
          <thead>
            <tr>
              {!locked && <th scope="col">Select</th>}
              <th scope="col">Member</th>
              <th scope="col">Fit</th>
              <th scope="col">Basis</th>
            </tr>
          </thead>
          <tbody>
            {data.members.map((m) => (
              <tr key={m.person_id}>
                {!locked && (
                  <td data-label="Select">
                    <input
                      type="checkbox"
                      className="row-check"
                      aria-label={`Select ${memberName(m)}`}
                      checked={picked.includes(m.person_id)}
                      onChange={() => toggle(m.person_id)}
                    />
                  </td>
                )}
                <td data-label="Member">
                  <strong>{memberName(m)}</strong>
                </td>
                <td data-label="Fit" className="fit-cell">
                  {m.fit_pct === null ? (
                    <span className="no-history">{NO_HISTORY}</span>
                  ) : (
                    <PctBar value={m.fit_pct} label={`Fit for ${memberName(m)}`} />
                  )}
                </td>
                <td data-label="Basis" className="small">
                  {m.basis.length === 0 ? (
                    <span className="muted">No cited recovery in the ranked areas</span>
                  ) : (
                    m.basis.map((b) => (
                      <span key={b.area_key} className="basis-item">
                        {b.title}: {b.incidents.join(", ")}
                      </span>
                    ))
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {!locked && (
        <div className="row gap-s wrap">
          {picked.length === 1 && (
            <button disabled={busy} onClick={() => onAssign(picked[0])}>
              Assign directly
            </button>
          )}
          {picked.length >= 2 && (
            <button disabled={busy || picked.length > 4} onClick={() => setDialog(true)}>
              Start common assessment
            </button>
          )}
          <span className="muted small" role="status">
            {picked.length === 0
              ? "Select one person to assign directly, or 2–4 for a common assessment."
              : picked.length > 4
                ? "A common assessment takes 2–4 candidates."
                : `${picked.length} selected`}
          </span>
        </div>
      )}

      {dialog && (
        <Modal title="Start common assessment" onClose={() => setDialog(false)}>
          <form className="stack" onSubmit={start}>
            <p className="small">Candidates: {picked.map(name).join(", ")}. Each gets one official attempt.</p>
            {data.released_exercises.length === 0 ? (
              <p className="notice">Release an exercise for this handoff first.</p>
            ) : (
              <label className="field">
                <span>Released exercise</span>
                <select value={exerciseId} onChange={(e) => setExerciseId(e.target.value)}>
                  {data.released_exercises.map((x) => (
                    <option key={x.id} value={x.id}>
                      {x.title} · knowledge v{x.knowledge_version_no}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <label className="field">
              <span>Due</span>
              <input type="datetime-local" required value={dueLocal} onChange={(e) => setDueLocal(e.target.value)} />
            </label>
            <div className="row gap-s wrap">
              <button type="submit" disabled={busy || !exerciseId || !dueLocal}>
                Start assessment
              </button>
              <button type="button" className="ghost" onClick={() => setDialog(false)}>
                Cancel
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
