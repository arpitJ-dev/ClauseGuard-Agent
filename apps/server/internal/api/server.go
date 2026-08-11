package api

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"os"
	"path"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/arpitJ-dev/ClauseGuard-Agent/apps/server/internal/domain"
	"github.com/arpitJ-dev/ClauseGuard-Agent/apps/server/internal/jobs"
	"github.com/arpitJ-dev/ClauseGuard-Agent/apps/server/internal/store"
)

const healthTimeout = 5 * time.Second

var allowedExtensions = map[string]struct{}{
	".docx": {},
	".pdf":  {},
	".txt":  {},
}

var jobIDPattern = regexp.MustCompile(`^[a-f0-9]{32}$`)

type JobService interface {
	Submit(context.Context, domain.JobSpec) (domain.Job, error)
	Get(context.Context, string) (domain.Job, error)
	List(context.Context, int) ([]domain.Job, error)
	Cancel(context.Context, string) (domain.Job, error)
	Delete(context.Context, string) (domain.Job, bool, error)
	Subscribe(context.Context, string) (<-chan domain.Job, func(), error)
	Health(context.Context) (domain.Health, error)
}

type Config struct {
	DataDir        string
	WebDir         string
	MaxUploadBytes int64
	AllowedOrigin  string
}

type Server struct {
	service        JobService
	dataDir        string
	webDir         string
	maxUploadBytes int64
	allowedOrigin  string
}

type errorPayload struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}

type errorResponse struct {
	Error errorPayload `json:"error"`
}

func New(service JobService, config Config) (http.Handler, error) {
	if service == nil {
		return nil, errors.New("job service is required")
	}
	if config.MaxUploadBytes <= 0 {
		return nil, errors.New("maximum upload size must be positive")
	}
	dataDir, err := filepath.Abs(config.DataDir)
	if err != nil {
		return nil, fmt.Errorf("resolve API data directory: %w", err)
	}
	webDir := strings.TrimSpace(config.WebDir)
	if webDir != "" {
		webDir, err = filepath.Abs(webDir)
		if err != nil {
			return nil, fmt.Errorf("resolve web directory: %w", err)
		}
		indexPath := filepath.Join(webDir, "index.html")
		indexInfo, statErr := os.Stat(indexPath)
		if statErr != nil || indexInfo.IsDir() {
			return nil, fmt.Errorf("web bundle not found at %s; run the frontend build first", indexPath)
		}
	}
	server := &Server{
		service:        service,
		dataDir:        dataDir,
		webDir:         webDir,
		maxUploadBytes: config.MaxUploadBytes,
		allowedOrigin:  strings.TrimSpace(config.AllowedOrigin),
	}

	mux := http.NewServeMux()
	mux.HandleFunc("POST /api/v1/analyses", server.handleAnalysis)
	mux.HandleFunc("POST /api/v1/comparisons", server.handleComparison)
	mux.HandleFunc("GET /api/v1/jobs", server.handleListJobs)
	mux.HandleFunc("GET /api/v1/jobs/{id}", server.handleGetJob)
	mux.HandleFunc("GET /api/v1/jobs/{id}/events", server.handleJobEvents)
	mux.HandleFunc("GET /api/v1/jobs/{id}/report", server.handleReport)
	mux.HandleFunc("DELETE /api/v1/jobs/{id}", server.handleDeleteJob)
	mux.HandleFunc("GET /api/v1/health", server.handleHealth)
	mux.HandleFunc("/", server.handleWeb)
	return server.middleware(mux), nil
}

func (server *Server) handleWeb(writer http.ResponseWriter, request *http.Request) {
	if strings.HasPrefix(request.URL.Path, "/api/") || server.webDir == "" {
		writeError(writer, http.StatusNotFound, "route_not_found", "The requested route does not exist.")
		return
	}
	if request.Method != http.MethodGet && request.Method != http.MethodHead {
		writeError(writer, http.StatusMethodNotAllowed, "method_not_allowed", "The request method is not allowed.")
		return
	}

	cleaned := path.Clean("/" + request.URL.Path)
	if cleaned != "/" {
		relative := strings.TrimPrefix(cleaned, "/")
		target := filepath.Join(server.webDir, filepath.FromSlash(relative))
		if within(server.webDir, target) {
			if info, err := os.Stat(target); err == nil && !info.IsDir() {
				if strings.HasPrefix(cleaned, "/assets/") {
					writer.Header().Set("Cache-Control", "public, max-age=31536000, immutable")
				}
				http.ServeFile(writer, request, target)
				return
			}
		}
		if filepath.Ext(cleaned) != "" {
			http.NotFound(writer, request)
			return
		}
	}

	writer.Header().Set("Cache-Control", "no-cache")
	http.ServeFile(writer, request, filepath.Join(server.webDir, "index.html"))
}

func (server *Server) handleAnalysis(writer http.ResponseWriter, request *http.Request) {
	server.createJob(writer, request, domain.JobTypeAnalysis, []string{"document"})
}

func (server *Server) handleComparison(writer http.ResponseWriter, request *http.Request) {
	server.createJob(writer, request, domain.JobTypeComparison, []string{"original", "modified"})
}

func (server *Server) createJob(
	writer http.ResponseWriter,
	request *http.Request,
	jobType domain.JobType,
	fields []string,
) {
	jobID, err := domain.NewID()
	if err != nil {
		writeError(writer, http.StatusInternalServerError, "id_generation_failed", "Could not create a job identifier.")
		return
	}
	jobDir := filepath.Join(server.dataDir, "jobs", jobID)
	inputDir := filepath.Join(jobDir, "inputs")
	outputDir := filepath.Join(jobDir, "output")
	if err := os.MkdirAll(inputDir, 0o750); err != nil {
		writeError(writer, http.StatusInternalServerError, "storage_error", "Could not prepare job storage.")
		return
	}
	removeJobFiles := true
	defer func() {
		if removeJobFiles {
			_ = os.RemoveAll(jobDir)
		}
	}()

	request.Body = http.MaxBytesReader(writer, request.Body, server.maxUploadBytes)
	reader, err := request.MultipartReader()
	if err != nil {
		writeError(writer, http.StatusUnsupportedMediaType, "multipart_required", "Use multipart/form-data for document uploads.")
		return
	}
	inputs, err := server.readUploads(reader, inputDir, fields)
	if err != nil {
		server.writeUploadError(writer, err)
		return
	}
	if err := os.MkdirAll(outputDir, 0o750); err != nil {
		writeError(writer, http.StatusInternalServerError, "storage_error", "Could not prepare report storage.")
		return
	}

	job, err := server.service.Submit(request.Context(), domain.JobSpec{
		ID:        jobID,
		Type:      jobType,
		Inputs:    inputs,
		OutputDir: outputDir,
	})
	if err != nil {
		server.writeServiceError(writer, err)
		return
	}
	removeJobFiles = false
	writeJSON(writer, http.StatusAccepted, map[string]any{
		"job": job,
		"links": map[string]string{
			"self":   "/api/v1/jobs/" + job.ID,
			"events": "/api/v1/jobs/" + job.ID + "/events",
		},
	})
}

func (server *Server) readUploads(
	reader *multipart.Reader,
	inputDir string,
	fields []string,
) ([]domain.InputFile, error) {
	expected := make(map[string]bool, len(fields))
	for _, field := range fields {
		expected[field] = false
	}
	loaded := make(map[string]domain.InputFile, len(fields))
	for {
		part, err := reader.NextPart()
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			return nil, fmt.Errorf("read multipart upload: %w", err)
		}
		field := part.FormName()
		filename := part.FileName()
		if _, exists := expected[field]; !exists || filename == "" {
			_ = part.Close()
			return nil, fmt.Errorf("unexpected multipart field %q", field)
		}
		if expected[field] {
			_ = part.Close()
			return nil, fmt.Errorf("duplicate multipart field %q", field)
		}

		extension := strings.ToLower(filepath.Ext(filename))
		if _, allowed := allowedExtensions[extension]; !allowed {
			_ = part.Close()
			return nil, fmt.Errorf("unsupported file type %q", extension)
		}
		destination := filepath.Join(inputDir, field+extension)
		file, err := os.OpenFile(destination, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0o640)
		if err != nil {
			_ = part.Close()
			return nil, fmt.Errorf("create uploaded file: %w", err)
		}
		bytesWritten, copyError := io.Copy(file, part)
		closeError := file.Close()
		_ = part.Close()
		if copyError != nil {
			return nil, fmt.Errorf("store uploaded file: %w", copyError)
		}
		if closeError != nil {
			return nil, fmt.Errorf("close uploaded file: %w", closeError)
		}
		if bytesWritten == 0 {
			return nil, fmt.Errorf("uploaded file %q is empty", field)
		}
		expected[field] = true
		loaded[field] = domain.InputFile{Name: displayName(filename), Path: destination}
	}

	inputs := make([]domain.InputFile, 0, len(fields))
	for _, field := range fields {
		if !expected[field] {
			return nil, fmt.Errorf("missing multipart field %q", field)
		}
		inputs = append(inputs, loaded[field])
	}
	return inputs, nil
}

func (server *Server) handleListJobs(writer http.ResponseWriter, request *http.Request) {
	limit := 50
	if raw := request.URL.Query().Get("limit"); raw != "" {
		parsed, err := strconv.Atoi(raw)
		if err != nil || parsed <= 0 || parsed > 100 {
			writeError(writer, http.StatusBadRequest, "invalid_limit", "limit must be between 1 and 100.")
			return
		}
		limit = parsed
	}
	listed, err := server.service.List(request.Context(), limit)
	if err != nil {
		server.writeServiceError(writer, err)
		return
	}
	writeJSON(writer, http.StatusOK, map[string]any{"jobs": listed})
}

func (server *Server) handleGetJob(writer http.ResponseWriter, request *http.Request) {
	id, ok := pathJobID(writer, request)
	if !ok {
		return
	}
	job, err := server.service.Get(request.Context(), id)
	if err != nil {
		server.writeServiceError(writer, err)
		return
	}
	writeJSON(writer, http.StatusOK, map[string]any{"job": job})
}

func (server *Server) handleDeleteJob(writer http.ResponseWriter, request *http.Request) {
	id, ok := pathJobID(writer, request)
	if !ok {
		return
	}
	job, deleted, err := server.service.Delete(request.Context(), id)
	if err != nil {
		server.writeServiceError(writer, err)
		return
	}
	status := http.StatusOK
	if !deleted {
		status = http.StatusAccepted
	}
	writeJSON(writer, status, map[string]any{"job": job, "deleted": deleted})
}

func (server *Server) handleJobEvents(writer http.ResponseWriter, request *http.Request) {
	id, valid := pathJobID(writer, request)
	if !valid {
		return
	}
	flusher, ok := writer.(http.Flusher)
	if !ok {
		writeError(writer, http.StatusInternalServerError, "streaming_unavailable", "Streaming is unavailable.")
		return
	}
	updates, unsubscribe, err := server.service.Subscribe(request.Context(), id)
	if err != nil {
		server.writeServiceError(writer, err)
		return
	}
	defer unsubscribe()
	writer.Header().Set("Content-Type", "text/event-stream")
	writer.Header().Set("Cache-Control", "no-cache")
	writer.Header().Set("Connection", "keep-alive")
	writer.Header().Set("X-Accel-Buffering", "no")
	_, _ = io.WriteString(writer, "retry: 2000\n\n")
	flusher.Flush()

	keepAlive := time.NewTicker(15 * time.Second)
	defer keepAlive.Stop()
	for {
		select {
		case job, open := <-updates:
			if !open {
				return
			}
			payload, err := json.Marshal(job)
			if err != nil {
				return
			}
			_, _ = fmt.Fprintf(writer, "id: %d\nevent: job\ndata: %s\n\n", job.UpdatedAt.UnixNano(), payload)
			flusher.Flush()
			if job.Status.Terminal() {
				return
			}
		case <-keepAlive.C:
			_, _ = io.WriteString(writer, ": keep-alive\n\n")
			flusher.Flush()
		case <-request.Context().Done():
			return
		}
	}
}

func (server *Server) handleReport(writer http.ResponseWriter, request *http.Request) {
	id, ok := pathJobID(writer, request)
	if !ok {
		return
	}
	job, err := server.service.Get(request.Context(), id)
	if err != nil {
		server.writeServiceError(writer, err)
		return
	}
	if job.Status != domain.JobCompleted || job.ReportPath == "" {
		writeError(writer, http.StatusConflict, "report_unavailable", "The report is not available for this job.")
		return
	}
	if !within(server.dataDir, job.ReportPath) {
		writeError(writer, http.StatusInternalServerError, "unsafe_report_path", "The stored report path is invalid.")
		return
	}
	file, err := os.Open(job.ReportPath)
	if err != nil {
		writeError(writer, http.StatusNotFound, "report_missing", "The report file could not be found.")
		return
	}
	defer file.Close()
	info, err := file.Stat()
	if err != nil || info.IsDir() {
		writeError(writer, http.StatusNotFound, "report_missing", "The report file could not be found.")
		return
	}
	writer.Header().Set("Content-Type", "application/json; charset=utf-8")
	writer.Header().Set("Content-Disposition", `inline; filename="clauseguard-report.json"`)
	writer.Header().Set("Cache-Control", "no-store")
	http.ServeContent(writer, request, info.Name(), info.ModTime(), file)
}

func (server *Server) handleHealth(writer http.ResponseWriter, request *http.Request) {
	ctx, cancel := context.WithTimeout(request.Context(), healthTimeout)
	defer cancel()
	health, err := server.service.Health(ctx)
	status := http.StatusOK
	state := "ok"
	if err != nil || !health.Ready {
		status = http.StatusServiceUnavailable
		state = "unavailable"
	}
	writeJSON(writer, status, map[string]any{"status": state, "engine": health})
}

func (server *Server) middleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		writer.Header().Set("X-Content-Type-Options", "nosniff")
		writer.Header().Set("Referrer-Policy", "no-referrer")
		writer.Header().Set("X-Frame-Options", "DENY")
		writer.Header().Set("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
		writer.Header().Set("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
		origin := strings.TrimSpace(request.Header.Get("Origin"))
		if origin != "" {
			if !server.originAllowed(request, origin) {
				writeError(writer, http.StatusForbidden, "origin_not_allowed", "The request origin is not allowed.")
				return
			}
			writer.Header().Set("Access-Control-Allow-Origin", origin)
			writer.Header().Set("Vary", "Origin")
			writer.Header().Set("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
			writer.Header().Set("Access-Control-Allow-Headers", "Content-Type")
			if request.Method == http.MethodOptions {
				writer.WriteHeader(http.StatusNoContent)
				return
			}
		}
		defer func() {
			if recover() != nil {
				writeError(writer, http.StatusInternalServerError, "internal_error", "An unexpected server error occurred.")
			}
		}()
		next.ServeHTTP(writer, request)
	})
}

func (server *Server) originAllowed(request *http.Request, origin string) bool {
	if server.allowedOrigin != "" && origin == server.allowedOrigin {
		return true
	}
	scheme := "http"
	if request.TLS != nil {
		scheme = "https"
	}
	return origin == scheme+"://"+request.Host
}

func (server *Server) writeUploadError(writer http.ResponseWriter, err error) {
	var maxBytesError *http.MaxBytesError
	if errors.As(err, &maxBytesError) {
		writeError(writer, http.StatusRequestEntityTooLarge, "upload_too_large", "The upload exceeds the configured size limit.")
		return
	}
	message := err.Error()
	if strings.Contains(message, "unsupported file type") {
		writeError(writer, http.StatusUnsupportedMediaType, "unsupported_file_type", "Supported document types are .txt, .docx, and .pdf.")
		return
	}
	if strings.Contains(message, "create uploaded file") || strings.Contains(message, "store uploaded file") || strings.Contains(message, "close uploaded file") {
		writeError(writer, http.StatusInternalServerError, "storage_error", "Could not store the uploaded document.")
		return
	}
	writeError(writer, http.StatusBadRequest, "invalid_upload", message)
}

func (server *Server) writeServiceError(writer http.ResponseWriter, err error) {
	switch {
	case errors.Is(err, store.ErrNotFound):
		writeError(writer, http.StatusNotFound, "job_not_found", "The requested job does not exist.")
	case errors.Is(err, jobs.ErrConflict):
		writeError(writer, http.StatusConflict, "invalid_job_state", "The job state does not allow this operation.")
	case errors.Is(err, jobs.ErrUnsafePath):
		writeError(writer, http.StatusInternalServerError, "unsafe_job_path", "The job storage path is invalid.")
	case errors.Is(err, jobs.ErrCapacity):
		writer.Header().Set("Retry-After", "5")
		writeError(writer, http.StatusTooManyRequests, "queue_full", "The analysis queue is full. Retry shortly.")
	case errors.Is(err, jobs.ErrShuttingDown):
		writer.Header().Set("Retry-After", "5")
		writeError(writer, http.StatusServiceUnavailable, "server_shutting_down", "The analysis service is shutting down.")
	default:
		writeError(writer, http.StatusInternalServerError, "service_error", "The job operation could not be completed.")
	}
}

func writeError(writer http.ResponseWriter, status int, code, message string) {
	writeJSON(writer, status, errorResponse{Error: errorPayload{Code: code, Message: message}})
}

func writeJSON(writer http.ResponseWriter, status int, payload any) {
	writer.Header().Set("Content-Type", "application/json; charset=utf-8")
	writer.WriteHeader(status)
	_ = json.NewEncoder(writer).Encode(payload)
}

func pathJobID(writer http.ResponseWriter, request *http.Request) (string, bool) {
	id := request.PathValue("id")
	if !jobIDPattern.MatchString(id) {
		writeError(writer, http.StatusBadRequest, "invalid_job_id", "The job ID is invalid.")
		return "", false
	}
	return id, true
}

func displayName(name string) string {
	name = path.Base(strings.ReplaceAll(strings.TrimSpace(name), "\\", "/"))
	runes := []rune(name)
	if len(runes) > 255 {
		name = string(runes[:255])
	}
	return name
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
