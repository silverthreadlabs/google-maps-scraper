package webrunner

import (
	"context"
	"encoding/csv"
	"encoding/json"
	"fmt"
	"io"
	"reflect"
	"sync"

	"github.com/gosom/scrapemate"
)

var _ scrapemate.ResultWriter = (*csvJSONTeeWriter)(nil)

// csvJSONTeeWriter consumes a single scrapemate result channel and writes each
// result to both a CSV file (preserving the legacy contract used by the web UI
// and existing downstream consumers) and an NDJSON file (one JSON-encoded entry
// per line, used by structured consumers that need the full Entry payload).
//
// It exists because scrapemate uses a single shared result channel — registering
// two ResultWriter implementations side-by-side would split the stream rather
// than fan it out. This writer is the single registered writer in webrunner.
type csvJSONTeeWriter struct {
	csvW    *csv.Writer
	jsonEnc *json.Encoder
	once    sync.Once
}

// newCsvJSONTeeWriter builds a tee writer that writes CSV rows to csvOut and
// NDJSON lines to jsonOut. The caller owns the lifecycle of both writers.
func newCsvJSONTeeWriter(csvOut io.Writer, jsonOut io.Writer) *csvJSONTeeWriter {
	return &csvJSONTeeWriter{
		csvW:    csv.NewWriter(csvOut),
		jsonEnc: json.NewEncoder(jsonOut),
	}
}

// Run consumes the result stream until it closes, writing each entry to both
// outputs. The first hard write error is returned and stops consumption.
func (t *csvJSONTeeWriter) Run(_ context.Context, in <-chan scrapemate.Result) error {
	for result := range in {
		elements, err := toCsvCapable(result.Data)
		if err != nil {
			return err
		}

		if len(elements) == 0 {
			continue
		}

		t.once.Do(func() {
			_ = t.csvW.Write(elements[0].CsvHeaders())
		})

		for _, element := range elements {
			if err := t.csvW.Write(element.CsvRow()); err != nil {
				return fmt.Errorf("csv write: %w", err)
			}

			if err := t.jsonEnc.Encode(element); err != nil {
				return fmt.Errorf("ndjson encode: %w", err)
			}
		}

		t.csvW.Flush()
	}

	return t.csvW.Error()
}

func toCsvCapable(data any) ([]scrapemate.CsvCapable, error) {
	if data == nil {
		return nil, nil
	}

	if reflect.TypeOf(data).Kind() == reflect.Slice {
		s := reflect.ValueOf(data)
		out := make([]scrapemate.CsvCapable, 0, s.Len())

		for i := 0; i < s.Len(); i++ {
			val := s.Index(i).Interface()

			element, ok := val.(scrapemate.CsvCapable)
			if !ok {
				return nil, fmt.Errorf("%w: unexpected element type: %T", scrapemate.ErrorNotCsvCapable, val)
			}

			out = append(out, element)
		}

		return out, nil
	}

	element, ok := data.(scrapemate.CsvCapable)
	if !ok {
		return nil, fmt.Errorf("%w: unexpected data type: %T", scrapemate.ErrorNotCsvCapable, data)
	}

	return []scrapemate.CsvCapable{element}, nil
}
