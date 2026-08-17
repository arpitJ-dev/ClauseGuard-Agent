package engine

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/arpitJ-dev/ClauseGuard-Agent/apps/server/internal/domain"
)

const (
	eventSchemaVersion = "1.0"
	maxEventBytes      = 1 << 20
	maxDiagnosticBytes = 64 << 10
	defaultHealthTTL   = 10 * time.Second
)

type EventSink func(domain.EngineEvent)

type Runner interface {
	Run(context.Context, domain.JobSpec, EventSink) (domain.RunResult, error)
	Health(context.Context) domain.Health
}

type CLIRunner struct {
	PythonExecutable string
	Workspace        string
	MockModels       bool
	HealthCacheTTL   time.Duration
	healthMu         sync.Mutex
	healthAt         time.Time
	healthValue      domain.Health
}

type RunError struct {
	ExitCode int
	Message  string
	Stderr   string
	Cause    error
}

func (err *RunError) Error() string {
	if err.Message != "" {
		return err.Message
	}
	if err.Cause != nil {
		return err.Cause.Error()
	}
	return "ClauseGuard engine failed"
}

func (err *RunError) Unwrap() error {
	return err.Cause
}

func (runner *CLIRunner) Run(
	ctx context.Context,
	spec domain.JobSpec,
	sink EventSink,
) (domain.RunResult, error) {
	if err := domain.ValidateSpec(spec); err != nil {
		return domain.RunResult{}, &RunError{ExitCode: 2, Message: err.Error(), Cause: err}
	}
	if err := os.MkdirAll(spec.OutputDir, 0o750); err != nil {
		return domain.RunResult{}, &RunError{
			ExitCode: 20,
			Message:  "create job output directory",
			Cause:    err,
		}
	}

	command := exec.CommandContext(ctx, runner.PythonExecutable, runner.arguments(spec)...)
	command.Dir = runner.Workspace
	command.Env = append(os.Environ(), "PYTHONUNBUFFERED=1")
	stdout, err := command.StdoutPipe()
	if err != nil {
		return domain.RunResult{}, &RunError{ExitCode: 20, Message: "open engine output", Cause: err}
	}
	stderr, err := command.StderrPipe()
	if err != nil {
		return domain.RunResult{}, &RunError{ExitCode: 20, Message: "open engine diagnostics", Cause: err}
	}

	if err := command.Start(); err != nil {
		return domain.RunResult{}, &RunError{
			ExitCode: 20,
			Message:  "start ClauseGuard Python engine",
			Cause:    err,
		}
	}

	diagnostics := newLimitedBuffer(maxDiagnosticBytes)
	var diagnosticsWait sync.WaitGroup
	diagnosticsWait.Add(1)
	go func() {
		defer diagnosticsWait.Done()
		_, _ = io.Copy(diagnostics, stderr)
	}()

	scanner := bufio.NewScanner(stdout)
	scanner.Buffer(make([]byte, 64<<10), maxEventBytes)
	expectedSequence := 1
	lastProgress := -1
	terminalSeen := false
	completedSeen := false
	reportPath := ""
	var protocolError error
	for scanner.Scan() {
		if protocolError != nil {
			continue
		}
		var event domain.EngineEvent
		if err := json.Unmarshal(scanner.Bytes(), &event); err != nil {
			protocolError = fmt.Errorf("decode engine event: %w", err)
			continue
		}
		if err := validateEvent(event, spec.ID, expectedSequence); err != nil {
			protocolError = err
			continue
		}
		if terminalSeen {
			protocolError = errors.New("engine emitted an event after a terminal event")
			continue
		}
		if event.Progress < lastProgress {
			protocolError = errors.New("engine event progress moved backwards")
			continue
		}
		expectedSequence++
		lastProgress = event.Progress
		if event.Type == "completed" {
			terminalSeen = true
			completedSeen = true
		} else if event.Type == "error" {
			terminalSeen = true
		}
		if path := jsonReportPath(event.Details); path != "" {
			reportPath = path
		}
		if sink != nil {
			sink(event)
		}
	}
	if err := scanner.Err(); err != nil {
		if protocolError == nil {
			protocolError = fmt.Errorf("read engine event stream: %w", err)
		}
		_, _ = io.Copy(io.Discard, stdout)
	}

	waitError := command.Wait()
	diagnosticsWait.Wait()
	stderrText := strings.TrimSpace(diagnostics.String())
	if ctx.Err() != nil {
		exitCode := 130
		message := "analysis cancelled"
		if errors.Is(ctx.Err(), context.DeadlineExceeded) {
			exitCode = 14
			message = "analysis timed out"
		}
		return domain.RunResult{}, &RunError{
			ExitCode: exitCode,
			Message:  message,
			Stderr:   stderrText,
			Cause:    ctx.Err(),
		}
	}
	if waitError != nil {
		exitCode := 20
		var exitError *exec.ExitError
		if errors.As(waitError, &exitError) {
			exitCode = exitError.ExitCode()
		}
		message := "ClauseGuard engine exited with an error"
		if stderrText != "" {
			message = stderrText
		}
		return domain.RunResult{}, &RunError{
			ExitCode: exitCode,
			Message:  message,
			Stderr:   stderrText,
			Cause:    waitError,
		}
	}
	if !completedSeen && protocolError == nil {
		protocolError = errors.New("engine exited successfully without a completed event")
	}
	if protocolError != nil {
		return domain.RunResult{}, &RunError{
			ExitCode: 20,
			Message:  "invalid event stream from ClauseGuard engine",
			Stderr:   stderrText,
			Cause:    protocolError,
		}
	}

	if reportPath == "" {
		reportPath = expectedReportPath(spec)
	}
	reportPath, err = filepath.Abs(reportPath)
	if err != nil {
		return domain.RunResult{}, &RunError{ExitCode: 20, Message: "resolve report path", Cause: err}
	}
	if !within(spec.OutputDir, reportPath) {
		return domain.RunResult{}, &RunError{ExitCode: 20, Message: "engine returned a report outside the job directory"}
	}
	info, err := os.Stat(reportPath)
	if err != nil || info.IsDir() {
		return domain.RunResult{}, &RunError{ExitCode: 20, Message: "engine did not produce the JSON report", Cause: err}
	}
	if err := sanitizeReportMetadata(reportPath, spec); err != nil {
		return domain.RunResult{}, &RunError{
			ExitCode: 20,
			Message:  "sanitize report metadata",
			Cause:    err,
		}
	}
	return domain.RunResult{ReportPath: reportPath}, nil
}

func (runner *CLIRunner) Health(ctx context.Context) domain.Health {
	runner.healthMu.Lock()
	defer runner.healthMu.Unlock()
	ttl := runner.HealthCacheTTL
	if ttl <= 0 {
		ttl = defaultHealthTTL
	}
	if !runner.healthAt.IsZero() && time.Since(runner.healthAt) < ttl {
		return runner.healthValue
	}
	health := runner.checkHealth(ctx)
	runner.healthAt = time.Now()
	runner.healthValue = health
	return health
}

func (runner *CLIRunner) checkHealth(ctx context.Context) domain.Health {
	command := exec.CommandContext(ctx, runner.PythonExecutable, "-m", "clauseguard", "models", "--json")
	command.Dir = runner.Workspace
	output, err := command.Output()
	if err != nil {
		return domain.Health{Ready: false, Error: err.Error()}
	}
	var models []map[string]any
	if err := json.Unmarshal(output, &models); err != nil {
		return domain.Health{Ready: false, Error: "invalid model inventory from Python engine"}
	}
	return domain.Health{Ready: true, Models: models}
}

func (runner *CLIRunner) arguments(spec domain.JobSpec) []string {
	arguments := []string{"-m", "clauseguard"}
	if spec.Type == domain.JobTypeAnalysis {
		arguments = append(
			arguments,
			"analyze",
			spec.Inputs[0].Path,
			"--output-dir", spec.OutputDir,
			"--format", "json",
			"--events-jsonl",
			"--run-id", spec.ID,
		)
		if runner.MockModels {
			arguments = append(arguments, "--mock-models")
		}
		return arguments
	}

	arguments = append(
		arguments,
		"compare",
		spec.Inputs[0].Path,
		spec.Inputs[1].Path,
		"--output-dir", spec.OutputDir,
		"--format", "json",
		"--events-jsonl",
		"--run-id", spec.ID,
	)
	if !runner.MockModels {
		arguments = append(arguments, "--real-models")
	}
	return arguments
}

func validateEvent(event domain.EngineEvent, runID string, expectedSequence int) error {
	if event.SchemaVersion != eventSchemaVersion {
		return fmt.Errorf("unsupported event schema %q", event.SchemaVersion)
	}
	if event.RunID != runID {
		return errors.New("engine event run ID does not match job ID")
	}
	if event.Sequence != expectedSequence {
		return fmt.Errorf("engine event sequence %d; expected %d", event.Sequence, expectedSequence)
	}
	if event.Progress < 0 || event.Progress > 100 {
		return errors.New("engine event progress is outside 0-100")
	}
	if event.Stage == "" || event.Status == "" || event.Type == "" {
		return errors.New("engine event is missing required fields")
	}
	if _, err := time.Parse(time.RFC3339Nano, event.Timestamp); err != nil {
		return errors.New("engine event has an invalid timestamp")
	}
	validStages := map[string]bool{
		"queued": true, "loading": true, "extracting": true, "retrieving": true,
		"checking": true, "verifying": true, "scoring": true, "rewriting": true,
		"comparing": true, "reporting": true, "completed": true, "failed": true,
	}
	if !validStages[event.Stage] {
		return fmt.Errorf("unsupported engine stage %q", event.Stage)
	}
	validStatuses := map[string]bool{"queued": true, "started": true, "completed": true, "failed": true}
	if !validStatuses[event.Status] {
		return fmt.Errorf("unsupported engine status %q", event.Status)
	}
	switch event.Type {
	case "progress":
		if event.Stage == "completed" || event.Stage == "failed" || event.Status == "failed" || event.Error != nil {
			return errors.New("progress event uses terminal fields")
		}
		if (event.Stage == "queued") != (event.Status == "queued") {
			return errors.New("queued stage and status must be used together")
		}
	case "completed":
		if event.Stage != "completed" || event.Status != "completed" || event.Progress != 100 || event.Error != nil {
			return errors.New("completed event has inconsistent terminal fields")
		}
	case "error":
		if event.Stage != "failed" || event.Status != "failed" || event.Progress != 100 || event.Error == nil {
			return errors.New("error event has inconsistent terminal fields")
		}
	default:
		return fmt.Errorf("unsupported engine event type %q", event.Type)
	}
	return nil
}

func jsonReportPath(details map[string]any) string {
	raw, ok := details["report_files"]
	if !ok {
		return ""
	}
	files, ok := raw.([]any)
	if !ok {
		return ""
	}
	for _, value := range files {
		path, ok := value.(string)
		if ok && strings.EqualFold(filepath.Ext(path), ".json") {
			return path
		}
	}
	return ""
}

func expectedReportPath(spec domain.JobSpec) string {
	name := "analysis_report.json"
	if spec.Type == domain.JobTypeComparison {
		name = "comparison_report.json"
	}
	return filepath.Join(spec.OutputDir, name)
}

func sanitizeReportMetadata(reportPath string, spec domain.JobSpec) error {
	payload, err := os.ReadFile(reportPath)
	if err != nil {
		return err
	}
	var report map[string]json.RawMessage
	if err := json.Unmarshal(payload, &report); err != nil {
		return fmt.Errorf("decode report: %w", err)
	}
	replacements := map[string]string{}
	if spec.Type == domain.JobTypeAnalysis {
		replacements["file_path"] = spec.Inputs[0].Name
	} else {
		replacements["original_document"] = spec.Inputs[0].Name
		replacements["modified_document"] = spec.Inputs[1].Name
	}
	for key, value := range replacements {
		encoded, err := json.Marshal(value)
		if err != nil {
			return fmt.Errorf("encode %s: %w", key, err)
		}
		report[key] = encoded
	}
	sanitized, err := json.MarshalIndent(report, "", "  ")
	if err != nil {
		return fmt.Errorf("encode sanitized report: %w", err)
	}
	sanitized = append(sanitized, '\n')
	if err := os.WriteFile(reportPath, sanitized, 0o640); err != nil {
		return fmt.Errorf("write sanitized report: %w", err)
	}
	return nil
}

func within(root, target string) bool {
	rootPath, err := filepath.Abs(root)
	if err != nil {
		return false
	}
	targetPath, err := filepath.Abs(target)
	if err != nil {
		return false
	}
	relative, err := filepath.Rel(rootPath, targetPath)
	if err != nil {
		return false
	}
	return relative != ".." && !strings.HasPrefix(relative, ".."+string(filepath.Separator))
}

type limitedBuffer struct {
	mu        sync.Mutex
	buffer    bytes.Buffer
	remaining int
}

func newLimitedBuffer(limit int) *limitedBuffer {
	return &limitedBuffer{remaining: limit}
}

func (buffer *limitedBuffer) Write(payload []byte) (int, error) {
	buffer.mu.Lock()
	defer buffer.mu.Unlock()
	written := len(payload)
	if buffer.remaining > 0 {
		keep := len(payload)
		if keep > buffer.remaining {
			keep = buffer.remaining
		}
		_, _ = buffer.buffer.Write(payload[:keep])
		buffer.remaining -= keep
	}
	return written, nil
}

func (buffer *limitedBuffer) String() string {
	buffer.mu.Lock()
	defer buffer.mu.Unlock()
	return buffer.buffer.String()
}
