package domain

import (
	"path/filepath"
	"testing"
)

func TestNewIDIsOpaqueAndUnique(t *testing.T) {
	first, err := NewID()
	if err != nil {
		t.Fatal(err)
	}
	second, err := NewID()
	if err != nil {
		t.Fatal(err)
	}
	if len(first) != 32 || len(second) != 32 {
		t.Fatalf("expected 32-character identifiers, got %q and %q", first, second)
	}
	if first == second {
		t.Fatal("generated duplicate identifiers")
	}
}

func TestValidateSpecEnforcesInputCount(t *testing.T) {
	analysis := JobSpec{
		ID:        "analysis-id",
		Type:      JobTypeAnalysis,
		Inputs:    []InputFile{{Name: "contract.txt", Path: filepath.Join("tmp", "contract.txt")}},
		OutputDir: filepath.Join("tmp", "output"),
	}
	if err := ValidateSpec(analysis); err != nil {
		t.Fatalf("valid analysis rejected: %v", err)
	}
	analysis.Inputs = append(analysis.Inputs, InputFile{Name: "extra.txt", Path: "extra.txt"})
	if err := ValidateSpec(analysis); err == nil {
		t.Fatal("analysis with two inputs was accepted")
	}
}

func TestTerminalStatuses(t *testing.T) {
	for _, status := range []JobStatus{JobCompleted, JobFailed, JobCancelled, JobTimedOut} {
		if !status.Terminal() {
			t.Fatalf("expected %q to be terminal", status)
		}
	}
	for _, status := range []JobStatus{JobQueued, JobRunning} {
		if status.Terminal() {
			t.Fatalf("expected %q to be active", status)
		}
	}
}
