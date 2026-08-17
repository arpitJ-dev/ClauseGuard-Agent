import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { comparisonReport } from "../test/fixtures";
import { ComparisonReportView } from "./ComparisonReportView";

describe("ComparisonReportView", () => {
  it("shows risk signals and version deltas", () => {
    render(<ComparisonReportView report={comparisonReport} onDownload={vi.fn()} />);
    expect(screen.getByText("New Risk Term")).toBeVisible();
    expect(screen.getByText("Payment is due immediately on demand.")).toBeVisible();
  });

  it("filters clause changes", async () => {
    const user = userEvent.setup();
    render(<ComparisonReportView report={comparisonReport} onDownload={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: "Unchanged" }));
    expect(screen.getByText("Notices")).toBeVisible();
    expect(screen.queryByText("Payment is due immediately on demand.")).not.toBeInTheDocument();
  });
});
