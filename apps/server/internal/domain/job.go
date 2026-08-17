package domain

import (
	"crypto/rand"
	"encoding/hex"
	"errors"
	"time"
)

type JobType string

const (
	JobTypeAnalysis   JobType = "analysis"
	JobTypeComparison JobType = "comparison"
)

func (kind JobType) Valid() bool {
	return kind == JobTypeAnalysis || kind == JobTypeComparison
}

type JobStatus string

const (
	JobQueued    JobStatus = "queued"
	JobRunning   JobStatus = "running"
	JobCompleted JobStatus = "completed"
	JobFailed    JobStatus = "failed"
	JobCancelled JobStatus = "cancelled"
	JobTimedOut  JobStatus = "timed_out"
)

func (status JobStatus) Terminal() bool {
	switch status {
	case JobCompleted, JobFailed, JobCancelled, JobTimedOut:
		return true
	default:
		return false
	}
}

type InputFile struct {
	Name string `json:"name"`
	Path string `json:"-"`
}

type JobError struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}

type Job struct {
	ID          string      `json:"id"`
	Type        JobType     `json:"type"`
	Status      JobStatus   `json:"status"`
	Stage       string      `json:"stage"`
	Progress    int         `json:"progress"`
	Message     string      `json:"message"`
	Inputs      []InputFile `json:"inputs"`
	OutputDir   string      `json:"-"`
	ReportPath  string      `json:"-"`
	ReportURL   string      `json:"report_url,omitempty"`
	Error       *JobError   `json:"error,omitempty"`
	ExitCode    *int        `json:"exit_code,omitempty"`
	CreatedAt   time.Time   `json:"created_at"`
	UpdatedAt   time.Time   `json:"updated_at"`
	StartedAt   *time.Time  `json:"started_at,omitempty"`
	CompletedAt *time.Time  `json:"completed_at,omitempty"`
}

type JobSpec struct {
	ID        string
	Type      JobType
	Inputs    []InputFile
	OutputDir string
}

type EngineError struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}

type EngineEvent struct {
	SchemaVersion string         `json:"schema_version"`
	RunID         string         `json:"run_id"`
	Sequence      int            `json:"sequence"`
	Type          string         `json:"type"`
	Stage         string         `json:"stage"`
	Status        string         `json:"status"`
	Progress      int            `json:"progress"`
	Message       string         `json:"message"`
	Timestamp     string         `json:"timestamp"`
	Details       map[string]any `json:"details"`
	Error         *EngineError   `json:"error"`
}

type RunResult struct {
	ReportPath string
}

type Health struct {
	Ready  bool             `json:"ready"`
	Models []map[string]any `json:"models,omitempty"`
	Error  string           `json:"error,omitempty"`
}

func NewID() (string, error) {
	buffer := make([]byte, 16)
	if _, err := rand.Read(buffer); err != nil {
		return "", err
	}
	return hex.EncodeToString(buffer), nil
}

func ValidateSpec(spec JobSpec) error {
	if spec.ID == "" {
		return errors.New("job ID is required")
	}
	if !spec.Type.Valid() {
		return errors.New("unsupported job type")
	}
	expectedInputs := 1
	if spec.Type == JobTypeComparison {
		expectedInputs = 2
	}
	if len(spec.Inputs) != expectedInputs {
		return errors.New("unexpected input count")
	}
	if spec.OutputDir == "" {
		return errors.New("output directory is required")
	}
	for _, input := range spec.Inputs {
		if input.Name == "" || input.Path == "" {
			return errors.New("input name and path are required")
		}
	}
	return nil
}
