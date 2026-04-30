"""
Shared CLI helpers for outreach/scripts/.

Each stage script (enrich, validate, handoff, …) takes a `<pipeline>`
positional arg, loads `pipelines/<pipeline>/config.py`, and resolves paths
under `pipelines/<pipeline>/{raw,enrichment,outputs}/`.

Concurrency: every script wraps its main work in `pipeline_lock(...)`,
which acquires an exclusive `.lock` file under the pipeline directory.
Concurrent runs of the same pipeline (whether same stage or different
stages) refuse to start while a live PID holds the lock — preventing
the read-modify-write races where one stage's atomic write silently
overwrites another's annotations.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
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


def _pid_alive(pid: int) -> bool:
    """Best-effort liveness check. POSIX-only (Linux per the project setup).
    Returns False on PermissionError too — the process exists but is
    not ours; treat it as "live, don't reclaim"."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


@contextmanager
def pipeline_lock(pipeline_name: str, stage: str):
    """Acquire an exclusive `.lock` for `pipeline_name`, blocking concurrent
    runs of any stage on the same pipeline.

    Lockfile contents: `{pid, stage, since}`. On entry:
      - if the lockfile exists and the holding PID is alive → exit 2 with
        a clear error pointing at the holder (PID, stage, started-at) and
        the path to delete if the holding process is actually gone.
      - if the lockfile exists but its PID is not alive (or the file is
        corrupt) → reclaim with a stderr warning.
    On exit (success or exception) the lockfile is removed.
    """
    lockfile = pipeline_dir(pipeline_name) / '.lock'
    lockfile.parent.mkdir(parents=True, exist_ok=True)

    if lockfile.exists():
        try:
            holder = json.loads(lockfile.read_text())
        except (json.JSONDecodeError, OSError):
            sys.stderr.write(
                f"warn: corrupt lockfile {lockfile}; reclaiming\n"
            )
            lockfile.unlink(missing_ok=True)
        else:
            holder_pid = holder.get('pid', 0)
            if _pid_alive(holder_pid):
                sys.stderr.write(
                    f"error: pipeline {pipeline_name!r} is locked by pid "
                    f"{holder_pid} (stage {holder.get('stage')!r}, "
                    f"since {holder.get('since')}).\n"
                    f"if that process is no longer running, delete {lockfile}\n"
                )
                sys.exit(2)
            sys.stderr.write(
                f"warn: stale lockfile {lockfile} "
                f"(pid {holder_pid} not alive); reclaiming\n"
            )
            lockfile.unlink(missing_ok=True)

    payload = {
        'pid': os.getpid(),
        'stage': stage,
        'since': datetime.now(timezone.utc).isoformat(timespec='seconds'),
    }
    lockfile.write_text(json.dumps(payload))
    try:
        yield
    finally:
        # On the way out, only remove the lockfile if it's still ours.
        # A signal-killed run could leave a stale lock; so could a manual
        # `rm` mid-run. Either way, don't remove someone else's lock.
        try:
            current = json.loads(lockfile.read_text())
            if current.get('pid') == os.getpid():
                lockfile.unlink(missing_ok=True)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass
