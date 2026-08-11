package store

import (
	"context"
	"database/sql"
	"errors"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/arpitJ-dev/ClauseGuard-Agent/apps/server/internal/domain"
)

func TestSQLiteJobLifecycle(t *testing.T) {
	repository, err := Open(filepath.Join(t.TempDir(), "jobs.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer repository.Close()
	var schemaVersion int
	if err := repository.database.QueryRow("PRAGMA user_version").Scan(&schemaVersion); err != nil {
		t.Fatal(err)
	}
	if schemaVersion != databaseSchemaVersion {
		t.Fatalf("schema version is %d", schemaVersion)
	}

	ctx := context.Background()
	now := time.Now().UTC().Truncate(time.Microsecond)
	job := domain.Job{
		ID:        "job-1",
		Type:      domain.JobTypeAnalysis,
		Status:    domain.JobQueued,
		Stage:     "queued",
		Message:   "accepted",
		Inputs:    []domain.InputFile{{Name: "contract.txt", Path: filepath.Join("jobs", "job-1", "contract.txt")}},
		OutputDir: filepath.Join("jobs", "job-1", "output"),
		CreatedAt: now,
		UpdatedAt: now,
	}
	if err := repository.Create(ctx, job); err != nil {
		t.Fatal(err)
	}
	if err := repository.Ping(ctx); err != nil {
		t.Fatalf("database ping failed: %v", err)
	}
	loaded, err := repository.Get(ctx, job.ID)
	if err != nil {
		t.Fatal(err)
	}
	if loaded.Inputs[0].Path != job.Inputs[0].Path || loaded.Status != domain.JobQueued {
		t.Fatalf("round trip changed job: %+v", loaded)
	}

	exitCode := 0
	completed := now.Add(time.Second)
	loaded.Status = domain.JobCompleted
	loaded.Stage = "completed"
	loaded.Progress = 100
	loaded.ReportPath = filepath.Join(loaded.OutputDir, "analysis_report.json")
	loaded.ExitCode = &exitCode
	loaded.CompletedAt = &completed
	loaded.UpdatedAt = completed
	if err := repository.Update(ctx, loaded); err != nil {
		t.Fatal(err)
	}
	listed, err := repository.List(ctx, 10)
	if err != nil {
		t.Fatal(err)
	}
	if len(listed) != 1 || listed[0].ReportPath != loaded.ReportPath {
		t.Fatalf("unexpected job list: %+v", listed)
	}
	if err := repository.Delete(ctx, job.ID); err != nil {
		t.Fatal(err)
	}
	if _, err := repository.Get(ctx, job.ID); !errors.Is(err, ErrNotFound) {
		t.Fatalf("expected ErrNotFound, got %v", err)
	}
}

func TestSQLiteRejectsNewerSchema(t *testing.T) {
	path := filepath.Join(t.TempDir(), "jobs.db")
	repository, err := Open(path)
	if err != nil {
		t.Fatal(err)
	}
	if err := repository.Close(); err != nil {
		t.Fatal(err)
	}
	database, err := sql.Open("sqlite", path)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := database.Exec("PRAGMA user_version = 99"); err != nil {
		t.Fatal(err)
	}
	if err := database.Close(); err != nil {
		t.Fatal(err)
	}
	if _, err := Open(path); err == nil || !strings.Contains(err.Error(), "newer than supported") {
		t.Fatalf("newer schema was not rejected: %v", err)
	}
}

func TestSQLiteRecoversInterruptedJobs(t *testing.T) {
	repository, err := Open(filepath.Join(t.TempDir(), "jobs.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer repository.Close()

	now := time.Now().UTC()
	job := domain.Job{
		ID:        "interrupted",
		Type:      domain.JobTypeAnalysis,
		Status:    domain.JobRunning,
		Stage:     "checking",
		Progress:  50,
		Message:   "running",
		Inputs:    []domain.InputFile{{Name: "contract.txt", Path: "contract.txt"}},
		OutputDir: "output",
		CreatedAt: now,
		UpdatedAt: now,
	}
	if err := repository.Create(context.Background(), job); err != nil {
		t.Fatal(err)
	}
	recoveredAt := now.Add(time.Minute)
	count, err := repository.RecoverInterrupted(context.Background(), recoveredAt)
	if err != nil {
		t.Fatal(err)
	}
	if count != 1 {
		t.Fatalf("expected one recovered job, got %d", count)
	}
	loaded, err := repository.Get(context.Background(), job.ID)
	if err != nil {
		t.Fatal(err)
	}
	if loaded.Status != domain.JobFailed || loaded.Error == nil || loaded.Error.Code != "server_restarted" {
		t.Fatalf("unexpected recovered state: %+v", loaded)
	}
}
