"""Graft no-website DM company channels onto master (CLAUDE.md rule 1: add
fields + _source + _added_at, never overwrite populated values, never drop).

Adds:
  social_urls            (list[str])  facebook/instagram/yelp/linkedin URLs found
  social_urls_source     'dm_nowebsite_research'
  social_urls_added_at   ISO-8601 UTC
  emails / emails_source : appends a verified company email if present & new
"""
from __future__ import annotations
import json, sys
from datetime import datetime, timezone
from pathlib import Path

CAMP = Path(__file__).resolve().parents[2]
MASTER = CAMP / 'outputs' / '2026-06-12' / 'master.json'
COMP = Path(__file__).resolve().parent / 'company_channels.json'

now = datetime.now(timezone.utc).isoformat()
company = json.load(COMP.open())
leads = json.load(MASTER.open())
by_pid = {l.get('place_id'): l for l in leads}

socials_added = emails_added = leads_touched = 0
for pid, chans in company.items():
    lead = by_pid.get(pid)
    if lead is None:
        continue
    touched = False
    urls = [chans[k] for k in ('facebook', 'instagram', 'linkedin', 'yelp') if chans.get(k)]
    if urls:
        existing = lead.get('social_urls') or []
        merged = list(dict.fromkeys(existing + urls))  # dedupe, preserve order
        if merged != existing:
            lead['social_urls'] = merged
            lead['social_urls_source'] = 'dm_nowebsite_research'
            lead['social_urls_added_at'] = now
            socials_added += len(merged) - len(existing)
            touched = True
    email = chans.get('email')
    if email:
        emails = lead.get('emails') or []
        if email not in emails:
            lead['emails'] = emails + [email]
            lead.setdefault('emails_source', {})
            if isinstance(lead['emails_source'], dict):
                lead['emails_source'][email] = 'dm_nowebsite_research'
            emails_added += 1
            touched = True
    if touched:
        leads_touched += 1

tmp = MASTER.with_suffix('.json.tmp')
tmp.write_text(json.dumps(leads, ensure_ascii=False, indent=2))
tmp.rename(MASTER)
print(f'leads touched : {leads_touched}')
print(f'social urls + : {socials_added}')
print(f'emails +      : {emails_added}')
print(f'wrote {MASTER}')
