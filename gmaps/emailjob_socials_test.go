package gmaps_test

import (
	"context"
	"encoding/json"
	"os"
	"strings"
	"testing"

	"github.com/PuerkitoBio/goquery"
	"github.com/gosom/scrapemate"
	"github.com/stretchr/testify/require"

	"github.com/gosom/google-maps-scraper/gmaps"
)

// buildPlaceJSON returns a minimal `APP_INITIALIZATION_STATE`-style payload
// accepted by gmaps.EntryFromJSON. Only the fields touched by our assertions
// are populated; getNthElementAndCast is gracefully forgiving on missing
// indices. website is placed at darray[7][0], which is where
// EntryFromJSON reads entry.WebSite.
func buildPlaceJSON(t *testing.T, website string) []byte {
	t.Helper()

	// darray must be large enough that EntryFromJSON's deepest reads
	// (index 203) don't panic. getNthElementAndCast handles missing
	// higher indices by returning zero values.
	const darrayLen = 210

	darray := make([]any, darrayLen)
	darray[7] = []any{website}

	// Minimal outer wrapper: jd[6] == darray. len(jd) >= 7 required.
	jd := make([]any, 7)
	jd[6] = darray

	raw, err := json.Marshal(jd)
	require.NoError(t, err)

	return raw
}

// loadDoc parses an HTML fixture into a *goquery.Document.
func loadDoc(t *testing.T, path string) *goquery.Document {
	t.Helper()

	fd, err := os.Open(path)
	require.NoError(t, err)

	defer fd.Close()

	doc, err := goquery.NewDocumentFromReader(fd)
	require.NoError(t, err)

	return doc
}

// ---------------------------------------------------------------------------
// Path A: entry.WebSite IS a social URL → PlaceJob.Process must NOT spawn an
// EmailExtractJob AND entry.Socials must contain the platform.
// ---------------------------------------------------------------------------

func TestPlaceJob_Process_WebsiteIsSocial_NoEmailJob_SocialsPopulated(t *testing.T) {
	cases := []struct {
		name             string
		website          string
		expectedPlatform string
		expectedHandle   string
		expectedPathType string
	}{
		{
			name:             "facebook",
			website:          "https://www.facebook.com/acmeinc",
			expectedPlatform: "facebook",
			expectedHandle:   "acmeinc",
			expectedPathType: "",
		},
		{
			name:             "linkedin-company",
			website:          "https://www.linkedin.com/company/acme",
			expectedPlatform: "linkedin",
			expectedHandle:   "acme",
			expectedPathType: "company",
		},
		{
			name:             "instagram-typo-regression",
			website:          "https://www.instagram.com/acme",
			expectedPlatform: "instagram",
			expectedHandle:   "acme",
			expectedPathType: "",
		},
		{
			name:             "youtube-handle",
			website:          "https://www.youtube.com/@acme",
			expectedPlatform: "youtube",
			expectedHandle:   "acme",
			expectedPathType: "@",
		},
		{
			name:             "tiktok",
			website:          "https://www.tiktok.com/@acme",
			expectedPlatform: "tiktok",
			expectedHandle:   "acme",
			expectedPathType: "",
		},
		{
			name:             "pinterest",
			website:          "https://www.pinterest.com/acme",
			expectedPlatform: "pinterest",
			expectedHandle:   "acme",
			expectedPathType: "",
		},
		{
			name:             "whatsapp",
			website:          "https://wa.me/1234567890",
			expectedPlatform: "whatsapp",
			expectedHandle:   "1234567890",
			expectedPathType: "",
		},
		{
			name:             "telegram",
			website:          "https://t.me/acme",
			expectedPlatform: "telegram",
			expectedHandle:   "acme",
			expectedPathType: "",
		},
		{
			name:             "threads",
			website:          "https://www.threads.net/@acme",
			expectedPlatform: "threads",
			expectedHandle:   "acme",
			expectedPathType: "",
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			raw := buildPlaceJSON(t, tc.website)

			job := gmaps.NewPlaceJob("parent-id", "en", "https://maps.google.com/", true, false)

			resp := &scrapemate.Response{
				Meta: map[string]any{"json": raw},
			}

			result, next, err := job.Process(context.Background(), resp)
			require.NoError(t, err)
			require.Empty(t, next, "no EmailExtractJob must be spawned for a social website")

			entry, ok := result.(*gmaps.Entry)
			require.True(t, ok, "result should be *gmaps.Entry when no email job spawns")

			require.Len(t, entry.Socials, 1)
			require.Equal(t, tc.expectedPlatform, entry.Socials[0].Platform)
			require.Equal(t, tc.expectedHandle, entry.Socials[0].Handle)
			require.Equal(t, tc.expectedPathType, entry.Socials[0].PathType)
		})
	}
}

// ---------------------------------------------------------------------------
// Path B: EmailExtractJob.Process inline extraction from a fetched document.
// ---------------------------------------------------------------------------

func TestEmailExtractJob_Process_ExtractsAllSources(t *testing.T) {
	doc := loadDoc(t, "testdata/socials_full.html")

	entry := &gmaps.Entry{WebSite: "https://acme.example.com"}
	job := gmaps.NewEmailJob("parent-id", entry)

	resp := &scrapemate.Response{Document: doc}

	_, next, err := job.Process(context.Background(), resp)
	require.NoError(t, err)
	require.Empty(t, next)

	// Must contain exactly one entry per platform: facebook, linkedin, x
	// (from twitter.com→x host canonicalization), and instagram.
	byPlatform := indexByPlatform(entry.Socials)

	require.Contains(t, byPlatform, "facebook")
	require.Equal(t, "acme", byPlatform["facebook"].Handle)
	require.Equal(t, "", byPlatform["facebook"].PathType)

	require.Contains(t, byPlatform, "linkedin")
	require.Equal(t, "acme", byPlatform["linkedin"].Handle)
	require.Equal(t, "company", byPlatform["linkedin"].PathType)

	require.Contains(t, byPlatform, "x")
	require.Equal(t, "acme", byPlatform["x"].Handle)
	require.Equal(t, "", byPlatform["x"].PathType)

	require.Contains(t, byPlatform, "instagram")
	require.Equal(t, "acme", byPlatform["instagram"].Handle)
	require.Equal(t, "", byPlatform["instagram"].PathType)

	require.Len(t, entry.Socials, 4, "expected exactly 4 platforms, got %+v", entry.Socials)
}

func TestEmailExtractJob_Process_DuplicateAnchorsDedupe(t *testing.T) {
	doc := loadDoc(t, "testdata/socials_dup_anchors.html")

	entry := &gmaps.Entry{}
	job := gmaps.NewEmailJob("parent-id", entry)

	resp := &scrapemate.Response{Document: doc}

	_, _, err := job.Process(context.Background(), resp)
	require.NoError(t, err)

	require.Len(t, entry.Socials, 1)
	require.Equal(t, "facebook", entry.Socials[0].Platform)
	require.Equal(t, "acme", entry.Socials[0].Handle)
}

func TestEmailExtractJob_Process_PlatformPrecedenceGmapsWins(t *testing.T) {
	doc := loadDoc(t, "testdata/socials_precedence.html")

	// Simulate HarvestWebsiteIfSocial having already populated entry.Socials
	// from entry.WebSite in PlaceJob.Process.
	entry := &gmaps.Entry{
		Socials: []gmaps.SocialLink{
			{Platform: "facebook", Handle: "gmapsvalue", PathType: ""},
		},
	}
	job := gmaps.NewEmailJob("parent-id", entry)

	resp := &scrapemate.Response{Document: doc}

	_, _, err := job.Process(context.Background(), resp)
	require.NoError(t, err)

	// Platform-level precedence: the Google Maps value must survive; the
	// footer facebook link must NOT be appended even though the handle
	// differs ("footerlink" vs "gmapsvalue").
	require.Len(t, entry.Socials, 1)
	require.Equal(t, "facebook", entry.Socials[0].Platform)
	require.Equal(t, "gmapsvalue", entry.Socials[0].Handle)
}

func TestEmailExtractJob_Process_MalformedJSONLDLoggedAndSkipped(t *testing.T) {
	doc := loadDoc(t, "testdata/socials_malformed_jsonld.html")

	entry := &gmaps.Entry{}
	job := gmaps.NewEmailJob("parent-id", entry)

	resp := &scrapemate.Response{Document: doc}

	_, _, err := job.Process(context.Background(), resp)
	require.NoError(t, err, "malformed JSON-LD must never cause Process to return an error")

	// The anchor on the same page must still have been extracted.
	require.Len(t, entry.Socials, 1)
	require.Equal(t, "instagram", entry.Socials[0].Platform)
	require.Equal(t, "acme", entry.Socials[0].Handle)
}

func TestEmailExtractJob_Process_AggregatorHostGoesToSocialsRaw(t *testing.T) {
	doc := loadDoc(t, "testdata/socials_aggregator.html")

	entry := &gmaps.Entry{}
	job := gmaps.NewEmailJob("parent-id", entry)

	resp := &scrapemate.Response{Document: doc}

	_, _, err := job.Process(context.Background(), resp)
	require.NoError(t, err)

	require.Empty(t, entry.Socials, "aggregators must not be added to Socials")
	require.Equal(t, []string{"https://linktr.ee/acme"}, entry.SocialsRaw)
}

func TestEmailExtractJob_Process_AggregatorDedupByExactString(t *testing.T) {
	doc := loadDoc(t, "testdata/socials_aggregator_dup.html")

	entry := &gmaps.Entry{}
	job := gmaps.NewEmailJob("parent-id", entry)

	resp := &scrapemate.Response{Document: doc}

	_, _, err := job.Process(context.Background(), resp)
	require.NoError(t, err)

	require.Equal(t, []string{"https://linktr.ee/acme"}, entry.SocialsRaw)
}

func TestEmailExtractJob_Process_NoSocialsLeavesEntryUntouched(t *testing.T) {
	doc := loadDoc(t, "testdata/socials_empty.html")

	entry := &gmaps.Entry{}
	job := gmaps.NewEmailJob("parent-id", entry)

	resp := &scrapemate.Response{Document: doc}

	_, _, err := job.Process(context.Background(), resp)
	require.NoError(t, err)

	require.Empty(t, entry.Socials)
	require.Empty(t, entry.SocialsRaw)
}

func TestEmailExtractJob_Process_RespErrorEarlyReturnLeavesEntryUntouched(t *testing.T) {
	doc := loadDoc(t, "testdata/socials_full.html")

	entry := &gmaps.Entry{}
	job := gmaps.NewEmailJob("parent-id", entry)

	resp := &scrapemate.Response{
		Document: doc,
		Error:    context.DeadlineExceeded,
	}

	_, _, err := job.Process(context.Background(), resp)
	require.NoError(t, err)

	require.Empty(t, entry.Socials, "resp.Error must short-circuit before extraction")
	require.Empty(t, entry.SocialsRaw)
}

// ---------------------------------------------------------------------------
// Regression: IsWebsiteValidForEmail returns false for instagram.com (old
// code had a "instragram" typo that let instagram leak through).
// ---------------------------------------------------------------------------

func TestEntry_IsWebsiteValidForEmail_InstagramTypoRegression(t *testing.T) {
	entry := &gmaps.Entry{WebSite: "https://www.instagram.com/foo"}

	require.False(t, entry.IsWebsiteValidForEmail(),
		"instagram.com must be gated by IsSocialHost — old code's typo'd "+
			"\"instragram\" blacklist let real instagram.com leak through")
}

// indexByPlatform returns a map keyed by Platform for ergonomic lookup in
// assertions. Each platform is expected to appear exactly once on the input.
func indexByPlatform(links []gmaps.SocialLink) map[string]gmaps.SocialLink {
	out := make(map[string]gmaps.SocialLink, len(links))
	for _, l := range links {
		out[l.Platform] = l
	}

	return out
}

// ---------------------------------------------------------------------------
// Text-label fallback: anchor visible text is used when href doesn't match.
// ---------------------------------------------------------------------------

// parseInlineHTML is a test helper that builds a *goquery.Document from an
// inline HTML string so fixture tests don't need separate files on disk.
func parseInlineHTML(t *testing.T, html string) *goquery.Document {
	t.Helper()

	doc, err := goquery.NewDocumentFromReader(strings.NewReader(html))
	require.NoError(t, err)

	return doc
}

func TestExtractSocialsFromDoc_AnchorTextFallback(t *testing.T) {
	cases := []struct {
		name          string
		html          string
		wantPlatform  string
		wantHandle    string
		wantAbsent    string // platform that must NOT appear (empty = no check)
		wantNoSocials bool
	}{
		{
			name:         "href_hash_text_is_facebook_url",
			html:         `<html><body><a href="#">https://facebook.com/acmeinc</a></body></html>`,
			wantPlatform: "facebook",
			wantHandle:   "acmeinc",
		},
		{
			name:         "href_javascript_void_text_is_instagram_url",
			html:         `<html><body><a href="javascript:void(0)">https://instagram.com/acmeinc</a></body></html>`,
			wantPlatform: "instagram",
			wantHandle:   "acmeinc",
		},
		{
			name:         "no_href_attr_text_is_bare_facebook_url",
			html:         `<html><body><a>facebook.com/acmeinc</a></body></html>`,
			wantPlatform: "facebook",
			wantHandle:   "acmeinc",
		},
		{
			name:         "href_wins_text_ghost_skipped",
			html:         `<html><body><a href="https://facebook.com/realowner">https://facebook.com/textghost</a></body></html>`,
			wantPlatform: "facebook",
			wantHandle:   "realowner",
		},
		{
			name:          "href_hash_prose_text_no_social",
			html:          `<html><body><a href="#">Follow us on Facebook</a></body></html>`,
			wantNoSocials: true,
		},
		{
			name: "href_hash_text_over_200_chars_no_social",
			// A 250-char https:// URL is URL-shaped but must be rejected by isURLShaped len cap.
			html:          `<html><body><a href="#">https://facebook.com/` + strings.Repeat("a", 230) + `</a></body></html>`,
			wantNoSocials: true,
		},
		{
			name:          "href_hash_text_not_url_shaped_no_social",
			html:          `<html><body><a href="#">not-a-url</a></body></html>`,
			wantNoSocials: true,
		},
		{
			// href hits facebook; text says instagram — lazy skip means instagram never processed.
			name:         "href_hit_text_instagram_lazy_skip",
			html:         `<html><body><a href="https://facebook.com/real">https://instagram.com/text</a></body></html>`,
			wantPlatform: "facebook",
			wantHandle:   "real",
			wantAbsent:   "instagram",
		},
		{
			// No href attribute at all (exists=false); text branch must run.
			name:         "no_href_attr_text_is_twitter_url",
			html:         `<html><body><a>https://twitter.com/acmeinc</a></body></html>`,
			wantPlatform: "x",
			wantHandle:   "acmeinc",
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			doc := parseInlineHTML(t, tc.html)
			entry := &gmaps.Entry{}
			job := gmaps.NewEmailJob("parent-id", entry)
			resp := &scrapemate.Response{Document: doc}

			_, _, err := job.Process(context.Background(), resp)
			require.NoError(t, err)

			byPlatform := indexByPlatform(entry.Socials)

			if tc.wantNoSocials {
				require.Empty(t, entry.Socials, "expected no socials, got %+v", entry.Socials)
				return
			}

			require.Contains(t, byPlatform, tc.wantPlatform,
				"expected platform %q in socials %+v", tc.wantPlatform, entry.Socials)
			require.Equal(t, tc.wantHandle, byPlatform[tc.wantPlatform].Handle)

			if tc.wantAbsent != "" {
				require.NotContains(t, byPlatform, tc.wantAbsent,
					"platform %q must be absent (lazy-skip), got %+v", tc.wantAbsent, entry.Socials)
			}
		})
	}
}
