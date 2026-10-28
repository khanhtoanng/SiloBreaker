import type {
  AdminUser,
  Analysis,
  AssistantAnswer,
  Attempt,
  AuditEvent,
  Bundle,
  Chunk,
  Coach,
  Criterion,
  Draft,
  Exercise,
  Finding,
  FindingDetail,
  Handoff,
  HandoffDetail,
  HandoffSummary,
  KnowledgeContent,
  KnowledgeVersion,
  LibraryEntry,
  MyExercise,
  Page,
  PracticeResult,
  Readiness,
  Role,
  SelectionDecision,
  Suitability,
  User,
  Verdict,
} from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    // Safe identifiers the backend adds to recover, e.g. attempt_id after a provider failure.
    public extra: Record<string, string> = {},
  ) {
    super(message);
  }
}

const PROVIDER_CODES = new Set(["provider_error", "provider_timeout", "provider_not_configured"]);

export type ErrorKind = "stale" | "provider" | "network" | "other";

/** Classifies an error so stale data and provider failures get their own message. */
export function describeError(e: unknown): { kind: ErrorKind; message: string } {
  if (!(e instanceof ApiError)) return { kind: "other", message: String(e) };
  if (e.status === 409 && e.code === "stale_revision")
    return { kind: "stale", message: "This data has changed. Reload to see the latest version." };
  if (e.status >= 500 && PROVIDER_CODES.has(e.code)) {
    const what =
      e.code === "provider_timeout"
        ? "The AI provider did not answer in time"
        : e.code === "provider_not_configured"
          ? "The AI provider is not configured"
          : "The AI provider failed";
    return {
      kind: "provider",
      message: `${what}. This is a system error, not a result about anyone's knowledge. (${e.code})`,
    };
  }
  if (e.code === "network") return { kind: "network", message: e.message };
  return { kind: "other", message: `${e.message} (${e.code})` };
}

const WRITE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

// Set by AuthProvider: a 401 on any call means the session ended, so the app signs out.
let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: (() => void) | null) {
  onUnauthorized = fn;
}

async function call<T>(method: string, path: string, body?: unknown, idempotent = false): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  // The backend refuses writes without this header (CSRF protection for cookie sessions).
  if (WRITE_METHODS.has(method)) headers["X-Requested-With"] = "silobreaker";
  if (idempotent) headers["Idempotency-Key"] = crypto.randomUUID();
  let res: Response;
  try {
    res = await fetch(`/api${path}`, {
      method,
      headers,
      credentials: "include",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "network", "Cannot reach the SiloBreaker API. Is the backend running?");
  }
  const text = await res.text();
  if (!res.ok) {
    let code = "http_error";
    let detail = text || res.statusText;
    let extra: Record<string, string> = {};
    try {
      const j = JSON.parse(text);
      if (j.error) ({ code, detail, ...extra } = j.error);
      else if (j.detail) detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {
      /* not JSON */
    }
    if (res.status === 401 && !path.startsWith("/auth/")) onUnauthorized?.();
    throw new ApiError(res.status, code, detail, extra);
  }
  const type = res.headers.get("content-type") ?? "";
  if (!text) return undefined as T;
  return (type.includes("json") ? JSON.parse(text) : text) as T;
}

function query(params: Record<string, string | number | undefined | null>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
  const s = q.toString();
  return s ? `?${s}` : "";
}

export type UserCreate = { username: string; display_name?: string; role: Role; password: string; person_id?: string };
export type UserPatch = { display_name?: string | null; role?: Role; is_active?: boolean; password?: string };

export const api = {
  // Session. The acting person is always the signed-in account; no call names an actor.
  login: (username: string, password: string) =>
    call<{ user: User; expires_at: string }>("POST", "/auth/login", { username, password }),
  logout: () => call<void>("POST", "/auth/logout"),
  me: () => call<{ user: User }>("GET", "/auth/me"),

  // Admin
  reset: () => call<Bundle>("POST", "/demo/reset"),
  importBundle: () => call<Bundle>("POST", "/bundles/import"),
  bundle: (id: string) => call<Bundle>("GET", `/bundles/${id}`),
  users: (p: { q?: string; role?: string; page?: number; size?: number }) =>
    call<Page<AdminUser>>("GET", `/admin/users${query(p)}`),
  createUser: (b: UserCreate) => call<AdminUser>("POST", "/admin/users", b),
  updateUser: (id: string, b: UserPatch) => call<AdminUser>("PATCH", `/admin/users/${id}`, b),
  audit: (p: { actor?: string; action?: string; date_from?: string; date_to?: string; page?: number; size?: number }) =>
    call<Page<AuditEvent>>("GET", `/admin/audit${query(p)}`),

  // Handoffs and Detect
  handoffs: () => call<HandoffSummary[]>("GET", "/handoffs"),
  handoff: (id: string) => call<HandoffDetail>("GET", `/handoffs/${id}`),
  // Without successor_id the handoff is "unassigned": the successor is chosen later.
  createHandoff: (b: { bundle_id: string; expert_id: string; successor_id?: string }) =>
    call<Handoff>("POST", "/handoffs", b),

  // Successor selection. Fit, scores, top and tie all come from the backend.
  suitability: (handoffId: string) => call<Suitability>("GET", `/handoffs/${handoffId}/suitability`),
  assignSuccessor: (handoffId: string, successorId: string) =>
    call<Handoff>("POST", `/handoffs/${handoffId}/assign`, { successor_id: successorId }),
  startAssessment: (handoffId: string, b: { candidate_ids: string[]; exercise_id: string; due_at: string }) =>
    call<Handoff>("POST", `/handoffs/${handoffId}/assessment`, b),
  readiness: (handoffId: string) => call<Readiness>("GET", `/handoffs/${handoffId}/readiness`),
  selectSuccessor: (handoffId: string, b: { selected_person_id: string; reason?: string }) =>
    call<SelectionDecision>("POST", `/handoffs/${handoffId}/selection`, b),
  studyOpened: (handoffId: string) =>
    call<{ handoff_id: string; alias: string; study_opened_at: string }>("POST", `/handoffs/${handoffId}/study-opened`),
  analyze: (handoffId: string, selected: string) =>
    call<Analysis>("POST", `/handoffs/${handoffId}/analyses`, { selected_engineer_id: selected }, true),
  getAnalysis: (id: string) => call<Analysis>("GET", `/analyses/${id}`),
  chunk: (id: string) => call<Chunk>("GET", `/chunks/${id}`),

  // Capture
  finding: (id: string) => call<FindingDetail>("GET", `/findings/${id}`),
  review: (id: string, b: { action: string; reason: string; expected_revision: number; corrected_summary?: string }) =>
    call<Finding>("POST", `/findings/${id}/review`, b),
  structure: (id: string, answer: string) =>
    call<KnowledgeContent>("POST", `/findings/${id}/structure`, { answer }),
  saveDraft: (id: string, b: { content: KnowledgeContent; expected_revision: number | null }) =>
    call<Draft>("PUT", `/findings/${id}/draft`, b),
  publish: (id: string, b: { expected_finding_revision: number; draft_revision: number }) =>
    call<KnowledgeVersion>("POST", `/findings/${id}/publish`, b, true),
  knowledge: (versionId: string) => call<KnowledgeVersion>("GET", `/knowledge/${versionId}`),
  okf: (versionId: string) => call<string>("GET", `/knowledge/${versionId}/okf`),
  library: () => call<LibraryEntry[]>("GET", "/library"),

  // Verify. The backend decides from the session what this viewer may see.
  createExercise: (versionId: string) => call<Exercise>("POST", `/knowledge/${versionId}/exercises`, undefined, true),
  listExercises: (versionId: string) => call<Exercise[]>("GET", `/knowledge/${versionId}/exercises`),
  getExercise: (id: string) => call<Exercise>("GET", `/exercises/${id}`),
  myExercises: () => call<MyExercise[]>("GET", "/me/exercises"),
  saveExerciseDraft: (id: string, b: { scenario: string; criteria: Criterion[]; expected_revision: number }) =>
    call<Exercise>("PUT", `/exercises/${id}/draft`, b),
  approveExercise: (id: string, b: { expected_revision: number }) =>
    call<Exercise>("POST", `/exercises/${id}/approve`, b),
  submitAttempt: (exerciseId: string, b: { answer: string }) =>
    call<Attempt>("POST", `/exercises/${exerciseId}/attempts`, b, true),
  getAttempt: (id: string) => call<Attempt>("GET", `/attempts/${id}`),
  reassess: (id: string) => call<Attempt>("POST", `/attempts/${id}/reassess`),
  requestReview: (id: string) => call<Attempt>("POST", `/attempts/${id}/review-request`),
  reviewAttempt: (id: string, b: { overrides: Record<string, Verdict>; reason: string }) =>
    call<Attempt>("POST", `/attempts/${id}/review`, b),

  // Help assistant. Nothing is stored; who is asking comes from the session.
  ask: (b: { question: string; page: string; handoff_id?: string }) =>
    call<AssistantAnswer>("POST", "/assistant/ask", b),

  // Learning coach. Only the attempt's owner; practice is never stored or counted.
  getCoach: (attemptId: string) => call<Coach>("GET", `/attempts/${attemptId}/coach`),
  checkPractice: (b: { practice_id: string; answer: string }) =>
    call<PracticeResult>("POST", "/coach/practice", b),
};
