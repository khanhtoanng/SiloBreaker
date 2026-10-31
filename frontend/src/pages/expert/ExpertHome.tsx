import { Link } from "react-router-dom";
import { api } from "../../api";
import ErrorNotice from "../../components/ErrorNotice";
import { useLoad } from "../../hooks";

export default function ExpertHome() {
  const { data, error, reload } = useLoad(() => api.handoffs(), []);
  const mine = data?.filter((h) => h.viewer_role === "expert") ?? [];
  const learning = data?.filter((h) => h.viewer_role === "successor") ?? [];

  return (
    <section className="stack" aria-labelledby="expert-title">
      <h2 id="expert-title">Handoffs where you are the experienced engineer</h2>
      <ErrorNotice error={error} onReload={reload} />
      {data && mine.length === 0 && (
        <p className="notice">You are not the experienced engineer in any handoff. An administrator creates handoffs.</p>
      )}
      <ul className="card-list">
        {mine.map((h) => (
          <li key={h.id} className="card-row panel">
            <div>
              <strong>{h.project_key}</strong>
              <span className="muted small">
                {" "}
                ·{" "}
                {h.successor_id
                  ? `successor ${h.successor_id}`
                  : h.status === "selecting"
                    ? `selecting among ${h.candidates?.map((c) => c.alias).join(", ") ?? "candidates"}`
                    : "successor not chosen yet"}
              </span>
            </div>
            <Link className="button small" to={`/expert/handoffs/${h.id}/detect`}>
              Open Detect
            </Link>
          </li>
        ))}
      </ul>
      {learning.length > 0 && (
        <p className="muted">
          You are also the successor in {learning.length} handoff{learning.length === 1 ? "" : "s"}.{" "}
          <Link to="/learn">Go to Learning</Link>
        </p>
      )}
    </section>
  );
}
