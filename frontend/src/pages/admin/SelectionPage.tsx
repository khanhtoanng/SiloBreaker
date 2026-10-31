import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ApiError } from "../../api";
import ErrorNotice from "../../components/ErrorNotice";
import ResultsTable from "../../components/ResultsTable";
import SuitabilityTable, { type StartAssessment } from "../../components/SuitabilityTable";
import { useLoad } from "../../hooks";

type Tab = "suitability" | "results";

const STATUS_TEXT = {
  unassigned: "Successor not chosen yet",
  selecting: "Common assessment in progress",
  active: "Successor chosen",
};

export default function SelectionPage() {
  const { id = "" } = useParams();
  const { data, error, reload } = useLoad(async () => {
    const handoff = await api.handoff(id);
    // Suitability needs an analysis; without one the page says so instead of failing.
    const suitability = await api.suitability(id).catch((e) => {
      if (e instanceof ApiError && e.code === "analysis_required") return null;
      throw e;
    });
    const readiness = handoff.candidates?.length ? await api.readiness(id) : null;
    return { handoff, suitability, readiness };
  }, [id]);
  const [tab, setTab] = useState<Tab | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<unknown>(null);

  useEffect(() => {
    if (data && tab === null) setTab(data.readiness ? "results" : "suitability");
  }, [data, tab]);

  const run = async (label: string, fn: () => Promise<unknown>, then?: Tab) => {
    setBusy(label);
    setActionError(null);
    try {
      await fn();
      await reload();
      if (then) setTab(then);
    } catch (e) {
      setActionError(e);
    } finally {
      setBusy(null);
    }
  };

  if (error) return <ErrorNotice error={error} onReload={reload} />;
  if (!data || !tab)
    return (
      <p className="busy" role="status">
        Loading…
      </p>
    );

  const { handoff, suitability, readiness } = data;
  const status = handoff.status ?? "active";
  const tabs: { key: Tab; label: string }[] = [
    { key: "suitability", label: "Suitability" },
    { key: "results", label: "Results" },
  ];

  return (
    <section className="stack" aria-labelledby="selection-title">
      <Link className="small" to="/admin/handoffs">
        ← Back to handoffs
      </Link>
      <div>
        <p className="eyebrow">Successor selection</p>
        <h2 id="selection-title">
          {handoff.project_key} · expert {handoff.expert_id}
        </h2>
        <p className="muted small">
          {STATUS_TEXT[status]}
          {handoff.successor_id && ` · successor ${handoff.successor_id}`}. The administrator makes the final decision.
        </p>
      </div>
      <ErrorNotice error={actionError} onReload={reload} />
      {busy && (
        <p className="busy" role="status">
          {busy}…
        </p>
      )}

      <div className="tabs" role="tablist" aria-label="Selection views">
        {tabs.map((t) => (
          <button
            key={t.key}
            role="tab"
            id={`tab-${t.key}`}
            aria-controls={`panel-${t.key}`}
            aria-selected={tab === t.key}
            className={tab === t.key ? "tab active" : "tab"}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="panel" role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {tab === "suitability" &&
          (suitability ? (
            <SuitabilityTable
              data={suitability}
              locked={status !== "unassigned"}
              busy={!!busy}
              onAssign={(pid) => run("Assigning successor", () => api.assignSuccessor(id, pid))}
              onStart={(b: StartAssessment) =>
                run("Starting common assessment", () => api.startAssessment(id, b), "results")
              }
            />
          ) : (
            <p className="notice">Run an analysis for this handoff first: fit is computed from its ranked areas.</p>
          ))}
        {tab === "results" &&
          (readiness ? (
            <ResultsTable
              data={readiness}
              busy={!!busy}
              onSelect={(pid, reason) =>
                run("Recording the decision", () =>
                  api.selectSuccessor(id, { selected_person_id: pid, ...(reason ? { reason } : {}) }),
                )
              }
            />
          ) : (
            <p className="notice">No common assessment yet. Start one from the Suitability tab.</p>
          ))}
      </div>
    </section>
  );
}
