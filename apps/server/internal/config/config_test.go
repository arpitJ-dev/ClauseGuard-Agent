package config

import (
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestLoadUsesValidatedEnvironment(t *testing.T) {
	workspace := t.TempDir()
	if err := os.WriteFile(filepath.Join(workspace, "pyproject.toml"), []byte("[project]\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.Mkdir(filepath.Join(workspace, "clauseguard"), 0o750); err != nil {
		t.Fatal(err)
	}
	dataDir := filepath.Join(t.TempDir(), "runtime")
	t.Setenv("CLAUSEGUARD_WORKSPACE", workspace)
	t.Setenv("CLAUSEGUARD_DATA_DIR", dataDir)
	t.Setenv("CLAUSEGUARD_WEB_DIR", "web-build")
	t.Setenv("CLAUSEGUARD_PYTHON", "python-test")
	t.Setenv("CLAUSEGUARD_SERVER_ADDR", "127.0.0.1:9000")
	t.Setenv("CLAUSEGUARD_MAX_UPLOAD_BYTES", "4096")
	t.Setenv("CLAUSEGUARD_JOB_TIMEOUT", "45s")
	t.Setenv("CLAUSEGUARD_MAX_CONCURRENT_JOBS", "3")
	t.Setenv("CLAUSEGUARD_MAX_ACTIVE_JOBS", "8")
	t.Setenv("CLAUSEGUARD_MOCK_MODELS", "false")
	t.Setenv("CLAUSEGUARD_ALLOWED_ORIGIN", "http://localhost:5173")

	loaded, err := Load()
	if err != nil {
		t.Fatal(err)
	}
	if loaded.Workspace != workspace || loaded.DataDir != dataDir {
		t.Fatalf("unexpected paths: %+v", loaded)
	}
	if loaded.WebDir != filepath.Join(workspace, "web-build") {
		t.Fatalf("unexpected web directory: %q", loaded.WebDir)
	}
	if loaded.PythonExecutable != "python-test" || loaded.Address != "127.0.0.1:9000" {
		t.Fatalf("unexpected process configuration: %+v", loaded)
	}
	if loaded.MaxUploadBytes != 4096 || loaded.JobTimeout != 45*time.Second || loaded.MaxConcurrentJobs != 3 || loaded.MaxActiveJobs != 8 {
		t.Fatalf("unexpected limits: %+v", loaded)
	}
	if loaded.MockModels || loaded.AllowedOrigin != "http://localhost:5173" {
		t.Fatalf("unexpected runtime mode: %+v", loaded)
	}
}

func TestLoadRejectsActiveLimitBelowConcurrency(t *testing.T) {
	workspace := t.TempDir()
	if err := os.WriteFile(filepath.Join(workspace, "pyproject.toml"), nil, 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.Mkdir(filepath.Join(workspace, "clauseguard"), 0o750); err != nil {
		t.Fatal(err)
	}
	t.Setenv("CLAUSEGUARD_WORKSPACE", workspace)
	t.Setenv("CLAUSEGUARD_MAX_CONCURRENT_JOBS", "3")
	t.Setenv("CLAUSEGUARD_MAX_ACTIVE_JOBS", "2")
	if _, err := Load(); err == nil {
		t.Fatal("active limit below concurrency was accepted")
	}
}

func TestLoadRejectsInvalidLimits(t *testing.T) {
	workspace := t.TempDir()
	if err := os.WriteFile(filepath.Join(workspace, "pyproject.toml"), nil, 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.Mkdir(filepath.Join(workspace, "clauseguard"), 0o750); err != nil {
		t.Fatal(err)
	}
	t.Setenv("CLAUSEGUARD_WORKSPACE", workspace)
	t.Setenv("CLAUSEGUARD_MAX_CONCURRENT_JOBS", "0")
	if _, err := Load(); err == nil {
		t.Fatal("invalid concurrency limit was accepted")
	}
}

func TestLoadResolvesRelativeDataDirectoryFromWorkspace(t *testing.T) {
	workspace := t.TempDir()
	if err := os.WriteFile(filepath.Join(workspace, "pyproject.toml"), nil, 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.Mkdir(filepath.Join(workspace, "clauseguard"), 0o750); err != nil {
		t.Fatal(err)
	}
	t.Setenv("CLAUSEGUARD_WORKSPACE", workspace)
	t.Setenv("CLAUSEGUARD_DATA_DIR", ".runtime")
	loaded, err := Load()
	if err != nil {
		t.Fatal(err)
	}
	if loaded.DataDir != filepath.Join(workspace, ".runtime") {
		t.Fatalf("relative data directory resolved to %q", loaded.DataDir)
	}
}

func TestLoadReadsWorkspaceDotEnvWithoutOverridingProcessEnvironment(t *testing.T) {
	workspace := t.TempDir()
	if err := os.WriteFile(filepath.Join(workspace, "pyproject.toml"), nil, 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.Mkdir(filepath.Join(workspace, "clauseguard"), 0o750); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(
		filepath.Join(workspace, ".env"),
		[]byte("CLAUSEGUARD_SERVER_ADDR=127.0.0.1:9123\nCLAUSEGUARD_MAX_CONCURRENT_JOBS=1\nCLAUSEGUARD_MAX_ACTIVE_JOBS=4\n"),
		0o600,
	); err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{
		"CLAUSEGUARD_SERVER_ADDR", "CLAUSEGUARD_MAX_CONCURRENT_JOBS", "CLAUSEGUARD_MAX_ACTIVE_JOBS",
	} {
		unsetForTest(t, name)
	}
	t.Setenv("CLAUSEGUARD_WORKSPACE", workspace)
	t.Setenv("CLAUSEGUARD_SERVER_ADDR", "127.0.0.1:9222")
	loaded, err := Load()
	if err != nil {
		t.Fatal(err)
	}
	if loaded.Address != "127.0.0.1:9222" {
		t.Fatalf(".env overrode process environment: %q", loaded.Address)
	}
	if loaded.MaxConcurrentJobs != 1 || loaded.MaxActiveJobs != 4 {
		t.Fatalf(".env limits were not loaded: %+v", loaded)
	}
}

func unsetForTest(t *testing.T, name string) {
	t.Helper()
	original, existed := os.LookupEnv(name)
	if err := os.Unsetenv(name); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if existed {
			_ = os.Setenv(name, original)
		} else {
			_ = os.Unsetenv(name)
		}
	})
}
