"""Render per-city query files from a vertical template × a location.

Inputs:
    templates     — newline-separated template lines using placeholders
                    {vertical_keyword}, {city}, {state}, {neighborhood}.
                    Templates containing {neighborhood} expand once per
                    neighborhood in the city; templates without it emit
                    once per city.
    location      — dict with keys 'metros', 'neighborhoods',
                    'cities_state', 'cities_vertical_keyword'.
                    See render_queries_tests.py for shape.
    out_dir       — destination directory; files written as <city>.txt.

Pattern:
    Replace {city} with the metro name lowercased.
    Replace {state} with the per-city state (may be empty).
    Replace {vertical_keyword} with the caller-supplied default; per-city
        overrides are sourced from location['cities_vertical_keyword'].
    Replace {neighborhood} by expanding the line once per neighborhood.

The output is sorted-then-deduped per city so re-renders are stable.
"""
from __future__ import annotations

from pathlib import Path


def render_for_campaign(
    templates: str,
    location: dict,
    out_dir: Path,
    *,
    vertical_keyword: str,
) -> None:
    """Render templates × location into <out_dir>/<city>.txt files."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    template_lines = [
        line for line in (line.rstrip() for line in templates.splitlines())
        if line
    ]

    for city in location['metros']:
        state = location['cities_state'].get(city, '')
        neighborhoods = location['neighborhoods'].get(city) or []
        keyword = location['cities_vertical_keyword'].get(city, vertical_keyword)

        rendered: list[str] = []
        for tpl in template_lines:
            needs_neighborhood = '{neighborhood}' in tpl
            if needs_neighborhood:
                if not neighborhoods:
                    continue
                for nb in neighborhoods:
                    rendered.append(_substitute(
                        tpl, keyword=keyword, city=city, state=state,
                        neighborhood=nb,
                    ))
            else:
                rendered.append(_substitute(
                    tpl, keyword=keyword, city=city, state=state,
                ))

        seen: set[str] = set()
        ordered: list[str] = []
        for line in rendered:
            if line in seen:
                continue
            seen.add(line)
            ordered.append(line)

        (out_dir / f'{city}.txt').write_text('\n'.join(ordered) + '\n')


def _substitute(
    tpl: str,
    *,
    keyword: str,
    city: str,
    state: str,
    neighborhood: str = '',
) -> str:
    """Apply placeholder substitutions, then collapse any double spaces
    introduced when {state} or {neighborhood} resolves to an empty string."""
    out = (tpl
           .replace('{vertical_keyword}', keyword)
           .replace('{neighborhood}', neighborhood)
           .replace('{city}', city)
           .replace('{state}', state))
    while '  ' in out:
        out = out.replace('  ', ' ')
    return out.strip()
