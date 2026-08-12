import { describe, expect, it } from "vitest";

import { clampProgress, formatBytes, formatDate, formatScore, humanize } from "./format";

describe("format helpers", () => {
  it("humanizes identifiers", () => {
    expect(humanize("missing_governing-law")).toBe("Missing Governing Law");
  });

  it("formats byte ranges", () => {
    expect(formatBytes(15)).toBe("15 B");
    expect(formatBytes(2048)).toBe("2.0 KB");
    expect(formatBytes(2 * 1024 * 1024)).toBe("2.0 MB");
  });

  it("bounds scores and progress", () => {
    expect(formatScore(1.2)).toBe("100%");
    expect(formatScore(-1)).toBe("0%");
    expect(clampProgress(120)).toBe(100);
    expect(clampProgress(-5)).toBe(0);
  });

  it("handles invalid dates", () => {
    expect(formatDate("not-a-date")).toBe("Unknown time");
  });
});
