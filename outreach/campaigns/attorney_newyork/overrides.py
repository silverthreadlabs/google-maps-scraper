"""Attorney NYC (LPO) — campaign overrides on verticals/attorney/config.py.

Reachability profile: the LPO client's lead value is a strict PERSONAL-CHANNEL
ladder, and reachability IS the classification (pain is skipped). See DDD-0003.
Scoped here per campaign, mirroring DDD-0002's precedent.

Ladder (highest → lowest), which maps directly onto tiers A/B/C/D:
  A  ≥2 personal channels (POC LinkedIn OR personal email, e.g. @gmail)
  B   1 personal channel
  C   no personal channel, but a personal social OR a named business email
      (john.doe@acme.com)
  D   none of the above, but a generic business email AND a phone (lowest);
      phone-only / nothing = unreachable, bottom of D.
"""
from __future__ import annotations

REACHABILITY_PROFILE = 'lpo_ladder'
