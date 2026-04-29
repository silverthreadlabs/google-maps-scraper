"""
Pipeline orchestrator — single CLI for running campaign stages.

Stub for v1. Each stage is a function that operates on a pipeline folder.
Stages are idempotent and resumable: running `analyze` twice produces the
same output; `enrich` skips leads already in the enrichment sidecar.

Usage:
    python outreach/orchestrator.py <stage> <pipeline-name>

Stages (planned):
    scrape    — gosom Docker → pipelines/<name>/raw/<metro>.json
    analyze   — pain mining + chain detection + quality_score → outputs/<date>/master.json
    enrich    — website_crawl → enrichment/dental_enrichment.json
    validate  — email/phone/POC validators → annotated master.json
    handoff   — build CSV + README → outputs/<date>/handoff.csv

Run `python outreach/orchestrator.py --help` for the actual implemented set.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).parent

# Make `lib.*` and `pipelines.*` importable.
sys.path.insert(0, str(ROOT))


def cmd_scrape(args: argparse.Namespace) -> int:
    print(f"[stub] scrape {args.pipeline}", flush=True)
    print("       wraps the gosom Docker scraper to write raw NDJSONs into")
    print(f"       pipelines/{args.pipeline}/raw/. Implementation pending.")
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    print(f"[stub] analyze {args.pipeline}", flush=True)
    print("       reads raw NDJSONs, runs pain classifier (regex/sbert/llm),")
    print("       chain detection, quality_score, writes outputs/<date>/master.json.")
    print("       Implementation pending — currently in legacy script.")
    return 0


def cmd_enrich(args: argparse.Namespace) -> int:
    print(f"[stub] enrich {args.pipeline}", flush=True)
    print("       runs lib/enrichers/website_crawl.py against the master.json.")
    print("       Implementation pending — currently in legacy script.")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    print(f"[stub] validate {args.pipeline}", flush=True)
    print("       runs lib/validators/{email,phone,poc} against master.json,")
    print("       marking invalid values via sibling flags (never deletes).")
    print("       Implementation pending.")
    return 0


def cmd_handoff(args: argparse.Namespace) -> int:
    print(f"[stub] handoff {args.pipeline}", flush=True)
    print("       runs lib/handoff/csv_builder.py to write outputs/<date>/handoff.csv.")
    print("       Implementation pending — currently in legacy script.")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Run all stages in sequence."""
    for fn in [cmd_scrape, cmd_analyze, cmd_enrich, cmd_validate, cmd_handoff]:
        rc = fn(args)
        if rc != 0:
            return rc
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Outreach pipeline orchestrator')
    subparsers = parser.add_subparsers(dest='cmd', required=True)

    for name, fn in [
        ('scrape', cmd_scrape),
        ('analyze', cmd_analyze),
        ('enrich', cmd_enrich),
        ('validate', cmd_validate),
        ('handoff', cmd_handoff),
        ('run', cmd_run),
    ]:
        sub = subparsers.add_parser(name, help=fn.__doc__ or name)
        sub.add_argument('pipeline', help='pipeline name, e.g. dental_sunbelt')
        sub.set_defaults(func=fn)

    args = parser.parse_args(argv)

    pipeline_dir = ROOT / 'pipelines' / args.pipeline
    if not pipeline_dir.is_dir():
        print(f"error: pipeline not found: {pipeline_dir}", file=sys.stderr)
        return 2
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
