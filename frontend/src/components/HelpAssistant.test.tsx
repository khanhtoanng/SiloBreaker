import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../api";
import type { AssistantAnswer } from "../types";
import HelpAssistant, { handoffIdOf } from "./HelpAssistant";

const help: AssistantAnswer = {
  mode: "help",
  answer: "A ranked score is capped at 60 when the knowledge is not concentrated.",
  citations: [{ kind: "help_topic", id: "cap", title: "The cap at 60" }],
  suggestions: ["How is the review priority calculated?", "What does insufficient evidence mean?", "What do I click next?"],
  provider: "offline",
};
const knowledge: AssistantAnswer = {
  mode: "knowledge",
  answer: 'From the approved knowledge "Settlement recovery" v1:\nSteps:\n- Check the provider transaction state',
  citations: [
    { kind: "knowledge_version", id: "v1", title: "Settlement recovery", version_no: 1, link: "/library?open=v1" },
  ],
  suggestions: ["Can I try again?", "Why can't I submit?", "What do I click next?"],
  provider: "offline",
};
const locked: AssistantAnswer = {
  mode: "locked",
  answer:
    "Knowledge answers are paused while you have an exercise to complete. Read the approved knowledge yourself from the exercise page.",
  citations: [],
  suggestions: ["Why can't I submit?", "Can I try again?", "What do I click next?"],
  provider: "offline",
};

afterEach(() => vi.restoreAllMocks());

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <HelpAssistant />
    </MemoryRouter>,
  );
}

const openPanel = async () => {
  await userEvent.click(screen.getByRole("button", { name: "Open help" }));
  return screen.getByRole("dialog", { name: "SiloBreaker Assistant" });
};

describe("HelpAssistant", () => {
  it("is closed by default, opens and closes", async () => {
    renderAt("/library");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    const panel = await openPanel();
    expect(panel).toHaveTextContent("Answers come only from the help guide and approved knowledge.");
    await userEvent.click(within(panel).getByRole("button", { name: "Close assistant" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await openPanel();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("sends a question with Enter, with the page and handoff id, and renders citations", async () => {
    let resolve!: (a: AssistantAnswer) => void;
    const ask = vi.spyOn(api, "ask").mockImplementation(() => new Promise((r) => (resolve = r)));
    renderAt("/expert/handoffs/h-42/detect");
    const panel = await openPanel();
    await userEvent.type(within(panel).getByRole("textbox", { name: "Your question" }), "Why is Webhooks capped at 60?{Enter}");
    expect(ask).toHaveBeenCalledWith({
      question: "Why is Webhooks capped at 60?",
      page: "/expert/handoffs/h-42/detect",
      handoff_id: "h-42",
    });
    expect(within(panel).getByRole("status")).toHaveTextContent("Looking it up");
    expect(within(panel).getByRole("button", { name: "Send" })).toBeDisabled();
    resolve(help);
    expect(await within(panel).findByText("Help: The cap at 60")).toBeInTheDocument();
    expect(panel).toHaveTextContent("capped at 60");
    expect(within(panel).queryByRole("status")).not.toBeInTheDocument();
    // The backend's suggestions replace the starter questions.
    expect(within(panel).getByRole("button", { name: "What does insufficient evidence mean?" })).toBeInTheDocument();

    ask.mockResolvedValue(knowledge);
    await userEvent.type(within(panel).getByRole("textbox"), "When do I escalate?{Enter}");
    const chip = await within(panel).findByRole("link", { name: "Knowledge: Settlement recovery v1" });
    expect(chip).toHaveAttribute("href", "/library?open=v1");
  });

  it("shows the locked notice as a neutral status, without citations", async () => {
    vi.spyOn(api, "ask").mockResolvedValue(locked);
    renderAt("/learn/exercises/e1");
    const panel = await openPanel();
    await userEvent.type(within(panel).getByRole("textbox"), "What should I check before retrying?{Enter}");
    const notice = await within(panel).findByRole("status");
    expect(notice).toHaveClass("assistant-locked");
    expect(notice).toHaveTextContent("Knowledge answers are paused");
    expect(within(panel).queryByLabelText("Sources")).not.toBeInTheDocument();
  });

  it("sends a suggested question when clicked, and Clear empties the chat", async () => {
    const ask = vi.spyOn(api, "ask").mockResolvedValue(help);
    renderAt("/admin/handoffs/h-7");
    const panel = await openPanel();
    await userEvent.click(within(panel).getByRole("button", { name: "What does No history mean?" }));
    expect(ask).toHaveBeenCalledWith({ question: "What does No history mean?", page: "/admin/handoffs/h-7", handoff_id: "h-7" });
    expect(await within(panel).findByText("What does No history mean?")).toBeInTheDocument();
    await userEvent.click(within(panel).getByRole("button", { name: "Clear" }));
    expect(within(panel).queryByText("Help: The cap at 60")).not.toBeInTheDocument();
  });

  it("shows an error without inventing an answer", async () => {
    const { ApiError } = await import("../api");
    vi.spyOn(api, "ask").mockRejectedValue(new ApiError(422, "validation_error", "question too long"));
    renderAt("/library");
    const panel = await openPanel();
    await userEvent.type(within(panel).getByRole("textbox"), "x{Enter}");
    expect(await within(panel).findByRole("alert")).toHaveTextContent("question too long");
  });

  it("sends a handoff id only on handoff routes", () => {
    expect(handoffIdOf("/admin/handoffs/abc")).toBe("abc");
    expect(handoffIdOf("/expert/handoffs/abc/detect")).toBe("abc");
    expect(handoffIdOf("/expert/findings/abc")).toBeUndefined();
    expect(handoffIdOf("/learn/exercises/abc")).toBeUndefined();
    expect(handoffIdOf("/admin/handoffs")).toBeUndefined();
  });
});
