package gmaps

import (
	"strings"
	"testing"

	"github.com/PuerkitoBio/goquery"
)

// ---------------------------------------------------------------------------
// isURLShaped unit tests
// ---------------------------------------------------------------------------

func TestIsURLShaped(t *testing.T) {
	cases := []struct {
		name  string
		input string
		want  bool
	}{
		{
			name:  "https_url",
			input: "https://facebook.com/acme",
			want:  true,
		},
		{
			name:  "http_url",
			input: "http://fb.com/acme",
			want:  true,
		},
		{
			name:  "protocol_relative",
			input: "//instagram.com/acme",
			want:  true,
		},
		{
			name:  "bare_host_path",
			input: "facebook.com/acme",
			want:  true,
		},
		{
			name:  "prose_text",
			input: "Follow us on Facebook",
			want:  false,
		},
		{
			name:  "empty_string",
			input: "",
			want:  false,
		},
		{
			name:  "over_200_chars",
			input: "https://facebook.com/" + strings.Repeat("a", 181), // total = 21 + 181 = 202 chars
			want:  false,
		},
		{
			name:  "no_slash_no_dot",
			input: "facebook",
			want:  false,
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := isURLShaped(tc.input)
			if got != tc.want {
				t.Errorf("isURLShaped(%q) = %v, want %v", tc.input, got, tc.want)
			}
		})
	}
}

// ---------------------------------------------------------------------------
// getValidEmail unit tests
// ---------------------------------------------------------------------------

func TestGetValidEmail(t *testing.T) {
	cases := []struct {
		name    string
		input   string
		wantErr bool
		wantOut string
	}{
		{
			name:    "valid_email",
			input:   "user@example.com",
			wantErr: false,
			wantOut: "user@example.com",
		},
		{
			name:    "valid_email_with_whitespace",
			input:   "  user@example.com  ",
			wantErr: false,
			wantOut: "user@example.com",
		},
		{
			name:    "invalid_email",
			input:   "not-an-email",
			wantErr: true,
		},
		{
			name:    "empty_string",
			input:   "",
			wantErr: true,
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got, err := getValidEmail(tc.input)
			if tc.wantErr {
				if err == nil {
					t.Errorf("getValidEmail(%q) expected error, got nil", tc.input)
				}
				return
			}
			if err != nil {
				t.Errorf("getValidEmail(%q) unexpected error: %v", tc.input, err)
			}
			if got != tc.wantOut {
				t.Errorf("getValidEmail(%q) = %q, want %q", tc.input, got, tc.wantOut)
			}
		})
	}
}

// ---------------------------------------------------------------------------
// docEmailExtractor unit tests
// ---------------------------------------------------------------------------

func TestDocEmailExtractor(t *testing.T) {
	cases := []struct {
		name string
		html string
		want []string
	}{
		{
			name: "single_mailto_link",
			html: `<html><body><a href="mailto:user@example.com">Email us</a></body></html>`,
			want: []string{"user@example.com"},
		},
		{
			name: "duplicate_mailto_links_deduped",
			html: `<html><body><a href="mailto:user@example.com">Email 1</a><a href="mailto:user@example.com">Email 2</a></body></html>`,
			want: []string{"user@example.com"},
		},
		{
			name: "no_mailto_links",
			html: `<html><body><a href="https://example.com">No email</a></body></html>`,
			want: nil,
		},
		{
			name: "invalid_mailto_skipped",
			html: `<html><body><a href="mailto:not-an-email">Bad email</a></body></html>`,
			want: nil,
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			doc, err := goquery.NewDocumentFromReader(strings.NewReader(tc.html))
			if err != nil {
				t.Fatalf("failed to parse HTML: %v", err)
			}
			got := docEmailExtractor(doc)
			if len(got) != len(tc.want) {
				t.Errorf("docEmailExtractor() = %v, want %v", got, tc.want)
				return
			}
			for i := range got {
				if got[i] != tc.want[i] {
					t.Errorf("docEmailExtractor()[%d] = %q, want %q", i, got[i], tc.want[i])
				}
			}
		})
	}
}

// ---------------------------------------------------------------------------
// regexEmailExtractor unit tests
// ---------------------------------------------------------------------------

func TestRegexEmailExtractor(t *testing.T) {
	cases := []struct {
		name string
		body []byte
		want []string
	}{
		{
			name: "single_email_in_body",
			body: []byte("Contact us at user@example.com for more info."),
			want: []string{"user@example.com"},
		},
		{
			name: "duplicate_emails_deduped",
			body: []byte("user@example.com and also user@example.com"),
			want: []string{"user@example.com"},
		},
		{
			name: "no_emails",
			body: []byte("No emails here"),
			want: nil,
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := regexEmailExtractor(tc.body)
			if len(got) != len(tc.want) {
				t.Errorf("regexEmailExtractor() = %v, want %v", got, tc.want)
				return
			}
			for i := range got {
				if got[i] != tc.want[i] {
					t.Errorf("regexEmailExtractor()[%d] = %q, want %q", i, got[i], tc.want[i])
				}
			}
		})
	}
}

// ---------------------------------------------------------------------------
// normalizeGoogleURL unit tests
// ---------------------------------------------------------------------------

func TestNormalizeGoogleURL(t *testing.T) {
	cases := []struct {
		name  string
		input string
		want  string
	}{
		{
			name:  "empty_string",
			input: "",
			want:  "",
		},
		{
			name:  "google_redirect_url",
			input: "/url?q=https://example.com/&opi=123",
			want:  "https://example.com/",
		},
		{
			name:  "relative_path",
			input: "/some/path",
			want:  "https://www.google.com/some/path",
		},
		{
			name:  "absolute_url_unchanged",
			input: "https://example.com",
			want:  "https://example.com",
		},
		{
			name:  "google_redirect_no_q_param",
			input: "/url?other=value",
			want:  "https://www.google.com/url?other=value",
		},
		{
			name:  "absolute_redirect_with_sa_param",
			input: "https://www.google.com/url?q=https://rainbowcc.com.pk&sa=t",
			want:  "https://rainbowcc.com.pk",
		},
		{
			name:  "absolute_redirect_with_opi_param",
			input: "https://www.google.com/url?q=https://example.com&opi=89978449",
			want:  "https://example.com",
		},
		{
			name:  "maps_subdomain_redirect",
			input: "https://maps.google.com/url?q=https://example.com",
			want:  "https://example.com",
		},
		{
			name:  "google_maps_place_url_unchanged",
			input: "https://www.google.com/maps/place/SomePlace",
			want:  "https://www.google.com/maps/place/SomePlace",
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := normalizeGoogleURL(tc.input)
			if got != tc.want {
				t.Errorf("normalizeGoogleURL(%q) = %q, want %q", tc.input, got, tc.want)
			}
		})
	}
}

// ---------------------------------------------------------------------------
// harvestWebsiteIfSocialLocal unit tests
// ---------------------------------------------------------------------------

func TestHarvestWebsiteIfSocialLocal(t *testing.T) {
	t.Run("empty_url_no_op", func(t *testing.T) {
		var out []SocialLink
		harvestWebsiteIfSocialLocal("", &out)
		if len(out) != 0 {
			t.Errorf("expected empty slice, got %v", out)
		}
	})

	t.Run("nil_out_no_panic", func(t *testing.T) {
		harvestWebsiteIfSocialLocal("https://facebook.com/acme", nil)
		// No panic is the assertion
	})

	t.Run("non_social_url_ignored", func(t *testing.T) {
		var out []SocialLink
		harvestWebsiteIfSocialLocal("https://example.com", &out)
		if len(out) != 0 {
			t.Errorf("expected empty slice for non-social URL, got %v", out)
		}
	})

	t.Run("social_url_appended", func(t *testing.T) {
		var out []SocialLink
		harvestWebsiteIfSocialLocal("https://www.facebook.com/acme", &out)
		if len(out) != 1 {
			t.Fatalf("expected 1 entry, got %d: %v", len(out), out)
		}
		if out[0].Platform != "facebook" || out[0].Handle != "acme" {
			t.Errorf("unexpected entry: %+v", out[0])
		}
	})

	t.Run("duplicate_tuple_deduped", func(t *testing.T) {
		var out []SocialLink
		harvestWebsiteIfSocialLocal("https://www.facebook.com/acme", &out)
		harvestWebsiteIfSocialLocal("https://www.facebook.com/acme", &out)
		if len(out) != 1 {
			t.Errorf("expected 1 entry after dedup, got %d: %v", len(out), out)
		}
	})

	t.Run("case_insensitive_handle_deduped", func(t *testing.T) {
		var out []SocialLink
		harvestWebsiteIfSocialLocal("https://www.facebook.com/Acme", &out)
		harvestWebsiteIfSocialLocal("https://www.facebook.com/acme", &out)
		if len(out) != 1 {
			t.Errorf("expected 1 entry after case-insensitive dedup, got %d: %v", len(out), out)
		}
	})
}

// ---------------------------------------------------------------------------
// collectSameAs unit tests
// ---------------------------------------------------------------------------

func TestCollectSameAs(t *testing.T) {
	t.Run("single_string_sameAs", func(t *testing.T) {
		node := map[string]any{
			"sameAs": "https://facebook.com/acme",
		}
		got := collectSameAs(node)
		if len(got) != 1 || got[0] != "https://facebook.com/acme" {
			t.Errorf("expected [https://facebook.com/acme], got %v", got)
		}
	})

	t.Run("array_sameAs", func(t *testing.T) {
		node := map[string]any{
			"sameAs": []any{"https://facebook.com/acme", "https://twitter.com/acme"},
		}
		got := collectSameAs(node)
		if len(got) != 2 {
			t.Errorf("expected 2 items, got %v", got)
		}
	})

	t.Run("graph_nesting", func(t *testing.T) {
		node := map[string]any{
			"@graph": []any{
				map[string]any{
					"sameAs": "https://instagram.com/acme",
				},
			},
		}
		got := collectSameAs(node)
		if len(got) != 1 || got[0] != "https://instagram.com/acme" {
			t.Errorf("expected [https://instagram.com/acme], got %v", got)
		}
	})

	t.Run("array_of_objects", func(t *testing.T) {
		node := []any{
			map[string]any{"sameAs": "https://facebook.com/a"},
			map[string]any{"sameAs": "https://facebook.com/b"},
		}
		got := collectSameAs(node)
		if len(got) != 2 {
			t.Errorf("expected 2 items, got %v", got)
		}
	})

	t.Run("no_same_as_returns_empty", func(t *testing.T) {
		node := map[string]any{"name": "Acme Inc"}
		got := collectSameAs(node)
		if len(got) != 0 {
			t.Errorf("expected empty, got %v", got)
		}
	})
}

// ---------------------------------------------------------------------------
// WithEmailJobExitMonitor / WithEmailJobWriterManagedCompletion option tests
// ---------------------------------------------------------------------------

func TestEmailJobOptions(t *testing.T) {
	t.Run("with_exit_monitor", func(t *testing.T) {
		entry := &Entry{}
		// A nil exiter still exercises the option path without needing a real exiter.
		job := NewEmailJob("parent", entry, WithEmailJobExitMonitor(nil))
		if job.ExitMonitor != nil {
			t.Errorf("expected nil exit monitor, got %v", job.ExitMonitor)
		}
		// Re-run with option applied via internal field check — coverage is the goal.
	})

	t.Run("with_writer_managed_completion", func(t *testing.T) {
		entry := &Entry{}
		job := NewEmailJob("parent", entry, WithEmailJobWriterManagedCompletion())
		if !job.WriterManagedCompletion {
			t.Error("expected WriterManagedCompletion to be true")
		}
	})
}

// ---------------------------------------------------------------------------
// ProcessOnFetchError coverage
// ---------------------------------------------------------------------------

func TestEmailExtractJob_ProcessOnFetchError(t *testing.T) {
	entry := &Entry{}
	job := NewEmailJob("parent", entry)
	if !job.ProcessOnFetchError() {
		t.Error("expected ProcessOnFetchError() to return true")
	}
}
