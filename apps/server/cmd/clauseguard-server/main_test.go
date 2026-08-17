package main

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestRunStartsAndShutsDown(t *testing.T) {
	workspace := t.TempDir()
	writeTestFile(t, filepath.Join(workspace, "pyproject.toml"), "[project]\n")
	if err := os.Mkdir(filepath.Join(workspace, "clauseguard"), 0o750); err != nil {
		t.Fatal(err)
	}
	webDir := filepath.Join(workspace, "apps", "web", "dist")
	writeTestFile(t, filepath.Join(webDir, "index.html"), "<main>ClauseGuard</main>")

	t.Setenv("CLAUSEGUARD_WORKSPACE", workspace)
	t.Setenv("CLAUSEGUARD_DATA_DIR", filepath.Join(workspace, ".runtime-test"))
	t.Setenv("CLAUSEGUARD_WEB_DIR", webDir)
	t.Setenv("CLAUSEGUARD_SERVER_ADDR", "127.0.0.1:0")
	t.Setenv("CLAUSEGUARD_MOCK_MODELS", "true")

	runContext, cancel := context.WithCancel(context.Background())
	result := make(chan error, 1)
	go func() {
		result <- run(runContext)
	}()

	time.Sleep(100 * time.Millisecond)
	cancel()
	select {
	case err := <-result:
		if err != nil {
			t.Fatalf("server shutdown failed: %v", err)
		}
	case <-time.After(10 * time.Second):
		t.Fatal("server did not stop after cancellation")
	}
}

func TestRunFailsClearlyWithoutWebBundle(t *testing.T) {
	workspace := t.TempDir()
	writeTestFile(t, filepath.Join(workspace, "pyproject.toml"), "[project]\n")
	if err := os.Mkdir(filepath.Join(workspace, "clauseguard"), 0o750); err != nil {
		t.Fatal(err)
	}
	t.Setenv("CLAUSEGUARD_WORKSPACE", workspace)
	t.Setenv("CLAUSEGUARD_DATA_DIR", filepath.Join(workspace, ".runtime-test"))
	t.Setenv("CLAUSEGUARD_WEB_DIR", filepath.Join(workspace, "missing-web"))
	t.Setenv("CLAUSEGUARD_SERVER_ADDR", "127.0.0.1:0")

	err := run(context.Background())
	if err == nil {
		t.Fatal("server started without a web bundle")
	}
}

func TestRunCleansUpAfterListenFailure(t *testing.T) {
	workspace := t.TempDir()
	writeTestFile(t, filepath.Join(workspace, "pyproject.toml"), "[project]\n")
	if err := os.Mkdir(filepath.Join(workspace, "clauseguard"), 0o750); err != nil {
		t.Fatal(err)
	}
	webDir := filepath.Join(workspace, "apps", "web", "dist")
	writeTestFile(t, filepath.Join(webDir, "index.html"), "<main>ClauseGuard</main>")

	t.Setenv("CLAUSEGUARD_WORKSPACE", workspace)
	t.Setenv("CLAUSEGUARD_DATA_DIR", filepath.Join(workspace, ".runtime-test"))
	t.Setenv("CLAUSEGUARD_WEB_DIR", webDir)
	t.Setenv("CLAUSEGUARD_SERVER_ADDR", "127.0.0.1:-1")
	t.Setenv("CLAUSEGUARD_MOCK_MODELS", "true")

	err := run(context.Background())
	if err == nil || !strings.Contains(err.Error(), "invalid port") {
		t.Fatalf("expected a listen error, got %v", err)
	}
}

func writeTestFile(t *testing.T, path, content string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o750); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte(content), 0o600); err != nil {
		t.Fatal(err)
	}
}
