import { afterEach, describe, expect, it, vi } from "vitest";

import {
  deleteJob,
  getHealth,
  getJob,
  getReport,
  jobEventsURL,
  listJobs,
  submitAnalysis,
  submitComparison,
} from "./client";
import { completedAnalysisJob } from "../test/fixtures";
import { analysisReport } from "../test/fixtures";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("API client", () => {
  it("lists jobs", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ jobs: [completedAnalysisJob] }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(listJobs()).resolves.toEqual([completedAnalysisJob]);
  });

  it("preserves a structured API error and retry delay", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ error: { code: "queue_full", message: "Queue full" } }), {
          status: 429,
          headers: { "Retry-After": "8" },
        }),
      ),
    );

    await expect(listJobs()).rejects.toMatchObject({
      code: "queue_full",
      status: 429,
      retryAfter: 8,
    });
  });

  it("returns dependency health for a 503 response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ status: "unavailable", engine: { ready: false } }), {
          status: 503,
        }),
      ),
    );

    await expect(getHealth()).resolves.toEqual({ status: "unavailable", engine: { ready: false } });
  });

  it("submits an analysis as multipart form data", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          job: completedAnalysisJob,
          links: { self: "/job", events: "/events" },
        }),
        { status: 202 },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    const file = new File(["Agreement"], "agreement.txt", { type: "text/plain" });

    await submitAnalysis(file);

    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(init.method).toBe("POST");
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.body as FormData).get("document")).toBe(file);
  });

  it("reads job state and reports", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ job: completedAnalysisJob }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(analysisReport), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(getJob(completedAnalysisJob.id)).resolves.toEqual(completedAnalysisJob);
    await expect(getReport(completedAnalysisJob.id)).resolves.toEqual(analysisReport);
    expect(jobEventsURL(completedAnalysisJob.id)).toContain(`${completedAnalysisJob.id}/events`);
  });

  it("submits comparisons and deletes jobs", async () => {
    const response = { job: completedAnalysisJob, links: { self: "/job", events: "/events" } };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(response), { status: 202 }))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ job: completedAnalysisJob, deleted: true }), { status: 200 }),
      );
    vi.stubGlobal("fetch", fetchMock);
    const original = new File(["before"], "before.txt");
    const modified = new File(["after"], "after.txt");

    await submitComparison(original, modified);
    const comparisonBody = fetchMock.mock.calls[0]?.[1]?.body as FormData;
    expect(comparisonBody.get("original")).toBe(original);
    expect(comparisonBody.get("modified")).toBe(modified);
    await expect(deleteJob(completedAnalysisJob.id)).resolves.toMatchObject({ deleted: true });
  });
});
