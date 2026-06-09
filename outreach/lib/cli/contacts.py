"""DEPRECATED — folded into the unified `decision-makers` stage.

`contacts` used to find the non-owner team (CTO / sales / BizDev) and append
them to `pocs[]`. That capability now lives in `lib.cli.decision_makers`,
which captures the owner AND the rest of the team in one pass (and projects
the owner_* scalars off the designated primary). This module stays as a thin
forwarding shim so existing invocations keep working.

Use going forward:
  python outreach/lib/cli/decision_makers.py <pipeline> --print-queue|--apply
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from lib.cli.decision_makers import main as _decision_makers_main

DEPRECATION_NOTICE = (
    "warning: `contacts` is deprecated and now forwards to `decision-makers`. "
    "Update your runbook to call decision_makers.py; the default sidecar path "
    "is now enrichment/decision_makers/<date>.json (pass --sidecar for an "
    "older contacts/ sidecar).\n"
)


def main(argv: list[str] | None = None) -> int:
    sys.stderr.write(DEPRECATION_NOTICE)
    return _decision_makers_main(argv)


if __name__ == '__main__':
    sys.exit(main())
