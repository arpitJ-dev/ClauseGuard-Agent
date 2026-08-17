import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { SubmissionPanel } from "./SubmissionPanel";

describe("SubmissionPanel", () => {
  it("submits an analysis and clears the selected file", async () => {
    const user = userEvent.setup();
    const onAnalyze = vi.fn().mockResolvedValue(undefined);
    render(
      <SubmissionPanel
        mode="analysis"
        busy={false}
        engineReady
        onModeChange={vi.fn()}
        onAnalyze={onAnalyze}
        onCompare={vi.fn()}
      />,
    );
    const file = new File(["agreement"], "agreement.txt", { type: "text/plain" });

    await user.upload(screen.getByLabelText("Contract"), file);
    await user.click(screen.getByRole("button", { name: "Run analysis" }));

    expect(onAnalyze).toHaveBeenCalledWith(file);
    expect(screen.queryByText("agreement.txt")).not.toBeInTheDocument();
  });

  it("submits both documents in comparison mode", async () => {
    const user = userEvent.setup();
    const onCompare = vi.fn().mockResolvedValue(undefined);
    render(
      <SubmissionPanel
        mode="comparison"
        busy={false}
        engineReady
        onModeChange={vi.fn()}
        onAnalyze={vi.fn()}
        onCompare={onCompare}
      />,
    );
    const original = new File(["original"], "original.docx");
    const modified = new File(["modified"], "modified.pdf");

    await user.upload(screen.getByLabelText("Original"), original);
    await user.upload(screen.getByLabelText("Modified"), modified);
    await user.click(screen.getByRole("button", { name: "Compare versions" }));

    expect(onCompare).toHaveBeenCalledWith(original, modified);
  });

  it("surfaces submission errors and mode changes", async () => {
    const user = userEvent.setup();
    const onAnalyze = vi.fn().mockRejectedValue(new Error("Queue limit reached"));
    const onModeChange = vi.fn();
    render(
      <SubmissionPanel
        mode="analysis"
        busy={false}
        engineReady
        onModeChange={onModeChange}
        onAnalyze={onAnalyze}
        onCompare={vi.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Compare" }));
    expect(onModeChange).toHaveBeenCalledWith("comparison");

    await user.upload(
      screen.getByLabelText("Contract"),
      new File(["agreement"], "agreement.txt", { type: "text/plain" }),
    );
    await user.click(screen.getByRole("button", { name: "Run analysis" }));
    expect(await screen.findByText("Queue limit reached")).toBeVisible();
  });

  it("blocks submissions while the engine is unavailable", () => {
    render(
      <SubmissionPanel
        mode="analysis"
        busy={false}
        engineReady={false}
        onModeChange={vi.fn()}
        onAnalyze={vi.fn()}
        onCompare={vi.fn()}
      />,
    );

    expect(screen.getByText("Analysis engine unavailable")).toBeVisible();
    expect(screen.getByRole("button", { name: "Run analysis" })).toBeDisabled();
  });
});
