package api

import (
	"bytes"
	"context"
	"encoding/json"
	"math"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/arpitJ-dev/ClauseGuard-Agent/apps/server/internal/domain"
	"github.com/arpitJ-dev/ClauseGuard-Agent/apps/server/internal/jobs"
	"github.com/arpitJ-dev/ClauseGuard-Agent/apps/server/internal/store"
)

const validJobID = "11111111111111111111111111111111"

type stubService struct {
	submitted domain.JobSpec
	job       domain.Job
	health    domain.Health
	submitErr error
	getError  error
	listError error
	deleteErr error
}

func (service *stubService) Submit(_ context.Context, spec domain.JobSpec) (domain.Job, error) {
	if service.submitErr != nil {
		return domain.Job{}, service.submitErr
	}
	service.submitted = spec
	now := time.Now().UTC()
	service.job = domain.Job{
		ID:        spec.ID,
		Type:      spec.Type,
		Status:    domain.JobQueued,
		Stage:     "queued",
		Message:   "Job accepted",
		Inputs:    spec.Inputs,
		OutputDir: spec.OutputDir,
		CreatedAt: now,
		UpdatedAt: now,
	}
	return service.job, nil
}

func (service *stubService) Get(context.Context, string) (domain.Job, error) {
	return service.job, service.getError
}

func (service *stubService) List(context.Context, int) ([]domain.Job, error) {
	return []domain.Job{service.job}, service.listError
}

func (service *stubService) Cancel(context.Context, string) (domain.Job, error) {
	service.job.Status = domain.JobCancelled
	return service.job, nil
}

func (service *stubService) Delete(context.Context, string) (domain.Job, bool, error) {
	return service.job, service.job.Status.Terminal(), service.deleteErr
}

func (service *stubService) Subscribe(context.Context, string) (<-chan domain.Job, func(), error) {
	updates := make(chan domain.Job, 1)
	updates <- service.job
	return updates, func() { close(updates) }, nil
}

func (service *stubService) Health(context.Context) (domain.Health, error) {
	return service.health, nil
}

func TestAnalysisUploadIsContainedAndPathIsPrivate(t *testing.T) {
	dataDir := t.TempDir()
	service := &stubService{health: domain.Health{Ready: true}}
	handler := testHandler(t, service, dataDir, 1<<20)
	request := multipartRequest(t, "/api/v1/analyses", map[string]upload{
		"document": {name: "client-contract.txt", content: "SERVICE AGREEMENT"},
	})
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusAccepted {
		t.Fatalf("unexpected status %d: %s", recorder.Code, recorder.Body.String())
	}
	if len(service.submitted.Inputs) != 1 {
		t.Fatalf("unexpected submitted spec: %+v", service.submitted)
	}
	input := service.submitted.Inputs[0]
	if filepath.Base(input.Path) != "document.txt" || !within(dataDir, input.Path) {
		t.Fatalf("upload was not safely contained: %+v", input)
	}
	payload, err := os.ReadFile(input.Path)
	if err != nil || string(payload) != "SERVICE AGREEMENT" {
		t.Fatalf("stored upload mismatch: %q, %v", payload, err)
	}
	if strings.Contains(recorder.Body.String(), dataDir) || strings.Contains(recorder.Body.String(), input.Path) {
		t.Fatal("response leaked an internal filesystem path")
	}
}

func TestUploadClientFilenameCannotInfluenceStoragePath(t *testing.T) {
	dataDir := t.TempDir()
	service := &stubService{health: domain.Health{Ready: true}}
	handler := testHandler(t, service, dataDir, 1<<20)
	request := multipartRequest(t, "/api/v1/analyses", map[string]upload{
		"document": {name: "../../outside.txt", content: "SERVICE AGREEMENT"},
	})
	recorder := httptest.NewRecorder()

	handler.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusAccepted {
		t.Fatalf("unexpected status %d: %s", recorder.Code, recorder.Body.String())
	}
	if len(service.submitted.Inputs) != 1 {
		t.Fatalf("unexpected submitted spec: %+v", service.submitted)
	}
	input := service.submitted.Inputs[0]
	if filepath.Base(input.Path) != "document.txt" || !within(dataDir, input.Path) {
		t.Fatalf("client filename influenced storage path: %+v", input)
	}
	if _, err := os.Stat(filepath.Join(dataDir, "outside.txt")); !os.IsNotExist(err) {
		t.Fatalf("upload escaped managed storage: %v", err)
	}
}

func TestUploadRejectsPathLikeMultipartField(t *testing.T) {
	dataDir := t.TempDir()
	service := &stubService{health: domain.Health{Ready: true}}
	handler := testHandler(t, service, dataDir, 1<<20)
	request := multipartRequest(t, "/api/v1/analyses", map[string]upload{
		"../document": {name: "contract.txt", content: "SERVICE AGREEMENT"},
	})
	recorder := httptest.NewRecorder()

	handler.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusBadRequest || !strings.Contains(recorder.Body.String(), "invalid_upload") {
		t.Fatalf("path-like multipart field returned %d: %s", recorder.Code, recorder.Body.String())
	}
}

func TestComparisonUploadPreservesSemanticOrder(t *testing.T) {
	dataDir := t.TempDir()
	service := &stubService{health: domain.Health{Ready: true}}
	handler := testHandler(t, service, dataDir, 1<<20)
	request := multipartRequest(t, "/api/v1/comparisons", map[string]upload{
		"modified": {name: "new.txt", content: "new"},
		"original": {name: "old.txt", content: "old"},
	})
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusAccepted {
		t.Fatalf("unexpected status %d: %s", recorder.Code, recorder.Body.String())
	}
	if service.submitted.Inputs[0].Name != "old.txt" || service.submitted.Inputs[1].Name != "new.txt" {
		t.Fatalf("comparison order changed: %+v", service.submitted.Inputs)
	}
}

func TestUploadLimitAppliesPerDocumentInsteadOfMultipartEnvelope(t *testing.T) {
	const perFileLimit = int64(16)
	service := &stubService{health: domain.Health{Ready: true}}
	handler := testHandler(t, service, t.TempDir(), perFileLimit)
	request := multipartRequest(t, "/api/v1/comparisons", map[string]upload{
		"original": {name: "old.txt", content: strings.Repeat("o", int(perFileLimit))},
		"modified": {name: "new.txt", content: strings.Repeat("n", int(perFileLimit))},
	})
	recorder := httptest.NewRecorder()

	handler.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusAccepted {
		t.Fatalf("two valid files were rejected by the multipart envelope: %d %s", recorder.Code, recorder.Body.String())
	}
}

func TestMultipartRequestLimitSaturatesWithoutOverflow(t *testing.T) {
	if got := multipartRequestLimit(math.MaxInt64, 2); got != math.MaxInt64 {
		t.Fatalf("multipart request limit overflowed: %d", got)
	}
}

func TestUploadRejectsUnsupportedAndOversizedFiles(t *testing.T) {
	for _, test := range []struct {
		name       string
		filename   string
		content    string
		limit      int64
		wantStatus int
	}{
		{name: "unsupported", filename: "contract.exe", content: "x", limit: 1 << 20, wantStatus: http.StatusUnsupportedMediaType},
		{name: "oversized", filename: "contract.txt", content: strings.Repeat("x", 1024), limit: 256, wantStatus: http.StatusRequestEntityTooLarge},
	} {
		t.Run(test.name, func(t *testing.T) {
			service := &stubService{health: domain.Health{Ready: true}}
			handler := testHandler(t, service, t.TempDir(), test.limit)
			request := multipartRequest(t, "/api/v1/analyses", map[string]upload{
				"document": {name: test.filename, content: test.content},
			})
			recorder := httptest.NewRecorder()
			handler.ServeHTTP(recorder, request)
			if recorder.Code != test.wantStatus {
				t.Fatalf("unexpected status %d: %s", recorder.Code, recorder.Body.String())
			}
		})
	}
}

func TestReportEndpointServesOnlyManagedCompletedReports(t *testing.T) {
	dataDir := t.TempDir()
	reportPath := filepath.Join(dataDir, "jobs", validJobID, "output", "analysis_report.json")
	if err := os.MkdirAll(filepath.Dir(reportPath), 0o750); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(reportPath, []byte(`{"schema_version":"1.0"}`), 0o600); err != nil {
		t.Fatal(err)
	}
	service := &stubService{
		health: domain.Health{Ready: true},
		job: domain.Job{
			ID:         validJobID,
			Status:     domain.JobCompleted,
			ReportPath: reportPath,
			UpdatedAt:  time.Now().UTC(),
		},
	}
	handler := testHandler(t, service, dataDir, 1<<20)
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, httptest.NewRequest(http.MethodGet, "/api/v1/jobs/"+validJobID+"/report", nil))
	if recorder.Code != http.StatusOK || !strings.Contains(recorder.Body.String(), "schema_version") {
		t.Fatalf("report not served: %d %s", recorder.Code, recorder.Body.String())
	}

	service.job.ReportPath = filepath.Join(t.TempDir(), "outside.json")
	recorder = httptest.NewRecorder()
	handler.ServeHTTP(recorder, httptest.NewRequest(http.MethodGet, "/api/v1/jobs/"+validJobID+"/report", nil))
	if recorder.Code != http.StatusInternalServerError {
		t.Fatalf("unsafe report path accepted: %d", recorder.Code)
	}
}

func TestSSEDeliversTerminalSnapshot(t *testing.T) {
	service := &stubService{
		health: domain.Health{Ready: true},
		job: domain.Job{
			ID:        validJobID,
			Status:    domain.JobCompleted,
			Stage:     "completed",
			Progress:  100,
			UpdatedAt: time.Now().UTC(),
		},
	}
	handler := testHandler(t, service, t.TempDir(), 1<<20)
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, httptest.NewRequest(http.MethodGet, "/api/v1/jobs/"+validJobID+"/events", nil))
	if recorder.Code != http.StatusOK || !strings.Contains(recorder.Body.String(), "event: job") || !strings.Contains(recorder.Body.String(), `"status":"completed"`) {
		t.Fatalf("unexpected SSE response: %d %s", recorder.Code, recorder.Body.String())
	}
}

func TestHealthReflectsEngineReadiness(t *testing.T) {
	service := &stubService{health: domain.Health{Ready: true}}
	handler := testHandler(t, service, t.TempDir(), 1<<20)
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, httptest.NewRequest(http.MethodGet, "/api/v1/health", nil))
	if recorder.Code != http.StatusOK {
		t.Fatalf("unexpected health status: %d", recorder.Code)
	}
	var payload map[string]any
	if err := json.Unmarshal(recorder.Body.Bytes(), &payload); err != nil || payload["status"] != "ok" {
		t.Fatalf("unexpected health payload: %s, %v", recorder.Body.String(), err)
	}
}

func TestDisplayNameRemovesClientPathFragments(t *testing.T) {
	if got := displayName(`C:\Users\candidate\contract.txt`); got != "contract.txt" {
		t.Fatalf("unexpected display name %q", got)
	}
}

func TestJobCollectionAndDeleteRoutes(t *testing.T) {
	now := time.Now().UTC()
	service := &stubService{
		health: domain.Health{Ready: true},
		job: domain.Job{
			ID: validJobID, Type: domain.JobTypeAnalysis, Status: domain.JobQueued,
			Stage: "queued", Inputs: []domain.InputFile{{Name: "contract.txt"}},
			CreatedAt: now, UpdatedAt: now,
		},
	}
	handler := testHandler(t, service, t.TempDir(), 1<<20)

	for _, route := range []string{"/api/v1/jobs", "/api/v1/jobs/" + validJobID} {
		recorder := httptest.NewRecorder()
		handler.ServeHTTP(recorder, httptest.NewRequest(http.MethodGet, route, nil))
		if recorder.Code != http.StatusOK {
			t.Fatalf("GET %s returned %d: %s", route, recorder.Code, recorder.Body.String())
		}
	}
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, httptest.NewRequest(http.MethodGet, "/api/v1/jobs?limit=0", nil))
	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("invalid list limit returned %d", recorder.Code)
	}

	recorder = httptest.NewRecorder()
	handler.ServeHTTP(recorder, httptest.NewRequest(http.MethodDelete, "/api/v1/jobs/"+validJobID, nil))
	if recorder.Code != http.StatusAccepted {
		t.Fatalf("active delete returned %d", recorder.Code)
	}
	service.job.Status = domain.JobCompleted
	recorder = httptest.NewRecorder()
	handler.ServeHTTP(recorder, httptest.NewRequest(http.MethodDelete, "/api/v1/jobs/"+validJobID, nil))
	if recorder.Code != http.StatusOK {
		t.Fatalf("terminal delete returned %d", recorder.Code)
	}
}

func TestNotFoundAndUnavailableRoutesUseTypedErrors(t *testing.T) {
	service := &stubService{
		health:   domain.Health{Ready: false, Error: "engine unavailable"},
		getError: store.ErrNotFound,
	}
	handler := testHandler(t, service, t.TempDir(), 1<<20)
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, httptest.NewRequest(http.MethodGet, "/api/v1/jobs/22222222222222222222222222222222", nil))
	if recorder.Code != http.StatusNotFound || !strings.Contains(recorder.Body.String(), "job_not_found") {
		t.Fatalf("unexpected not-found response: %d %s", recorder.Code, recorder.Body.String())
	}
	recorder = httptest.NewRecorder()
	handler.ServeHTTP(recorder, httptest.NewRequest(http.MethodGet, "/api/v1/health", nil))
	if recorder.Code != http.StatusServiceUnavailable {
		t.Fatalf("unready health returned %d", recorder.Code)
	}
}

func TestInvalidJobIDIsRejectedBeforeLookup(t *testing.T) {
	service := &stubService{health: domain.Health{Ready: true}}
	handler := testHandler(t, service, t.TempDir(), 1<<20)
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, httptest.NewRequest(http.MethodGet, "/api/v1/jobs/not-a-job-id", nil))
	if recorder.Code != http.StatusBadRequest || !strings.Contains(recorder.Body.String(), "invalid_job_id") {
		t.Fatalf("unexpected invalid-ID response: %d %s", recorder.Code, recorder.Body.String())
	}
}

func TestConfiguredCORSPreflight(t *testing.T) {
	service := &stubService{health: domain.Health{Ready: true}}
	handler, err := New(service, Config{
		DataDir: t.TempDir(), MaxUploadBytes: 1 << 20, AllowedOrigin: "http://localhost:5173",
	})
	if err != nil {
		t.Fatal(err)
	}
	request := httptest.NewRequest(http.MethodOptions, "/api/v1/analyses", nil)
	request.Header.Set("Origin", "http://localhost:5173")
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusNoContent || recorder.Header().Get("Access-Control-Allow-Origin") == "" {
		t.Fatalf("unexpected preflight response: %d %+v", recorder.Code, recorder.Header())
	}
}

func TestCrossOriginRequestIsRejected(t *testing.T) {
	service := &stubService{health: domain.Health{Ready: true}}
	handler := testHandler(t, service, t.TempDir(), 1<<20)
	request := httptest.NewRequest(http.MethodGet, "/api/v1/health", nil)
	request.Header.Set("Origin", "https://untrusted.example")
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusForbidden || !strings.Contains(recorder.Body.String(), "origin_not_allowed") {
		t.Fatalf("cross-origin request was not rejected: %d %s", recorder.Code, recorder.Body.String())
	}
}

func TestAPIResponsesArePrivateAndBrowserHeadersArePresent(t *testing.T) {
	service := &stubService{health: domain.Health{Ready: true}}
	handler := testHandler(t, service, t.TempDir(), 1<<20)
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, httptest.NewRequest(http.MethodGet, "/api/v1/health", nil))

	if recorder.Header().Get("Cache-Control") != "no-store" {
		t.Fatalf("API response was cacheable: %+v", recorder.Header())
	}
	for _, header := range []string{
		"Content-Security-Policy",
		"Cross-Origin-Opener-Policy",
		"Cross-Origin-Resource-Policy",
		"Permissions-Policy",
		"X-Content-Type-Options",
	} {
		if recorder.Header().Get(header) == "" {
			t.Fatalf("API response omitted %s", header)
		}
	}
}

func TestFullQueueReturnsRetryableStatus(t *testing.T) {
	service := &stubService{health: domain.Health{Ready: true}, submitErr: jobs.ErrCapacity}
	handler := testHandler(t, service, t.TempDir(), 1<<20)
	request := multipartRequest(t, "/api/v1/analyses", map[string]upload{
		"document": {name: "contract.txt", content: "Agreement"},
	})
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusTooManyRequests || recorder.Header().Get("Retry-After") == "" {
		t.Fatalf("unexpected capacity response: %d %s", recorder.Code, recorder.Body.String())
	}
}

func TestShuttingDownReturnsUnavailable(t *testing.T) {
	service := &stubService{health: domain.Health{Ready: true}, submitErr: jobs.ErrShuttingDown}
	handler := testHandler(t, service, t.TempDir(), 1<<20)
	request := multipartRequest(t, "/api/v1/analyses", map[string]upload{
		"document": {name: "contract.txt", content: "Agreement"},
	})
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusServiceUnavailable || !strings.Contains(recorder.Body.String(), "server_shutting_down") {
		t.Fatalf("unexpected shutdown response: %d %s", recorder.Code, recorder.Body.String())
	}
}

func TestWebBundleAndSPARoutesAreServed(t *testing.T) {
	webDir := t.TempDir()
	if err := os.Mkdir(filepath.Join(webDir, "assets"), 0o750); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(webDir, "index.html"), []byte("<main>ClauseGuard</main>"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(webDir, "assets", "app.js"), []byte("console.log('ready')"), 0o600); err != nil {
		t.Fatal(err)
	}
	service := &stubService{health: domain.Health{Ready: true}}
	handler, err := New(service, Config{DataDir: t.TempDir(), WebDir: webDir, MaxUploadBytes: 1 << 20})
	if err != nil {
		t.Fatal(err)
	}

	for _, route := range []string{"/", "/reviews/current"} {
		recorder := httptest.NewRecorder()
		handler.ServeHTTP(recorder, httptest.NewRequest(http.MethodGet, route, nil))
		if recorder.Code != http.StatusOK || !strings.Contains(recorder.Body.String(), "ClauseGuard") {
			t.Fatalf("SPA route %s returned %d: %s", route, recorder.Code, recorder.Body.String())
		}
		if recorder.Header().Get("Content-Security-Policy") == "" {
			t.Fatalf("SPA route %s omitted browser security headers", route)
		}
	}

	asset := httptest.NewRecorder()
	handler.ServeHTTP(asset, httptest.NewRequest(http.MethodGet, "/assets/app.js", nil))
	if asset.Code != http.StatusOK || asset.Header().Get("Cache-Control") != "public, max-age=31536000, immutable" {
		t.Fatalf("asset was not served with immutable caching: %d %+v", asset.Code, asset.Header())
	}

	missingAsset := httptest.NewRecorder()
	handler.ServeHTTP(missingAsset, httptest.NewRequest(http.MethodGet, "/assets/missing.js", nil))
	if missingAsset.Code != http.StatusNotFound {
		t.Fatalf("missing asset returned %d", missingAsset.Code)
	}

	missingAPI := httptest.NewRecorder()
	handler.ServeHTTP(missingAPI, httptest.NewRequest(http.MethodGet, "/api/v1/missing", nil))
	if missingAPI.Code != http.StatusNotFound || !strings.Contains(missingAPI.Body.String(), "route_not_found") {
		t.Fatalf("unknown API route returned %d: %s", missingAPI.Code, missingAPI.Body.String())
	}
}

func TestWebBundleTraversalRequestsCannotReadOutsideFiles(t *testing.T) {
	rootDir := t.TempDir()
	webDir := filepath.Join(rootDir, "web")
	if err := os.Mkdir(webDir, 0o750); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(webDir, "index.html"), []byte("<main>ClauseGuard</main>"), 0o600); err != nil {
		t.Fatal(err)
	}
	const secret = "outside-web-root"
	if err := os.WriteFile(filepath.Join(rootDir, "secret.txt"), []byte(secret), 0o600); err != nil {
		t.Fatal(err)
	}
	assets, err := loadWebBundle(webDir)
	if err != nil {
		t.Fatal(err)
	}
	server := &Server{webAssets: assets}

	for _, route := range []string{
		"/../secret.txt",
		"/assets/../../secret.txt",
		"/..\\secret.txt",
		"//secret.txt",
	} {
		t.Run(route, func(t *testing.T) {
			request := httptest.NewRequest(http.MethodGet, "http://clauseguard.test/", nil)
			request.URL.Path = route
			recorder := httptest.NewRecorder()

			server.handleWeb(recorder, request)

			if recorder.Code == http.StatusOK || strings.Contains(recorder.Body.String(), secret) {
				t.Fatalf("traversal route %q exposed an outside file: %d %s", route, recorder.Code, recorder.Body.String())
			}
		})
	}
}

func TestWebBundleMustContainIndex(t *testing.T) {
	_, err := New(&stubService{}, Config{
		DataDir: t.TempDir(), WebDir: t.TempDir(), MaxUploadBytes: 1 << 20,
	})
	if err == nil || !strings.Contains(err.Error(), "web bundle not found") {
		t.Fatalf("missing web bundle returned %v", err)
	}
}

type upload struct {
	name    string
	content string
}

func multipartRequest(t *testing.T, path string, files map[string]upload) *http.Request {
	t.Helper()
	var body bytes.Buffer
	writer := multipart.NewWriter(&body)
	for field, file := range files {
		part, err := writer.CreateFormFile(field, file.name)
		if err != nil {
			t.Fatal(err)
		}
		if _, err := part.Write([]byte(file.content)); err != nil {
			t.Fatal(err)
		}
	}
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
	request := httptest.NewRequest(http.MethodPost, path, &body)
	request.Header.Set("Content-Type", writer.FormDataContentType())
	return request
}

func testHandler(t *testing.T, service JobService, dataDir string, maxUploadBytes int64) http.Handler {
	t.Helper()
	handler, err := New(service, Config{DataDir: dataDir, MaxUploadBytes: maxUploadBytes})
	if err != nil {
		t.Fatal(err)
	}
	return handler
}
