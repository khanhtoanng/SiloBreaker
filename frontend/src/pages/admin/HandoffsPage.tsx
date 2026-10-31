import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../../api";
import ErrorNotice from "../../components/ErrorNotice";
import { useLoad } from "../../hooks";
import type { HandoffStatus } from "../../types";

// FR-04: the four coverage states mean different things for the signals computed from them.
const SOURCE_STATE_HELP: Record<string, string> = {
  included: "imported in full",
  incomplete: "imported, but the export is known to be partial; signals that depend on it are unknown",
  excluded: "deliberately left out of this bundle",
  unavailable: "not supplied; signals that depend on it are unknown",
};

const CHOOSE_LATER = "__later__";

const STATUS_LABEL: Record<HandoffStatus, string> = {
  unassigned: "choose successor later",
  selecting: "common assessment",
  active: "active",
};

export default function HandoffsPage() {
  const navigate = useNavigate();
  const { data, error, reload } = useLoad(async () => {
    const [bundle, handoffs, members] = await Promise.all([
      api.importBundle(),
      api.handoffs(),
      api.users({ role: "member", size: 100 }),
    ]);
    return { bundle, handoffs, members: members.items.filter((m) => m.is_active && m.person_id) };
  }, []);
  const [expert, setExpert] = useState("");
  const [successor, setSuccessor] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<unknown>(null);

  // Experts must appear in the evidence and have an account; successors only need an account.
  const inEvidence = new Set(data?.bundle.people.map((p) => p.id) ?? []);
  const experts = data?.members.filter((m) => inEvidence.has(m.person_id!)) ?? [];
  const successors = data?.members.filter((m) => m.person_id !== expert) ?? [];

  useEffect(() => {
    if (!expert && experts.length) setExpert(experts[0].person_id!);
  }, [experts, expert]);
  useEffect(() => {
    if ((!successor || successor === expert) && successors.length) setSuccessor(successors[0].person_id!);
  }, [successors, successor, expert]);
  const later = successor === CHOOSE_LATER;

  const run = async (label: string, fn: () => Promise<void>) => {
    setBusy(label);
    setActionError(null);
    try {
      await fn();
    } catch (e) {
      setActionError(e);
    } finally {
      setBusy(null);
    }
  };

  const create = (e: FormEvent) => {
    e.preventDefault();
    run("Creating handoff", async () => {
      await api.createHandoff({
        bundle_id: data!.bundle.id,
        expert_id: expert,
        // Unassigned: the successor is chosen later through Suitability and an assessment.
        ...(later ? {} : { successor_id: successor }),
      });
      await reload();
    });
  };

  const analyse = (id: string, expertId: string) =>
    run("Analysing", async () => {
      await api.analyze(id, expertId);
      navigate(`/expert/handoffs/${id}/detect`);
    });

  const reset = () => {
    if (!window.confirm("Reset the demo? All handoffs, findings, knowledge and attempts are deleted. Accounts stay."))
      return;
    run("Resetting demo", async () => {
      await api.reset();
      await reload(); // fresh from the server, never a patch of a list loaded before the reset
    });
  };

  const name = (pid: string) => data?.members.find((m) => m.person_id === pid)?.display_name ?? pid;

  return (
    <section className="stack" aria-labelledby="handoffs-title">
      <div className="row between wrap gap-s">
        <h2 id="handoffs-title">Handoffs</h2>
        <button className="danger" onClick={reset} disabled={!!busy || !data}>
          Reset demo
        </button>
      </div>
      <ErrorNotice error={error ?? actionError} onReload={reload} />
      {busy && (
        <p className="busy" role="status">
          {busy}…
        </p>
      )}

      {data && (
        <section className="panel" aria-labelledby="bundle-title">
          <p className="eyebrow">Evidence bundle</p>
          <h3 id="bundle-title">{data.bundle.project_key}</h3>
          <dl className="inventory">
            {Object.entries(data.bundle.source_inventory).map(([k, v]) => (
              <div key={k} className={`inv inv-${v}`} title={SOURCE_STATE_HELP[v] ?? v}>
                <dt>{k}</dt>
                <dd>
                  {v}
                  <span className="visually-hidden"> — {SOURCE_STATE_HELP[v] ?? v}</span>
                </dd>
              </div>
            ))}
            <div className="inv">
              <dt>records</dt>
              <dd>{data.bundle.item_count}</dd>
            </div>
          </dl>
          {!data.bundle.import_complete && (
            <p className="notice" role="status">
              Some sources are incomplete. Missing documentation is treated as unknown, never as a gap.
            </p>
          )}

          <form className="row gap wrap end" onSubmit={create} aria-label="Create handoff">
            <label className="field">
              <span>Experienced engineer (must appear in the evidence)</span>
              <select value={expert} onChange={(e) => setExpert(e.target.value)}>
                {experts.map((m) => (
                  <option key={m.id} value={m.person_id!}>
                    {m.display_name ?? m.username}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Successor (any active member)</span>
              <select value={successor} onChange={(e) => setSuccessor(e.target.value)}>
                <option value={CHOOSE_LATER}>Choose successor later</option>
                {successors.map((m) => (
                  <option key={m.id} value={m.person_id!}>
                    {m.display_name ?? m.username}
                    {inEvidence.has(m.person_id!) ? "" : " (new to the project)"}
                  </option>
                ))}
              </select>
            </label>
            <button type="submit" disabled={!!busy || !expert || !successor || expert === successor}>
              Create handoff
            </button>
          </form>
        </section>
      )}

      <section className="panel" aria-labelledby="list-title">
        <h3 id="list-title">All handoffs</h3>
        {data && data.handoffs.length === 0 && <p className="muted">No handoffs yet.</p>}
        <ul className="card-list">
          {data?.handoffs.map((h) => (
            <li key={h.id} className="card-row">
              <div>
                <strong>
                  {name(h.expert_id)} → {h.successor_id ? name(h.successor_id) : "successor not chosen"}
                </strong>
                <span className="muted small">
                  {" "}
                  · {STATUS_LABEL[h.status ?? "active"]} · {h.project_key}
                  {h.created_at && ` · ${new Date(h.created_at).toLocaleString()}`}
                </span>
              </div>
              <div className="row gap-s wrap">
                <button className="secondary small" disabled={!!busy} onClick={() => analyse(h.id, h.expert_id)}>
                  Run analysis
                </button>
                <Link className="button ghost small" to={`/expert/handoffs/${h.id}/detect`}>
                  View results
                </Link>
                {(h.status !== "active" || !!h.candidates?.length) && (
                  <Link className="button secondary small" to={`/admin/handoffs/${h.id}`}>
                    {h.status === "active" ? "Selection" : "Choose successor"}
                  </Link>
                )}
              </div>
            </li>
          ))}
        </ul>
      </section>
    </section>
  );
}
