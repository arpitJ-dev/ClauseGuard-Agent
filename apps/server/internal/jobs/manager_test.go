package jobs

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/arpitJ-dev/ClauseGuard-Agent/apps/server/internal/domain"
	"github.com/arpitJ-dev/ClauseGuard-Agent/apps/server/internal/engine"
	"github.com/arpitJ-dev/ClauseGuard-Agent/apps/server/internal/store"
)

type fakeRunner struct {
	run    func(context.Context, domain.JobSpec, engine.EventSink) (domain.RunResult, error)
	health domain.Health
}

type delayedGetRepository struct {
	store.Repository
	entered chan struct{}
	release chan struct{}
	once    sync.Once
}

func (repository *delayedGetRepository) Get(ctx context.Context, id string) (domain.Job, error) {
	repository.once.Do(func() {
		close(repository.entered)
		select {
		case <-repository.release:
		case <-ctx.Done():
		}
	})
	return repository.Repository.Get(ctx, id)
}

func (runner *fakeRunner) Run(
	ctx context.Context,
	spec domain.JobSpec,
	sink engine.EventSink,
) (domain.RunResult, error) {
	return runner.run(ctx, spec, sink)
}

func (runner *fakeRunner) Health(context.Context) domain.Health {
	return runner.health
}

func TestManagerCompletesStreamsAndDeletesJob(t *testing.T) {
	runner := &fakeRunner{health: domain.Health{Ready: true}}
	runner.run = func(_ context.Context, spec domain.JobSpec, sink engine.EventSink) (domain.RunResult, error) {
		sink(domain.EngineEvent{
			SchemaVersion: "1.0",
			RunID:         spec.ID,
			Sequence:      1,
			Type:          "progress",
			Stage:         "checking",
			Status:        "started",
			Progress:      50,
			Message:       "Checking clauses",
		})
		report := filepath.Join(spec.OutputDir, "analysis_report.json")
		if err := os.MkdirAll(spec.OutputDir, 0o750); err != nil {
			return domain.RunResult{}, err
		}
		if err := os.WriteFile(report, []byte(`{"schema_version":"1.0"}`), 0o600); err != nil {
			return domain.RunResult{}, err
		}
		return domain.RunResult{ReportPath: report}, nil
	}
	manager, repository, root := testManager(t, runner, time.Second)
	spec := testSpec(t, root, "complete-job")
	accepted, err := manager.Submit(context.Background(), spec)
	if err != nil {
		t.Fatal(err)
	}
	updates, unsubscribe, err := manager.Subscribe(context.Background(), accepted.ID)
	if err != nil {
		t.Fatal(err)
	}
	defer unsubscribe()

	final := awaitTerminal(t, updates)
	if final.Status != domain.JobCompleted || final.ReportURL == "" || final.Progress != 100 {
		t.Fatalf("unexpected final job: %+v", final)
	}
	stored, err := repository.Get(context.Background(), final.ID)
	if err != nil || stored.ReportPath == "" {
		t.Fatalf("report path not persisted: %+v, %v", stored, err)
	}
	deletedJob, deleted, err := manager.Delete(context.Background(), final.ID)
	if err != nil || !deleted {
		t.Fatalf("terminal job was not deleted: deleted=%v err=%v", deleted, err)
	}
	if deletedJob.ReportURL != "" || deletedJob.ReportPath != "" {
		t.Fatalf("deleted job retained a report link: %+v", deletedJob)
	}
	if _, err := os.Stat(filepath.Join(root, "jobs", final.ID)); !os.IsNotExist(err) {
		t.Fatalf("job directory still exists: %v", err)
	}
}

func TestManagerCancelsRunningJob(t *testing.T) {
	started := make(chan struct{})
	runner := &fakeRunner{health: domain.Health{Ready: true}}
	runner.run = func(ctx context.Context, _ domain.JobSpec, _ engine.EventSink) (domain.RunResult, error) {
		close(started)
		<-ctx.Done()
		return domain.RunResult{}, &engine.RunError{ExitCode: 130, Message: "cancelled", Cause: ctx.Err()}
	}
	manager, _, root := testManager(t, runner, time.Second)
	spec := testSpec(t, root, "cancel-job")
	if _, err := manager.Submit(context.Background(), spec); err != nil {
		t.Fatal(err)
	}
	select {
	case <-started:
	case <-time.After(time.Second):
		t.Fatal("runner did not start")
	}
	if _, err := manager.Cancel(context.Background(), spec.ID); err != nil {
		t.Fatal(err)
	}
	final := awaitStoredTerminal(t, manager, spec.ID)
	if final.Status != domain.JobCancelled || final.ExitCode == nil || *final.ExitCode != 130 {
		t.Fatalf("unexpected cancelled state: %+v", final)
	}
}

func TestManagerTimesOutJob(t *testing.T) {
	runner := &fakeRunner{health: domain.Health{Ready: true}}
	runner.run = func(ctx context.Context, _ domain.JobSpec, _ engine.EventSink) (domain.RunResult, error) {
		<-ctx.Done()
		return domain.RunResult{}, &engine.RunError{ExitCode: 14, Message: "timed out", Cause: ctx.Err()}
	}
	manager, _, root := testManager(t, runner, 20*time.Millisecond)
	spec := testSpec(t, root, "timeout-job")
	if _, err := manager.Submit(context.Background(), spec); err != nil {
		t.Fatal(err)
	}
	final := awaitStoredTerminal(t, manager, spec.ID)
	if final.Status != domain.JobTimedOut || final.Error == nil || final.Error.Code != "timeout" {
		t.Fatalf("unexpected timeout state: %+v", final)
	}
}

func TestManagerMapsEngineExitCode(t *testing.T) {
	runner := &fakeRunner{health: domain.Health{Ready: true}}
	runner.run = func(context.Context, domain.JobSpec, engine.EventSink) (domain.RunResult, error) {
		return domain.RunResult{}, &engine.RunError{
			ExitCode: 12,
			Message:  `model unavailable for C:\private\contract.txt`,
		}
	}
	manager, _, root := testManager(t, runner, time.Second)
	spec := testSpec(t, root, "failed-job")
	if _, err := manager.Submit(context.Background(), spec); err != nil {
		t.Fatal(err)
	}
	final := awaitStoredTerminal(t, manager, spec.ID)
	if final.Status != domain.JobFailed || final.Error == nil || final.Error.Code != "model_error" {
		t.Fatalf("unexpected failed state: %+v", final)
	}
	if strings.Contains(final.Message, "private") || strings.Contains(final.Error.Message, "private") {
		t.Fatalf("job state leaked engine diagnostics: %+v", final)
	}
}

func TestManagerRejectsPathsOutsideDataDirectory(t *testing.T) {
	runner := &fakeRunner{
		health: domain.Health{Ready: true},
		run: func(context.Context, domain.JobSpec, engine.EventSink) (domain.RunResult, error) {
			return domain.RunResult{}, nil
		},
	}
	manager, _, root := testManager(t, runner, time.Second)
	spec := testSpec(t, root, "unsafe-job")
	spec.Inputs[0].Path = filepath.Join(t.TempDir(), "outside.txt")
	if _, err := manager.Submit(context.Background(), spec); !errors.Is(err, ErrUnsafePath) {
		t.Fatalf("expected ErrUnsafePath, got %v", err)
	}
}

func TestManagerEnforcesConcurrencyLimit(t *testing.T) {
	started := make(chan string, 2)
	release := make(chan struct{}, 2)
	var active atomic.Int32
	var maximum atomic.Int32
	runner := &fakeRunner{health: domain.Health{Ready: true}}
	runner.run = func(_ context.Context, spec domain.JobSpec, _ engine.EventSink) (domain.RunResult, error) {
		current := active.Add(1)
		defer active.Add(-1)
		for {
			observed := maximum.Load()
			if current <= observed || maximum.CompareAndSwap(observed, current) {
				break
			}
		}
		started <- spec.ID
		<-release
		report := filepath.Join(spec.OutputDir, "analysis_report.json")
		if err := os.MkdirAll(spec.OutputDir, 0o750); err != nil {
			return domain.RunResult{}, err
		}
		if err := os.WriteFile(report, []byte("{}"), 0o600); err != nil {
			return domain.RunResult{}, err
		}
		return domain.RunResult{ReportPath: report}, nil
	}
	manager, _, root := testManager(t, runner, time.Second)
	first := testSpec(t, root, "first-job")
	second := testSpec(t, root, "second-job")
	if _, err := manager.Submit(context.Background(), first); err != nil {
		t.Fatal(err)
	}
	if _, err := manager.Submit(context.Background(), second); err != nil {
		t.Fatal(err)
	}
	select {
	case <-started:
	case <-time.After(time.Second):
		t.Fatal("first job did not start")
	}
	select {
	case id := <-started:
		t.Fatalf("second job %q started before capacity was released", id)
	case <-time.After(50 * time.Millisecond):
	}
	release <- struct{}{}
	select {
	case <-started:
	case <-time.After(time.Second):
		t.Fatal("queued job did not start after capacity was released")
	}
	release <- struct{}{}
	awaitStoredTerminal(t, manager, first.ID)
	awaitStoredTerminal(t, manager, second.ID)
	if maximum.Load() != 1 {
		t.Fatalf("observed %d concurrent runners", maximum.Load())
	}
}

func TestManagerRejectsJobsBeyondActiveCapacity(t *testing.T) {
	runner := &fakeRunner{health: domain.Health{Ready: true}}
	runner.run = func(ctx context.Context, _ domain.JobSpec, _ engine.EventSink) (domain.RunResult, error) {
		<-ctx.Done()
		return domain.RunResult{}, &engine.RunError{ExitCode: 130, Message: "cancelled", Cause: ctx.Err()}
	}
	root := t.TempDir()
	repository, err := store.Open(filepath.Join(root, "jobs.db"))
	if err != nil {
		t.Fatal(err)
	}
	manager, err := New(repository, runner, Options{
		Timeout: time.Second, MaxConcurrentJobs: 1, MaxActiveJobs: 1, DataDir: root,
	})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		ctx, cancel := context.WithTimeout(context.Background(), time.Second)
		defer cancel()
		_ = manager.Shutdown(ctx)
		_ = repository.Close()
	})
	first := testSpec(t, root, "capacity-first")
	second := testSpec(t, root, "capacity-second")
	if _, err := manager.Submit(context.Background(), first); err != nil {
		t.Fatal(err)
	}
	if _, err := manager.Submit(context.Background(), first); !errors.Is(err, ErrConflict) {
		t.Fatalf("expected duplicate job conflict, got %v", err)
	}
	if _, err := manager.Submit(context.Background(), second); !errors.Is(err, ErrCapacity) {
		t.Fatalf("expected ErrCapacity, got %v", err)
	}
	if _, err := manager.Cancel(context.Background(), first.ID); err != nil {
		t.Fatal(err)
	}
	awaitStoredTerminal(t, manager, first.ID)
}

func TestShutdownRejectsLateSubmissions(t *testing.T) {
	runner := &fakeRunner{
		health: domain.Health{Ready: true},
		run: func(context.Context, domain.JobSpec, engine.EventSink) (domain.RunResult, error) {
			return domain.RunResult{}, nil
		},
	}
	manager, _, root := testManager(t, runner, time.Second)
	if err := manager.Shutdown(context.Background()); err != nil {
		t.Fatal(err)
	}
	spec := testSpec(t, root, "late-job")
	if _, err := manager.Submit(context.Background(), spec); !errors.Is(err, ErrShuttingDown) {
		t.Fatalf("expected ErrShuttingDown, got %v", err)
	}
}

func TestSubscribeDoesNotBlockWhenUpdateArrivesDuringInitialRead(t *testing.T) {
	root := t.TempDir()
	base, err := store.Open(filepath.Join(root, "jobs.db"))
	if err != nil {
		t.Fatal(err)
	}
	now := time.Now().UTC()
	job := domain.Job{
		ID: "subscribe-race", Type: domain.JobTypeAnalysis, Status: domain.JobCompleted,
		Stage: "completed", Progress: 100, Message: "done",
		Inputs:    []domain.InputFile{{Name: "contract.txt", Path: filepath.Join(root, "jobs", "subscribe-race", "inputs", "document.txt")}},
		OutputDir: filepath.Join(root, "jobs", "subscribe-race", "output"),
		CreatedAt: now, UpdatedAt: now, CompletedAt: &now,
	}
	if err := base.Create(context.Background(), job); err != nil {
		t.Fatal(err)
	}
	repository := &delayedGetRepository{
		Repository: base, entered: make(chan struct{}), release: make(chan struct{}),
	}
	runner := &fakeRunner{
		health: domain.Health{Ready: true},
		run: func(context.Context, domain.JobSpec, engine.EventSink) (domain.RunResult, error) {
			return domain.RunResult{}, nil
		},
	}
	manager, err := New(repository, runner, Options{
		Timeout: time.Second, MaxConcurrentJobs: 1, MaxActiveJobs: 2, DataDir: root,
	})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		_ = manager.Shutdown(context.Background())
		_ = base.Close()
	})
	type subscription struct {
		updates     <-chan domain.Job
		unsubscribe func()
		err         error
	}
	result := make(chan subscription, 1)
	go func() {
		updates, unsubscribe, err := manager.Subscribe(context.Background(), job.ID)
		result <- subscription{updates: updates, unsubscribe: unsubscribe, err: err}
	}()
	select {
	case <-repository.entered:
	case <-time.After(time.Second):
		t.Fatal("subscription did not begin its initial read")
	}
	manager.publish(job)
	close(repository.release)
	select {
	case subscribed := <-result:
		if subscribed.err != nil {
			t.Fatal(subscribed.err)
		}
		defer subscribed.unsubscribe()
		select {
		case snapshot := <-subscribed.updates:
			if snapshot.Status != domain.JobCompleted {
				t.Fatalf("unexpected snapshot: %+v", snapshot)
			}
		case <-time.After(time.Second):
			t.Fatal("subscription returned without a snapshot")
		}
	case <-time.After(time.Second):
		t.Fatal("subscription blocked on a full initial-update channel")
	}
}

func TestManagerListAndHealth(t *testing.T) {
	runner := &fakeRunner{health: domain.Health{Ready: true}}
	runner.run = func(_ context.Context, spec domain.JobSpec, _ engine.EventSink) (domain.RunResult, error) {
		report := filepath.Join(spec.OutputDir, "analysis_report.json")
		if err := os.MkdirAll(spec.OutputDir, 0o750); err != nil {
			return domain.RunResult{}, err
		}
		if err := os.WriteFile(report, []byte("{}"), 0o600); err != nil {
			return domain.RunResult{}, err
		}
		return domain.RunResult{ReportPath: report}, nil
	}
	manager, _, root := testManager(t, runner, time.Second)
	spec := testSpec(t, root, "listed-job")
	if _, err := manager.Submit(context.Background(), spec); err != nil {
		t.Fatal(err)
	}
	awaitStoredTerminal(t, manager, spec.ID)
	listed, err := manager.List(context.Background(), 10)
	if err != nil || len(listed) != 1 || listed[0].ReportURL == "" {
		t.Fatalf("unexpected list result: %+v, %v", listed, err)
	}
	health, err := manager.Health(context.Background())
	if err != nil || !health.Ready {
		t.Fatalf("unexpected health result: %+v, %v", health, err)
	}
}

func TestExitCodeMappingIsStable(t *testing.T) {
	tests := map[int]string{
		2: "usage_error", 10: "configuration_error", 11: "document_error",
		12: "model_error", 13: "usage_limit", 14: "timeout",
		15: "data_error", 130: "cancelled", 99: "engine_error",
	}
	for exitCode, want := range tests {
		if got := errorCodeForExit(exitCode); got != want {
			t.Fatalf("exit code %d mapped to %q, want %q", exitCode, got, want)
		}
	}
	for _, exitCode := range []int{2, 10, 11, 12, 13, 14, 15, 20, 130} {
		if message := errorMessageForExit(exitCode); message == "" {
			t.Fatalf("exit code %d has no public message", exitCode)
		}
	}
}

func testManager(
	t *testing.T,
	runner engine.Runner,
	timeout time.Duration,
) (*Manager, *store.SQLite, string) {
	t.Helper()
	root := t.TempDir()
	repository, err := store.Open(filepath.Join(root, "jobs.db"))
	if err != nil {
		t.Fatal(err)
	}
	manager, err := New(repository, runner, Options{
		Timeout:           timeout,
		MaxConcurrentJobs: 1,
		MaxActiveJobs:     10,
		DataDir:           root,
	})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		ctx, cancel := context.WithTimeout(context.Background(), time.Second)
		defer cancel()
		_ = manager.Shutdown(ctx)
		_ = repository.Close()
	})
	return manager, repository, root
}

func testSpec(t *testing.T, root, id string) domain.JobSpec {
	t.Helper()
	inputDir := filepath.Join(root, "jobs", id, "inputs")
	outputDir := filepath.Join(root, "jobs", id, "output")
	if err := os.MkdirAll(inputDir, 0o750); err != nil {
		t.Fatal(err)
	}
	input := filepath.Join(inputDir, "document.txt")
	if err := os.WriteFile(input, []byte("Agreement"), 0o600); err != nil {
		t.Fatal(err)
	}
	return domain.JobSpec{
		ID:        id,
		Type:      domain.JobTypeAnalysis,
		Inputs:    []domain.InputFile{{Name: "document.txt", Path: input}},
		OutputDir: outputDir,
	}
}

func awaitTerminal(t *testing.T, updates <-chan domain.Job) domain.Job {
	t.Helper()
	timer := time.NewTimer(2 * time.Second)
	defer timer.Stop()
	for {
		select {
		case job := <-updates:
			if job.Status.Terminal() {
				return job
			}
		case <-timer.C:
			t.Fatal("timed out waiting for terminal job update")
		}
	}
}

func awaitStoredTerminal(t *testing.T, manager *Manager, id string) domain.Job {
	t.Helper()
	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		job, err := manager.Get(context.Background(), id)
		if err == nil && job.Status.Terminal() {
			return job
		}
		time.Sleep(5 * time.Millisecond)
	}
	t.Fatal("timed out waiting for stored terminal job")
	return domain.Job{}
}
