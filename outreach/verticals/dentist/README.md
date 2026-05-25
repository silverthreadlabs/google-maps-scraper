# Dentist vertical

Targets independent dental practices for Silverthread Labs Voice AI
+ Agentic AI services. Pain weighting prioritizes call coverage,
booking friction, and follow-up — the categories STL's product
directly addresses.

## Default vertical_keyword

`dentist` — set per-city in `locations/<loc>.yaml` if a market uses
a different industry term.

## Query templates

See `query_templates.txt`. Placeholders: `{vertical_keyword}`,
`{city}`, `{state}`, `{neighborhood}`. Lines containing
`{neighborhood}` are expanded once per neighborhood in
`locations/<loc>.yaml`; lines without it emit once per city.

## Adding a dental campaign

1. Author or pick a location: `outreach/locations/<loc>.yaml`
2. Create the campaign dir: `outreach/campaigns/dentist_<loc>/`
3. Write `campaign.yaml`:
   ```yaml
   vertical: dentist
   location: <loc>
   slug: dentist_<loc>
   ```
4. Generate queries: `python outreach/lib/render_queries.py dentist_<loc>`
5. Scrape Google Maps; persist NDJSON to `raw/<city>.json`.
6. Run the pipeline: `python outreach/lib/cli/analyze.py dentist_<loc>` etc.
