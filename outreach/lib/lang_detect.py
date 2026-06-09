"""Lightweight language gate for the translate stage.

`needs_translation(snippet, locale)` decides whether a review snippet should
be sent to the translator subagent.

Two gates, cheap and dependency-free:
  1. Locale gate — English-locale campaigns (`en-*`) never translate.
  2. Script gate — a snippet is sent only if it contains Cyrillic characters.

LIMITATION: the script gate is correct for the current Ukrainian/Russian
campaign (Cyrillic source). A future Latin-script source language (e.g. pl-PL,
es-ES) would pass the locale gate but fail the script gate, yielding a no-op.
When such a campaign appears, replace the script heuristic with a real
detector (e.g. a langdetect dependency) — the rest of the stage is unchanged.
"""
from __future__ import annotations


def _has_cyrillic(s: str) -> bool:
    return any('Ѐ' <= ch <= 'ӿ' for ch in s)


def needs_translation(snippet: str, locale: str) -> bool:
    if not snippet or not snippet.strip():
        return False
    if (locale or '').lower().startswith('en'):
        return False
    return _has_cyrillic(snippet)
