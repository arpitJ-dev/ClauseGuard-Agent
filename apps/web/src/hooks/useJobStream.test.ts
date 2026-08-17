import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { completedAnalysisJob } from "../test/fixtures";

const apiMocks = vi.hoisted(() => ({
  getJob: vi.fn(),
}));

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, getJob: apiMocks.getJob };
});

import { useJobStream } from "./useJobStream";

type EventHandler = (event: Event) => void;

class FakeEventSource {
  static instances: FakeEventSource[] = [];

  readonly url: string;
  readonly close = vi.fn();
  private readonly handlers = new Map<string, EventHandler[]>();

  constructor(url: string | URL) {
    this.url = String(url);
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, handler: EventListenerOrEventListenerObject): void {
    const callback =
      typeof handler === "function" ? handler : (event: Event) => handler.handleEvent(event);
    this.handlers.set(type, [...(this.handlers.get(type) ?? []), callback]);
  }

  emit(type: string, data?: string): void {
    const event = data === undefined ? new Event(type) : new MessageEvent(type, { data });
    this.handlers.get(type)?.forEach((handler) => handler(event));
  }
}

beforeEach(() => {
  vi.clearAllMocks();
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
});

describe("useJobStream", () => {
  it("does not connect without an active job", () => {
    renderHook(() =>
      useJobStream({
        jobId: null,
        active: false,
        onJob: vi.fn(),
        onConnectionChange: vi.fn(),
      }),
    );

    expect(FakeEventSource.instances).toHaveLength(0);
  });

  it("accepts server events and closes after a terminal update", () => {
    const onJob = vi.fn();
    const onConnectionChange = vi.fn();
    renderHook(() =>
      useJobStream({
        jobId: completedAnalysisJob.id,
        active: true,
        onJob,
        onConnectionChange,
      }),
    );

    const source = FakeEventSource.instances[0]!;
    expect(source.url).toContain(`/api/v1/jobs/${completedAnalysisJob.id}/events`);

    act(() => source.emit("open"));
    expect(onConnectionChange).toHaveBeenCalledWith(true);

    act(() => source.emit("job", JSON.stringify(completedAnalysisJob)));
    expect(onJob).toHaveBeenCalledWith(completedAnalysisJob);
    expect(source.close).toHaveBeenCalledOnce();
    expect(onConnectionChange).toHaveBeenLastCalledWith(false);
  });

  it("falls back to polling when the event stream fails", async () => {
    const runningJob = { ...completedAnalysisJob, status: "running" as const, progress: 40 };
    apiMocks.getJob.mockResolvedValue(runningJob);
    const onJob = vi.fn();
    const onConnectionChange = vi.fn();
    const { unmount } = renderHook(() =>
      useJobStream({
        jobId: runningJob.id,
        active: true,
        onJob,
        onConnectionChange,
      }),
    );

    act(() => FakeEventSource.instances[0]!.emit("error"));

    await waitFor(() => expect(apiMocks.getJob).toHaveBeenCalledWith(runningJob.id));
    expect(onJob).toHaveBeenCalledWith(runningJob);
    expect(onConnectionChange).toHaveBeenCalledWith(false);

    unmount();
    expect(FakeEventSource.instances[0]!.close).toHaveBeenCalled();
  });

  it("uses polling for malformed events and reports polling errors", async () => {
    apiMocks.getJob.mockRejectedValue(new Error("offline"));
    const onConnectionChange = vi.fn();
    renderHook(() =>
      useJobStream({
        jobId: completedAnalysisJob.id,
        active: true,
        onJob: vi.fn(),
        onConnectionChange,
      }),
    );

    act(() => FakeEventSource.instances[0]!.emit("job", "not-json"));

    await waitFor(() => expect(apiMocks.getJob).toHaveBeenCalledOnce());
    expect(onConnectionChange).toHaveBeenCalledWith(false);
  });

  it("polls when EventSource construction is unavailable", async () => {
    apiMocks.getJob.mockResolvedValue(completedAnalysisJob);
    vi.stubGlobal(
      "EventSource",
      class {
        constructor() {
          throw new Error("unsupported");
        }
      },
    );
    const onJob = vi.fn();

    renderHook(() =>
      useJobStream({
        jobId: completedAnalysisJob.id,
        active: true,
        onJob,
        onConnectionChange: vi.fn(),
      }),
    );

    await waitFor(() => expect(onJob).toHaveBeenCalledWith(completedAnalysisJob));
  });
});
