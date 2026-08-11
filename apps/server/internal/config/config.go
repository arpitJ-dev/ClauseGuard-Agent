package config

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"github.com/joho/godotenv"
)

const (
	defaultAddress           = "127.0.0.1:8080"
	defaultMaxUploadBytes    = int64(25 << 20)
	defaultJobTimeout        = 10 * time.Minute
	defaultConcurrentJobs    = 2
	defaultActiveJobs        = 20
	workspaceEnvironmentName = "CLAUSEGUARD_WORKSPACE"
)

type Config struct {
	Address           string
	PythonExecutable  string
	Workspace         string
	DataDir           string
	MaxUploadBytes    int64
	JobTimeout        time.Duration
	MaxConcurrentJobs int
	MaxActiveJobs     int
	MockModels        bool
	AllowedOrigin     string
}

func Load() (Config, error) {
	workspace, err := workspacePath()
	if err != nil {
		return Config{}, err
	}
	if err := loadEnvironment(workspace); err != nil {
		return Config{}, err
	}

	dataDir := strings.TrimSpace(os.Getenv("CLAUSEGUARD_DATA_DIR"))
	if dataDir == "" {
		dataDir = filepath.Join(workspace, ".clauseguard")
	} else if !filepath.IsAbs(dataDir) {
		dataDir = filepath.Join(workspace, dataDir)
	}
	dataDir, err = filepath.Abs(dataDir)
	if err != nil {
		return Config{}, fmt.Errorf("resolve data directory: %w", err)
	}

	maxUploadBytes, err := positiveInt64("CLAUSEGUARD_MAX_UPLOAD_BYTES", defaultMaxUploadBytes)
	if err != nil {
		return Config{}, err
	}
	jobTimeout, err := positiveDuration("CLAUSEGUARD_JOB_TIMEOUT", defaultJobTimeout)
	if err != nil {
		return Config{}, err
	}
	maxConcurrentJobs, err := positiveInt("CLAUSEGUARD_MAX_CONCURRENT_JOBS", defaultConcurrentJobs)
	if err != nil {
		return Config{}, err
	}
	maxActiveJobs, err := positiveInt("CLAUSEGUARD_MAX_ACTIVE_JOBS", defaultActiveJobs)
	if err != nil {
		return Config{}, err
	}
	if maxActiveJobs < maxConcurrentJobs {
		return Config{}, errors.New("CLAUSEGUARD_MAX_ACTIVE_JOBS cannot be lower than CLAUSEGUARD_MAX_CONCURRENT_JOBS")
	}
	mockModels, err := boolean("CLAUSEGUARD_MOCK_MODELS", true)
	if err != nil {
		return Config{}, err
	}

	python := strings.TrimSpace(os.Getenv("CLAUSEGUARD_PYTHON"))
	if python == "" {
		python = "python"
	}
	address := strings.TrimSpace(os.Getenv("CLAUSEGUARD_SERVER_ADDR"))
	if address == "" {
		address = defaultAddress
	}

	return Config{
		Address:           address,
		PythonExecutable:  python,
		Workspace:         workspace,
		DataDir:           dataDir,
		MaxUploadBytes:    maxUploadBytes,
		JobTimeout:        jobTimeout,
		MaxConcurrentJobs: maxConcurrentJobs,
		MaxActiveJobs:     maxActiveJobs,
		MockModels:        mockModels,
		AllowedOrigin:     strings.TrimSpace(os.Getenv("CLAUSEGUARD_ALLOWED_ORIGIN")),
	}, nil
}

func loadEnvironment(workspace string) error {
	err := godotenv.Load(filepath.Join(workspace, ".env"))
	if err != nil && !errors.Is(err, os.ErrNotExist) {
		return fmt.Errorf("load workspace .env: %w", err)
	}
	return nil
}

func workspacePath() (string, error) {
	configured := strings.TrimSpace(os.Getenv(workspaceEnvironmentName))
	if configured != "" {
		absolute, err := filepath.Abs(configured)
		if err != nil {
			return "", fmt.Errorf("resolve %s: %w", workspaceEnvironmentName, err)
		}
		if !isWorkspace(absolute) {
			return "", fmt.Errorf("%s does not contain pyproject.toml and clauseguard", workspaceEnvironmentName)
		}
		return absolute, nil
	}

	current, err := os.Getwd()
	if err != nil {
		return "", fmt.Errorf("get working directory: %w", err)
	}
	for {
		if isWorkspace(current) {
			return current, nil
		}
		parent := filepath.Dir(current)
		if parent == current {
			break
		}
		current = parent
	}
	return "", errors.New("ClauseGuard workspace not found; set CLAUSEGUARD_WORKSPACE")
}

func isWorkspace(path string) bool {
	if _, err := os.Stat(filepath.Join(path, "pyproject.toml")); err != nil {
		return false
	}
	info, err := os.Stat(filepath.Join(path, "clauseguard"))
	return err == nil && info.IsDir()
}

func positiveInt(name string, fallback int) (int, error) {
	raw := strings.TrimSpace(os.Getenv(name))
	if raw == "" {
		return fallback, nil
	}
	value, err := strconv.Atoi(raw)
	if err != nil || value <= 0 {
		return 0, fmt.Errorf("%s must be a positive integer", name)
	}
	return value, nil
}

func positiveInt64(name string, fallback int64) (int64, error) {
	raw := strings.TrimSpace(os.Getenv(name))
	if raw == "" {
		return fallback, nil
	}
	value, err := strconv.ParseInt(raw, 10, 64)
	if err != nil || value <= 0 {
		return 0, fmt.Errorf("%s must be a positive integer", name)
	}
	return value, nil
}

func positiveDuration(name string, fallback time.Duration) (time.Duration, error) {
	raw := strings.TrimSpace(os.Getenv(name))
	if raw == "" {
		return fallback, nil
	}
	value, err := time.ParseDuration(raw)
	if err != nil || value <= 0 {
		return 0, fmt.Errorf("%s must be a positive duration", name)
	}
	return value, nil
}

func boolean(name string, fallback bool) (bool, error) {
	raw := strings.TrimSpace(os.Getenv(name))
	if raw == "" {
		return fallback, nil
	}
	value, err := strconv.ParseBool(raw)
	if err != nil {
		return false, fmt.Errorf("%s must be true or false", name)
	}
	return value, nil
}
