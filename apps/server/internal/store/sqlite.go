package store

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"time"

	"github.com/arpitJ-dev/ClauseGuard-Agent/apps/server/internal/domain"
	_ "modernc.org/sqlite"
)

var ErrNotFound = errors.New("job not found")

const databaseSchemaVersion = 1

type Repository interface {
	Create(context.Context, domain.Job) error
	Update(context.Context, domain.Job) error
	Get(context.Context, string) (domain.Job, error)
	List(context.Context, int) ([]domain.Job, error)
	Delete(context.Context, string) error
	RecoverInterrupted(context.Context, time.Time) (int64, error)
	Ping(context.Context) error
	Close() error
}

type SQLite struct {
	database *sql.DB
}

func Open(path string) (*SQLite, error) {
	if err := os.MkdirAll(filepath.Dir(path), 0o750); err != nil {
		return nil, fmt.Errorf("create database directory: %w", err)
	}
	database, err := sql.Open("sqlite", path)
	if err != nil {
		return nil, fmt.Errorf("open SQLite database: %w", err)
	}
	database.SetMaxOpenConns(1)
	for _, statement := range []string{
		"PRAGMA busy_timeout = 5000",
		"PRAGMA journal_mode = WAL",
		"PRAGMA foreign_keys = ON",
	} {
		if _, err := database.Exec(statement); err != nil {
			_ = database.Close()
			return nil, fmt.Errorf("configure SQLite database: %w", err)
		}
	}
	if err := initializeSchema(database); err != nil {
		_ = database.Close()
		return nil, err
	}
	return &SQLite{database: database}, nil
}

func initializeSchema(database *sql.DB) error {
	var version int
	if err := database.QueryRow("PRAGMA user_version").Scan(&version); err != nil {
		return fmt.Errorf("read SQLite schema version: %w", err)
	}
	if version > databaseSchemaVersion {
		return fmt.Errorf(
			"SQLite schema version %d is newer than supported version %d",
			version,
			databaseSchemaVersion,
		)
	}
	if version == databaseSchemaVersion {
		return nil
	}

	transaction, err := database.Begin()
	if err != nil {
		return fmt.Errorf("begin SQLite schema migration: %w", err)
	}
	defer transaction.Rollback()
	if _, err := transaction.Exec(`
		CREATE TABLE IF NOT EXISTS jobs (
			id TEXT PRIMARY KEY,
			type TEXT NOT NULL,
			status TEXT NOT NULL,
			stage TEXT NOT NULL,
			progress INTEGER NOT NULL,
			message TEXT NOT NULL,
			input_names TEXT NOT NULL,
			input_paths TEXT NOT NULL,
			output_dir TEXT NOT NULL,
			report_path TEXT,
			error_code TEXT,
			error_message TEXT,
			exit_code INTEGER,
			created_at TEXT NOT NULL,
			updated_at TEXT NOT NULL,
			started_at TEXT,
			completed_at TEXT
		)
	`); err != nil {
		return fmt.Errorf("create jobs table: %w", err)
	}
	if _, err := transaction.Exec(fmt.Sprintf("PRAGMA user_version = %d", databaseSchemaVersion)); err != nil {
		return fmt.Errorf("record SQLite schema version: %w", err)
	}
	if err := transaction.Commit(); err != nil {
		return fmt.Errorf("commit SQLite schema migration: %w", err)
	}
	return nil
}

func (store *SQLite) Create(ctx context.Context, job domain.Job) error {
	names, paths, err := encodeInputs(job.Inputs)
	if err != nil {
		return err
	}
	errorCode, errorMessage := errorValues(job.Error)
	_, err = store.database.ExecContext(ctx, `
		INSERT INTO jobs (
			id, type, status, stage, progress, message, input_names, input_paths,
			output_dir, report_path, error_code, error_message, exit_code,
			created_at, updated_at, started_at, completed_at
		) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
	`,
		job.ID, job.Type, job.Status, job.Stage, job.Progress, job.Message, names, paths,
		job.OutputDir, nullableString(job.ReportPath), errorCode, errorMessage, nullableInt(job.ExitCode),
		formatTime(job.CreatedAt), formatTime(job.UpdatedAt), nullableTime(job.StartedAt), nullableTime(job.CompletedAt),
	)
	if err != nil {
		return fmt.Errorf("create job: %w", err)
	}
	return nil
}

func (store *SQLite) Update(ctx context.Context, job domain.Job) error {
	names, paths, err := encodeInputs(job.Inputs)
	if err != nil {
		return err
	}
	errorCode, errorMessage := errorValues(job.Error)
	result, err := store.database.ExecContext(ctx, `
		UPDATE jobs SET
			type = ?, status = ?, stage = ?, progress = ?, message = ?,
			input_names = ?, input_paths = ?, output_dir = ?, report_path = ?,
			error_code = ?, error_message = ?, exit_code = ?, updated_at = ?,
			started_at = ?, completed_at = ?
		WHERE id = ?
	`,
		job.Type, job.Status, job.Stage, job.Progress, job.Message,
		names, paths, job.OutputDir, nullableString(job.ReportPath),
		errorCode, errorMessage, nullableInt(job.ExitCode), formatTime(job.UpdatedAt),
		nullableTime(job.StartedAt), nullableTime(job.CompletedAt), job.ID,
	)
	if err != nil {
		return fmt.Errorf("update job: %w", err)
	}
	count, err := result.RowsAffected()
	if err != nil {
		return fmt.Errorf("count updated jobs: %w", err)
	}
	if count == 0 {
		return ErrNotFound
	}
	return nil
}

func (store *SQLite) Get(ctx context.Context, id string) (domain.Job, error) {
	row := store.database.QueryRowContext(ctx, selectJob+" WHERE id = ?", id)
	job, err := scanJob(row)
	if errors.Is(err, sql.ErrNoRows) {
		return domain.Job{}, ErrNotFound
	}
	if err != nil {
		return domain.Job{}, fmt.Errorf("get job: %w", err)
	}
	return job, nil
}

func (store *SQLite) List(ctx context.Context, limit int) ([]domain.Job, error) {
	if limit <= 0 {
		limit = 50
	}
	rows, err := store.database.QueryContext(ctx, selectJob+" ORDER BY created_at DESC LIMIT ?", limit)
	if err != nil {
		return nil, fmt.Errorf("list jobs: %w", err)
	}
	defer rows.Close()

	jobs := make([]domain.Job, 0)
	for rows.Next() {
		job, err := scanJob(rows)
		if err != nil {
			return nil, fmt.Errorf("scan listed job: %w", err)
		}
		jobs = append(jobs, job)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate jobs: %w", err)
	}
	return jobs, nil
}

func (store *SQLite) Delete(ctx context.Context, id string) error {
	result, err := store.database.ExecContext(ctx, "DELETE FROM jobs WHERE id = ?", id)
	if err != nil {
		return fmt.Errorf("delete job: %w", err)
	}
	count, err := result.RowsAffected()
	if err != nil {
		return fmt.Errorf("count deleted jobs: %w", err)
	}
	if count == 0 {
		return ErrNotFound
	}
	return nil
}

func (store *SQLite) RecoverInterrupted(ctx context.Context, recoveredAt time.Time) (int64, error) {
	timestamp := formatTime(recoveredAt)
	result, err := store.database.ExecContext(ctx, `
		UPDATE jobs SET
			status = ?, stage = ?, progress = 100,
			message = ?, error_code = ?, error_message = ?,
			exit_code = 20, updated_at = ?, completed_at = ?
		WHERE status IN (?, ?)
	`,
		domain.JobFailed, "failed", "Job interrupted by server restart",
		"server_restarted", "The server restarted before the job completed.",
		timestamp, timestamp, domain.JobQueued, domain.JobRunning,
	)
	if err != nil {
		return 0, fmt.Errorf("recover interrupted jobs: %w", err)
	}
	return result.RowsAffected()
}

func (store *SQLite) Ping(ctx context.Context) error {
	return store.database.PingContext(ctx)
}

func (store *SQLite) Close() error {
	return store.database.Close()
}

const selectJob = `
	SELECT id, type, status, stage, progress, message, input_names, input_paths,
		output_dir, report_path, error_code, error_message, exit_code,
		created_at, updated_at, started_at, completed_at
	FROM jobs`

type rowScanner interface {
	Scan(...any) error
}

func scanJob(scanner rowScanner) (domain.Job, error) {
	var job domain.Job
	var jobType, status string
	var names, paths string
	var reportPath, errorCode, errorMessage sql.NullString
	var exitCode sql.NullInt64
	var createdAt, updatedAt string
	var startedAt, completedAt sql.NullString
	if err := scanner.Scan(
		&job.ID, &jobType, &status, &job.Stage, &job.Progress, &job.Message,
		&names, &paths, &job.OutputDir, &reportPath, &errorCode, &errorMessage,
		&exitCode, &createdAt, &updatedAt, &startedAt, &completedAt,
	); err != nil {
		return domain.Job{}, err
	}
	job.Type = domain.JobType(jobType)
	job.Status = domain.JobStatus(status)
	job.ReportPath = reportPath.String
	if errorCode.Valid || errorMessage.Valid {
		job.Error = &domain.JobError{Code: errorCode.String, Message: errorMessage.String}
	}
	if exitCode.Valid {
		value := int(exitCode.Int64)
		job.ExitCode = &value
	}
	var err error
	job.Inputs, err = decodeInputs(names, paths)
	if err != nil {
		return domain.Job{}, err
	}
	job.CreatedAt, err = time.Parse(time.RFC3339Nano, createdAt)
	if err != nil {
		return domain.Job{}, fmt.Errorf("parse created_at: %w", err)
	}
	job.UpdatedAt, err = time.Parse(time.RFC3339Nano, updatedAt)
	if err != nil {
		return domain.Job{}, fmt.Errorf("parse updated_at: %w", err)
	}
	job.StartedAt, err = parseNullableTime(startedAt)
	if err != nil {
		return domain.Job{}, fmt.Errorf("parse started_at: %w", err)
	}
	job.CompletedAt, err = parseNullableTime(completedAt)
	if err != nil {
		return domain.Job{}, fmt.Errorf("parse completed_at: %w", err)
	}
	return job, nil
}

func encodeInputs(inputs []domain.InputFile) (string, string, error) {
	names := make([]string, 0, len(inputs))
	paths := make([]string, 0, len(inputs))
	for _, input := range inputs {
		names = append(names, input.Name)
		paths = append(paths, input.Path)
	}
	encodedNames, err := json.Marshal(names)
	if err != nil {
		return "", "", fmt.Errorf("encode input names: %w", err)
	}
	encodedPaths, err := json.Marshal(paths)
	if err != nil {
		return "", "", fmt.Errorf("encode input paths: %w", err)
	}
	return string(encodedNames), string(encodedPaths), nil
}

func decodeInputs(encodedNames, encodedPaths string) ([]domain.InputFile, error) {
	var names, paths []string
	if err := json.Unmarshal([]byte(encodedNames), &names); err != nil {
		return nil, fmt.Errorf("decode input names: %w", err)
	}
	if err := json.Unmarshal([]byte(encodedPaths), &paths); err != nil {
		return nil, fmt.Errorf("decode input paths: %w", err)
	}
	if len(names) != len(paths) {
		return nil, errors.New("stored input names and paths are inconsistent")
	}
	inputs := make([]domain.InputFile, 0, len(names))
	for index := range names {
		inputs = append(inputs, domain.InputFile{Name: names[index], Path: paths[index]})
	}
	return inputs, nil
}

func errorValues(jobError *domain.JobError) (any, any) {
	if jobError == nil {
		return nil, nil
	}
	return jobError.Code, jobError.Message
}

func nullableString(value string) any {
	if value == "" {
		return nil
	}
	return value
}

func nullableInt(value *int) any {
	if value == nil {
		return nil
	}
	return *value
}

func nullableTime(value *time.Time) any {
	if value == nil {
		return nil
	}
	return formatTime(*value)
}

func parseNullableTime(value sql.NullString) (*time.Time, error) {
	if !value.Valid {
		return nil, nil
	}
	parsed, err := time.Parse(time.RFC3339Nano, value.String)
	if err != nil {
		return nil, err
	}
	return &parsed, nil
}

func formatTime(value time.Time) string {
	return value.UTC().Format(time.RFC3339Nano)
}
