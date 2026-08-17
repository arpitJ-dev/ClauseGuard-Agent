import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { analysisReport } from "../test/fixtures";
import { AnalysisReportView } from "./AnalysisReportView";

describe("AnalysisReportView", () => {
  it("shows findings and their evidence", () => {
    render(<AnalysisReportView report={analysisReport} onDownload={vi.fn()} />);

    expect(screen.getByRole("heading", { name: "SERVICES AGREEMENT" })).toBeVisible();
    expect(screen.getByText("Balanced Discretion Checklist")).toBeVisible();
    expect(screen.getByText("84%")).toBeVisible();
  });

  it("filters by severity and opens report tabs", async () => {
    const user = userEvent.setup();
    render(<AnalysisReportView report={analysisReport} onDownload={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: "Medium" }));
    expect(screen.getByText("Payment Ambiguity")).toBeVisible();
    expect(screen.queryByText("Risky Language")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Rewrites" }));
    expect(screen.getByText("Adds objective and mutual safeguards.")).toBeVisible();
  });

  it("navigates clauses and audit details and downloads the report", async () => {
    const user = userEvent.setup();
    const onDownload = vi.fn();
    render(<AnalysisReportView report={analysisReport} onDownload={onDownload} />);

    await user.click(screen.getByRole("button", { name: "JSON" }));
    expect(onDownload).toHaveBeenCalledOnce();

    await user.click(screen.getByRole("button", { name: "Clauses" }));
    expect(screen.getByRole("heading", { name: "Extracted clauses" })).toBeVisible();
    expect(screen.getByText("Provider may terminate in its sole discretion.")).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Audit" }));
    expect(screen.getByText(analysisReport.document_id)).toBeVisible();
    expect(screen.getByText("Findings require qualified legal review.")).toBeVisible();
  });

  it("collapses an expanded finding and reports an empty filter", async () => {
    const user = userEvent.setup();
    render(<AnalysisReportView report={analysisReport} onDownload={vi.fn()} />);

    const finding = screen.getByRole("button", { name: /Risky Language/i });
    expect(finding).toHaveAttribute("aria-expanded", "true");
    await user.click(finding);
    expect(finding).toHaveAttribute("aria-expanded", "false");

    await user.click(screen.getByRole("button", { name: "Low" }));
    expect(screen.getByText("No matching findings")).toBeVisible();
  });
});
