"""
Shared CLI helpers for outreach/scripts/.

Each stage script (enrich, validate, handoff, …) takes a `<pipeline>`
positional arg, loads `pipelines/<pipeline>/config.py`, and resolves paths
under `pipelines/<pipeline>/{raw,enrichment,outputs}/`.
"""
from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path
from types import ModuleType

OUTREACH_ROOT = Path(__file__).resolve().parent.parent

if str(OUTREACH_ROOT) not in sys.path:
    sys.path.insert(0, str(OUTREACH_ROOT))


def load_pipeline_config(pipeline_name: str) -> ModuleType:
    """Import `pipelines.<pipeline_name>.config` and return the module.

    Exits 2 with a clear stderr message if the pipeline doesn't exist.
    """
    if not (OUTREACH_ROOT / 'pipelines' / pipeline_name).is_dir():
        sys.stderr.write(
            f"error: pipeline not found: {OUTREACH_ROOT / 'pipelines' / pipeline_name}\n"
        )
        sys.exit(2)
    try:
        return importlib.import_module(f'pipelines.{pipeline_name}.config')
    except ModuleNotFoundError as e:
        sys.stderr.write(f"error: failed to import pipelines/{pipeline_name}/config.py: {e}\n")
        sys.exit(2)


def pipeline_dir(pipeline_name: str) -> Path:
    return OUTREACH_ROOT / 'pipelines' / pipeline_name


def add_pipeline_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        'pipeline',
        help='pipeline name, e.g. dental_sunbelt — resolved against outreach/pipelines/<name>/',
    )


def require_attr(cfg: ModuleType, name: str, pipeline: str) -> object:
    """Look up `name` on the pipeline config module; exit 2 if missing."""
    if not hasattr(cfg, name):
        sys.stderr.write(
            f"error: pipelines/{pipeline}/config.py does not define {name}\n"
        )
        sys.exit(2)
    return getattr(cfg, name)
