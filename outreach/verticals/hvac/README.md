# HVAC vertical

Targets independent HVAC shops for **AssistantDial AI** (client) — a 24/7
AI phone receptionist that answers inbound calls, qualifies leads, and
books jobs. Pain weighting prioritizes call coverage and booking friction
(the product is inbound-only: no outbound calling, no SMS campaigns, no
live human handoff — see the client sales doc).

Ideal lead: small owner-operated shop, independent (non-PE, non-franchise),
has a real website, and reviews showing phone pain ("called five times,
nobody answered", "no callback", "couldn't get through after hours").
Avoid: franchise/PE platforms (call centers already), shops with almost no
reviews (too little call volume to justify $397/mo).

## Reachability rule (THIS CLIENT — AssistantDial outreaches by PHONE)

Confirmed with the client team (2026-07-04): their reps cold-call
prospects using the client's phone-sales script. Channel ladder,
best first:

1. POC's direct/cell phone (rare from public sources; for 1-4 person
   shops the business number is often the owner's cell anyway)
2. Business phone (already on every Google Maps lead)

Low priority (still collect, don't gate on them): emails, LinkedIn,
other socials. Generic role emails (`info@`, …) remain worth ~zero.

Consequence: reachability is near-universal — the sellable gate is
pain evidence + independence + a validated phone (`phone_invalid`
flag from the validate stage matters now). The `decision-makers`
stage's main value shifts to the OWNER'S NAME (reps ask for the
owner by name) and any direct line surfaced by whois / license
registries / Facebook pages. Do NOT source personal cells from
data-broker people-search sites (ToS + TCPA/DNC risk).

## Default vertical_keyword

`hvac repair` — set per-city in `locations/<loc>.yaml` if a market uses a
different term.

## Query guidance

Keep queries generic ("hvac repair", "ac repair", "hvac contractor").
Avoid "emergency" / "24 hour" phrasing — it biases results toward shops
that already solved after-hours coverage, the worst-fit leads for this
client.

## Adding an HVAC campaign

1. Author or pick a location: `outreach/locations/<loc>.yaml`
2. Create the campaign dir: `outreach/campaigns/hvac_<loc>/`
3. Write `campaign.yaml`:
   ```yaml
   vertical: hvac
   location: <loc>
   slug: hvac_<loc>
   ```
4. Generate queries: `python outreach/lib/render_queries.py hvac_<loc>`
5. Scrape Google Maps; persist NDJSON to `raw/<city>.json`.
6. Run the pipeline: `python outreach/lib/cli/analyze.py hvac_<loc>` etc.
