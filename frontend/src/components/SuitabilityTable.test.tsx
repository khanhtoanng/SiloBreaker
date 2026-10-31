import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Suitability } from "../types";
import SuitabilityTable, { FIT_NOTE, NO_HISTORY } from "./SuitabilityTable";

// What the backend returns: the fit numbers are the API's, never recomputed here.
const DATA: Suitability = {
  handoff_id: "h1",
  status: "unassigned",
  analysis_id: "a1",
  ranked_areas: [
    { area_key: "settlement", title: "Settlement recovery", review_priority: 88 },
    { area_key: "webhooks", title: "Webhooks recovery", review_priority: 60 },
  ],
  total_priority: 148,
  members: [
    {
      person_id: "bob",
      display_name: "Bob",
      fit_pct: 20,
      fit_status: "scored",
      basis: [{ area_key: "webhooks", title: "Webhooks recovery", review_priority: 60, incidents: ["PAY-347"], experience: 0.5 }],
    },
    {
      person_id: "carol",
      display_name: "Carol",
      fit_pct: 20,
      fit_status: "scored",
      basis: [{ area_key: "webhooks", title: "Webhooks recovery", review_priority: 60, incidents: ["PAY-360"], experience: 0.5 }],
    },
    { person_id: "minh", display_name: "Minh", fit_pct: null, fit_status: "no_history", basis: [] },
  ],
  released_exercises: [
    { id: "ex1", title: "Settlement recovery", area_key: "settlement", knowledge_version_no: 1, approved_at: "2026-10-24T00:00:00Z" },
  ],
  note: FIT_NOTE,
};

function renderTable(onAssign = vi.fn(), onStart = vi.fn(), locked = false) {
  render(<SuitabilityTable data={DATA} locked={locked} busy={false} onAssign={onAssign} onStart={onStart} />);
  return { onAssign, onStart };
}

const row = (name: string) => screen.getByRole("checkbox", { name: `Select ${name}` }).closest("tr")!;

describe("SuitabilityTable", () => {
  it("shows the backend's fit as an SVG bar and No history, never 0%, without history", () => {
    renderTable();
    expect(screen.getByRole("img", { name: "Fit for Bob 20%" })).toBeInTheDocument();
    expect(within(row("Bob")).getByText("20%")).toBeInTheDocument();
    expect(within(row("Bob")).getByText("Webhooks recovery: PAY-347")).toBeInTheDocument();
    const minh = row("Minh");
    expect(within(minh).getByText(NO_HISTORY)).toBeInTheDocument();
    expect(within(minh).queryByText("0%")).not.toBeInTheDocument();
    expect(within(minh).queryByRole("img")).not.toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent(FIT_NOTE);
  });

  it("offers Assign directly for one person and a common assessment from two", async () => {
    const { onAssign, onStart } = renderTable();
    expect(screen.queryByRole("button", { name: "Assign directly" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Start common assessment" })).not.toBeInTheDocument();

    await userEvent.click(screen.getByLabelText("Select Bob"));
    expect(screen.getByRole("button", { name: "Assign directly" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "Start common assessment" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Assign directly" }));
    expect(onAssign).toHaveBeenCalledWith("bob");

    await userEvent.click(screen.getByLabelText("Select Minh"));
    expect(screen.queryByRole("button", { name: "Assign directly" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Start common assessment" }));
    const dialog = screen.getByRole("dialog", { name: "Start common assessment" });
    expect(within(dialog).getByLabelText("Released exercise")).toHaveValue("ex1");
    expect(within(dialog).getByLabelText("Due")).not.toHaveValue("");
    await userEvent.click(within(dialog).getByRole("button", { name: "Start assessment" }));
    expect(onStart).toHaveBeenCalledWith(
      expect.objectContaining({ candidate_ids: ["bob", "minh"], exercise_id: "ex1", due_at: expect.any(String) }),
    );
  });

  it("is read-only once the successor path is chosen", () => {
    renderTable(vi.fn(), vi.fn(), true);
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.getByText(NO_HISTORY)).toBeInTheDocument();
  });
});
