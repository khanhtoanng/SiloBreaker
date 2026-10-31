import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api";
import ErrorNotice from "../components/ErrorNotice";
import { useLoad } from "../hooks";
import type { KnowledgeContent, KnowledgeVersion, LibraryEntry } from "../types";

const SECTIONS: { key: Exclude<keyof KnowledgeContent, "applicability">; label: string; ordered?: boolean }[] = [
  { key: "prerequisites", label: "Preconditions" },
  { key: "steps", label: "Steps", ordered: true },
  { key: "stop_and_escalate", label: "Stop and escalate" },
  { key: "success_checks", label: "Success checks" },
  { key: "limitations", label: "Limitations" },
  { key: "unresolved", label: "Unresolved details" },
];

export default function LibraryPage() {
  const { data, error, reload } = useLoad(() => api.library(), []);
  // ?open=<version id> opens one entry; ?back=/learn/... links back to the exercise.
  const [params] = useSearchParams();
  const [open, setOpen] = useState<string | null>(params.get("open"));
  const back = params.get("back");

  return (
    <section className="stack" aria-labelledby="library-title">
      {back?.startsWith("/learn/") && (
        <Link className="small" to={back}>
          ← Back to your exercise
        </Link>
      )}
      <h2 id="library-title">Knowledge library</h2>
      <p className="muted">Approved knowledge only. Retired knowledge is not listed.</p>
      <ErrorNotice error={error} onReload={reload} />
      {data && data.length === 0 && <p className="notice">Nothing has been approved yet.</p>}
      <ul className="card-list">
        {data?.map((e) => (
          <li key={e.version_id} className="panel">
            <div className="row between wrap gap-s">
              <div>
                <span className="truth truth-human">Human-approved knowledge</span>
                <h3>
                  {e.title} <span className="muted small">v{e.version_no}</span>
                </h3>
                <p className="muted small">
                  {e.project_key} · approved by {e.approved_by} on {new Date(e.approved_at).toLocaleDateString()}
                </p>
              </div>
              <button
                className="secondary small"
                aria-expanded={open === e.version_id}
                onClick={() => setOpen(open === e.version_id ? null : e.version_id)}
              >
                {open === e.version_id ? "Hide" : "Read"}
              </button>
            </div>
            {open === e.version_id && <Entry entry={e} />}
          </li>
        ))}
      </ul>
    </section>
  );
}

function Entry({ entry }: { entry: LibraryEntry }) {
  const { data, error, reload } = useLoad(
    async (): Promise<{ version: KnowledgeVersion; okf: string }> => {
      const [version, okf] = await Promise.all([api.knowledge(entry.version_id), api.okf(entry.version_id)]);
      return { version, okf };
    },
    [entry.version_id],
  );
  if (error) return <ErrorNotice error={error} onReload={reload} />;
  if (!data) return <p role="status">Loading…</p>;
  const c = data.version.approved_content;
  const file = `${entry.area_key}-v${entry.version_no}.md`;
  return (
    <div className="knowledge stack">
      <p>
        <strong>Applies to:</strong> {c.applicability}
      </p>
      {SECTIONS.filter((s) => c[s.key].length > 0).map((s) => {
        const List = s.ordered ? "ol" : "ul";
        return (
          <div key={s.key}>
            <h4>{s.label}</h4>
            <List>
              {c[s.key].map((x) => (
                <li key={x}>{x}</li>
              ))}
            </List>
          </div>
        );
      })}
      <a
        className="button secondary small"
        download={file}
        href={URL.createObjectURL(new Blob([data.okf], { type: "text/markdown" }))}
      >
        Download OKF ({file})
      </a>
    </div>
  );
}
