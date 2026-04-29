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
