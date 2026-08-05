"""
Quality scoring + tier assignment — industry-agnostic.

`quality_score` combines weighted-pain × breadth × log(practice size) ×
rating-gap into a single number that ranks leads for outreach priority.
The weights themselves are vertical-specific (different verticals weight
"missed calls" vs "billing errors" differently against their service catalog).

`tier` bins quality_score into A/B/C/D for fast triage.
"""
from __future__ import annotations

import math
from typing import Literal

from lib.reachability import reachability_score

Tier = Literal['A', 'B', 'C', 'D', 'unranked']


def tier(quality_score: float | None) -> Tier:
    if quality_score is None:
        return 'unranked'
    if quality_score >= 60:
        return 'A'
    if quality_score >= 30:
        return 'B'
    if quality_score >= 15:
        return 'C'
    return 'D'


def quality_score(
    pain_hits: dict[str, list],
    review_count: int,
    rating: float,
    pain_weights: dict[str, int],
    *,
    rating_anchor: float = 4.9,
    weight_breadth: float = 2.0,
    weight_size: float = 3.0,
    weight_rating_gap: float = 4.0,
) -> tuple[float, int, int]:
    """
    Compute (quality_score, weighted_pain, breadth) for a lead.

    Args:
        pain_hits: dict[category -> list[hit-like]]. Hit list lengths matter
            (more hits per category = more evidence).
        review_count: total review count on Google Maps (proxy for size).
        rating: overall rating (0-5).
        pain_weights: dict[category -> int]. How much each pain category is
            worth — vertical-specific. Categories not in the dict default to 1.
        rating_anchor: rating from which the gap is measured. 4.9 means a
            perfect-5★ practice gets 0 contribution from the rating term.
        weight_breadth: per-distinct-category multiplier.
        weight_size: log10(reviews) multiplier.
        weight_rating_gap: (anchor - rating) multiplier.

    Returns:
        (quality_score, weighted_pain, breadth)
    """
    weighted = sum(pain_weights.get(c, 1) * len(hits) for c, hits in pain_hits.items())
    breadth = len(pain_hits)
    size = math.log10(max(review_count, 1))
    rating_gap = max(0.0, rating_anchor - (rating or 0.0))

    score = weighted + breadth * weight_breadth + size * weight_size + rating_gap * weight_rating_gap
    return round(score, 2), weighted, breadth


FIT_FULL = 60.0  # raw service-fit at/above which the fit half saturates at 50


def service_fit_norm(raw_fit: float | None, *, fit_full: float = FIT_FULL) -> float:
    """Map the open-ended raw service-fit score onto 0–50: linear below
    `fit_full`, capped at 50 above. See DDD-0001."""
    if raw_fit is None:
        return 0.0
    return round(min(1.0, max(0.0, raw_fit) / fit_full) * 50.0, 2)


def blended_tier(quality_score: float | None) -> Tier:
    """Tier on the blended 0–100 scale (DDD-0001). Distinct from `tier`,
    which still bins the legacy open-ended scale until stages migrate."""
    if quality_score is None:
        return 'unranked'
    if quality_score >= 75:
        return 'A'
    if quality_score >= 50:
        return 'B'
    if quality_score >= 25:
        return 'C'
    return 'D'


def score_lead(lead: dict, *, pain_weights: dict[str, int],
               reachability_profile: str = 'poc_channels') -> dict:
    """Single entry point for the blended rating. Reads the lead's pain,
    reviews, and contact data; returns the fields to merge onto the lead:
    raw + normalized service-fit, reachability + breakdown, blended
    quality_score (0–100), and blended tier.

    `reachability_profile` selects the reachability model (DDD-0002) —
    campaign-config-driven; default preserves the POC-channel behavior.
    Profiles that return a 0–50 half ('poc_channels', 'phone_first',
    'phone_email_parallel') need no branch here; their per-arm detail rides
    along in `reachability_breakdown` for the CSV builder to read without
    re-scoring."""
    reach, breakdown = reachability_score(lead, profile=reachability_profile)
    if reachability_profile == 'lpo_ladder':
        # DDD-0003: reachability is the whole classification (pain is skipped).
        # The ladder score already spans the 0–100 tier bands, so it IS the
        # blended quality_score; there is no service-fit half.
        raw_fit = fit = 0.0
        weighted = breadth = 0
        blended = round(reach, 2)
    else:
        pain = lead.get('agent_pain_hits') or lead.get('pain_hits') or {}
        rating = lead.get('rating', lead.get('review_rating')) or 0.0
        raw_fit, weighted, breadth = quality_score(
            pain, lead.get('review_count') or 0, rating, pain_weights=pain_weights,
        )
        fit = service_fit_norm(raw_fit)
        blended = round(fit + reach, 2)
    return {
        'service_fit_raw': raw_fit,
        'service_fit_score': fit,
        'reachability_score': reach,
        'reachability_breakdown': breakdown,
        'weighted_pain': weighted,
        'pain_breadth': breadth,
        'quality_score': blended,
        'tier': blended_tier(blended),
    }
