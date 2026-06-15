# Automotive vertical

Shared template for automotive-services campaigns. Targets the local
automotive trade — independent repair, body/collision, detailing, glass,
smog, tire, transmission, parts, upholstery/audio/customization, paint,
rental, and used-car businesses. Owner-/manager-led local service shops,
so this vertical is modeled on **dentist** (OSINT on, owner-led enrich
markers), not retail.

## What's here

- `config.py` — pain weights, service map, DSO chain regex/domains,
  `EnrichProfile`, OSINT templates. All knobs vertical-wide.
- `query_templates.txt` — 19 literal service-type lines (one per service
  category) expanded per city by `lib/render_queries.py`. Lines carry no
  `{vertical_keyword}`; only `{city}`/`{state}`/`{neighborhood}` are
  substituted.

## Pain taxonomy

Vertical-agnostic STL hierarchy (mains 1–6). Weights are the proven dental
default. **Tunable:** for auto repair, surprise-billing ("quoted X, billed
Y") and dropped quotes are the signature pains — `billing_or_intake_errors`
may warrant a 5. Bump it via `campaigns/<c>/overrides.py:PAIN_WEIGHTS` once
review data justifies it; don't hand-edit the vertical default without it.

## Chains

National automotive chains (Jiffy Lube, Midas, Caliber Collision, AutoZone,
Enterprise, CarMax, …) live in `config.py`. Region-specific franchise groups
go in `campaigns/<c>/overrides.py` under `DSO_TITLE_REGEX_EXTRA` /
`DSO_EMAIL_DOMAINS_EXTRA`.
