package socials

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// ----- Normalize table --------------------------------------------------

type normCase struct {
	name   string
	input  string
	want   SocialLink
	wantOK bool
}

func normalizeCases() []normCase {
	return []normCase{
		// ---------- happy paths, one per platform + path_type ----------
		{"fb plain slug with www", "https://www.facebook.com/acmeinc", SocialLink{Platform: "facebook", Handle: "acmeinc"}, true},
		{"fb profile.php numeric via m.", "https://m.facebook.com/profile.php?id=100012345", SocialLink{Platform: "facebook", Handle: "100012345", PathType: "profile.php"}, true},
		{"fb legacy pages", "https://facebook.com/pages/AcmeCo/98765", SocialLink{Platform: "facebook", Handle: "acmeco/98765", PathType: "pages"}, true},
		{"fb short host fb.com", "https://fb.com/acme", SocialLink{Platform: "facebook", Handle: "acme"}, true},
		{"fb short host fb.me", "https://fb.me/acme", SocialLink{Platform: "facebook", Handle: "acme"}, true},
		{"fb tracking params stripped", "https://facebook.com/acme?fbclid=xyz&utm_source=foo", SocialLink{Platform: "facebook", Handle: "acme"}, true},
		{"fb profile.php keeps id only", "https://facebook.com/profile.php?id=123&fbclid=xyz", SocialLink{Platform: "facebook", Handle: "123", PathType: "profile.php"}, true},

		{"ig plain with trailing slash", "https://www.instagram.com/acme/", SocialLink{Platform: "instagram", Handle: "acme"}, true},
		{"ig igshid stripped", "https://instagram.com/acme?igshid=xyz", SocialLink{Platform: "instagram", Handle: "acme"}, true},

		{"twitter rewritten to x", "https://twitter.com/acmeinc", SocialLink{Platform: "x", Handle: "acmeinc"}, true},
		{"x uppercased handle lowercased", "https://x.com/ACMEINC", SocialLink{Platform: "x", Handle: "acmeinc"}, true},
		{"x si tracking stripped", "https://x.com/acmeinc?s=20&utm_medium=email", SocialLink{Platform: "x", Handle: "acmeinc"}, true},

		{"linkedin company", "https://www.linkedin.com/company/acme-corp", SocialLink{Platform: "linkedin", Handle: "acme-corp", PathType: "company"}, true},
		{"linkedin in (personal)", "https://www.linkedin.com/in/jane-doe", SocialLink{Platform: "linkedin", Handle: "jane-doe", PathType: "in"}, true},
		{"linkedin school", "https://www.linkedin.com/school/acme-university", SocialLink{Platform: "linkedin", Handle: "acme-university", PathType: "school"}, true},
		{"linkedin pub legacy", "https://www.linkedin.com/pub/foo-bar/a1/b2/c3", SocialLink{Platform: "linkedin", Handle: "foo-bar/a1/b2/c3", PathType: "pub"}, true},

		{"youtube @handle", "https://www.youtube.com/@acmevideos", SocialLink{Platform: "youtube", Handle: "acmevideos", PathType: "@"}, true},
		{"youtube channel ID lowercased", "https://www.youtube.com/channel/UCabcdef", SocialLink{Platform: "youtube", Handle: "ucabcdef", PathType: "channel"}, true},
		{"youtube /c/", "https://www.youtube.com/c/AcmeChannel", SocialLink{Platform: "youtube", Handle: "acmechannel", PathType: "c"}, true},
		{"youtube /user/", "https://www.youtube.com/user/legacyuser", SocialLink{Platform: "youtube", Handle: "legacyuser", PathType: "user"}, true},
		{"youtu.be short -> channel", "https://youtu.be/UCabc", SocialLink{Platform: "youtube", Handle: "ucabc", PathType: "channel"}, true},

		{"tiktok @handle", "https://www.tiktok.com/@acme", SocialLink{Platform: "tiktok", Handle: "acme"}, true},
		{"tiktok vm. short host", "https://vm.tiktok.com/ZMabc/", SocialLink{Platform: "tiktok", Handle: "zmabc"}, true},

		{"pinterest slug", "https://www.pinterest.com/acme/", SocialLink{Platform: "pinterest", Handle: "acme"}, true},
		{"pinterest ref stripped", "https://pinterest.com/acme?ref=foo", SocialLink{Platform: "pinterest", Handle: "acme"}, true},

		{"whatsapp digits plain", "https://wa.me/15551234567", SocialLink{Platform: "whatsapp", Handle: "15551234567"}, true},

		{"telegram slug", "https://t.me/acme", SocialLink{Platform: "telegram", Handle: "acme"}, true},

		{"threads @handle", "https://www.threads.net/@acme", SocialLink{Platform: "threads", Handle: "acme"}, true},
		{"threads mibextid stripped", "https://threads.net/@acme?mibextid=xyz", SocialLink{Platform: "threads", Handle: "acme"}, true},

		// ---------- rejection paths ----------
		{"fb l.php link shim", "https://l.facebook.com/l.php?u=https%3A%2F%2Fexample.com", SocialLink{}, false},
		{"fb sharer.php", "https://facebook.com/sharer.php?u=foo", SocialLink{}, false},
		{"fb dialog", "https://facebook.com/dialog/share?app_id=1", SocialLink{}, false},
		{"fb plugins", "https://facebook.com/plugins/like.php", SocialLink{}, false},
		{"fb tr pixel", "https://facebook.com/tr?id=1", SocialLink{}, false},
		{"fb profile.php missing id", "https://facebook.com/profile.php", SocialLink{}, false},
		{"fb pages too short", "https://facebook.com/pages/AcmeCo", SocialLink{}, false},

		{"ig post", "https://www.instagram.com/p/ABC123/", SocialLink{}, false},
		{"ig reel", "https://www.instagram.com/reel/XYZ/", SocialLink{}, false},
		{"ig stories", "https://www.instagram.com/stories/acme/", SocialLink{}, false},
		{"ig explore", "https://www.instagram.com/explore/tags/acme", SocialLink{}, false},

		{"x intent", "https://x.com/intent/tweet?text=hi", SocialLink{}, false},
		{"x share", "https://x.com/share?text=hi", SocialLink{}, false},
		{"x hashtag", "https://x.com/hashtag/acme", SocialLink{}, false},

		{"yt watch", "https://www.youtube.com/watch?v=dQw4", SocialLink{}, false},
		{"yt channel missing id", "https://www.youtube.com/channel", SocialLink{}, false},
		{"yt bare @ rejected", "https://www.youtube.com/@", SocialLink{}, false},

		{"linkedin bare root", "https://www.linkedin.com/", SocialLink{}, false},
		{"linkedin unknown path_type", "https://www.linkedin.com/jobs/acme", SocialLink{}, false},

		{"telegram invite rejected", "https://t.me/+abc123", SocialLink{}, false},

		{"messenger.com rejected", "https://messenger.com/acme", SocialLink{}, false},
		{"example.com not social", "https://www.example.com/about", SocialLink{}, false},
		{"empty string", "", SocialLink{}, false},
		{"whitespace-only", "   ", SocialLink{}, false},
		{"malformed URL no panic", "://bad", SocialLink{}, false},
		{"control char URL", "https://example.com/\x7f", SocialLink{}, false},

		{"whatsapp non-digits only", "https://wa.me/abc", SocialLink{}, false},
		{"whatsapp empty path", "https://wa.me/", SocialLink{}, false},
		{"tiktok bare @ rejected", "https://www.tiktok.com/@", SocialLink{}, false},
		{"threads bare @ rejected", "https://www.threads.net/@", SocialLink{}, false},
		{"facebook bad slug with braces", "https://facebook.com/{acme}", SocialLink{}, false},

		// ---------- protocol-relative URLs (//host/path) ----------
		{"protocol-relative facebook.com", "//facebook.com/acmeinc", SocialLink{Platform: "facebook", Handle: "acmeinc"}, true},
		{"protocol-relative fb.com", "//fb.com/acme", SocialLink{Platform: "facebook", Handle: "acme"}, true},
		{"protocol-relative instagram", "//www.instagram.com/acme", SocialLink{Platform: "instagram", Handle: "acme"}, true},
		{"protocol-relative linkedin company", "//linkedin.com/company/acme-corp", SocialLink{Platform: "linkedin", Handle: "acme-corp", PathType: "company"}, true},
		{"protocol-relative x.com", "//x.com/acme", SocialLink{Platform: "x", Handle: "acme"}, true},
		{"protocol-relative userinfo fb.com", "//user:pass@fb.com/acme", SocialLink{Platform: "facebook", Handle: "acme"}, true},
		{"protocol-relative triple-slash rejected", "///triple-slash", SocialLink{}, false},
		{"protocol-relative bare // rejected", "//", SocialLink{}, false},
	}
}

func TestNormalize(t *testing.T) {
	for _, tc := range normalizeCases() {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			got, ok := Normalize(tc.input)
			if ok != tc.wantOK {
				t.Fatalf("Normalize(%q) ok = %v, want %v (got=%+v)", tc.input, ok, tc.wantOK, got)
			}
			if got != tc.want {
				t.Fatalf("Normalize(%q) = %+v, want %+v", tc.input, got, tc.want)
			}
		})
	}
}

// Whatsapp digit stripping on a canonical-looking URL. We test the
// digit-stripping behaviour separately because a raw "+1 (555)..."
// substring would force URL-encoding in the input and distract from
// intent. We simulate the raw path a real scraper would extract.
func TestNormalizeWhatsAppDigitStripping(t *testing.T) {
	// URL-encoded equivalent of "+1 (555) 123-4567".
	in := "https://wa.me/%2B1%20%28555%29%20123-4567"
	got, ok := Normalize(in)
	if !ok {
		t.Fatalf("Normalize(%q) ok=false, want true; got=%+v", in, got)
	}
	want := SocialLink{Platform: "whatsapp", Handle: "15551234567"}
	if got != want {
		t.Fatalf("Normalize(%q) = %+v, want %+v", in, got, want)
	}
}

// ----- IsSocialHost -----------------------------------------------------

func TestIsSocialHost_Positives(t *testing.T) {
	positives := []string{
		"https://facebook.com/anything",
		"https://www.facebook.com/anything",
		"https://m.facebook.com/anything",
		"https://fb.com/anything",
		"https://fb.me/anything",
		"https://twitter.com/anything",
		"https://x.com/anything",
		"https://x.com/intent/tweet?text=hi", // IsSocialHost does not reject share paths
		"https://linkedin.com/x",
		"https://www.linkedin.com/jobs/view/123",
		"https://youtube.com/watch?v=abc", // host check only
		"https://youtu.be/abc",
		"https://instagram.com/p/ABC/",
		"https://www.instagram.com/anything",
		"https://tiktok.com/@acme",
		"https://vm.tiktok.com/ZMabc/",
		"https://pinterest.com/anything",
		"https://wa.me/15551234567",
		"https://t.me/+invitelink", // host is social even if Normalize rejects
		"https://threads.net/@anyone",
	}
	for _, u := range positives {
		if !IsSocialHost(u) {
			t.Errorf("IsSocialHost(%q) = false, want true", u)
		}
	}
}

func TestIsSocialHost_Negatives(t *testing.T) {
	negatives := []string{
		"",
		"   ",
		"://bad",
		"https://example.com",
		"https://messenger.com/anyone",
		"https://google.com",
		"https://accounts.google.com/signin",
	}
	for _, u := range negatives {
		if IsSocialHost(u) {
			t.Errorf("IsSocialHost(%q) = true, want false", u)
		}
	}
}

// ----- BuildURL ---------------------------------------------------------

func TestBuildURL(t *testing.T) {
	cases := []struct {
		name string
		link SocialLink
		want string
	}{
		{"facebook slug", SocialLink{Platform: "facebook", Handle: "acmeinc"}, "https://facebook.com/acmeinc"},
		{"facebook profile.php", SocialLink{Platform: "facebook", Handle: "12345", PathType: "profile.php"}, "https://facebook.com/profile.php?id=12345"},
		{"facebook pages", SocialLink{Platform: "facebook", Handle: "acme/12345", PathType: "pages"}, "https://facebook.com/pages/acme/12345"},
		{"instagram", SocialLink{Platform: "instagram", Handle: "acme"}, "https://instagram.com/acme"},
		{"x", SocialLink{Platform: "x", Handle: "acmeinc"}, "https://x.com/acmeinc"},
		{"linkedin company", SocialLink{Platform: "linkedin", Handle: "acme-corp", PathType: "company"}, "https://linkedin.com/company/acme-corp"},
		{"linkedin in", SocialLink{Platform: "linkedin", Handle: "jane-doe", PathType: "in"}, "https://linkedin.com/in/jane-doe"},
		{"linkedin school", SocialLink{Platform: "linkedin", Handle: "acme-u", PathType: "school"}, "https://linkedin.com/school/acme-u"},
		{"linkedin pub", SocialLink{Platform: "linkedin", Handle: "foo-bar/a1/b2/c3", PathType: "pub"}, "https://linkedin.com/pub/foo-bar/a1/b2/c3"},
		{"youtube @", SocialLink{Platform: "youtube", Handle: "acmevideos", PathType: "@"}, "https://youtube.com/@acmevideos"},
		{"youtube channel", SocialLink{Platform: "youtube", Handle: "UCxyz", PathType: "channel"}, "https://youtube.com/channel/UCxyz"},
		{"youtube c", SocialLink{Platform: "youtube", Handle: "acme", PathType: "c"}, "https://youtube.com/c/acme"},
		{"youtube user", SocialLink{Platform: "youtube", Handle: "legacy", PathType: "user"}, "https://youtube.com/user/legacy"},
		{"tiktok", SocialLink{Platform: "tiktok", Handle: "acme"}, "https://tiktok.com/@acme"},
		{"pinterest", SocialLink{Platform: "pinterest", Handle: "acme"}, "https://pinterest.com/acme"},
		{"whatsapp", SocialLink{Platform: "whatsapp", Handle: "15551234567"}, "https://wa.me/15551234567"},
		{"telegram", SocialLink{Platform: "telegram", Handle: "acme"}, "https://t.me/acme"},
		{"threads", SocialLink{Platform: "threads", Handle: "acme"}, "https://threads.net/@acme"},

		{"empty link", SocialLink{}, ""},
		{"unknown platform", SocialLink{Platform: "myspace", Handle: "x"}, ""},
		{"empty handle", SocialLink{Platform: "facebook", Handle: ""}, ""},
		{"facebook unknown path_type", SocialLink{Platform: "facebook", Handle: "x", PathType: "unknown"}, ""},
		{"linkedin unknown path_type", SocialLink{Platform: "linkedin", Handle: "x", PathType: "unknown"}, ""},
		{"youtube unknown path_type", SocialLink{Platform: "youtube", Handle: "x", PathType: "unknown"}, ""},
	}
	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			got := BuildURL(tc.link)
			if got != tc.want {
				t.Fatalf("BuildURL(%+v) = %q, want %q", tc.link, got, tc.want)
			}
		})
	}
}

// Round-trip: Normalize(url) -> BuildURL(link) -> Normalize again yields
// the same SocialLink.
func TestBuildURLRoundTrip(t *testing.T) {
	inputs := []string{
		"https://www.facebook.com/acmeinc",
		"https://m.facebook.com/profile.php?id=100012345",
		"https://facebook.com/pages/AcmeCo/98765",
		"https://instagram.com/acme",
		"https://x.com/acmeinc",
		"https://www.linkedin.com/company/acme-corp",
		"https://www.linkedin.com/in/jane-doe",
		"https://www.linkedin.com/pub/foo-bar/a1/b2/c3",
		"https://www.youtube.com/@acmevideos",
		"https://www.youtube.com/channel/UCabcdef",
		"https://www.youtube.com/c/AcmeChannel",
		"https://www.youtube.com/user/legacyuser",
		"https://www.tiktok.com/@acme",
		"https://www.pinterest.com/acme",
		"https://wa.me/15551234567",
		"https://t.me/acme",
		"https://www.threads.net/@acme",
	}
	for _, in := range inputs {
		in := in
		t.Run(in, func(t *testing.T) {
			link, ok := Normalize(in)
			if !ok {
				t.Fatalf("Normalize(%q) failed", in)
			}
			rebuilt := BuildURL(link)
			if rebuilt == "" {
				t.Fatalf("BuildURL(%+v) returned empty", link)
			}
			link2, ok := Normalize(rebuilt)
			if !ok {
				t.Fatalf("Normalize(%q) (rebuilt) failed", rebuilt)
			}
			if link != link2 {
				t.Fatalf("round-trip mismatch:\n  first : %+v\n  second: %+v\n  via   : %q", link, link2, rebuilt)
			}
		})
	}
}

// ----- HarvestWebsiteIfSocial ------------------------------------------

func TestHarvestWebsiteIfSocial_AppendsOnEmpty(t *testing.T) {
	var out []SocialLink
	HarvestWebsiteIfSocial("https://facebook.com/acme", &out)
	if len(out) != 1 {
		t.Fatalf("expected 1 entry, got %d", len(out))
	}
	want := SocialLink{Platform: "facebook", Handle: "acme"}
	if out[0] != want {
		t.Fatalf("got %+v, want %+v", out[0], want)
	}
}

func TestHarvestWebsiteIfSocial_DedupByTuple(t *testing.T) {
	out := []SocialLink{{Platform: "facebook", Handle: "acme"}}
	HarvestWebsiteIfSocial("https://www.facebook.com/ACME", &out)
	if len(out) != 1 {
		t.Fatalf("expected dedup to keep length 1, got %d (%+v)", len(out), out)
	}
}

func TestHarvestWebsiteIfSocial_DifferentPlatformAppends(t *testing.T) {
	out := []SocialLink{{Platform: "facebook", Handle: "acme"}}
	HarvestWebsiteIfSocial("https://instagram.com/acme", &out)
	if len(out) != 2 {
		t.Fatalf("expected 2 entries, got %d (%+v)", len(out), out)
	}
	if out[1].Platform != "instagram" {
		t.Fatalf("unexpected second entry: %+v", out[1])
	}
}

func TestHarvestWebsiteIfSocial_EmptyInput(t *testing.T) {
	out := []SocialLink{{Platform: "facebook", Handle: "acme"}}
	HarvestWebsiteIfSocial("", &out)
	if len(out) != 1 {
		t.Fatalf("empty input should not mutate: got %+v", out)
	}
}

func TestHarvestWebsiteIfSocial_NilOutNoPanic(t *testing.T) {
	// Should not panic.
	HarvestWebsiteIfSocial("https://facebook.com/acme", nil)
}

func TestHarvestWebsiteIfSocial_NonSocialURL(t *testing.T) {
	out := []SocialLink{{Platform: "facebook", Handle: "acme"}}
	HarvestWebsiteIfSocial("https://example.com/about", &out)
	if len(out) != 1 {
		t.Fatalf("non-social URL should not mutate: got %+v", out)
	}
}

// Same platform + tuple appearing via two different URLs (e.g. a trailing
// slash or uppercase variant) collapses to a single entry — this is the
// "Google Maps wins" precedence from the issue spec.
func TestHarvestWebsiteIfSocial_PrecedenceFirstWins(t *testing.T) {
	var out []SocialLink
	HarvestWebsiteIfSocial("https://facebook.com/acme", &out) // first
	HarvestWebsiteIfSocial("https://www.facebook.com/ACME/", &out)
	if len(out) != 1 {
		t.Fatalf("expected dedup, got %+v", out)
	}
	if out[0].Handle != "acme" {
		t.Fatalf("first entry should win: got %+v", out[0])
	}
}

// ----- Golden fixtures --------------------------------------------------

func TestGoldenFixtures(t *testing.T) {
	platforms := []string{
		"facebook", "instagram", "x", "linkedin", "youtube",
		"tiktok", "pinterest", "whatsapp", "telegram", "threads",
	}
	for _, p := range platforms {
		p := p
		t.Run(p, func(t *testing.T) {
			inputPath := filepath.Join("testdata", p+".input.txt")
			goldenPath := filepath.Join("testdata", p+".golden.json")

			inputBytes, err := os.ReadFile(inputPath)
			if err != nil {
				t.Fatalf("read input fixture: %v", err)
			}
			goldenBytes, err := os.ReadFile(goldenPath)
			if err != nil {
				t.Fatalf("read golden fixture: %v", err)
			}

			var want []SocialLink
			if err := json.Unmarshal(goldenBytes, &want); err != nil {
				t.Fatalf("unmarshal golden: %v", err)
			}

			var got []SocialLink
			for _, line := range strings.Split(strings.TrimSpace(string(inputBytes)), "\n") {
				line = strings.TrimSpace(line)
				if line == "" {
					continue
				}
				link, ok := Normalize(line)
				if !ok {
					t.Fatalf("Normalize(%q) failed in fixture %s", line, p)
				}
				got = append(got, link)
			}

			if len(got) != len(want) {
				t.Fatalf("%s: got %d entries, want %d\n got: %+v\nwant: %+v", p, len(got), len(want), got, want)
			}
			for i := range got {
				if got[i] != want[i] {
					t.Errorf("%s[%d]: got %+v, want %+v", p, i, got[i], want[i])
				}
			}
		})
	}
}

// ----- containsLink -----------------------------------------------------

func TestContainsLink_CaseInsensitiveHandle(t *testing.T) {
	existing := []SocialLink{{Platform: "facebook", Handle: "ACME"}}
	cand := SocialLink{Platform: "facebook", Handle: "acme"}
	if !containsLink(existing, cand) {
		t.Fatal("expected case-insensitive match")
	}
}

func TestContainsLink_DifferentPathTypeNoMatch(t *testing.T) {
	existing := []SocialLink{{Platform: "facebook", Handle: "acme"}}
	cand := SocialLink{Platform: "facebook", Handle: "acme", PathType: "profile.php"}
	if containsLink(existing, cand) {
		t.Fatal("different PathType should not match")
	}
}
