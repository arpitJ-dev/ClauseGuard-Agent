package main

import (
	"context"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"
	"time"

	"github.com/arpitJ-dev/ClauseGuard-Agent/apps/server/internal/api"
	"github.com/arpitJ-dev/ClauseGuard-Agent/apps/server/internal/config"
	"github.com/arpitJ-dev/ClauseGuard-Agent/apps/server/internal/engine"
	"github.com/arpitJ-dev/ClauseGuard-Agent/apps/server/internal/jobs"
	"github.com/arpitJ-dev/ClauseGuard-Agent/apps/server/internal/store"
)

func main() {
	signalContext, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	if err := run(signalContext); err != nil {
		slog.Error("ClauseGuard server stopped", "error", err)
		os.Exit(1)
	}
}

func run(runContext context.Context) error {
	settings, err := config.Load()
	if err != nil {
		return err
	}
	repository, err := store.Open(filepath.Join(settings.DataDir, "jobs.db"))
	if err != nil {
		return err
	}
	defer repository.Close()

	runner := &engine.CLIRunner{
		PythonExecutable: settings.PythonExecutable,
		Workspace:        settings.Workspace,
		MockModels:       settings.MockModels,
	}
	manager, err := jobs.New(repository, runner, jobs.Options{
		Timeout:           settings.JobTimeout,
		MaxConcurrentJobs: settings.MaxConcurrentJobs,
		MaxActiveJobs:     settings.MaxActiveJobs,
		DataDir:           settings.DataDir,
	})
	if err != nil {
		return err
	}
	handler, err := api.New(manager, api.Config{
		DataDir:        settings.DataDir,
		WebDir:         settings.WebDir,
		MaxUploadBytes: settings.MaxUploadBytes,
		AllowedOrigin:  settings.AllowedOrigin,
	})
	if err != nil {
		shutdownContext, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		return errors.Join(err, manager.Shutdown(shutdownContext))
	}

	httpServer := &http.Server{
		Addr:              settings.Address,
		Handler:           handler,
		ReadHeaderTimeout: 10 * time.Second,
		ReadTimeout:       2 * time.Minute,
		IdleTimeout:       60 * time.Second,
	}
	serverErrors := make(chan error, 1)
	go func() {
		slog.Info(
			"ClauseGuard control plane listening",
			"address", settings.Address,
			"web_dir", settings.WebDir,
			"mock_models", settings.MockModels,
		)
		serverErrors <- httpServer.ListenAndServe()
	}()

	var listenError error
	select {
	case <-runContext.Done():
	case err := <-serverErrors:
		if !errors.Is(err, http.ErrServerClosed) {
			listenError = err
		}
	}

	shutdownContext, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	serverShutdown := make(chan error, 1)
	go func() {
		serverShutdown <- httpServer.Shutdown(shutdownContext)
	}()
	managerError := manager.Shutdown(shutdownContext)
	serverError := <-serverShutdown
	return errors.Join(listenError, serverError, managerError)
}
