import { useEffect } from "react";

import { getJob, jobEventsURL } from "../api/client";
import type { Job } from "../api/types";
import { isTerminalStatus } from "../api/types";

interface JobStreamOptions {
  jobId: string | null;
  active: boolean;
  onJob: (job: Job) => void;
  onConnectionChange: (connected: boolean) => void;
}

export function useJobStream({
  jobId,
  active,
  onJob,
  onConnectionChange,
}: JobStreamOptions): void {
  useEffect(() => {
    if (!jobId || !active) return;

    let disposed = false;
    let pollingTimer: number | undefined;
    let source: EventSource | undefined;

    const stopPolling = () => {
      if (pollingTimer !== undefined) {
        window.clearInterval(pollingTimer);
        pollingTimer = undefined;
      }
    };

    const acceptJob = (job: Job) => {
      if (disposed) return;
      onJob(job);
      if (isTerminalStatus(job.status)) {
        stopPolling();
        source?.close();
        onConnectionChange(false);
      }
    };

    const poll = async () => {
      try {
        acceptJob(await getJob(jobId));
      } catch {
        onConnectionChange(false);
      }
    };

    const startPolling = () => {
      if (pollingTimer !== undefined || disposed) return;
      void poll();
      pollingTimer = window.setInterval(() => void poll(), 1500);
    };

    try {
      source = new EventSource(jobEventsURL(jobId));
      source.addEventListener("open", () => {
        if (!disposed) onConnectionChange(true);
      });
      source.addEventListener("job", (event) => {
        try {
          acceptJob(JSON.parse((event as MessageEvent<string>).data) as Job);
        } catch {
          source?.close();
          onConnectionChange(false);
          startPolling();
        }
      });
      source.addEventListener("error", () => {
        source?.close();
        onConnectionChange(false);
        startPolling();
      });
    } catch {
      startPolling();
    }

    return () => {
      disposed = true;
      source?.close();
      stopPolling();
      onConnectionChange(false);
    };
  }, [active, jobId, onConnectionChange, onJob]);
}
