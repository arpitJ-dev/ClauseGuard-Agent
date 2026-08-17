package api_test

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/arpitJ-dev/ClauseGuard-Agent/apps/server/internal/api"
	"github.com/arpitJ-dev/ClauseGuard-Agent/apps/server/internal/domain"
	"github.com/arpitJ-dev/ClauseGuard-Agent/apps/server/internal/engine"
	"github.com/arpitJ-dev/ClauseGuard-Agent/apps/server/internal/jobs"
	"github.com/arpitJ-dev/ClauseGuard-Agent/apps/server/internal/store"
)

func TestHTTPControlPlaneWithRealPythonBridge(t *testing.T) {
	python := os.Getenv("CLAUSEGUARD_INTEGRATION_PYTHON")
	workspace := os.Getenv("CLAUSEGUARD_INTEGRATION_WORKSPACE")
	if python == "" || workspace == "" {
		t.Skip("set CLAUSEGUARD_INTEGRATION_PYTHON and CLAUSEGUARD_INTEGRATION_WORKSPACE")
	}

	dataDir := t.TempDir()
	repository, err := store.Open(filepath.Join(dataDir, "jobs.db"))
	if err != nil {
		t.Fatal(err)
	}
	runner := &engine.CLIRunner{PythonExecutable: python, Workspace: workspace, MockModels: true}
	manager, err := jobs.New(repository, runner, jobs.Options{
		Timeout:           30 * time.Second,
		MaxConcurrentJobs: 1,
		MaxActiveJobs:     4,
		DataDir:           dataDir,
	})
	if err != nil {
		t.Fatal(err)
	}
	handler, err := api.New(manager, api.Config{DataDir: dataDir, MaxUploadBytes: 1 << 20})
	if err != nil {
		t.Fatal(err)
	}
	server := httptest.NewServer(handler)
	t.Cleanup(func() {
		server.Close()
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_ = manager.Shutdown(ctx)
		_ = repository.Close()
	})

	healthResponse, err := http.Get(server.URL + "/api/v1/health")
	if err != nil {
		t.Fatal(err)
	}
	_ = healthResponse.Body.Close()
	if healthResponse.StatusCode != http.StatusOK {
		t.Fatalf("health check returned %d", healthResponse.StatusCode)
	}

	analysisID := submitJob(t, server.URL+"/api/v1/analyses", map[string]testUpload{
		"document": {
			name: "agreement.txt",
			content: "SERVICE AGREEMENT\n1. Payment is due within 30 days.\n" +
				"2. Either party may terminate with written notice.",
		},
	})
	analysis := awaitHTTPJob(t, server.URL, analysisID)
	assertReport(t, server.URL, analysis, map[string]string{
		"schema_version": "1.0",
		"file_path":      "agreement.txt",
	})

	comparisonID := submitJob(t, server.URL+"/api/v1/comparisons", map[string]testUpload{
		"original": {name: "original.txt", content: "SERVICE AGREEMENT\n1. Payment is due within 30 days."},
		"modified": {name: "modified.txt", content: "SERVICE AGREEMENT\n1. Payment is due within 10 days."},
	})
	comparison := awaitHTTPJob(t, server.URL, comparisonID)
	assertReport(t, server.URL, comparison, map[string]string{
		"schema_version":    "1.0",
		"original_document": "original.txt",
		"modified_document": "modified.txt",
	})
	if _, err := os.Stat(filepath.Join(dataDir, "jobs", comparisonID, "output", "comparison_report.md")); !os.IsNotExist(err) {
		t.Fatalf("control-plane comparison wrote an unexpected Markdown artifact: %v", err)
	}
}

type testUpload struct {
	name    string
	content string
}

func submitJob(t *testing.T, endpoint string, uploads map[string]testUpload) string {
	t.Helper()
	var body bytes.Buffer
	writer := multipart.NewWriter(&body)
	for field, upload := range uploads {
		part, err := writer.CreateFormFile(field, upload.name)
		if err != nil {
			t.Fatal(err)
		}
		if _, err := part.Write([]byte(upload.content)); err != nil {
			t.Fatal(err)
		}
	}
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
	request, err := http.NewRequest(http.MethodPost, endpoint, &body)
	if err != nil {
		t.Fatal(err)
	}
	request.Header.Set("Content-Type", writer.FormDataContentType())
	response, err := http.DefaultClient.Do(request)
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	payload, err := io.ReadAll(response.Body)
	if err != nil {
		t.Fatal(err)
	}
	if response.StatusCode != http.StatusAccepted {
		t.Fatalf("submit returned %d: %s", response.StatusCode, payload)
	}
	var envelope struct {
		Job domain.Job `json:"job"`
	}
	if err := json.Unmarshal(payload, &envelope); err != nil {
		t.Fatal(err)
	}
	if envelope.Job.ID == "" {
		t.Fatal("submit response did not include a job ID")
	}
	return envelope.Job.ID
}

func awaitHTTPJob(t *testing.T, serverURL, id string) domain.Job {
	t.Helper()
	deadline := time.Now().Add(20 * time.Second)
	for time.Now().Before(deadline) {
		response, err := http.Get(serverURL + "/api/v1/jobs/" + id)
		if err != nil {
			t.Fatal(err)
		}
		var envelope struct {
			Job domain.Job `json:"job"`
		}
		decodeError := json.NewDecoder(response.Body).Decode(&envelope)
		_ = response.Body.Close()
		if response.StatusCode != http.StatusOK || decodeError != nil {
			t.Fatalf("job status failed: HTTP %d, decode=%v", response.StatusCode, decodeError)
		}
		if envelope.Job.Status.Terminal() {
			if envelope.Job.Status != domain.JobCompleted {
				t.Fatalf("job failed: %+v", envelope.Job)
			}
			return envelope.Job
		}
		time.Sleep(50 * time.Millisecond)
	}
	t.Fatalf("job %s did not complete", id)
	return domain.Job{}
}

func assertReport(t *testing.T, serverURL string, job domain.Job, expected map[string]string) {
	t.Helper()
	if job.ReportURL == "" {
		t.Fatalf("completed job has no report URL: %+v", job)
	}
	response, err := http.Get(serverURL + job.ReportURL)
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		t.Fatalf("report returned %d", response.StatusCode)
	}
	var report map[string]any
	if err := json.NewDecoder(response.Body).Decode(&report); err != nil {
		t.Fatal(err)
	}
	for field, want := range expected {
		if got := fmt.Sprint(report[field]); got != want {
			t.Fatalf("report field %s is %q, want %q", field, got, want)
		}
	}
}
