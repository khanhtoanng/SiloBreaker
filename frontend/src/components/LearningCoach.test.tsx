import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../api";
import type { Attempt, CandidateInfo, Coach, Exercise } from "../types";
import LearningCoach from "./LearningCoach";
import VerifyPanel from "./VerifyPanel";

const LINE = "Pause the retry worker and escalate to the AcmePay contact when the provider state is unknown";

const coach: Coach = {
  attempt_id: "a1",
  result: "not_yet",
  met_count: 3,
  total: 5,
  items: [
    {
      criterion_id: "C2",
      criterion_text: LINE,
      verdict: "unmet",
      your_quote: null,
      explanation: `Your answer did not cover: ${LINE}.`,
      reread: { version_id: "v1", version_no: 1, title: "Settlement recovery", line_id: "L6", text: LINE, link: "/library?open=v1" },
      practice: { practice_id: "tok-2", prompt: "In your own words: what does the approved knowledge say you should do here?" },
    },
    {
      criterion_id: "C4",
      criterion_text: "Check the provider transaction state for the existing attempt",
      verdict: "partial",
      your_quote: "I would look up the settlement",
      explanation: "Your answer only partly covered: Check the provider transaction state for the existing attempt.",
      reread: {
        version_id: "v1",
        version_no: 1,
        title: "Settlement recovery",
        line_id: "L2",
        text: "Check the provider transaction state for the existing attempt",
        link: "/library?open=v1",
      },
      practice: { practice_id: "tok-4", prompt: "In your own words, and in full this time: what does the approved knowledge say?" },
    },
  ],
  message: "Re-read these lines of the approved knowledge and practise them. Practice does not change your result.",
  next_step: "try_again",
  provider: "offline",
};

afterEach(() => vi.restoreAllMocks());

const openCoach = async () => {
  await userEvent.click(await screen.findByRole("button", { name: "Coach me on this attempt" }));
  return screen.findByRole("region", { name: "Learning Coach — practice does not change your result." });
};

describe("LearningCoach", () => {
  it("opens, renders the items and the re-read quote, and checks a practice answer", async () => {
    const getCoach = vi.spyOn(api, "getCoach").mockResolvedValue(coach);
    const check = vi
      .spyOn(api, "checkPractice")
      .mockResolvedValue({ verdict: "met", feedback: "Your practice answer covers the approved line.", reread_text: LINE });
    render(<LearningCoach attemptId="a1" onTryAgain={vi.fn()} />);
    expect(getCoach).not.toHaveBeenCalled(); // opens only on request

    const region = await openCoach();
    expect(getCoach).toHaveBeenCalledWith("a1");
    const cards = within(region).getAllByRole("article");
    expect(cards.map((c) => c.getAttribute("aria-label"))).toEqual([
      `Coach: ${LINE}`,
      "Coach: Check the provider transaction state for the existing attempt",
    ]);
    const [first, second] = cards;
    expect(within(first).getByText("Not met")).toBeInTheDocument();
    expect(within(second).getByText("Partly met")).toBeInTheDocument();
    expect(within(first).queryByText(/Your answer said/)).toBeNull();
    expect(second).toHaveTextContent("Your answer said: I would look up the settlement");
    expect(within(first).getByText("Re-read in the approved knowledge")).toBeInTheDocument();
    expect(first.querySelector("blockquote")).toHaveTextContent(LINE);
    expect(within(first).getByRole("link", { name: /in the Library$/ })).toHaveAttribute("href", "/library?open=v1");

    const box = within(first).getByRole("textbox", { name: /^Practice: In your own words/ });
    const checkButton = within(first).getByRole("button", { name: "Check" });
    expect(checkButton).toBeDisabled();
    await userEvent.type(box, "Stop the retry worker and raise it with the AcmePay contact");
    await userEvent.click(checkButton);
    expect(check).toHaveBeenCalledWith({
      practice_id: "tok-2",
      answer: "Stop the retry worker and raise it with the AcmePay contact",
    });
    const status = await within(first).findByRole("status");
    expect(status).toHaveTextContent("Covered. Your practice answer covers the approved line.");
    expect(status).toHaveTextContent(`The approved line: ${LINE}`);

    await userEvent.click(within(first).getByRole("button", { name: "Try another wording" }));
    expect(box).toHaveValue("");
    expect(within(first).queryByRole("status")).toBeNull();
  });

  it("sends a successor back to Try again", async () => {
    vi.spyOn(api, "getCoach").mockResolvedValue(coach);
    const onTryAgain = vi.fn();
    render(<LearningCoach attemptId="a1" onTryAgain={onTryAgain} />);
    const region = await openCoach();
    expect(within(region).queryByRole("note")).toBeNull();
    await userEvent.click(within(region).getByRole("button", { name: "Try again" }));
    expect(onTryAgain).toHaveBeenCalled();
  });

  it("tells a candidate the official result stands, with no Try again", async () => {
    vi.spyOn(api, "getCoach").mockResolvedValue({ ...coach, next_step: "official_result_stands" });
    render(<LearningCoach attemptId="a1" onTryAgain={vi.fn()} />);
    const region = await openCoach();
    expect(within(region).getByRole("note")).toHaveTextContent(
      "Your official result for this assessment stands. Practice is for learning only.",
    );
    expect(within(region).queryByRole("button", { name: "Try again" })).toBeNull();
  });

  it("never shows the word critical", async () => {
    vi.spyOn(api, "getCoach").mockResolvedValue(coach);
    vi.spyOn(api, "checkPractice").mockResolvedValue({ verdict: "unmet", feedback: "Not yet.", reread_text: LINE });
    const { container } = render(<LearningCoach attemptId="a1" onTryAgain={vi.fn()} />);
    const region = await openCoach();
    const box = within(region).getAllByRole("textbox")[0];
    await userEvent.type(box, "coffee");
    await userEvent.click(within(region).getAllByRole("button", { name: "Check" })[0]);
    await within(region).findByRole("status");
    expect(container.textContent?.toLowerCase()).not.toContain("critical");
    expect(container.innerHTML.toLowerCase()).not.toContain("critical");
  });
});

describe("Learning coach on the exercise page", () => {
  const candidate: CandidateInfo = {
    handoff_id: "h1",
    alias: "Candidate B",
    candidate_count: 3,
    due_at: "2026-10-30T10:00:00Z",
    max_attempts: 1,
    attempts_used: 1,
    attempts_left: 0,
    study_opened: true,
    is_assessment_exercise: true,
    closed: false,
  };
  const attempt = (result: Attempt["aggregate_result"]): Attempt => ({
    id: "a1",
    exercise_id: "ex1",
    knowledge_version_id: "v1",
    knowledge_version_no: 1,
    successor_id: "bob",
    answer: "My answer",
    assessment_status: "succeeded",
    assessment_error: null,
    aggregate_result: result,
    effective_result: result,
    score_pct: null,
    review: null,
    results: [{ criterion_id: "C1", text: "Do not create a new settlement", verdict: "met", evidence_quote: "My answer" }],
    created_at: "2026-10-24T10:00:00Z",
    assessed_at: "2026-10-24T10:00:01Z",
  });
  const exercise = (a: Attempt, c: CandidateInfo | null = null): Exercise => ({
    id: "ex1",
    knowledge_version_id: "v1",
    knowledge_version_no: 1,
    status: "ready",
    scenario: "You are on call for settlement recovery. Describe what you do.",
    approved_at: "2026-10-24T00:00:00Z",
    viewer_role: "successor",
    attempts: [a],
    candidate: c,
  });
  const renderPanel = () =>
    render(<VerifyPanel versionId="v1" versionNo={1} expectedRole="successor" exerciseId="ex1" coach />);

  it("offers the coach under a not-demonstrated attempt, and Try again opens the answer form", async () => {
    vi.spyOn(api, "listExercises").mockResolvedValue([exercise(attempt("not_yet"))]);
    vi.spyOn(api, "getCoach").mockResolvedValue(coach);
    renderPanel();
    const region = await openCoach();
    await userEvent.click(within(region).getByRole("button", { name: "Try again" }));
    expect(await screen.findByLabelText("Your answer")).toBeInTheDocument();
  });

  it("shows only a small line for a demonstrated attempt", async () => {
    vi.spyOn(api, "listExercises").mockResolvedValue([exercise(attempt("demonstrated"))]);
    renderPanel();
    expect(await screen.findByText("Nothing to fix in this attempt.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Coach me on this attempt" })).toBeNull();
  });

  it("gives a candidate who used the official attempt no Submit or Try again", async () => {
    vi.spyOn(api, "listExercises").mockResolvedValue([exercise(attempt("partial"), candidate)]);
    vi.spyOn(api, "getCoach").mockResolvedValue({ ...coach, result: "partial", next_step: "official_result_stands" });
    renderPanel();
    await openCoach();
    expect(screen.getByText("Your official result for this assessment stands. Practice is for learning only.")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Submit answer" })).toBeNull();
    expect(document.body.textContent?.toLowerCase()).not.toContain("critical");
  });
});
