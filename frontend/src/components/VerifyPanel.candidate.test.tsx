import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../api";
import type { Attempt, CandidateInfo, Exercise } from "../types";
import VerifyPanel from "./VerifyPanel";

const candidate: CandidateInfo = {
  handoff_id: "h1",
  alias: "Candidate B",
  candidate_count: 3,
  due_at: "2026-10-30T10:00:00Z",
  max_attempts: 1,
  attempts_used: 0,
  attempts_left: 1,
  study_opened: false,
  is_assessment_exercise: true,
  closed: false,
};

const exercise: Exercise = {
  id: "ex1",
  knowledge_version_id: "v1",
  knowledge_version_no: 1,
  status: "ready",
  scenario: "You are on call for settlement recovery. Describe what you do.",
  approved_at: "2026-10-24T00:00:00Z",
  viewer_role: "successor",
  attempts: [],
  candidate,
};

const graded: Attempt = {
  id: "a1",
  exercise_id: "ex1",
  knowledge_version_id: "v1",
  knowledge_version_no: 1,
  successor_id: "carol",
  answer: "My answer",
  assessment_status: "succeeded",
  assessment_error: null,
  aggregate_result: "partial",
  effective_result: "partial",
  score_pct: 86,
  review: null,
  results: [{ criterion_id: "C1", text: "Do not create a new settlement", verdict: "met", evidence_quote: "My answer" }],
  created_at: "2026-10-24T10:00:00Z",
  assessed_at: "2026-10-24T10:00:01Z",
};

afterEach(() => vi.restoreAllMocks());

const renderPanel = (onOpenKnowledge = vi.fn()) => {
  render(<VerifyPanel versionId="v1" versionNo={1} expectedRole="successor" exerciseId="ex1" onOpenKnowledge={onOpenKnowledge} />);
  return onOpenKnowledge;
};

describe("Learn as a candidate", () => {
  it("shows the banner and keeps Submit locked until the approved knowledge is read", async () => {
    vi.spyOn(api, "listExercises")
      .mockResolvedValueOnce([exercise])
      .mockResolvedValue([{ ...exercise, candidate: { ...candidate, study_opened: true } }]);
    const opened = vi.spyOn(api, "studyOpened").mockResolvedValue({ handoff_id: "h1", alias: "Candidate B", study_opened_at: "now" });
    const onOpen = renderPanel();

    expect(await screen.findByRole("note")).toHaveTextContent(
      /^You are one of 3 candidates · same exercise · one official attempt · due .+ · results are private$/,
    );
    await userEvent.type(screen.getByLabelText("Your answer"), "My answer");
    expect(screen.getByRole("button", { name: "Submit answer" })).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: "Read the approved knowledge" }));
    expect(opened).toHaveBeenCalledWith("h1");
    expect(onOpen).toHaveBeenCalled();
    await userEvent.type(await screen.findByLabelText("Your answer"), "My answer");
    expect(screen.getByRole("button", { name: "Submit answer" })).toBeEnabled();
  });

  it("shows the own score and Request review, and no way to submit once the attempt is used", async () => {
    const used = { ...candidate, study_opened: true, attempts_used: 1, attempts_left: 0 };
    vi.spyOn(api, "listExercises").mockResolvedValue([{ ...exercise, candidate: used, attempts: [graded] }]);
    const request = vi.spyOn(api, "requestReview").mockResolvedValue({ ...graded, review: { requested_at: "now", overrides: null, reason: null, reviewed_by: null, reviewed_at: null } });
    renderPanel();

    expect(await screen.findByText("86%")).toBeInTheDocument();
    expect(screen.getByText(/Your score:/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Your answer")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Submit answer" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
    expect(screen.getByText(/used your official attempt/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Request review" }));
    expect(request).toHaveBeenCalledWith("a1");
  });
});

describe("Expert review queue", () => {
  it("shows attempts by alias and needs a changed verdict and a reason", async () => {
    const asked: Attempt = {
      ...graded,
      successor_id: "Candidate B",
      results: [{ ...graded.results![0], verdict: "partial", critical: true }],
      review: { requested_at: "now", overrides: null, reason: null, reviewed_by: null, reviewed_at: null },
    };
    vi.spyOn(api, "listExercises").mockResolvedValue([
      { ...exercise, viewer_role: "expert", candidate: null, revision: 2, criteria: [], attempts: [asked] },
    ]);
    const review = vi.spyOn(api, "reviewAttempt").mockResolvedValue(asked);
    render(<VerifyPanel versionId="v1" versionNo={1} expectedRole="expert" />);

    expect(await screen.findByRole("heading", { name: "Review requests (1)" })).toBeInTheDocument();
    expect(screen.getByRole("article", { name: "Attempt 1 by Candidate B" })).toBeInTheDocument();
    expect(screen.queryByText(/carol/i)).not.toBeInTheDocument();
    const save = screen.getByRole("button", { name: "Save review" });
    expect(save).toBeDisabled();
    await userEvent.selectOptions(screen.getByLabelText(/^Verdict for C1/), "met");
    expect(save).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Reason for the change (required)"), "States the stop condition.");
    expect(save).toBeEnabled();
    await userEvent.click(save);
    expect(review).toHaveBeenCalledWith("a1", { overrides: { C1: "met" }, reason: "States the stop condition." });
  });
});
