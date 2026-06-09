"""DEPRECATED — folded into the unified `decision-makers` stage.

`owner-lookup` used to find the single top decision-maker and write the
`owner_name` / `owner_title` / `owner_linkedin` scalars. Those scalars are now
a *derived projection* of the primary POC produced by
`lib.cli.decision_makers`, which captures the owner AND the rest of the team in
one pass, each with all channels. This module stays as a thin forwarding shim
so existing invocations keep working.

The legacy sidecar shape `{place_id: {name, title, linkedin}}` is still
accepted by the unified applier (treated as a single primary person), so old
owner sidecars apply unchanged via `--sidecar`.

Use going forward:
  python outreach/lib/cli/decision_makers.py <pipeline> --print-queue|--apply
  python outreach/lib/cli/decision_makers.py <pipeline> --backfill-owner-pocs
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from lib.cli.decision_makers import main as _decision_makers_main

DEPRECATION_NOTICE = (
    "warning: `owner-lookup` is deprecated and now forwards to "
    "`decision-makers`. Update your runbook to call decision_makers.py; the "
    "default sidecar path is now enrichment/decision_makers/<date>.json (pass "
    "--sidecar for an older owner_lookups/ sidecar).\n"
)


def main(argv: list[str] | None = None) -> int:
    sys.stderr.write(DEPRECATION_NOTICE)
    return _decision_makers_main(argv)


if __name__ == '__main__':
    sys.exit(main())
