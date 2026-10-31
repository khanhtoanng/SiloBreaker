import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../../api";
import ErrorNotice from "../../components/ErrorNotice";
import VerifyPanel from "../../components/VerifyPanel";
import { useLoad } from "../../hooks";

export default function LearnExercisePage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const { data, error, reload } = useLoad(() => api.getExercise(id), [id]);
  if (error) return <ErrorNotice error={error} onReload={reload} />;
  if (!data)
    return (
      <p className="busy" role="status">
        Loading…
      </p>
    );
  const back = `/learn/exercises/${id}`;
  return (
    <div className="stack narrow">
      <Link className="small" to="/learn">
        ← Back to your exercises
      </Link>
      <VerifyPanel
        versionId={data.knowledge_version_id}
        versionNo={data.knowledge_version_no}
        expectedRole={data.viewer_role}
        exerciseId={data.id}
        coach
        onOpenKnowledge={() =>
          navigate(`/library?open=${data.knowledge_version_id}&back=${encodeURIComponent(back)}`)
        }
      />
    </div>
  );
}
