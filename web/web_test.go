package web

import (
	"context"
	"encoding/csv"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
)

type testJobRepo struct{}

func (testJobRepo) Get(context.Context, string) (Job, error)            { return Job{}, nil }
func (testJobRepo) Create(context.Context, *Job) error                  { return nil }
func (testJobRepo) Delete(context.Context, string) error                { return nil }
func (testJobRepo) Select(context.Context, SelectParams) ([]Job, error) { return nil, nil }
func (testJobRepo) Update(context.Context, *Job) error                  { return nil }

func TestDownloadCSVDefault(t *testing.T) {
	t.Parallel()

	const jobID = "18eafda3-53a9-4970-ac96-8f8dfc7011c3"

	tempDir := t.TempDir()
	expected := writeTestCSV(t, tempDir, jobID)

	srv := &Server{svc: NewService(testJobRepo{}, tempDir)}
	req := httptest.NewRequest(http.MethodGet, "/api/v1/jobs/"+jobID+"/download?id="+jobID, nil)
	req = requestWithID(req)
	rec := httptest.NewRecorder()

	srv.download(rec, req, downloadFormatCSV)

	res := rec.Result()
	defer res.Body.Close()

	if res.StatusCode != http.StatusOK {
		t.Fatalf("expected status %d, got %d", http.StatusOK, res.StatusCode)
	}

	if got := res.Header.Get("Content-Type"); got != "text/csv" {
		t.Fatalf("expected csv content type, got %q", got)
	}

	if got := rec.Body.String(); got != expected {
		t.Fatalf("expected csv body %q, got %q", expected, got)
	}
}

func TestDownloadJSONFormat(t *testing.T) {
	t.Parallel()

	const jobID = "18eafda3-53a9-4970-ac96-8f8dfc7011c3"

	tempDir := t.TempDir()
	writeTestCSV(t, tempDir, jobID)

	srv := &Server{svc: NewService(testJobRepo{}, tempDir)}
	req := httptest.NewRequest(http.MethodGet, "/api/v1/jobs/"+jobID+"/download?id="+jobID+"&format=json", nil)
	req = requestWithID(req)
	rec := httptest.NewRecorder()

	srv.download(rec, req, downloadFormatCSV)

	res := rec.Result()
	defer res.Body.Close()

	if res.StatusCode != http.StatusOK {
		t.Fatalf("expected status %d, got %d", http.StatusOK, res.StatusCode)
	}

	if got := res.Header.Get("Content-Type"); got != "application/json" {
		t.Fatalf("expected json content type, got %q", got)
	}

	var payload []map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &payload); err != nil {
		t.Fatalf("failed to decode json response: %v", err)
	}

	if len(payload) != 1 {
		t.Fatalf("expected 1 row, got %d", len(payload))
	}

	if got := payload[0]["title"]; got != "Cafe Central" {
		t.Fatalf("expected title %q, got %#v", "Cafe Central", got)
	}

	if got := payload[0]["review_count"]; got != float64(12) {
		t.Fatalf("expected review_count 12, got %#v", got)
	}

	openHours, ok := payload[0]["open_hours"].(map[string]any)
	if !ok {
		t.Fatalf("expected open_hours object, got %#v", payload[0]["open_hours"])
	}

	if got := openHours["mon"]; got == nil {
		t.Fatalf("expected monday hours, got %#v", openHours)
	}
}

func TestDownloadRejectsInvalidFormatOnAPI(t *testing.T) {
	t.Parallel()

	const jobID = "18eafda3-53a9-4970-ac96-8f8dfc7011c3"

	tempDir := t.TempDir()
	writeTestCSV(t, tempDir, jobID)

	srv := &Server{svc: NewService(testJobRepo{}, tempDir)}
	req := httptest.NewRequest(http.MethodGet, "/api/v1/jobs/"+jobID+"/download?id="+jobID+"&format=xml", nil)
	req = requestWithID(req)
	rec := httptest.NewRecorder()

	srv.download(rec, req, downloadFormatCSV)

	res := rec.Result()
	defer res.Body.Close()

	if res.StatusCode != http.StatusUnprocessableEntity {
		t.Fatalf("expected status %d, got %d", http.StatusUnprocessableEntity, res.StatusCode)
	}

	var payload apiError
	if err := json.Unmarshal(rec.Body.Bytes(), &payload); err != nil {
		t.Fatalf("failed to decode error response: %v", err)
	}

	if payload.Code != http.StatusUnprocessableEntity {
		t.Fatalf("expected error code %d, got %d", http.StatusUnprocessableEntity, payload.Code)
	}
}

func writeTestCSV(t *testing.T, dir, jobID string) string {
	t.Helper()

	filePath := filepath.Join(dir, jobID+".csv")

	file, err := os.Create(filePath)
	if err != nil {
		t.Fatalf("failed to create csv fixture: %v", err)
	}
	defer file.Close()

	writer := csv.NewWriter(file)

	records := [][]string{
		{"title", "review_count", "open_hours", "address"},
		{"Cafe Central", "12", `{"mon":["09:00-17:00"]}`, "123 Main St"},
	}

	for _, record := range records {
		if err := writer.Write(record); err != nil {
			t.Fatalf("failed to write csv fixture: %v", err)
		}
	}

	writer.Flush()
	if err := writer.Error(); err != nil {
		t.Fatalf("failed to flush csv fixture: %v", err)
	}

	data, err := os.ReadFile(filePath)
	if err != nil {
		t.Fatalf("failed to read csv fixture: %v", err)
	}

	return string(data)
}
