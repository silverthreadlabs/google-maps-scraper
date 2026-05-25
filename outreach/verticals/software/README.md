# Software / digital-agency vertical

Targets small-to-mid software, digital, and design agencies for Ezly
(AI reply assistant for client communication). Pain weighting
prioritizes communication-quality signals: tone, response speed,
follow-up.

## Default vertical_keyword

`software agency` — set per-city in `locations/<loc>.yaml` if a
market uses a different industry term.

## Honest fit notes

Ezly's ICP is solo freelancers on Upwork/Fiverr. The lists this
vertical scrapes (small/mid agencies) skew weaker than dental
gold sets (F1 ~0.78 vs ~0.85) because Google Maps reviews for B2B
software shops discuss project-delivery pain, not response-speed
pain. Pipeline proceeds anyway.

## Adding a software campaign

1. Author or pick a location: `outreach/locations/<loc>.yaml`
2. Create the campaign dir: `outreach/campaigns/software_<loc>/`
3. Write `campaign.yaml` (`vertical: software`, `location: <loc>`)
4. Optional: add `overrides.py` with regional outsourcer brand list
   (e.g. `DSO_TITLE_REGEX_EXTRA` for EPAM/GlobalLogic in UA).
5. Generate queries, scrape, run the pipeline.
