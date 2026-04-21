package webrunner

import (
	"bytes"
	"context"
	"encoding/csv"
	"encoding/json"
	"errors"
	"io"
	"strings"
	"testing"

	"github.com/gosom/scrapemate"
)

type fakeEntry struct {
	ID    string
	Title string
}

func (f fakeEntry) CsvHeaders() []string { return []string{"id", "title"} }
func (f fakeEntry) CsvRow() []string     { return []string{f.ID, f.Title} }

func TestTeeWriter_WritesCSVAndNDJSON(t *testing.T) {
	t.Parallel()

	var csvBuf, jsonBuf bytes.Buffer

	w := newCsvJSONTeeWriter(&csvBuf, &jsonBuf)
	in := make(chan scrapemate.Result, 2)
	in <- scrapemate.Result{Data: fakeEntry{ID: "1", Title: "a"}}
	in <- scrapemate.Result{Data: fakeEntry{ID: "2", Title: "b,c"}}
	close(in)

	if err := w.Run(context.Background(), in); err != nil {
		t.Fatalf("Run: %v", err)
	}

	rows := readCSVAll(t, &csvBuf)
	if len(rows) != 3 {
		t.Fatalf("csv rows = %d, want 3 (header + 2 data)", len(rows))
	}

	if rows[0][0] != "id" || rows[0][1] != "title" {
		t.Errorf("csv header = %v", rows[0])
	}

	if rows[1][0] != "1" || rows[1][1] != "a" {
		t.Errorf("csv row 1 = %v", rows[1])
	}

	if rows[2][0] != "2" || rows[2][1] != "b,c" {
		t.Errorf("csv row 2 = %v", rows[2])
	}

	entries := decodeNDJSON(t, &jsonBuf)
	if len(entries) != 2 {
		t.Fatalf("ndjson lines = %d, want 2", len(entries))
	}

	if entries[0]["ID"] != "1" || entries[0]["Title"] != "a" {
		t.Errorf("ndjson entry 0 = %v", entries[0])
	}

	if entries[1]["ID"] != "2" || entries[1]["Title"] != "b,c" {
		t.Errorf("ndjson entry 1 = %v", entries[1])
	}
}

func TestTeeWriter_AcceptsSliceData(t *testing.T) {
	t.Parallel()

	var csvBuf, jsonBuf bytes.Buffer

	w := newCsvJSONTeeWriter(&csvBuf, &jsonBuf)
	in := make(chan scrapemate.Result, 1)
	in <- scrapemate.Result{Data: []fakeEntry{{ID: "1", Title: "a"}, {ID: "2", Title: "b"}}}
	close(in)

	if err := w.Run(context.Background(), in); err != nil {
		t.Fatalf("Run: %v", err)
	}

	rows := readCSVAll(t, &csvBuf)
	if len(rows) != 3 {
		t.Fatalf("csv rows = %d, want 3", len(rows))
	}

	entries := decodeNDJSON(t, &jsonBuf)
	if len(entries) != 2 {
		t.Fatalf("ndjson lines = %d, want 2", len(entries))
	}
}

func TestTeeWriter_RejectsNonCsvCapable(t *testing.T) {
	t.Parallel()

	var csvBuf, jsonBuf bytes.Buffer

	w := newCsvJSONTeeWriter(&csvBuf, &jsonBuf)
	in := make(chan scrapemate.Result, 1)
	in <- scrapemate.Result{Data: struct{ X int }{X: 1}}
	close(in)

	err := w.Run(context.Background(), in)
	if !errors.Is(err, scrapemate.ErrorNotCsvCapable) {
		t.Fatalf("err = %v, want ErrorNotCsvCapable", err)
	}
}

func TestTeeWriter_SkipsEmptySlice(t *testing.T) {
	t.Parallel()

	var csvBuf, jsonBuf bytes.Buffer

	w := newCsvJSONTeeWriter(&csvBuf, &jsonBuf)
	in := make(chan scrapemate.Result, 1)
	in <- scrapemate.Result{Data: []fakeEntry{}}
	close(in)

	if err := w.Run(context.Background(), in); err != nil {
		t.Fatalf("Run: %v", err)
	}

	if csvBuf.Len() != 0 {
		t.Errorf("csv buf not empty: %q", csvBuf.String())
	}

	if jsonBuf.Len() != 0 {
		t.Errorf("ndjson buf not empty: %q", jsonBuf.String())
	}
}

func TestTeeWriter_NDJSONErrorPropagates(t *testing.T) {
	t.Parallel()

	var csvBuf bytes.Buffer

	w := newCsvJSONTeeWriter(&csvBuf, failingWriter{})

	in := make(chan scrapemate.Result, 1)
	in <- scrapemate.Result{Data: fakeEntry{ID: "1", Title: "a"}}
	close(in)

	if err := w.Run(context.Background(), in); err == nil {
		t.Fatal("expected error from failing ndjson writer")
	}
}

type failingWriter struct{}

func (failingWriter) Write([]byte) (int, error) { return 0, errors.New("disk full") }

func readCSVAll(t *testing.T, r io.Reader) [][]string {
	t.Helper()

	reader := csv.NewReader(r)
	reader.FieldsPerRecord = -1

	rows, err := reader.ReadAll()
	if err != nil {
		t.Fatalf("csv read: %v", err)
	}

	return rows
}

func decodeNDJSON(t *testing.T, r io.Reader) []map[string]any {
	t.Helper()

	var out []map[string]any

	dec := json.NewDecoder(strings.NewReader(readAll(t, r)))
	for {
		var m map[string]any
		if err := dec.Decode(&m); err != nil {
			if errors.Is(err, io.EOF) {
				return out
			}

			t.Fatalf("ndjson decode: %v", err)
		}

		out = append(out, m)
	}
}

func readAll(t *testing.T, r io.Reader) string {
	t.Helper()

	b, err := io.ReadAll(r)
	if err != nil {
		t.Fatalf("read: %v", err)
	}

	return string(b)
}
