"""
Build the sales-handoff CSV for a pipeline.

Reads master.json from the pipeline's latest dated outputs/ folder (or
`--master`); writes handoff.csv next to it (or `--out`).

Pipeline config requirements:
  PAIN_WEIGHTS  — category → weight
  SERVICE_MAP   — category → (service_name, service_url)

Both currently use the legacy flat category keys; the pain-classifier
subagent emits (main, sub) tuples. Re-keying both is the deferred work
in TODO.md.

Usage:
  python outreach/scripts/handoff.py <pipeline> [--master PATH] [--out PATH]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.handoff.csv_builder import build_handoff
from scripts._common import (
    add_pipeline_arg,
    load_pipeline_config,
    pipeline_dir,
    require_attr,
)
from scripts.validate import latest_master  # reuse the same convention


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Build the sales-handoff CSV for a pipeline.',
    )
    add_pipeline_arg(parser)
    parser.add_argument(
        '--master', type=Path, default=None,
        help='input master JSON (default: outputs/<latest-date>/master.json)',
    )
    parser.add_argument(
        '--out', type=Path, default=None,
        help='output CSV (default: <master-dir>/handoff.csv)',
    )
    args = parser.parse_args(argv)

    cfg = load_pipeline_config(args.pipeline)
    pain_weights = require_attr(cfg, 'PAIN_WEIGHTS', args.pipeline)
    service_map = require_attr(cfg, 'SERVICE_MAP', args.pipeline)

    pdir = pipeline_dir(args.pipeline)
    master_path = args.master or latest_master(pdir)
    if master_path is None or not master_path.exists():
        sys.stderr.write(
            f"error: master not found "
            f"(checked {args.master if args.master else f'{pdir}/outputs/<latest>/master.json'})\n"
        )
        return 2

    out_path = args.out or (master_path.parent / 'handoff.csv')

    build_handoff(
        input_path=master_path,
        output_path=out_path,
        service_map=service_map,
        pain_weights=pain_weights,
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())
