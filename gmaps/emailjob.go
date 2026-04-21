package gmaps

import (
	"context"
	"encoding/json"
	"net/url"
	"strings"

	"github.com/PuerkitoBio/goquery"
	"github.com/google/uuid"
	"github.com/gosom/scrapemate"
	"github.com/mcnijman/go-emailaddress"

	"github.com/gosom/google-maps-scraper/exiter"
	"github.com/gosom/google-maps-scraper/gmaps/socials"
)

type EmailExtractJobOptions func(*EmailExtractJob)

type EmailExtractJob struct {
	scrapemate.Job

	Entry                   *Entry
	ExitMonitor             exiter.Exiter
	WriterManagedCompletion bool
}

func NewEmailJob(parentID string, entry *Entry, opts ...EmailExtractJobOptions) *EmailExtractJob {
	const (
		defaultPrio       = scrapemate.PriorityHigh
		defaultMaxRetries = 0
	)

	job := EmailExtractJob{
		Job: scrapemate.Job{
			ID:         uuid.New().String(),
			ParentID:   parentID,
			Method:     "GET",
			URL:        normalizeGoogleURL(entry.WebSite),
			MaxRetries: defaultMaxRetries,
			Priority:   defaultPrio,
		},
	}

	job.Entry = entry

	for _, opt := range opts {
		opt(&job)
	}

	return &job
}

func WithEmailJobExitMonitor(exitMonitor exiter.Exiter) EmailExtractJobOptions {
	return func(j *EmailExtractJob) {
		j.ExitMonitor = exitMonitor
	}
}

func WithEmailJobWriterManagedCompletion() EmailExtractJobOptions {
	return func(j *EmailExtractJob) {
		j.WriterManagedCompletion = true
	}
}

func (j *EmailExtractJob) Process(ctx context.Context, resp *scrapemate.Response) (any, []scrapemate.IJob, error) {
	defer func() {
		resp.Document = nil
		resp.Body = nil
	}()

	defer func() {
		if j.ExitMonitor != nil && !j.WriterManagedCompletion {
			j.ExitMonitor.IncrPlacesCompleted(1)
		}
	}()

	log := scrapemate.GetLoggerFromContext(ctx)

	log.Info("Processing email job", "url", j.URL)

	// if html fetch failed just return
	if resp.Error != nil {
		return j.Entry, nil, nil
	}

	doc, ok := resp.Document.(*goquery.Document)
	if !ok {
		return j.Entry, nil, nil
	}

	// Extract socials from the fetched document BEFORE the defer nils doc.
	// Anchors → JSON-LD sameAs → OG meta. Dedups into j.Entry.Socials via
	// platform-level precedence (Google Maps wins). Aggregator hosts go
	// into j.Entry.SocialsRaw for future triage. Malformed JSON-LD is
	// logged at debug and skipped — never returns an error.
	extractSocialsFromDoc(ctx, doc, j.Entry)

	emails := docEmailExtractor(doc)
	if len(emails) == 0 {
		emails = regexEmailExtractor(resp.Body)
	}

	j.Entry.Emails = emails

	return j.Entry, nil, nil
}

func (j *EmailExtractJob) ProcessOnFetchError() bool {
	return true
}

func docEmailExtractor(doc *goquery.Document) []string {
	seen := map[string]bool{}

	var emails []string

	doc.Find("a[href^='mailto:']").Each(func(_ int, s *goquery.Selection) {
		mailto, exists := s.Attr("href")
		if exists {
			value := strings.TrimPrefix(mailto, "mailto:")
			if email, err := getValidEmail(value); err == nil {
				if !seen[email] {
					emails = append(emails, email)
					seen[email] = true
				}
			}
		}
	})

	return emails
}

func regexEmailExtractor(body []byte) []string {
	seen := map[string]bool{}

	var emails []string

	addresses := emailaddress.Find(body, false)
	for i := range addresses {
		if !seen[addresses[i].String()] {
			emails = append(emails, addresses[i].String())
			seen[addresses[i].String()] = true
		}
	}

	return emails
}

func getValidEmail(s string) (string, error) {
	email, err := emailaddress.Parse(strings.TrimSpace(s))
	if err != nil {
		return "", err
	}

	return email.String(), nil
}

// aggregatorHosts is the narrow allow-list of link-in-bio aggregators whose
// raw URLs are pushed to Entry.SocialsRaw for future triage. Kept tiny by
// design — do not pollute SocialsRaw with every random footer link.
var aggregatorHosts = map[string]struct{}{
	"linktr.ee":  {},
	"beacons.ai": {},
	"bio.link":   {},
}

// extractSocialsFromDoc walks anchors, JSON-LD sameAs arrays, and OG meta
// tags on the given document, appending matched SocialLinks to
// entry.Socials (deduped at platform level — Google Maps wins) and
// aggregator-host URLs to entry.SocialsRaw. Malformed JSON-LD is logged
// at debug and skipped — never returns an error.
func extractSocialsFromDoc(ctx context.Context, doc *goquery.Document, entry *Entry) {
	log := scrapemate.GetLoggerFromContext(ctx)

	consume := func(rawURL string) {
		if rawURL == "" {
			return
		}
		if _, ok := socials.Normalize(rawURL); ok {
			harvestWithDedup(rawURL, entry)
			return
		}
		if isAggregatorHost(rawURL) {
			addRawSocialOnce(entry, rawURL)
		}
	}

	// 1. Anchors
	doc.Find("a[href]").Each(func(_ int, s *goquery.Selection) {
		href, exists := s.Attr("href")
		if !exists {
			return
		}
		consume(href)
	})

	// 2. JSON-LD sameAs (log-and-skip on parse error)
	doc.Find("script[type='application/ld+json']").Each(func(_ int, s *goquery.Selection) {
		raw := strings.TrimSpace(s.Text())
		if raw == "" {
			return
		}

		var parsed any
		if err := json.Unmarshal([]byte(raw), &parsed); err != nil {
			log.Debug("malformed JSON-LD, skipping", "error", err.Error())

			return
		}

		for _, u := range collectSameAs(parsed) {
			consume(u)
		}
	})

	// 3. OG meta (fallback; many sites only use og:url / og:see_also)
	doc.Find(`meta[property^="og:"][content]`).Each(func(_ int, s *goquery.Selection) {
		content, _ := s.Attr("content")
		consume(content)
	})
}

// harvestWithDedup appends a normalized SocialLink for rawURL to
// entry.Socials unless the platform is already present (platform-level
// precedence: Google Maps pre-populated entries win over HTML-scraped ones).
func harvestWithDedup(rawURL string, entry *Entry) {
	link, ok := socials.Normalize(rawURL)
	if !ok {
		return
	}

	for _, existing := range entry.Socials {
		if existing.Platform == link.Platform {
			return
		}
	}

	entry.Socials = append(entry.Socials, SocialLink{
		Platform: link.Platform,
		Handle:   link.Handle,
		PathType: link.PathType,
	})
}

// harvestWebsiteIfSocialLocal mirrors socials.HarvestWebsiteIfSocial but
// operates on the local gmaps.SocialLink slice. It applies tuple-level
// dedup (same (Platform, PathType, lower(Handle))) to match the semantics
// of the upstream helper — this is the "same source repeats" case, not
// the across-source precedence case.
func harvestWebsiteIfSocialLocal(rawURL string, out *[]SocialLink) {
	if rawURL == "" || out == nil {
		return
	}

	link, ok := socials.Normalize(rawURL)
	if !ok {
		return
	}

	candidateHandle := strings.ToLower(link.Handle)
	for _, existing := range *out {
		if existing.Platform == link.Platform &&
			existing.PathType == link.PathType &&
			strings.ToLower(existing.Handle) == candidateHandle {
			return
		}
	}

	*out = append(*out, SocialLink{
		Platform: link.Platform,
		Handle:   link.Handle,
		PathType: link.PathType,
	})
}

// addRawSocialOnce appends rawURL to entry.SocialsRaw unless an exact
// string match already exists.
func addRawSocialOnce(entry *Entry, rawURL string) {
	for _, existing := range entry.SocialsRaw {
		if existing == rawURL {
			return
		}
	}

	entry.SocialsRaw = append(entry.SocialsRaw, rawURL)
}

// isAggregatorHost reports whether rawURL parses and its host (after
// stripping www.) belongs to the aggregator allow-list.
func isAggregatorHost(rawURL string) bool {
	u, err := url.Parse(rawURL)
	if err != nil {
		return false
	}

	host := strings.ToLower(u.Host)
	host = strings.TrimPrefix(host, "www.")

	_, ok := aggregatorHosts[host]

	return ok
}

// collectSameAs walks JSON-LD structures looking for "sameAs" arrays of
// strings. Handles top-level objects, arrays, and @graph nesting.
func collectSameAs(node any) []string {
	var out []string

	switch v := node.(type) {
	case []any:
		for _, e := range v {
			out = append(out, collectSameAs(e)...)
		}
	case map[string]any:
		if sa, ok := v["sameAs"]; ok {
			switch s := sa.(type) {
			case string:
				out = append(out, s)
			case []any:
				for _, e := range s {
					if str, ok := e.(string); ok {
						out = append(out, str)
					}
				}
			}
		}

		if graph, ok := v["@graph"]; ok {
			out = append(out, collectSameAs(graph)...)
		}
	}

	return out
}

// normalizeGoogleURL extracts the actual target URL from Google redirect URLs.
// Google Maps sometimes returns URLs like "/url?q=http://example.com/&opi=..."
// for external website links.
func normalizeGoogleURL(rawURL string) string {
	if rawURL == "" {
		return rawURL
	}

	if strings.HasPrefix(rawURL, "/url?q=") {
		fullURL := "https://www.google.com" + rawURL

		parsed, err := url.Parse(fullURL)
		if err != nil {
			return rawURL
		}

		if target := parsed.Query().Get("q"); target != "" {
			return target
		}
	}

	if strings.HasPrefix(rawURL, "/") {
		return "https://www.google.com" + rawURL
	}

	return rawURL
}
