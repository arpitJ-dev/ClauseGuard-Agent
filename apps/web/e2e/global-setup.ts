import { spawn, spawnSync, type ChildProcess } from "node:child_process";
import { existsSync, mkdirSync, rmSync } from "node:fs";
import { join, resolve } from "node:path";

const address = "127.0.0.1:18080";
const healthURL = `http://${address}/api/v1/health`;

function goExecutable(): string {
  const candidates = ["go"];
  if (process.env.GOROOT) {
    candidates.unshift(join(process.env.GOROOT, "bin", process.platform === "win32" ? "go.exe" : "go"));
  }
  if (process.platform === "win32" && process.env.ProgramFiles) {
    candidates.unshift(join(process.env.ProgramFiles, "Go", "bin", "go.exe"));
  }

  for (const candidate of candidates) {
    if (candidate !== "go" && !existsSync(candidate)) {
      continue;
    }
    const probe = spawnSync(candidate, ["version"], { encoding: "utf8" });
    if (!probe.error && probe.status === 0) {
      return candidate;
    }
  }
  throw new Error("Go is required to run the full-stack browser tests.");
}

function waitForExit(process: ChildProcess, timeoutMs: number): Promise<boolean> {
  if (process.exitCode !== null) {
    return Promise.resolve(true);
  }

  return new Promise((resolveExit) => {
    const timeout = setTimeout(() => resolveExit(false), timeoutMs);
    process.once("exit", () => {
      clearTimeout(timeout);
      resolveExit(true);
    });
  });
}

async function waitForHealth(process: ChildProcess): Promise<void> {
  const deadline = Date.now() + 60_000;
  while (Date.now() < deadline) {
    if (process.exitCode !== null) {
      throw new Error(`ClauseGuard server exited during startup (${process.exitCode}).`);
    }
    try {
      const response = await fetch(healthURL, { signal: AbortSignal.timeout(1_000) });
      if (response.ok) {
        return;
      }
    } catch {
      // The socket is expected to reject connections until the server is ready.
    }
    await new Promise((resolveWait) => setTimeout(resolveWait, 200));
  }
  throw new Error(`ClauseGuard server did not become healthy at ${healthURL}.`);
}

export default async function globalSetup(): Promise<() => Promise<void>> {
  const root = resolve(import.meta.dirname, "../../..");
  const serverDir = resolve(root, "apps/server");
  const runtimeDir = resolve(root, "apps/web/.runtime-e2e");
  const dataDir = resolve(runtimeDir, "data");
  const serverBinary = resolve(
    runtimeDir,
    process.platform === "win32" ? "clauseguard-server.exe" : "clauseguard-server",
  );

  rmSync(runtimeDir, { recursive: true, force: true });
  mkdirSync(dataDir, { recursive: true });

  const build = spawnSync(
    goExecutable(),
    ["build", "-buildvcs=false", "-o", serverBinary, "./cmd/clauseguard-server"],
    {
      cwd: serverDir,
      encoding: "utf8",
    },
  );
  if (build.error || build.status !== 0) {
    const details = build.error?.message ?? `${build.stdout}\n${build.stderr}`;
    throw new Error(`Go server build failed:\n${details}`);
  }

  const server = spawn(serverBinary, [], {
    cwd: serverDir,
    env: {
      ...process.env,
      CLAUSEGUARD_DATA_DIR: dataDir,
      CLAUSEGUARD_MOCK_MODELS: "true",
      CLAUSEGUARD_SERVER_ADDR: address,
      CLAUSEGUARD_WEB_DIR: resolve(root, "apps/web/dist"),
      CLAUSEGUARD_WORKSPACE: root,
    },
    stdio: "inherit",
    windowsHide: true,
  });

  try {
    await waitForHealth(server);
  } catch (error) {
    server.kill();
    await waitForExit(server, 2_000);
    throw error;
  }

  return async () => {
    if (server.exitCode !== null) {
      return;
    }
    server.kill();
    if (!(await waitForExit(server, 5_000))) {
      server.kill("SIGKILL");
      if (!(await waitForExit(server, 2_000))) {
        throw new Error("ClauseGuard E2E server did not stop.");
      }
    }
  };
}
