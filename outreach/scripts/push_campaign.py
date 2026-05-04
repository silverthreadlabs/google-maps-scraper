"""
Upsert a campaign in the stl-knights backend from a pipeline config.

Reads `pipelines/<pipeline>/config.py` for metro/vertical metadata and
POSTs to the campaigns API. The pipeline directory name becomes the slug.

Auth: reads OUTREACH_API_KEY from env (or --api-key). Exits 2 if unset.

Usage:
  python outreach/scripts/push_campaign.py <pipeline> [--base-url URL]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts._common import add_pipeline_arg, load_dotenv, load_pipeline_config

load_dotenv()


def _resolve_api_key(cli_key: str | None) -> str:
    key = cli_key or os.environ.get('OUTREACH_API_KEY', '')
    if not key:
        sys.stderr.write(
            "error: OUTREACH_API_KEY not set. "
            "Export it or pass --api-key.\n"
        )
        sys.exit(2)
    return key


def _vertical_from_config(cfg) -> str:
    """Best-effort vertical name from pipeline config.

    Checks VERTICAL (explicit), then docstring first line, then falls
    back to the pipeline slug itself."""
    if hasattr(cfg, 'VERTICAL'):
        return cfg.VERTICAL
    doc = (cfg.__doc__ or '').strip().split('\n')[0].strip()
    if doc:
        return doc.rstrip('.')
    return ''


def upsert_campaign(
    *,
    base_url: str,
    api_key: str,
    slug: str,
    name: str,
    metro: str,
    vertical: str,
    description: str | None = None,
) -> dict:
    payload = {
        'slug': slug,
        'name': name,
        'metro': metro,
        'vertical': vertical,
    }
    if description:
        payload['description'] = description

    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f'{base_url}/campaigns',
        data=data,
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(req) as resp:
            body = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode(errors='replace')
        sys.stderr.write(f"error: API returned {e.code}: {error_body}\n")
        sys.exit(1)
    except urllib.error.URLError as e:
        sys.stderr.write(f"error: cannot reach API at {base_url}: {e.reason}\n")
        sys.exit(2)

    return body


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Upsert a campaign from a pipeline config.',
    )
    add_pipeline_arg(parser)
    parser.add_argument(
        '--base-url', default=os.environ.get('STL_API_URL', 'http://localhost:3001'),
        help='stl-knights API base URL (default: $STL_API_URL or http://localhost:3001)',
    )
    parser.add_argument(
        '--api-key', default=None,
        help='override OUTREACH_API_KEY env var',
    )
    parser.add_argument(
        '--name', default=None,
        help='campaign display name (default: derived from pipeline name)',
    )
    args = parser.parse_args(argv)

    api_key = _resolve_api_key(args.api_key)
    cfg = load_pipeline_config(args.pipeline)

    slug = args.pipeline.replace('/', '_')
    metros = getattr(cfg, 'METROS', [])
    metro = metros[0] if metros else ''
    vertical = _vertical_from_config(cfg)
    name = args.name or slug.replace('_', ' ').title()

    result = upsert_campaign(
        base_url=args.base_url,
        api_key=api_key,
        slug=slug,
        name=name,
        metro=metro,
        vertical=vertical,
    )

    campaign = result.get('data', {})
    print(f"campaign upserted: {campaign.get('id', '?')} (slug={slug})", flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
