import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../../api";
import ErrorNotice from "../../components/ErrorNotice";
import EvidenceDrawer from "../../components/EvidenceDrawer";
import FindingCard from "../../components/FindingCard";
import { useLoad } from "../../hooks";
import type { Analysis, EvidenceRef } from "../../types";

export default function DetectPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const [evidence, setEvidence] = useState<EvidenceRef[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<unknown>(null);
  const { data, error, reload, setData } = useLoad(async () => {
    const handoff = await api.handoff(id);
    if (handoff.viewer_role === "successor") return { handoff, bundle: null, analysis: null as Analysis | null };
    const [bundle, analysis] = await Promise.all([
      api.bundle(handoff.bundle_id),
      handoff.analyses?.length ? api.getAnalysis(handoff.analyses[0].id) : Promise.resolve(null),
    ]);
    return { handoff, bundle, analysis };
  }, [id]);

  const analysis = data?.analysis ?? null;
  const [candidates, others] = useMemo(() => {
    const fs = analysis?.findings ?? [];
    return [fs.filter((f) => f.top_candidate), fs.filter((f) => !f.top_candidate)];
  }, [analysis]);

  if (error) return <ErrorNotice error={error} onReload={reload} />;
  if (!data)
    return (
      <p className="busy" role="status">
        Loading…
      </p>
    );

  const { handoff, bundle } = data;
  if (handoff.viewer_role === "successor")
    return (
      <section className="panel">
        <h2>Detect is for the experienced engineer</h2>
        <p>As the successor in this handoff you work from released exercises.</p>
        <Link to="/learn">Go to Learning</Link>
      </section>
    );

  const isExpert = handoff.viewer_role === "expert";
  const name = (pid: string) => bundle?.people.find((p) => p.id === pid)?.display_name ?? pid;
  const analyse = async (who: string) => {
    setBusy(true);
    setActionError(null);
    try {
      const a = await api.analyze(handoff.id, who);
      setData((d) => (d ? { ...d, analysis: a } : d));
    } catch (e) {
      setActionError(e);
    } finally {
      setBusy(false);
    }
  };
  // Capture starts from an analysis of the expert's own participation.
  const canCapture = isExpert && analysis?.selected_engineer_id === handoff.expert_id;

  return (
    <section className="detect stack" aria-labelledby="detect-title">
      <header className="panel-head">
        <div>
          <p className="eyebrow">Step 1 · Detect · {handoff.project_key}</p>
          <h2 id="detect-title">Candidate knowledge gaps</h2>
          <p className="muted small">
            {name(handoff.expert_id)} →{" "}
            {handoff.successor_id
              ? name(handoff.successor_id)
              : handoff.status === "selecting"
                ? "successor being selected"
                : "successor not chosen yet"}
          </p>
        </div>
        {bundle && (
          <label className="field inline">
            <span>Analyse for</span>
            <select
              value={analysis?.selected_engineer_id ?? ""}
              onChange={(e) => analyse(e.target.value)}
              disabled={busy}
            >
              {!analysis && <option value="">Choose an engineer</option>}
              {bundle.people.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.display_name}
                </option>
              ))}
            </select>
          </label>
        )}
      </header>
      <ErrorNotice error={actionError} />
      {busy && (
        <p className="busy" role="status">
          Analysing…
        </p>
      )}

      {!analysis && (
        <div className="panel stack">
          <p>No analysis has been run for this handoff yet.</p>
          <button disabled={busy} onClick={() => analyse(handoff.expert_id)}>
            Analyse {name(handoff.expert_id)}
          </button>
        </div>
      )}

      {analysis && (
        <div className="panel">
          <p className="muted small">
            {analysis.model_id} · {analysis.prompt_version} · scoring {analysis.scoring_version}
            {analysis.reused_extraction_from && " · same extraction snapshot, actor-sensitive signals recomputed"}
            {analysis.rejected_areas.length > 0 &&
              ` · ${analysis.rejected_areas.length} proposal(s) dropped for invalid citations`}
          </p>
          <p className="note">
            Review priority is a heuristic for what to ask first. It is not a probability of knowledge loss and not a
            judgement of any engineer.
          </p>
          {!isExpert && <p className="notice">Administrator view: only the experienced engineer can review findings.</p>}
          {candidates.length === 0 && (
            <p className="notice">No area qualifies as a ranked candidate for this engineer.</p>
          )}
          {candidates.map((f) => (
            <FindingCard
              key={f.id}
              finding={f}
              selected={false}
              onSelect={canCapture ? () => navigate(`/expert/findings/${f.id}`) : undefined}
              onEvidence={() => setEvidence(f.evidence_refs)}
            />
          ))}
          <details className="controls">
            <summary>Other areas examined ({others.length})</summary>
            {others.map((f) => (
              <FindingCard key={f.id} finding={f} selected={false} onEvidence={() => setEvidence(f.evidence_refs)} />
            ))}
          </details>
        </div>
      )}
      {evidence && <EvidenceDrawer refs={evidence} onClose={() => setEvidence(null)} />}
    </section>
  );
}
