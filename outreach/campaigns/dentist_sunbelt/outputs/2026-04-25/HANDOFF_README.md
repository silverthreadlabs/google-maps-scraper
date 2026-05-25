# Dental Outbound Lead List — Handoff README

**Delivery date:** 2026-04-25
**Delivered by:** Muhammad Fassih Haider (lead generation)
**Source file:** `dentists_handoff.csv` (292 rows, 47 columns)
**Target campaign:** Silverthread Labs outbound — Voice AI / Workflow Automation for dental practices
**Metros:** Phoenix AZ, Austin TX, Tampa FL (Sunbelt independents)

---

## What this list is

292 dental practices across 3 Sunbelt metros, ranked by their fit for Silverthread's services. "Fit" is computed from real ≤3-star Google review complaints — every lead with `pain_quote_1` populated has a verbatim customer pain point that maps directly to a Silverthread service we can sell.

Practices were filtered for independents (no DSOs / corporate chains) using both title regex and email-domain checks. Every chain we identified is in the file but flagged with `is_chain_or_dso=TRUE` and a reason — sales decides whether to skip them or work them anyway.

**Nothing is dropped.** Every lead I scraped is in this CSV. Filter on the columns to build your working list; rows you don't want are right there if your strategy changes.

---

## Tier definitions

| Tier | quality_score | What it means | How to work it |
|---|---|---|---|
| **A** | ≥ 60 | Multiple high-fit pain categories + large practice + verified contact | Personalize. Open the email by quoting `pain_quote_1`, name the `recommended_service`, drop a 15-min call CTA. ~5 minutes per prospect. |
| **B** | 30–60 | Solid multi-pain or single flagship pain at a sizeable practice | Templated with one variable substitution (`top_pain_category` + `recommended_service`). 1 minute per prospect. |
| **C** | 15–30 | Single flagship pain | Volume-template, lower expected reply rate. Skip if calendar is constrained. |
| **D** | < 15 | Soft signal only (mostly `staff_rude_front_desk`) | Lowest priority. Use only if you've worked everything else. |

Tiers apply to ALL rows including chains. Filter `is_chain_or_dso = FALSE` first if you only want independents.

**Counts (independent only, with verified email):** A=3, B=19, C=27, D=24 → **73 ready-to-email leads**.
**Phone-only independents:** ~85 additional. Hold for cold-call channel when bandwidth exists.

---

## Column reference (47 cols)

### Identity & contact
| Column | Description |
|---|---|
| `tier` | A / B / C / D — see above |
| `quality_score` | Composite: weighted pain × 1 + breadth × 2 + log10(reviews) × 3 + (4.9 − rating) × 4 |
| `metro` | phoenix / austin / tampa |
| `title` | Practice name on Google Maps |
| `best_email` | Most likely-to-reach address. Empty if no trustworthy email — work via phone or skip. |
| `all_emails` | Every email we found, semicolon-joined. Includes invalid-flagged ones for transparency. |
| `email_sources` | Where each email came from: `google_maps`, `agent_browser_crawl`, `web_search` |
| `phone` | E.164. Validated by area-code-to-metro check (see `phone_invalid`). |
| `phone_normalized` | Cleaned `+1XXXXXXXXXX` form |
| `website` / `address` / `google_maps_link` | Practice metadata |

### Decision-maker
| Column | Description |
|---|---|
| `owner_name` | Verified via LinkedIn or BBB. Populated for the 21 highest-priority Tier A+B leads. |
| `owner_title` | DDS / DMD / Owner / Co-Founder etc. |
| `owner_linkedin` | Direct LinkedIn URL when found. Use for InMail or LinkedIn-warmed email outreach. |
| `additional_team` | Other named dentists / partners — fallback decision-makers |
| `pocs` | Doctor names extracted from the practice's own website (cross-validated against `poc_extract.py`). May include false positives that survive validation. |

### Pain — the conversation starter
| Column | Description |
|---|---|
| `top_pain_category` | The highest-weighted pain at this practice |
| `pain_breadth_count` | How many distinct pain categories were detected (1–11) |
| `pain_quote_1` / `pain_quote_2` | **Verbatim ≤3-star review snippets.** This is the gold. Quote in cold email/call: *"I noticed a recent review mentioned: 'X'. We help dental practices solve exactly that with [service]."* |
| `pain_quote_1_rating` / `pain_quote_2_rating` | The reviewer's star rating for that snippet (1, 2, or 3) |
| `recommended_service` | Silverthread service mapped to the top pain |
| `recommended_service_url` | Direct link to the service page on silverthreadlabs.com |
| `all_pain_categories` | Full list of detected pain categories, semicolon-joined |
| `all_recommended_services` | Full list of mapped services |

### Practice context
| Column | Description |
|---|---|
| `review_count` | Total Google Maps reviews — proxy for practice size / patient volume |
| `rating` | Google Maps overall ★ |
| `negative_reviews_1_3_star` | Raw count of 1-3★ reviews on Google Maps |
| `reviews_analyzed` | How many reviews we mined for pain (merged base + extended pool, deduped) |

### Risk flags — read these before sending
| Column | When TRUE means |
|---|---|
| `is_chain_or_dso` | This is a corporate-owned location; pitching Voice AI to a sub-brand rarely works (decision is made at HQ). Default-skip unless you have HQ contacts. |
| `chain_reason` | How we identified the chain: `known_dso`, `dso_email_domain:<domain>`, `shared_hostname_<host>`, `brand_repeats_Nx_in_dataset` |
| `website_redirect_mismatch` | The practice's listed website redirects to a different domain — the listed site may be stale/parked. Verify before referencing in outreach. |
| `emails_invalid_count` | Count of emails we flagged invalid (placeholder, image artifact, vendor template, no-reply, chain affiliation). The values themselves are still in `all_emails` for transparency. |
| `crawled_emails_suspect` | Email was extracted from a site that didn't match the expected domain — treat as low-confidence. |
| `phone_invalid` | Phone format is bad or area code doesn't match metro. |

### Socials
| Column | Description |
|---|---|
| `socials_facebook` / `socials_instagram` / `socials_linkedin` / `socials_yelp` / `socials_tiktok` / `socials_youtube` | Per-platform URLs. LinkedIn columns include practice company pages (not personal). |

### Operational
| Column | Description |
|---|---|
| `crawl_status` | What happened when we crawled their website: `ok`, `no_email_found`, `cloudflare_blocked`, `timeout`, `open_error` |
| `research_note` | Anything I noticed that didn't fit other columns (e.g. "Family business 40+ years", "Also owns Tampa Palms Dentistry") |

---

## Pain category → Silverthread service mapping (full)

| Pain category | Pitch this service |
|---|---|
| `missed_calls_unreachable` | Voice AI for Dental (AI Receptionist) |
| `after_hours_emergency` | After-Hours Voice Coverage |
| `appointment_booking_delay` | Voice AI Appointment Booking |
| `no_show_reminder_missing` | Automated Appointment Reminders |
| `recall_followup_missing` | Outbound Recall Campaigns |
| `intake_paperwork_duplication` | Patient Intake Automation |
| `insurance_verification_missing` | Insurance Eligibility Verification Workflow |
| `billing_errors` | Billing Automation / Practice Management |
| `long_wait_in_chair` | Workflow Automation (Scheduling) |
| `staff_rude_front_desk` | AI Receptionist (consistent tone) |
| `language_barrier_spanish` | Multilingual (Spanish) Voice Agent |

---

## How to work the list (recommended)

1. Open in Excel/Sheets/CRM. Filter `is_chain_or_dso = FALSE` to see independents only.
2. Sort by `quality_score` DESC.
3. Work top–down within tier:
   - **Tier A first.** 3 leads, 5 min each, personalize using `pain_quote_1` + `owner_name`.
   - **Tier B second.** 19 leads, template with the variable: `pain_quote_1`, `top_pain_category`, `recommended_service`.
   - **Tier C third.** 27 leads, lighter template.
4. Don't email rows where `best_email` is empty — they're either on the cold-call queue or need more enrichment. Don't waste a personalized hook.
5. **Always quote the pain.** The reason these leads exist is that we found their actual patient complaints. A cold email that names a real complaint converts 3–5× higher than a generic pitch.

### Sample outreach hook (Tier A)

> *Subject:* Cutting Emergency Dentist of Austin's missed calls
>
> Hi Patrick,
>
> I noticed a recent 1★ review on your practice mentioned: "*[paste pain_quote_1]*". You're not alone — 35–68% of after-hours calls at dental practices go unanswered, and Silverthread Labs has a Voice AI Receptionist built specifically for this.
>
> Worth 15 minutes to see how it'd work for your practice?
>
> — [you]

---

## What I need back from sales (feedback loop)

This list is a starting point. To make the next delivery 2× better, I need disposition data back. Minimal viable feedback per row, in a shared sheet or CRM:

| Field | Values | Why |
|---|---|---|
| `disposition` | not_attempted / contacted / connected / qualified / customer / dead | So I can compute conversion rates per tier and per pain category |
| `dead_reason` | wrong_contact / not_decision_maker / chain_after_all / no_pain_match / no_budget / not_interested / other | So I can refine filters |
| `replied` | TRUE / FALSE | Reply-rate by tier |
| `notes` | Free text | Context that doesn't fit a code |

**Cadence:** Update inline as you work each lead. I'll pull this back into the next refresh and tune.

**What I'll do with it:**
- Tighten the chain filter when you flag chains we missed.
- Drop pain categories that don't convert (e.g. if `staff_rude_front_desk` never closes, I stop weighting it).
- Refine the metro / DSO filter.
- Add new metros if conversion proves the playbook.

---

## Refresh cadence

- **Next refresh trigger:** when 50% of Tier A+B has been worked, OR 60 days from delivery, whichever first.
- **What changes between refreshes:** Google reviews accumulate, practices change ownership, new pain emerges, chain-affiliation can shift. The pain-quote freshness is the biggest reason to re-scrape.
- **What stays:** the master JSON files in `gmapsdata/` are append-only. Nothing is ever deleted. The next CSV will be additive, not destructive.

---

## Methodology summary (for transparency)

1. **Source.** `gosom/google-maps-scraper` Docker container. 30 dentist queries across 3 metros. Pulled review pool with `-extra-reviews` (avg 530 reviews/practice — captures 1-3★ reviews that Google buries past position 10).
2. **Pain detection.** 11 regex categories tuned for dental complaints, only matched against ≤3★ reviews to avoid false positives like "great for emergencies!" matching `after_hours_emergency`.
3. **Chain detection.** Three signals: title regex (known DSO names), shared website hostname (≥2 practices on same domain = same operator), email-domain match (NADG / MB2 / Aspida / Smile Generation / etc.).
4. **POC extraction.** From practice websites — JSON-LD schema.org Person + h1-h4 doctor headings + image alt text. Validated through a strict regex (`Dr. <Name>` or `<Name>, DDS|DMD`) with address-suffix and practice-name guards (drops "Hancock Dr" / "Dental on Central").
5. **Email validation.** Drops placeholders (`user@domain.com`), image artifacts (`logo@2x.png`), vendor-marketing templates (`@gargle.com`), no-reply prefixes, and known DSO routing domains.
6. **Phone validation.** E.164 normalization + NANP area-code consistency check against the lead's metro.
7. **LinkedIn owner research.** Manual web search for the top 23 Tier A+B leads.

---

## Files & artifacts

| File | What it is |
|---|---|
| `dentists_handoff.csv` | **The deliverable** — 292 rows × 47 columns |
| `HANDOFF_README.md` | This file |
| `dentists_master_ranked.json` | Independents only (165 rows) — full structured data, source-of-truth for any analysis re-run |
| `dentists_all_ranked.json` | All 292 rows (including chains) — full structured data |
| `dental_enrichment.json` | Per-lead website crawl results |
| `dental_enrichment_contaminated_archive.json` | Audit trail for the parallelism bug we caught & fixed mid-run |
| `dental_retry_queue.json` | 17 leads that failed initial crawl — candidates for Playwright retry next round |
| `dentists_recrawl_queue.json` | 39 leads that needed re-crawl after the parallelism fix |

Everything is JSON; the CSV is derived. Re-running `build_handoff_csv.py` regenerates the CSV from current state.

---

## Questions / issues

Please flag anything in the data that doesn't make sense — that's how the next refresh gets better.
