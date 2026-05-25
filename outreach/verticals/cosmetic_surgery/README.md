# Cosmetic / Plastic Surgery vertical

Targets independent cosmetic + plastic surgery practices and medspas
for Silverthread Labs Voice AI + Agentic AI services.

## Default vertical_keyword

`cosmetic surgeon` — varies per template line; `query_templates.txt`
also covers `plastic surgeon`, `medspa`, and `aesthetic clinic`.

## Adding a cosmetic-surgery campaign

1. Author or pick a location.
2. Create `campaigns/cosmetic_surgery_<loc>/campaign.yaml`.
3. If the location has regional dermatology DSOs (USDP, Westlake
   Dermatology in TX), add them to `overrides.py` as
   `DSO_TITLE_REGEX_EXTRA`.
