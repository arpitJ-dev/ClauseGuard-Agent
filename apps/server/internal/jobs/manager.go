package jobs

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/arpitJ-dev/ClauseGuard-Agent/apps/server/internal/domain"
	"github.com/arpitJ-dev/ClauseGuard-Agent/apps/server/internal/engine"
	"github.com/arpitJ-dev/ClauseGuard-Agent/apps/server/internal/store"
)

var (
	ErrConflict     = errors.New("job state does not allow this operation")
	ErrUnsafePath   = errors.New("job path is outside the managed data directory")
	ErrCapacity     = errors.New("active job capacity reached")
	ErrShuttingDown = errors.New("job manager is shutting down")
)

type Options struct {
	Timeout           time.Duration
	MaxConcurrentJobs int
	MaxActiveJobs     int
	DataDir           string
}

type Manager struct {
	repository   store.Repository
	runner       engine.Runner
	timeout      time.Duration
	semaphore    chan struct{}
	dataDir      string
	maxActive    int
	stateMu      sync.Mutex
	mu           sync.Mutex
	shuttingDown bool
	cancels      map[string]context.CancelFunc
	subscribers  map[string]map[chan domain.Job]struct{}
	wait         sync.WaitGroup
}

func New(repository store.Repository, runner engine.Runner, options Options) (*Manager, error) {
	if repository == nil || runner == nil {
		return nil, errors.New("job repository and runner are required")
	}
	if options.Timeout <= 0 {
		return nil, errors.New("job timeout must be positive")
	}
	if options.MaxConcurrentJobs <= 0 {
		return nil, errors.New("maximum concurrent jobs must be positive")
	}
	if options.MaxActiveJobs < options.MaxConcurrentJobs {
		return nil, errors.New("maximum active jobs cannot be lower than maximum concurrent jobs")
	}
	dataDir, err := filepath.Abs(options.DataDir)
	if err != nil {
		return nil, fmt.Errorf("resolve managed data directory: %w", err)
	}
	manager := &Manager{
		repository:  repository,
		runner:      runner,
		timeout:     options.Timeout,
		semaphore:   make(chan struct{}, options.MaxConcurrentJobs),
		dataDir:     dataDir,
		maxActive:   options.MaxActiveJobs,
		cancels:     make(map[string]context.CancelFunc),
		subscribers: make(map[string]map[chan domain.Job]struct{}),
	}
	if _, err := repository.RecoverInterrupted(context.Background(), time.Now().UTC()); err != nil {
		return nil, err
	}
	return manager, nil
}

func (manager *Manager) Submit(ctx context.Context, spec domain.JobSpec) (domain.Job, error) {
	if err := domain.ValidateSpec(spec); err != nil {
		return domain.Job{}, err
	}
	if err := manager.validateSpecPaths(spec); err != nil {
		return domain.Job{}, err
	}
	now := time.Now().UTC()
	job := domain.Job{
		ID:        spec.ID,
		Type:      spec.Type,
		Status:    domain.JobQueued,
		Stage:     "queued",
		Progress:  0,
		Message:   "Job accepted",
		Inputs:    spec.Inputs,
		OutputDir: spec.OutputDir,
		CreatedAt: now,
		UpdatedAt: now,
	}
	runContext, cancel := context.WithCancel(context.Background())
	manager.mu.Lock()
	if manager.shuttingDown {
		manager.mu.Unlock()
		cancel()
		return domain.Job{}, ErrShuttingDown
	}
	if _, exists := manager.cancels[job.ID]; exists {
		manager.mu.Unlock()
		cancel()
		return domain.Job{}, ErrConflict
	}
	if len(manager.cancels) >= manager.maxActive {
		manager.mu.Unlock()
		cancel()
		return domain.Job{}, ErrCapacity
	}
	manager.cancels[job.ID] = cancel
	manager.wait.Add(1)
	manager.mu.Unlock()
	if err := manager.repository.Create(ctx, job); err != nil {
		manager.mu.Lock()
		delete(manager.cancels, job.ID)
		manager.mu.Unlock()
		cancel()
		manager.wait.Done()
		return domain.Job{}, err
	}
	manager.publish(job)
	go manager.execute(runContext, spec)
	return manager.decorate(job), nil
}

func (manager *Manager) Get(ctx context.Context, id string) (domain.Job, error) {
	job, err := manager.repository.Get(ctx, id)
	if err != nil {
		return domain.Job{}, err
	}
	return manager.decorate(job), nil
}

func (manager *Manager) List(ctx context.Context, limit int) ([]domain.Job, error) {
	jobs, err := manager.repository.List(ctx, limit)
	if err != nil {
		return nil, err
	}
	for index := range jobs {
		jobs[index] = manager.decorate(jobs[index])
	}
	return jobs, nil
}

func (manager *Manager) Cancel(ctx context.Context, id string) (domain.Job, error) {
	manager.stateMu.Lock()
	defer manager.stateMu.Unlock()
	job, err := manager.repository.Get(ctx, id)
	if err != nil {
		return domain.Job{}, err
	}
	if job.Status.Terminal() {
		return domain.Job{}, ErrConflict
	}

	manager.mu.Lock()
	cancel, exists := manager.cancels[id]
	manager.mu.Unlock()
	if !exists {
		return domain.Job{}, ErrConflict
	}
	job.Message = "Cancellation requested"
	job.UpdatedAt = time.Now().UTC()
	if err := manager.repository.Update(ctx, job); err != nil {
		return domain.Job{}, err
	}
	manager.publish(job)
	cancel()
	return manager.decorate(job), nil
}

// Delete removes a terminal job. Active jobs are cancelled and retained until
// the engine process has stopped and the final state has been persisted.
func (manager *Manager) Delete(ctx context.Context, id string) (domain.Job, bool, error) {
	job, err := manager.repository.Get(ctx, id)
	if err != nil {
		return domain.Job{}, false, err
	}
	if !job.Status.Terminal() {
		cancelled, err := manager.Cancel(ctx, id)
		return cancelled, false, err
	}

	jobDir := filepath.Join(manager.dataDir, "jobs", job.ID)
	if err := manager.validateJobDirectory(job, jobDir); err != nil {
		return domain.Job{}, false, err
	}
	if err := os.RemoveAll(jobDir); err != nil {
		return domain.Job{}, false, fmt.Errorf("remove job files: %w", err)
	}
	if err := manager.repository.Delete(ctx, id); err != nil {
		return domain.Job{}, false, err
	}
	job.ReportPath = ""
	job.ReportURL = ""
	return job, true, nil
}

func (manager *Manager) Subscribe(
	ctx context.Context,
	id string,
) (<-chan domain.Job, func(), error) {
	updates := make(chan domain.Job, 1)
	manager.mu.Lock()
	if manager.subscribers[id] == nil {
		manager.subscribers[id] = make(map[chan domain.Job]struct{})
	}
	manager.subscribers[id][updates] = struct{}{}
	manager.mu.Unlock()

	job, err := manager.repository.Get(ctx, id)
	if err != nil {
		manager.unsubscribe(id, updates)
		return nil, nil, err
	}
	manager.mu.Lock()
	if _, subscribed := manager.subscribers[id][updates]; subscribed {
		select {
		case updates <- manager.decorate(job):
		default:
		}
	}
	manager.mu.Unlock()
	return updates, func() { manager.unsubscribe(id, updates) }, nil
}

func (manager *Manager) Health(ctx context.Context) (domain.Health, error) {
	if err := manager.repository.Ping(ctx); err != nil {
		return domain.Health{Ready: false, Error: "job store unavailable"}, err
	}
	health := manager.runner.Health(ctx)
	if !health.Ready {
		slog.Debug("analysis engine health check failed", "error", health.Error)
		publicHealth := domain.Health{Ready: false, Error: "Python analysis engine unavailable"}
		return publicHealth, errors.New(publicHealth.Error)
	}
	return health, nil
}

func (manager *Manager) Shutdown(ctx context.Context) error {
	manager.mu.Lock()
	manager.shuttingDown = true
	for _, cancel := range manager.cancels {
		cancel()
	}
	manager.mu.Unlock()

	done := make(chan struct{})
	go func() {
		manager.wait.Wait()
		close(done)
	}()
	select {
	case <-done:
		return nil
	case <-ctx.Done():
		return ctx.Err()
	}
}

func (manager *Manager) execute(ctx context.Context, spec domain.JobSpec) {
	defer manager.wait.Done()
	defer func() {
		manager.mu.Lock()
		delete(manager.cancels, spec.ID)
		manager.mu.Unlock()
	}()

	select {
	case manager.semaphore <- struct{}{}:
		defer func() { <-manager.semaphore }()
	case <-ctx.Done():
		manager.finish(spec.ID, domain.RunResult{}, ctx.Err(), ctx.Err())
		return
	}

	manager.stateMu.Lock()
	job, err := manager.repository.Get(context.Background(), spec.ID)
	if err != nil {
		manager.stateMu.Unlock()
		return
	}
	now := time.Now().UTC()
	job.Status = domain.JobRunning
	job.Stage = "loading"
	job.Message = "Starting analysis engine"
	job.StartedAt = &now
	job.UpdatedAt = now
	if err := manager.repository.Update(context.Background(), job); err != nil {
		manager.stateMu.Unlock()
		return
	}
	manager.stateMu.Unlock()
	manager.publish(job)

	runContext, cancel := context.WithTimeout(ctx, manager.timeout)
	defer cancel()
	result, runError := manager.runner.Run(runContext, spec, func(event domain.EngineEvent) {
		manager.applyEvent(spec.ID, event)
	})
	manager.finish(spec.ID, result, runError, runContext.Err())
}

func (manager *Manager) applyEvent(id string, event domain.EngineEvent) {
	manager.stateMu.Lock()
	defer manager.stateMu.Unlock()
	job, err := manager.repository.Get(context.Background(), id)
	if err != nil || job.Status.Terminal() {
		return
	}
	job.Stage = event.Stage
	job.Progress = event.Progress
	job.Message = event.Message
	job.UpdatedAt = time.Now().UTC()
	if event.Error != nil {
		job.Message = "Analysis engine reported an error"
		job.Error = &domain.JobError{Code: event.Error.Code, Message: job.Message}
	}
	if err := manager.repository.Update(context.Background(), job); err != nil {
		return
	}
	manager.publish(job)
}

func (manager *Manager) finish(
	id string,
	result domain.RunResult,
	runError error,
	contextError error,
) {
	manager.stateMu.Lock()
	defer manager.stateMu.Unlock()
	job, err := manager.repository.Get(context.Background(), id)
	if err != nil {
		return
	}
	now := time.Now().UTC()
	job.UpdatedAt = now
	job.CompletedAt = &now
	job.Progress = 100
	job.ReportPath = result.ReportPath

	switch {
	case errors.Is(contextError, context.DeadlineExceeded):
		exitCode := 14
		job.Status = domain.JobTimedOut
		job.Stage = "failed"
		job.Message = "Analysis timed out"
		job.ExitCode = &exitCode
		job.Error = &domain.JobError{Code: "timeout", Message: job.Message}
	case errors.Is(contextError, context.Canceled):
		exitCode := 130
		job.Status = domain.JobCancelled
		job.Stage = "failed"
		job.Message = "Analysis cancelled"
		job.ExitCode = &exitCode
		job.Error = &domain.JobError{Code: "cancelled", Message: job.Message}
	case runError != nil:
		exitCode := 20
		var typedError *engine.RunError
		if errors.As(runError, &typedError) {
			exitCode = typedError.ExitCode
		}
		publicMessage := errorMessageForExit(exitCode)
		job.Status = domain.JobFailed
		job.Stage = "failed"
		job.Message = publicMessage
		job.Error = &domain.JobError{Code: errorCodeForExit(exitCode), Message: publicMessage}
		job.ExitCode = &exitCode
		slog.Error("analysis engine failed", "job_id", id, "exit_code", exitCode)
	default:
		job.Status = domain.JobCompleted
		job.Stage = "completed"
		job.Message = "Analysis completed"
		job.Error = nil
		job.ExitCode = nil
	}
	if err := manager.repository.Update(context.Background(), job); err != nil {
		return
	}
	manager.publish(job)
}

func (manager *Manager) publish(job domain.Job) {
	job = manager.decorate(job)
	manager.mu.Lock()
	defer manager.mu.Unlock()
	for subscriber := range manager.subscribers[job.ID] {
		select {
		case subscriber <- job:
		default:
			select {
			case <-subscriber:
			default:
			}
			select {
			case subscriber <- job:
			default:
			}
		}
	}
}

func (manager *Manager) unsubscribe(id string, updates chan domain.Job) {
	manager.mu.Lock()
	defer manager.mu.Unlock()
	subscribers := manager.subscribers[id]
	if _, exists := subscribers[updates]; !exists {
		return
	}
	delete(subscribers, updates)
	close(updates)
	if len(subscribers) == 0 {
		delete(manager.subscribers, id)
	}
}

func (manager *Manager) decorate(job domain.Job) domain.Job {
	if job.Status == domain.JobCompleted && job.ReportPath != "" {
		job.ReportURL = "/api/v1/jobs/" + job.ID + "/report"
	}
	return job
}

func (manager *Manager) validateSpecPaths(spec domain.JobSpec) error {
	if !within(manager.dataDir, spec.OutputDir) {
		return ErrUnsafePath
	}
	for _, input := range spec.Inputs {
		if !within(manager.dataDir, input.Path) {
			return ErrUnsafePath
		}
	}
	return nil
}

func (manager *Manager) validateJobDirectory(job domain.Job, expected string) error {
	jobDirectory := filepath.Dir(filepath.Clean(job.OutputDir))
	expectedPath, err := filepath.Abs(expected)
	if err != nil {
		return ErrUnsafePath
	}
	jobPath, err := filepath.Abs(jobDirectory)
	if err != nil || jobPath != expectedPath || !within(manager.dataDir, jobPath) {
		return ErrUnsafePath
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

func errorCodeForExit(exitCode int) string {
	switch exitCode {
	case 2:
		return "usage_error"
	case 10:
		return "configuration_error"
	case 11:
		return "document_error"
	case 12:
		return "model_error"
	case 13:
		return "usage_limit"
	case 14:
		return "timeout"
	case 15:
		return "data_error"
	case 130:
		return "cancelled"
	default:
		return "engine_error"
	}
}

func errorMessageForExit(exitCode int) string {
	switch exitCode {
	case 2:
		return "The analysis request was invalid"
	case 10:
		return "The analysis engine configuration is invalid"
	case 11:
		return "The uploaded document could not be processed"
	case 12:
		return "A configured analysis model was unavailable"
	case 13:
		return "A configured model usage limit was reached"
	case 14:
		return "Analysis timed out"
	case 15:
		return "Required analysis data was invalid"
	case 130:
		return "Analysis cancelled"
	default:
		return "The analysis engine encountered an internal error"
	}
}
