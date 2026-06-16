<!-- Generated: 2026-06-15 | Files scanned: requirements.txt, .env.example, push_*.py, enrichers/*.py | Token estimate: ~650 -->

# Dependencies (codemap)

External services this pipeline reaches, and the (deliberately small) Python footprint.

## External services / integrations

| Service | Used by | How |
|---------|---------|-----|
| **gosom Google Maps scraper** (Docker, parent repo) | `scrape` stage | slash-command only; output → `campaigns/<p>/raw/*.json`. See `.claude/skills/google-maps-scraper/SKILL.md` |
| **agent-browser** (Node CLI on `PATH`) → **Playwright** | `enrich` (`enrichers/website_crawl.py`), OSINT serp/deep-crawl | subprocess `agent-browser eval --stdin --session …`; Playwright browser binaries are the engine. Dependency chain: enrich → agent-browser → Playwright |
| **Claude Code + Anthropic API** | `classify`, `osint judge` stages | LLM subagents `.claude/agents/{pain-classifier,osint-binder}.md` (Read/Write tool budget only); no standalone script |
| **stl-knights backend API** | `push_campaign.py`, `push_leads.py` | `urllib` POST, `Bearer OUTREACH_API_KEY`. `POST {STL_API_URL}/campaigns` (upsert by slug) then `POST /leads/campaigns/:id/import` (chunks of 50, `importLeadsSchema` shape) |
| **WHOIS** registries | OSINT (`enrichers/whois_lookup.py`) | `python-whois` `lookup_domain(domain)` |
| **Search engines** (Google/Bing/DDG) | OSINT (`enrichers/serp.py`) | fetched via agent-browser; `run_serp_query_with_fallback` rotates on block |

## Environment (`.env.example`, loaded by `_common.load_dotenv`)

| Var | Purpose |
|-----|---------|
| `OUTREACH_API_KEY` | Bearer token for the stl-knights API (≥32 chars). `push_*` exit 2 if unset |
| `STL_API_URL` | API base URL (default `http://localhost:3001`) |

## Python packages (`requirements.txt`)

| Package | Used for |
|---------|----------|
| `python-whois>=0.9.0` | OSINT registrant lookup |
| `beautifulsoup4>=4.12` | HTML parsing (serp, deep_site_crawl, website_crawl) |
| `PyYAML>=6.0` | load `locations/*.yaml`, `campaign.yaml` |

HTTP uses the **stdlib `urllib`** (no `requests`/`httpx`). Python **3.11+** + `outreach/.venv`.

## Internal coupling

- Stages share `lib/cli/_common.py` (config load, dotenv, pipeline lock) and compose `lib/` modules (see `lib.md`).
- `push_leads.py` reuses `analyze` (review merge), `csv_builder` (email/pain field builders), and `push_campaign.upsert_campaign`.

## Setup

`scripts/setup.sh` (+ `--check`) bootstraps venv, agent-browser, Playwright binaries, and verifies Docker/Node/Claude Code. Full notes: `../README.md` "Prerequisites" / "Quickstart".
