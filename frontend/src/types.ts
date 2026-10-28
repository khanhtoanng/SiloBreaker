// Mirrors backend/app/api/serializers.py. The browser never computes scores itself.

export type Person = { id: string; display_name: string };

export type Bundle = {
  id: string;
  project_key: string;
  content_hash: string;
  source_inventory: Record<string, string>;
  coverage_start: string | null;
  coverage_end: string | null;
  import_complete: boolean;
  item_count: number;
  people: Person[];
};

// unassigned: no successor yet; selecting: a common assessment is running; active: chosen.
export type HandoffStatus = "unassigned" | "selecting" | "active";

export type HandoffCandidate = {
  alias: string;
  // Absent for the expert while the handoff is selecting: aliases only.
  person_id?: string;
  study_opened_at?: string | null;
};

export type Handoff = {
  id: string;
  project_key: string;
  bundle_id: string;
  expert_id: string;
  successor_id: string | null;
  status?: HandoffStatus;
  max_attempts?: number;
  created_at?: string;
  candidates?: HandoffCandidate[];
};

export type HandoffRole = "admin" | "expert" | "successor";

export type HandoffSummary = Handoff & { viewer_role: HandoffRole };

export type HandoffDetail = HandoffSummary & {
  // Absent for the successor, who works from released exercises only.
  analyses?: { id: string; selected_engineer_id: string; created_at: string }[];
};

// ---------- Successor selection (every number is computed by the backend) ----------

export type SuitabilityBasis = {
  area_key: string;
  title: string;
  review_priority: number;
  incidents: string[];
  experience: number;
};

export type SuitabilityMember = {
  person_id: string;
  display_name: string | null;
  // null means no cited recovery in the ranked areas: "No history", which is not 0%.
  fit_pct: number | null;
  fit_status: "scored" | "no_history";
  basis: SuitabilityBasis[];
};

export type ReleasedExercise = {
  id: string;
  title: string;
  area_key: string;
  knowledge_version_no: number;
  approved_at: string | null;
};

export type Suitability = {
  handoff_id: string;
  status: HandoffStatus;
  analysis_id: string;
  ranked_areas: { area_key: string; title: string; review_priority: number }[];
  total_priority: number;
  members: SuitabilityMember[];
  released_exercises: ReleasedExercise[];
  note: string;
};

export type ReadinessCriterion = {
  criterion_id: string;
  text: string;
  critical: boolean;
  weight: number;
  verdict: Verdict;
  overridden: boolean;
};

export type ReadinessCandidate = {
  person_id: string;
  display_name: string | null;
  alias: string;
  group: "ready" | "ready_with_support" | "not_yet" | "pending";
  group_label: string;
  best_attempt_id: string | null;
  best_result: AggregateResult | null;
  score_pct: number | null;
  ranked: boolean;
  submitted: boolean;
  missing_critical: boolean;
  is_top: boolean;
  criteria: ReadinessCriterion[] | null;
  attempts_used: number;
  max_attempts: number;
  study_opened: boolean;
  review_pending: boolean;
};

export type ReadinessWarning = { person_id: string | null; code: string };

export type SelectionDecision = {
  id: string;
  selected_person_id: string;
  recommended: string[];
  in_recommended: boolean;
  // null on decisions recorded before the score-based top existed.
  top_ids: string[] | null;
  tie: boolean | null;
  is_top: boolean | null;
  reason: string | null;
  decided_by: string;
  decided_at: string;
};

export type Readiness = {
  handoff_id: string;
  status: HandoffStatus;
  exercise_id: string | null;
  assessment: { exercise_id: string | null; due_at: string | null; started_at: string | null; max_attempts: number };
  weights: { critical: number; normal: number };
  // Ordered by the backend: ranked first (result, then score), then the unranked.
  candidates: ReadinessCandidate[];
  recommended: string[];
  top_ids: string[];
  tie: boolean;
  warnings: ReadinessWarning[];
  decision: SelectionDecision | null;
};

// The signed-in candidate's own place in a selection; never anything about other people.
export type CandidateInfo = {
  handoff_id: string;
  alias: string;
  candidate_count: number;
  due_at: string | null;
  max_attempts: number;
  attempts_used: number;
  attempts_left: number;
  study_opened: boolean;
  is_assessment_exercise: boolean;
  closed: boolean;
};

export type AttemptReview = {
  requested_at: string;
  overrides: Record<string, Verdict> | null;
  reason: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
};

export type Signal = number | null;
export type SignalKey = "A" | "D" | "O" | "M" | "B";
export type EvidenceRef = { chunk_id: string; quote: string; event?: string; document?: string };

export type PriorKnowledge = { finding_id: string; version_id: string; version_no: number };

export type Finding = {
  id: string;
  area_key: string;
  title: string;
  summary: string;
  question: string | null;
  signals: Record<SignalKey, Signal>;
  counts: Record<string, number | null>;
  raw_score: number | null;
  // Score breakdown computed by the backend; the browser only draws it.
  weights: Record<SignalKey, number>;
  contributions: Record<SignalKey, number | null>;
  cap: number;
  reasons: string[];
  missing_facets: string[];
  top_candidate: boolean;
  review_priority: number | null;
  evidence_confidence: "high" | "medium" | "low";
  eligibility_status:
    | "ranked"
    | "adequately_covered"
    | "not_prioritized"
    | "insufficient"
    | "review_required";
  status: "candidate" | "confirmed" | "rejected" | "obsolete";
  status_reason: string | null;
  revision: number;
  evidence_refs: EvidenceRef[];
  // Approved knowledge for the same area from an earlier analysis of this handoff.
  prior_knowledge: PriorKnowledge | null;
};

export type Analysis = {
  id: string;
  selected_engineer_id: string;
  model_id: string;
  prompt_version: string;
  scoring_version: string;
  bundle_hash: string;
  rejected_areas: { area_key: string; problems: string[] }[];
  reused_extraction_from: string | null;
  findings: Finding[];
};

export type Chunk = {
  chunk_id: string;
  line_start: number | null;
  line_end: number | null;
  text: string;
  item: {
    source: string;
    source_type: string;
    external_id: string;
    author_display_name: string | null;
    occurred_at: string | null;
    title: string | null;
    url: string | null;
  };
};

export type KnowledgeContent = {
  applicability: string;
  prerequisites: string[];
  steps: string[];
  stop_and_escalate: string[];
  success_checks: string[];
  limitations: string[];
  unresolved: string[];
};

export type Draft = { id: string; revision: number; content: KnowledgeContent };

export type KnowledgeVersion = {
  id: string;
  finding_id: string;
  version_no: number;
  draft_revision: number;
  approved_content: KnowledgeContent;
  approved_by: string;
  approved_at: string;
  content_hash: string;
  supersedes_version_id: string | null;
};

export type FindingDetail = Finding & {
  handoff: Handoff;
  draft: Draft | null;
  versions: KnowledgeVersion[];
};

// ---------- Verify ----------
// The successor's view never contains criteria; `results` appears only after assessment.

export type Criterion = { id: string; text: string; critical: boolean; source_path: string };

export type Verdict = "met" | "partial" | "unmet" | "uncertain";
export type AggregateResult = "demonstrated" | "partial" | "not_yet" | "review_required";

export type CriterionResult = {
  criterion_id: string;
  text: string;
  verdict: Verdict;
  evidence_quote: string;
  critical?: boolean; // expert view only
  source_path?: string; // expert view only
};

export type Attempt = {
  id: string;
  exercise_id: string;
  knowledge_version_id: string;
  knowledge_version_no: number;
  // The learner's person_id, or their alias for the expert while the successor is selected.
  successor_id: string;
  answer: string;
  assessment_status: "pending" | "succeeded" | "failed";
  assessment_error: string | null;
  aggregate_result: AggregateResult | null;
  // After an expert review; otherwise equal to aggregate_result.
  effective_result?: AggregateResult | null;
  score_pct?: number | null;
  review?: AttemptReview | null;
  results: CriterionResult[] | null;
  created_at: string;
  assessed_at: string | null;
};

export type Exercise = {
  id: string;
  knowledge_version_id: string;
  knowledge_version_no: number;
  status: "draft" | "ready" | "obsolete";
  scenario: string;
  approved_at: string | null;
  viewer_role: HandoffRole;
  attempts: Attempt[];
  // Present only for a candidate of a selecting handoff.
  candidate?: CandidateInfo | null;
  // expert and admin view only
  revision?: number;
  approved_by?: string | null;
  generator_id?: string | null;
  criteria?: Criterion[];
};

// ---------- Accounts ----------

export type Role = "admin" | "member";

export type User = {
  id: string;
  username: string;
  display_name: string | null;
  role: Role;
  person_id: string | null;
};

export type AdminUser = User & { is_active: boolean; created_at: string; last_login_at: string | null };

export type Page<T> = { items: T[]; total: number; page: number; size: number };

export type AuditEvent = {
  id: number;
  handoff_id: string | null;
  actor_id: string;
  action: string;
  target_type: string;
  target_id: string;
  target_revision: number | null;
  metadata: Record<string, unknown>;
  created_at: string;
};

export type MyExercise = {
  id: string;
  status: Exercise["status"];
  viewer_role: HandoffRole;
  handoff_id: string;
  project_key: string;
  finding_id: string;
  area_key: string;
  title: string;
  knowledge_version_id: string;
  knowledge_version_no: number;
  approved_at: string | null;
  latest_attempt: {
    id: string;
    assessment_status: Attempt["assessment_status"];
    aggregate_result: AggregateResult | null;
    created_at: string;
  } | null;
};

export type LibraryEntry = {
  version_id: string;
  version_no: number;
  finding_id: string;
  area_key: string;
  title: string;
  project_key: string;
  handoff_id: string;
  approved_by: string;
  approved_at: string;
};

// Help assistant. Answers come only from curated help topics and approved knowledge; the
// backend decides the mode (and the assessment lock) from the session.
export type AssistantMode = "help" | "knowledge" | "locked" | "unknown";

export type AssistantCitation = {
  kind: "help_topic" | "knowledge_version";
  id: string;
  title: string;
  version_no?: number;
  link?: string;
};

export type AssistantAnswer = {
  mode: AssistantMode;
  answer: string;
  citations: AssistantCitation[];
  suggestions: string[];
  provider: "offline" | "openai" | "offline_fallback";
};

// Learning coach. Only the attempt's owner gets it; it never carries a criterion's critical
// flag or source. Practice is checked by the backend and is never stored or counted.
export type CoachVerdict = "partial" | "unmet";

export type CoachItem = {
  criterion_id: string;
  criterion_text: string;
  verdict: CoachVerdict;
  your_quote: string | null;
  explanation: string;
  reread: { version_id: string; version_no: number; title: string; line_id: string; text: string; link: string };
  practice: { practice_id: string; prompt: string };
};

export type Coach = {
  attempt_id: string;
  result: AggregateResult | null;
  met_count: number;
  total: number;
  items: CoachItem[];
  message: string;
  next_step: "try_again" | "official_result_stands" | "none";
  provider: "offline" | "openai" | "offline_fallback";
};

export type PracticeResult = {
  verdict: "met" | "partial" | "unmet";
  feedback: string;
  reread_text: string;
};
