// Package socials normalizes social profile URLs to a canonical
// (platform, handle, path_type) triple used by gmaps.Entry.
package socials

import (
	"net/url"
	"strings"
)

// SocialLink is the canonical representation of a social profile URL.
// It mirrors gmaps.SocialLink (sibling copy; kept here to avoid an import
// cycle between gmaps and gmaps/socials).
type SocialLink struct {
	Platform string `json:"platform"`
	Handle   string `json:"handle"`
	PathType string `json:"path_type,omitempty"`
}

// shortHostMap rewrites short/legacy hosts to their canonical hosts.
// A mapped value of "" signals an explicit reject (e.g. messenger.com).
var shortHostMap = map[string]string{
	"fb.com":        "facebook.com",
	"fb.me":         "facebook.com",
	"twitter.com":   "x.com",
	"youtu.be":      "youtube.com",
	"messenger.com": "",
}

// platformFor returns the platform name for a canonical host, or "" if
// the host is not a supported social domain.
func platformFor(host string) string {
	switch host {
	case "facebook.com":
		return "facebook"
	case "instagram.com":
		return "instagram"
	case "x.com":
		return "x"
	case "linkedin.com":
		return "linkedin"
	case "youtube.com":
		return "youtube"
	case "tiktok.com":
		return "tiktok"
	case "pinterest.com":
		return "pinterest"
	case "wa.me":
		return "whatsapp"
	case "t.me":
		return "telegram"
	case "threads.net":
		return "threads"
	}
	return ""
}

// Normalize parses rawURL and returns a canonical SocialLink when the URL
// matches one of the 10 supported platforms and passes the share/intent
// rejection rules. Returns (SocialLink{}, false) otherwise. Malformed URL
// input returns (SocialLink{}, false) without panic.
func Normalize(rawURL string) (SocialLink, bool) {
	host, u, ok := canonicalHost(rawURL)
	if !ok {
		return SocialLink{}, false
	}
	platform := platformFor(host)
	if platform == "" {
		return SocialLink{}, false
	}

	rawPath := strings.TrimSuffix(u.Path, "/")

	switch platform {
	case "facebook":
		return normalizeFacebook(rawPath, u)
	case "instagram":
		return normalizeInstagram(rawPath)
	case "x":
		return normalizeX(rawPath)
	case "linkedin":
		return normalizeLinkedIn(rawPath)
	case "youtube":
		return normalizeYouTube(rawPath)
	case "tiktok":
		return normalizeTikTok(rawPath)
	case "pinterest":
		return normalizePinterest(rawPath)
	case "whatsapp":
		return normalizeWhatsApp(rawPath)
	case "telegram":
		return normalizeTelegram(rawPath)
	case "threads":
		return normalizeThreads(rawPath)
	}
	return SocialLink{}, false
}

// IsSocialHost reports whether rawURL belongs to one of the 10 supported
// platforms (after host normalization: www./m./l./vm. stripped, short
// hosts mapped). It does NOT parse the path. Malformed input returns false.
func IsSocialHost(rawURL string) bool {
	host, _, ok := canonicalHost(rawURL)
	if !ok {
		return false
	}
	return platformFor(host) != ""
}

// HarvestWebsiteIfSocial appends a SocialLink to *out (in place) if
// rawURL normalizes to a supported platform and the resulting tuple
// (platform, path_type, lower(handle)) is not already present in *out.
func HarvestWebsiteIfSocial(rawURL string, out *[]SocialLink) {
	if rawURL == "" || out == nil {
		return
	}
	link, ok := Normalize(rawURL)
	if !ok {
		return
	}
	if containsLink(*out, link) {
		return
	}
	*out = append(*out, link)
}

// BuildURL reconstructs a canonical HTTPS URL from a SocialLink. Returns
// an empty string if the SocialLink is empty or its Platform is unknown.
func BuildURL(link SocialLink) string {
	if link.Platform == "" || link.Handle == "" {
		return ""
	}
	switch link.Platform {
	case "facebook":
		switch link.PathType {
		case "":
			return "https://facebook.com/" + link.Handle
		case "profile.php":
			return "https://facebook.com/profile.php?id=" + link.Handle
		case "pages":
			return "https://facebook.com/pages/" + link.Handle
		}
	case "instagram":
		return "https://instagram.com/" + link.Handle
	case "x":
		return "https://x.com/" + link.Handle
	case "linkedin":
		switch link.PathType {
		case "in", "company", "school", "pub":
			return "https://linkedin.com/" + link.PathType + "/" + link.Handle
		}
	case "youtube":
		switch link.PathType {
		case "@":
			return "https://youtube.com/@" + link.Handle
		case "channel", "c", "user":
			return "https://youtube.com/" + link.PathType + "/" + link.Handle
		}
	case "tiktok":
		return "https://tiktok.com/@" + link.Handle
	case "pinterest":
		return "https://pinterest.com/" + link.Handle
	case "whatsapp":
		return "https://wa.me/" + link.Handle
	case "telegram":
		return "https://t.me/" + link.Handle
	case "threads":
		return "https://threads.net/@" + link.Handle
	}
	return ""
}

// containsLink returns true if existing already has an entry with the
// same (Platform, PathType, lower(Handle)) tuple — the dedup key.
func containsLink(existing []SocialLink, candidate SocialLink) bool {
	candidateHandle := strings.ToLower(candidate.Handle)
	for _, e := range existing {
		if e.Platform == candidate.Platform &&
			e.PathType == candidate.PathType &&
			strings.ToLower(e.Handle) == candidateHandle {
			return true
		}
	}
	return false
}

// canonicalHost parses rawURL, lowercases the host, strips the known
// subdomain prefixes (www., m., l., vm.), and applies shortHostMap.
// Returns the canonical host, the parsed *url.URL (for path/query access),
// and a success flag. On any parse failure or empty-host input, ok=false.
func canonicalHost(rawURL string) (string, *url.URL, bool) {
	s := strings.TrimSpace(rawURL)
	if s == "" {
		return "", nil, false
	}
	// If the user passed a bare host like "facebook.com/acme" with no
	// scheme, url.Parse treats it as opaque and Host ends up empty. Be
	// permissive: prepend https:// when no scheme is present.
	if !strings.Contains(s, "://") {
		s = "https://" + s
	}
	u, err := url.Parse(s)
	if err != nil {
		return "", nil, false
	}
	host := strings.ToLower(u.Host)
	// Drop port if any.
	if idx := strings.IndexByte(host, ':'); idx >= 0 {
		host = host[:idx]
	}
	if host == "" {
		return "", nil, false
	}
	// Strip well-known subdomain prefixes.
	for _, prefix := range []string{"www.", "m.", "vm.", "l."} {
		if strings.HasPrefix(host, prefix) {
			host = strings.TrimPrefix(host, prefix)
			break
		}
	}
	if mapped, found := shortHostMap[host]; found {
		if mapped == "" {
			return "", nil, false
		}
		host = mapped
	}
	return host, u, true
}

// splitSegments breaks a trimmed path into non-empty segments.
func splitSegments(path string) []string {
	trimmed := strings.TrimPrefix(path, "/")
	if trimmed == "" {
		return nil
	}
	parts := strings.Split(trimmed, "/")
	out := parts[:0]
	for _, p := range parts {
		if p != "" {
			out = append(out, p)
		}
	}
	return out
}

// --- Per-platform normalizers -------------------------------------------

func normalizeFacebook(rawPath string, u *url.URL) (SocialLink, bool) {
	segs := splitSegments(rawPath)
	if len(segs) == 0 {
		return SocialLink{}, false
	}
	first := strings.ToLower(segs[0])
	// Share/intent/widget rejections.
	switch first {
	case "sharer.php", "dialog", "plugins", "tr", "l.php":
		return SocialLink{}, false
	}
	// profile.php?id=<digits>
	if first == "profile.php" {
		id := strings.TrimSpace(u.Query().Get("id"))
		if id == "" {
			return SocialLink{}, false
		}
		return SocialLink{Platform: "facebook", Handle: strings.ToLower(id), PathType: "profile.php"}, true
	}
	// /pages/{name}/{id}
	if first == "pages" {
		if len(segs) < 3 {
			return SocialLink{}, false
		}
		handle := strings.ToLower(segs[1] + "/" + segs[2])
		return SocialLink{Platform: "facebook", Handle: handle, PathType: "pages"}, true
	}
	// Plain slug.
	if looksLikeBadSlug(first) {
		return SocialLink{}, false
	}
	return SocialLink{Platform: "facebook", Handle: first}, true
}

func normalizeInstagram(rawPath string) (SocialLink, bool) {
	segs := splitSegments(rawPath)
	if len(segs) == 0 {
		return SocialLink{}, false
	}
	first := strings.ToLower(segs[0])
	switch first {
	case "p", "reel", "stories", "explore":
		return SocialLink{}, false
	}
	if looksLikeBadSlug(first) {
		return SocialLink{}, false
	}
	return SocialLink{Platform: "instagram", Handle: first}, true
}

func normalizeX(rawPath string) (SocialLink, bool) {
	segs := splitSegments(rawPath)
	if len(segs) == 0 {
		return SocialLink{}, false
	}
	first := strings.ToLower(segs[0])
	switch first {
	case "intent", "share", "hashtag":
		return SocialLink{}, false
	}
	if looksLikeBadSlug(first) {
		return SocialLink{}, false
	}
	return SocialLink{Platform: "x", Handle: first}, true
}

func normalizeLinkedIn(rawPath string) (SocialLink, bool) {
	segs := splitSegments(rawPath)
	if len(segs) < 2 {
		return SocialLink{}, false
	}
	first := strings.ToLower(segs[0])
	switch first {
	case "in", "company", "school":
		handle := strings.ToLower(segs[1])
		if handle == "" {
			return SocialLink{}, false
		}
		return SocialLink{Platform: "linkedin", Handle: handle, PathType: first}, true
	case "pub":
		// /pub/{name}/{ab}/{cd}/{12} — join all remaining lowercased.
		joined := strings.ToLower(strings.Join(segs[1:], "/"))
		return SocialLink{Platform: "linkedin", Handle: joined, PathType: "pub"}, true
	}
	return SocialLink{}, false
}

func normalizeYouTube(rawPath string) (SocialLink, bool) {
	segs := splitSegments(rawPath)
	if len(segs) == 0 {
		return SocialLink{}, false
	}
	first := segs[0]
	firstLower := strings.ToLower(first)
	// watch?v=... is content, not a profile.
	if firstLower == "watch" {
		return SocialLink{}, false
	}
	// Leading @ handle.
	if strings.HasPrefix(first, "@") {
		handle := strings.ToLower(strings.TrimPrefix(first, "@"))
		if handle == "" {
			return SocialLink{}, false
		}
		return SocialLink{Platform: "youtube", Handle: handle, PathType: "@"}, true
	}
	if firstLower == "channel" || firstLower == "c" || firstLower == "user" {
		if len(segs) < 2 {
			return SocialLink{}, false
		}
		handle := strings.ToLower(segs[1])
		return SocialLink{Platform: "youtube", Handle: handle, PathType: firstLower}, true
	}
	// If we got here via the youtu.be short-host, treat the single
	// segment as a channel id.
	// (canonicalHost already mapped host to youtube.com, so we cannot
	// distinguish youtu.be/xyz from youtube.com/xyz here; the latter
	// would be a bare slug which YouTube does NOT support, so treating
	// any bare single-segment as channel is safe per the spec.)
	if len(segs) == 1 {
		handle := strings.ToLower(segs[0])
		return SocialLink{Platform: "youtube", Handle: handle, PathType: "channel"}, true
	}
	return SocialLink{}, false
}

func normalizeTikTok(rawPath string) (SocialLink, bool) {
	segs := splitSegments(rawPath)
	if len(segs) == 0 {
		return SocialLink{}, false
	}
	first := segs[0]
	// Strip leading @ if present.
	handle := strings.ToLower(strings.TrimPrefix(first, "@"))
	if handle == "" {
		return SocialLink{}, false
	}
	if looksLikeBadSlug(handle) {
		return SocialLink{}, false
	}
	return SocialLink{Platform: "tiktok", Handle: handle}, true
}

func normalizePinterest(rawPath string) (SocialLink, bool) {
	segs := splitSegments(rawPath)
	if len(segs) == 0 {
		return SocialLink{}, false
	}
	first := strings.ToLower(segs[0])
	if looksLikeBadSlug(first) {
		return SocialLink{}, false
	}
	return SocialLink{Platform: "pinterest", Handle: first}, true
}

func normalizeWhatsApp(rawPath string) (SocialLink, bool) {
	segs := splitSegments(rawPath)
	if len(segs) == 0 {
		return SocialLink{}, false
	}
	first := segs[0]
	// Keep only ASCII digits.
	var b strings.Builder
	for _, r := range first {
		if r >= '0' && r <= '9' {
			b.WriteRune(r)
		}
	}
	digits := b.String()
	if digits == "" {
		return SocialLink{}, false
	}
	return SocialLink{Platform: "whatsapp", Handle: digits}, true
}

func normalizeTelegram(rawPath string) (SocialLink, bool) {
	segs := splitSegments(rawPath)
	if len(segs) == 0 {
		return SocialLink{}, false
	}
	first := segs[0]
	if strings.HasPrefix(first, "+") {
		return SocialLink{}, false
	}
	handle := strings.ToLower(first)
	if looksLikeBadSlug(handle) {
		return SocialLink{}, false
	}
	return SocialLink{Platform: "telegram", Handle: handle}, true
}

func normalizeThreads(rawPath string) (SocialLink, bool) {
	segs := splitSegments(rawPath)
	if len(segs) == 0 {
		return SocialLink{}, false
	}
	first := segs[0]
	handle := strings.ToLower(strings.TrimPrefix(first, "@"))
	if handle == "" {
		return SocialLink{}, false
	}
	if looksLikeBadSlug(handle) {
		return SocialLink{}, false
	}
	return SocialLink{Platform: "threads", Handle: handle}, true
}

// looksLikeBadSlug rejects obvious non-handle segments (query-only or
// punctuation). Handles are allowed to contain letters, digits, hyphens,
// underscores, and dots.
func looksLikeBadSlug(s string) bool {
	if s == "" {
		return true
	}
	for _, r := range s {
		if r >= 'a' && r <= 'z' {
			continue
		}
		if r >= '0' && r <= '9' {
			continue
		}
		if r == '-' || r == '_' || r == '.' {
			continue
		}
		return true
	}
	return false
}

// NOTE on tracking-param handling: the platform normalizers intentionally
// read only specific query fields (e.g. Facebook profile.php reads only
// `id`) and otherwise draw all canonical information from the URL path.
// As a result, utm_*, fbclid, igshid, si, feature, ref, and mibextid are
// silently dropped: they never influence the Platform/Handle/PathType
// triple and never appear in BuildURL output, which reconstructs the URL
// from the canonical fields rather than the original query string.
