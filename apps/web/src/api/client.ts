import type {
  DeleteResponse,
  HealthResponse,
  Job,
  Report,
  SubmissionResponse,
} from "./types";

const configuredBase = import.meta.env.VITE_API_BASE_URL?.trim() ?? "";
export const apiBase = configuredBase.replace(/\/$/, "");

interface ErrorEnvelope {
  error?: {
    code?: string;
    message?: string;
  };
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly retryAfter?: number;

  constructor(status: number, code: string, message: string, retryAfter?: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.retryAfter = retryAfter;
  }
}

async function parseJSON<T>(response: Response): Promise<T> {
  let payload: T | ErrorEnvelope;
  try {
    payload = (await response.json()) as T | ErrorEnvelope;
  } catch {
    throw new ApiError(response.status, "invalid_response", "The server returned invalid JSON.");
  }
  if (!response.ok) {
    const envelope = payload as ErrorEnvelope;
    const retryHeader = response.headers.get("Retry-After");
    throw new ApiError(
      response.status,
      envelope.error?.code ?? "request_failed",
      envelope.error?.message ?? `Request failed with status ${response.status}.`,
      retryHeader ? Number.parseInt(retryHeader, 10) : undefined,
    );
  }
  return payload as T;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...init?.headers,
    },
  });
  return parseJSON<T>(response);
}

export async function getHealth(): Promise<HealthResponse> {
  const response = await fetch(`${apiBase}/api/v1/health`, {
    headers: { Accept: "application/json" },
  });
  if (response.status === 503) {
    return (await response.json()) as HealthResponse;
  }
  return parseJSON<HealthResponse>(response);
}

export async function listJobs(limit = 50): Promise<Job[]> {
  const payload = await request<{ jobs: Job[] }>(`/api/v1/jobs?limit=${limit}`);
  return payload.jobs;
}

export async function getJob(id: string): Promise<Job> {
  const payload = await request<{ job: Job }>(`/api/v1/jobs/${encodeURIComponent(id)}`);
  return payload.job;
}

export async function getReport(id: string): Promise<Report> {
  return request<Report>(`/api/v1/jobs/${encodeURIComponent(id)}/report`);
}

export async function submitAnalysis(file: File): Promise<SubmissionResponse> {
  const body = new FormData();
  body.append("document", file);
  return request<SubmissionResponse>("/api/v1/analyses", { method: "POST", body });
}

export async function submitComparison(
  original: File,
  modified: File,
): Promise<SubmissionResponse> {
  const body = new FormData();
  body.append("original", original);
  body.append("modified", modified);
  return request<SubmissionResponse>("/api/v1/comparisons", { method: "POST", body });
}

export async function deleteJob(id: string): Promise<DeleteResponse> {
  return request<DeleteResponse>(`/api/v1/jobs/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export function jobEventsURL(id: string): string {
  return `${apiBase}/api/v1/jobs/${encodeURIComponent(id)}/events`;
}
