import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { analysisReport, completedAnalysisJob } from "./test/fixtures";

const apiMocks = vi.hoisted(() => ({
  getHealth: vi.fn(),
  listJobs: vi.fn(),
  getReport: vi.fn(),
  submitAnalysis: vi.fn(),
  submitComparison: vi.fn(),
  deleteJob: vi.fn(),
}));

vi.mock("./api/client", async () => {
  const actual = await vi.importActual<typeof import("./api/client")>("./api/client");
  return { ...actual, ...apiMocks };
});

vi.mock("./hooks/useJobStream", () => ({ useJobStream: vi.fn() }));

import App from "./App";

beforeEach(() => {
  vi.clearAllMocks();
  apiMocks.getHealth.mockResolvedValue({
    status: "ok",
    engine: { ready: true, models: [{ role: "extraction" }, { role: "reasoning" }] },
  });
  apiMocks.listJobs.mockResolvedValue([completedAnalysisJob]);
  apiMocks.getReport.mockResolvedValue(analysisReport);
});

describe("App", () => {
  it("loads persisted jobs and opens a completed report", async () => {
    const user = userEvent.setup();
    render(<App />);

    expect(await screen.findByText("Engine ready")).toBeVisible();
    const jobLabel = await screen.findByText("services-agreement.txt");
    await user.click(jobLabel.closest("button")!);

    expect(await screen.findByRole("heading", { name: "SERVICES AGREEMENT" })).toBeVisible();
    expect(apiMocks.getReport).toHaveBeenCalledWith(completedAnalysisJob.id);
  });

  it("submits a document and displays active job progress", async () => {
    const user = userEvent.setup();
    const runningJob = {
      ...completedAnalysisJob,
      id: "11111111111111111111111111111111",
      status: "running" as const,
      stage: "checking",
      progress: 62,
      message: "Checking candidate findings",
      report_url: undefined,
    };
    apiMocks.listJobs.mockResolvedValue([]);
    apiMocks.submitAnalysis.mockResolvedValue({
      job: runningJob,
      links: { self: "/job", events: "/events" },
    });
    render(<App />);

    await screen.findByText("Engine ready");
    await user.upload(
      screen.getByLabelText("Contract"),
      new File(["Agreement"], "new-agreement.txt", { type: "text/plain" }),
    );
    await user.click(screen.getByRole("button", { name: "Run analysis" }));

    expect(await screen.findByRole("heading", { name: "Checking" })).toBeVisible();
    expect(screen.getByText("62%")).toBeVisible();
    expect(apiMocks.submitAnalysis).toHaveBeenCalledOnce();
  });

  it("deletes a terminal review after confirmation", async () => {
    const user = userEvent.setup();
    apiMocks.deleteJob.mockResolvedValue({ job: completedAnalysisJob, deleted: true });
    render(<App />);

    await screen.findByText("services-agreement.txt");
    await user.click(screen.getByRole("button", { name: "Delete services-agreement.txt" }));
    expect(screen.getByRole("dialog", { name: "Delete review?" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Delete" }));

    await waitFor(() => expect(screen.queryByText("services-agreement.txt")).not.toBeInTheDocument());
  });
});
