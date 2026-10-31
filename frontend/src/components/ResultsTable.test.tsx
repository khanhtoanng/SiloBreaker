import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Readiness, ReadinessCandidate } from "../types";
import ResultsTable, { RESULTS_NOTE } from "./ResultsTable";

function candidate(p: Partial<ReadinessCandidate> & { person_id: string }): ReadinessCandidate {
  return {
    display_name: p.person_id[0].toUpperCase() + p.person_id.slice(1),
    alias: "Candidate A",
    group: "ready",
    group_label: "Ready",
    best_attempt_id: "a",
    best_result: "demonstrated",
    score_pct: 100,
    ranked: true,
    submitted: true,
    missing_critical: false,
    is_top: false,
    criteria: [
      { criterion_id: "C1", text: "Do not create a new settlement", critical: true, weight: 2, verdict: "met", overridden: false },
      { criterion_id: "C3", text: "Ledger shows one settlement", critical: false, weight: 1, verdict: "unmet", overridden: false },
    ],
    attempts_used: 1,
    max_attempts: 1,
    study_opened: true,
    review_pending: false,
    ...p,
  };
}

// The backend's verdict: order, top, tie and critical misses are all in the payload.
function readiness(p: Partial<Readiness> = {}): Readiness {
  return {
    handoff_id: "h1",
    status: "selecting",
    exercise_id: "ex1",
    assessment: { exercise_id: "ex1", due_at: "2026-10-30T10:00:00Z", started_at: "2026-10-24T10:00:00Z", max_attempts: 1 },
    weights: { critical: 2, normal: 1 },
    candidates: [
      candidate({ person_id: "bob", alias: "Candidate B", is_top: true }),
      candidate({ person_id: "carol", alias: "Candidate A", best_result: "partial", group: "ready_with_support", group_label: "Ready with support", score_pct: 86 }),
      candidate({ person_id: "minh", alias: "Candidate C", best_result: "not_yet", group: "not_yet", group_label: "Not yet", score_pct: 21, missing_critical: true }),
    ],
    recommended: ["bob"],
    top_ids: ["bob"],
    tie: false,
    warnings: [],
    decision: null,
    ...p,
  };
}

const rowOf = (name: RegExp) => screen.getByRole("row", { name });

describe("ResultsTable", () => {
  it("shows the backend's scores and the best, critical and not-submitted badges", () => {
    const data = readiness();
    data.candidates.push(
      candidate({ person_id: "dan", alias: "Candidate D", submitted: false, ranked: false, score_pct: null, best_result: null, criteria: null, group: "pending" }),
    );
    data.warnings = [{ person_id: "dan", code: "no_result" }];
    render(<ResultsTable data={data} busy={false} onSelect={vi.fn()} />);
    expect(screen.getByRole("img", { name: "Score for Carol 86%" })).toBeInTheDocument();
    expect(within(rowOf(/^Bob/)).getByText("Best result")).toBeInTheDocument();
    expect(within(rowOf(/^Minh/)).getByText("Missing a critical condition")).toBeInTheDocument();
    expect(within(rowOf(/^Carol/)).queryByText("Best result")).not.toBeInTheDocument();
    expect(within(rowOf(/^Dan/)).getByText("Not submitted")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Warnings" })).toHaveTextContent("Dan (Candidate D) has not submitted");
    expect(screen.getByRole("note")).toHaveTextContent(RESULTS_NOTE);
  });

  it("marks a tie and leaves the decision to the admin", () => {
    const data = readiness({ top_ids: ["bob", "carol"], tie: true });
    data.candidates[1] = { ...data.candidates[1], is_top: true, best_result: "demonstrated", score_pct: 100 };
    render(<ResultsTable data={data} busy={false} onSelect={vi.fn()} />);
    expect(within(rowOf(/^Bob/)).getByText("Tie — admin decides")).toBeInTheDocument();
    expect(within(rowOf(/^Carol/)).getByText("Tie — admin decides")).toBeInTheDocument();
    expect(screen.queryByText("Best result")).not.toBeInTheDocument();
  });

  it("shows criterion details with critical marked", async () => {
    render(<ResultsTable data={readiness()} busy={false} onSelect={vi.fn()} />);
    await userEvent.click(within(rowOf(/^Bob/)).getByRole("button", { name: "Details" }));
    const list = screen.getByRole("list", { name: "Criteria for Bob" });
    expect(within(list).getAllByText("critical")).toHaveLength(1);
    expect(list).toHaveTextContent("C1 · Do not create a new settlement");
  });

  it("requires a reason to select someone outside the top", async () => {
    const onSelect = vi.fn();
    render(<ResultsTable data={readiness()} busy={false} onSelect={onSelect} />);
    await userEvent.click(within(rowOf(/^Carol/)).getByRole("button", { name: "Select as successor" }));
    const dialog = screen.getByRole("dialog", { name: "Select as successor" });
    const confirm = within(dialog).getByRole("button", { name: "Confirm selection" });
    expect(within(dialog).getByLabelText(/Reason \(required/)).toBeRequired();
    expect(confirm).toBeDisabled();
    await userEvent.type(within(dialog).getByLabelText(/Reason/), "   ");
    expect(confirm).toBeDisabled();
    await userEvent.type(within(dialog).getByLabelText(/Reason/), "Carol stays on the team");
    expect(confirm).toBeEnabled();
    await userEvent.click(confirm);
    expect(onSelect).toHaveBeenCalledWith("carol", "Carol stays on the team");
  });

  it("needs no reason inside the top, and shows the recorded decision", async () => {
    const onSelect = vi.fn();
    const { rerender } = render(<ResultsTable data={readiness()} busy={false} onSelect={onSelect} />);
    await userEvent.click(within(rowOf(/^Bob/)).getByRole("button", { name: "Select as successor" }));
    const dialog = screen.getByRole("dialog", { name: "Select as successor" });
    expect(within(dialog).getByLabelText("Reason (optional)")).not.toBeRequired();
    await userEvent.click(within(dialog).getByRole("button", { name: "Confirm selection" }));
    expect(onSelect).toHaveBeenCalledWith("bob", "");

    const decided = readiness({
      status: "active",
      decision: {
        id: "s1",
        selected_person_id: "bob",
        recommended: ["bob"],
        in_recommended: true,
        top_ids: ["bob"],
        tie: false,
        is_top: true,
        reason: null,
        decided_by: "admin",
        decided_at: "2026-10-25T09:00:00Z",
      },
    });
    rerender(<ResultsTable data={decided} busy={false} onSelect={onSelect} />);
    const decision = screen.getByRole("region", { name: "Decision" });
    expect(decision).toHaveTextContent("Bob (Candidate B) selected by admin");
    expect(decision).toHaveTextContent("In the top result: yes");
    expect(decision).toHaveTextContent("Tie: no");
    expect(screen.queryByRole("button", { name: "Select as successor" })).not.toBeInTheDocument();
  });
});
