package engine

import (
	"bytes"
	"context"
	"os"
	"path/filepath"
	"reflect"
	"testing"
	"time"

	"github.com/arpitJ-dev/ClauseGuard-Agent/apps/server/internal/domain"
)

func TestArgumentsKeepAnalysisInMockMode(t *testing.T) {
	runner := CLIRunner{MockModels: true}
	spec := domain.JobSpec{
		ID:        "job-1",
		Type:      domain.JobTypeAnalysis,
		Inputs:    []domain.InputFile{{Name: "contract.txt", Path: "contract.txt"}},
		OutputDir: "output",
	}
	want := []string{
		"-m", "clauseguard", "analyze", "contract.txt", "--output-dir", "output",
		"--format", "json", "--events-jsonl", "--run-id", "job-1", "--mock-models",
	}
	if got := runner.arguments(spec); !reflect.DeepEqual(got, want) {
		t.Fatalf("unexpected arguments:\n got: %#v\nwant: %#v", got, want)
	}
}

func TestArgumentsEnableRealComparisonOnlyWhenConfigured(t *testing.T) {
	runner := CLIRunner{MockModels: false}
	spec := domain.JobSpec{
		ID:   "job-2",
		Type: domain.JobTypeComparison,
		Inputs: []domain.InputFile{
			{Name: "original.txt", Path: "original.txt"},
			{Name: "modified.txt", Path: "modified.txt"},
		},
		OutputDir: "output",
	}
	arguments := runner.arguments(spec)
	if arguments[len(arguments)-1] != "--real-models" {
		t.Fatalf("real comparison flag missing: %#v", arguments)
	}
}

func TestValidateEventRejectsCorrelationAndSequenceErrors(t *testing.T) {
	valid := domain.EngineEvent{
		SchemaVersion: "1.0",
		RunID:         "job-1",
		Sequence:      1,
		Type:          "progress",
		Stage:         "loading",
		Status:        "started",
		Progress:      5,
		Timestamp:     "2026-08-11T12:00:00Z",
	}
	if err := validateEvent(valid, "job-1", 1); err != nil {
		t.Fatalf("valid event rejected: %v", err)
	}
	valid.RunID = "another-job"
	if err := validateEvent(valid, "job-1", 1); err == nil {
		t.Fatal("mismatched run ID accepted")
	}
	valid.RunID = "job-1"
	valid.Sequence = 3
	if err := validateEvent(valid, "job-1", 1); err == nil {
		t.Fatal("out-of-order event accepted")
	}
}

func TestValidateEventEnforcesTerminalShape(t *testing.T) {
	completed := domain.EngineEvent{
		SchemaVersion: "1.0", RunID: "job-1", Sequence: 2, Type: "completed",
		Stage: "completed", Status: "completed", Progress: 100,
		Timestamp: "2026-08-11T12:00:00Z",
	}
	if err := validateEvent(completed, "job-1", 2); err != nil {
		t.Fatalf("valid terminal event rejected: %v", err)
	}
	completed.Progress = 99
	if err := validateEvent(completed, "job-1", 2); err == nil {
		t.Fatal("incomplete terminal progress was accepted")
	}
	completed.Progress = 100
	completed.Type = "unexpected"
	if err := validateEvent(completed, "job-1", 2); err == nil {
		t.Fatal("unknown event type was accepted")
	}
}

func TestJSONReportPathSelectsJSONArtifact(t *testing.T) {
	details := map[string]any{
		"report_files": []any{"report.md", filepath.Join("output", "analysis_report.json")},
	}
	if got := jsonReportPath(details); filepath.Ext(got) != ".json" {
		t.Fatalf("JSON report not selected: %q", got)
	}
}

func TestLimitedBufferDrainsWithoutGrowingPastLimit(t *testing.T) {
	buffer := newLimitedBuffer(4)
	payload := []byte("abcdefgh")
	written, err := buffer.Write(payload)
	if err != nil || written != len(payload) {
		t.Fatalf("unexpected write result: %d, %v", written, err)
	}
	if got := buffer.String(); got != "abcd" {
		t.Fatalf("unexpected retained diagnostics: %q", got)
	}
}

func TestRunErrorPreservesMessageAndCause(t *testing.T) {
	cause := context.Canceled
	runError := &RunError{ExitCode: 130, Message: "cancelled by caller", Cause: cause}
	if runError.Error() != "cancelled by caller" || !reflect.DeepEqual(runError.Unwrap(), cause) {
		t.Fatalf("unexpected run error behavior: %+v", runError)
	}
	if fallback := (&RunError{Cause: cause}).Error(); fallback != cause.Error() {
		t.Fatalf("cause fallback was %q", fallback)
	}
	if fallback := (&RunError{}).Error(); fallback == "" {
		t.Fatal("empty run error has no fallback message")
	}
}

func TestExpectedReportPathUsesJobType(t *testing.T) {
	analysis := domain.JobSpec{Type: domain.JobTypeAnalysis, OutputDir: "output"}
	comparison := domain.JobSpec{Type: domain.JobTypeComparison, OutputDir: "output"}
	if got := filepath.Base(expectedReportPath(analysis)); got != "analysis_report.json" {
		t.Fatalf("unexpected analysis report name %q", got)
	}
	if got := filepath.Base(expectedReportPath(comparison)); got != "comparison_report.json" {
		t.Fatalf("unexpected comparison report name %q", got)
	}
}

func TestHealthUsesFreshCachedResult(t *testing.T) {
	runner := CLIRunner{
		PythonExecutable: "executable-that-must-not-run",
		HealthCacheTTL:   time.Hour,
		healthAt:         time.Now(),
		healthValue:      domain.Health{Ready: true},
	}
	if health := runner.Health(context.Background()); !health.Ready {
		t.Fatalf("fresh cached health was ignored: %+v", health)
	}
}

func TestSanitizeReportMetadataRemovesInternalPaths(t *testing.T) {
	root := t.TempDir()
	tests := []struct {
		name        string
		spec        domain.JobSpec
		report      string
		expectation map[string]string
	}{
		{
			name: "analysis",
			spec: domain.JobSpec{
				Type: domain.JobTypeAnalysis,
				Inputs: []domain.InputFile{{
					Name: "agreement.txt", Path: filepath.Join(root, "private", "document.txt"),
				}},
			},
			report:      `{"schema_version":"1.0","file_path":"C:\\private\\document.txt"}`,
			expectation: map[string]string{"file_path": "agreement.txt"},
		},
		{
			name: "comparison",
			spec: domain.JobSpec{
				Type: domain.JobTypeComparison,
				Inputs: []domain.InputFile{
					{Name: "before.txt", Path: filepath.Join(root, "private", "original.txt")},
					{Name: "after.txt", Path: filepath.Join(root, "private", "modified.txt")},
				},
			},
			report: `{"schema_version":"1.0","original_document":"private-original",` +
				`"modified_document":"private-modified"}`,
			expectation: map[string]string{
				"original_document": "before.txt", "modified_document": "after.txt",
			},
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			path := filepath.Join(root, test.name+".json")
			if err := os.WriteFile(path, []byte(test.report), 0o600); err != nil {
				t.Fatal(err)
			}
			if err := sanitizeReportMetadata(path, test.spec); err != nil {
				t.Fatal(err)
			}
			payload, err := os.ReadFile(path)
			if err != nil {
				t.Fatal(err)
			}
			for key, value := range test.expectation {
				fragment := `"` + key + `": "` + value + `"`
				if !bytes.Contains(payload, []byte(fragment)) {
					t.Fatalf("sanitized report missing %q: %s", fragment, payload)
				}
			}
			if bytes.Contains(payload, []byte("private")) {
				t.Fatalf("sanitized report retained an internal path: %s", payload)
			}
		})
	}
}

func TestCLIRunnerWithRealPythonBridge(t *testing.T) {
	python := os.Getenv("CLAUSEGUARD_INTEGRATION_PYTHON")
	workspace := os.Getenv("CLAUSEGUARD_INTEGRATION_WORKSPACE")
	if python == "" || workspace == "" {
		t.Skip("set CLAUSEGUARD_INTEGRATION_PYTHON and CLAUSEGUARD_INTEGRATION_WORKSPACE")
	}
	root := t.TempDir()
	document := filepath.Join(root, "contract.txt")
	if err := os.WriteFile(document, []byte("SERVICE AGREEMENT\n1. Payment is due within 30 days.\n2. Either party may terminate with notice."), 0o600); err != nil {
		t.Fatal(err)
	}
	spec := domain.JobSpec{
		ID:        "integration-job",
		Type:      domain.JobTypeAnalysis,
		Inputs:    []domain.InputFile{{Name: "contract.txt", Path: document}},
		OutputDir: filepath.Join(root, "output"),
	}
	runner := CLIRunner{PythonExecutable: python, Workspace: workspace, MockModels: true}
	if health := runner.Health(context.Background()); !health.Ready || len(health.Models) == 0 {
		t.Fatalf("Python bridge is not healthy: %+v", health)
	}
	var events []domain.EngineEvent
	result, err := runner.Run(context.Background(), spec, func(event domain.EngineEvent) {
		events = append(events, event)
	})
	if err != nil {
		t.Fatal(err)
	}
	if len(events) < 3 || events[len(events)-1].Type != "completed" {
		t.Fatalf("unexpected event stream: %#v", events)
	}
	if _, err := os.Stat(result.ReportPath); err != nil {
		t.Fatalf("report missing: %v", err)
	}
}
