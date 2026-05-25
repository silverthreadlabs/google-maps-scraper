"""
Shared CLI helpers for outreach/lib/cli/.

Each stage script (enrich, validate, handoff, …) takes a `<pipeline>`
positional arg (kept for back-compat — the value resolves to
`campaigns/<name>/`). The helpers below load the merged CampaignConfig
(via `lib.campaign_config.load_campaign`) and resolve paths under
`campaigns/<name>/{raw,enrichment,outputs}/`.

Concurrency: every script wraps its main work in `pipeline_lock(...)`,
which acquires an exclusive `.lock` file under the campaign directory.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

OUTREACH_ROOT = Path(__file__).resolve().parent.parent.parent

if str(OUTREACH_ROOT) not in sys.path:
    sys.path.insert(0, str(OUTREACH_ROOT))


def load_dotenv(path: Path | None = None) -> None:
    """Load a .env file into os.environ; do not override existing values."""
    env_file = path or OUTREACH_ROOT / '.env'
    if not env_file.exists():
        return
    with env_file.open() as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, value = line.partition('=')
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def load_pipeline_config(pipeline_name: str):
    """Load merged CampaignConfig for `pipeline_name` (resolves to
    campaigns/<pipeline_name>/). Exits 2 with a clear stderr message
    if the campaign doesn't exist."""
    from lib.campaign_config import load_campaign
    campaign_dir = OUTREACH_ROOT / 'campaigns' / pipeline_name
    if not campaign_dir.is_dir():
        sys.stderr.write(
            f"error: campaign not found: {campaign_dir}\n"
        )
        sys.exit(2)
    try:
        return load_campaign(pipeline_name)
    except (FileNotFoundError, ValueError) as e:
        sys.stderr.write(f"error: failed to load campaign {pipeline_name!r}: {e}\n")
        sys.exit(2)


def pipeline_dir(pipeline_name: str) -> Path:
    return OUTREACH_ROOT / 'campaigns' / pipeline_name


def add_pipeline_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        'pipeline',
        help='campaign name, e.g. dentist_sunbelt — resolved against outreach/campaigns/<name>/',
    )


def require_attr(cfg, name: str, pipeline: str) -> object:
    """Look up `name` on the merged CampaignConfig. Names follow the
    legacy module-attribute style (PAIN_WEIGHTS, DSO_TITLE_REGEX, …);
    we translate them to the dataclass field names."""
    _MAPPING = {
        'PAIN_WEIGHTS':         'pain_weights',
        'SERVICE_MAP':          'service_map',
        'DSO_TITLE_REGEX':      'dso_title_regex',
        'DSO_EMAIL_DOMAINS':    'dso_email_domains',
        'GEOGRAPHIC_PREFIXES':  'geographic_prefixes',
        'METROS':               'metros',
        'METRO_AREA_CODES':     'metro_area_codes',
        'ENRICH_PROFILE':       'enrich_profile',
        'VENDOR_DOMAINS_EXTRA': 'vendor_domains_extra',
        'INDEPENDENT_FILTERS':  'independent_filters',
        'OSINT_ENABLED':        'osint_enabled',
        'OSINT_SOURCES':        'osint_sources',
        'OSINT_FIELDS_DESIRED': 'osint_fields_desired',
        'OSINT_CONFIDENCE_THRESHOLD': 'osint_confidence_threshold',
        'OSINT_HANDOFF_FIELDS': 'osint_handoff_fields',
        'OSINT_SERP_QUERIES':   'osint_serp_queries',
        'OSINT_DEEP_CRAWL_PATHS': 'osint_deep_crawl_paths',
        'OSINT_INDUSTRY_TERMS': 'osint_industry_terms',
        'VERTICAL':             'vertical',
    }
    field = _MAPPING.get(name)
    if field is None or not hasattr(cfg, field):
        sys.stderr.write(
            f"error: campaign {pipeline} does not define {name}\n"
        )
        sys.exit(2)
    return getattr(cfg, field)


def _pid_alive(pid: int) -> bool:
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
    """Acquire an exclusive .lock under campaigns/<pipeline_name>/.
    Same protocol as before, just rooted in campaigns/."""
    lockfile = pipeline_dir(pipeline_name) / '.lock'
    lockfile.parent.mkdir(parents=True, exist_ok=True)

    if lockfile.exists():
        try:
            holder = json.loads(lockfile.read_text())
        except (json.JSONDecodeError, OSError):
            sys.stderr.write(f"warn: corrupt lockfile {lockfile}; reclaiming\n")
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
                f"warn: stale lockfile {lockfile} (pid {holder_pid} not alive); reclaiming\n"
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
        try:
            current = json.loads(lockfile.read_text())
            if current.get('pid') == os.getpid():
                lockfile.unlink(missing_ok=True)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass
