"""
Regex-based pain classifier — industry-agnostic.

Wraps a `dict[category -> list[regex pattern]]` provided by the caller. Useful
as (a) a fast cheap baseline, (b) a corroboration signal for SBERT (UNION
boosts F1 modestly), and (c) a starting point when there is no labeled data
to tune SBERT thresholds.

Known limitation: keyword regex generates false positives on subjective text
(e.g. "emergency" matches both complaint and service description). Prefer
SBERT for production classification on subjective fields.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass


@dataclass
class RegexHit:
    category: str
    snippet: str
    rating: int | None
    reviewer: str | None
    matched_text: str          # the actual substring the regex matched


class RegexPainClassifier:
    """Industry-agnostic regex pain mining."""

    def __init__(
        self,
        patterns: dict[str, list[str]],
        max_rating: int = 3,
    ):
        """
        Args:
            patterns: dict[category -> list[regex pattern]]. Patterns compiled
                case-insensitive.
            max_rating: only classify reviews with rating <= this (default 3 —
                positive reviews don't carry pain we want to surface).
        """
        self.patterns = patterns
        self.max_rating = max_rating
        self._compiled: dict[str, list[re.Pattern]] = {
            cat: [re.compile(p, re.IGNORECASE) for p in pats]
            for cat, pats in patterns.items()
        }

    def classify(
        self,
        review_text: str,
        rating: int | None = None,
        reviewer: str | None = None,
    ) -> list[RegexHit]:
        if not review_text or (rating is not None and rating > self.max_rating):
            return []
        hits: list[RegexHit] = []
        for cat, pats in self._compiled.items():
            for p in pats:
                m = p.search(review_text)
                if m:
                    hits.append(RegexHit(
                        category=cat,
                        snippet=review_text,
                        rating=rating,
                        reviewer=reviewer,
                        matched_text=m.group(0),
                    ))
                    break  # one hit per category per review
        return hits

    def classify_many(self, reviews: list[dict]) -> dict[str, list[RegexHit]]:
        out: dict[str, list[RegexHit]] = defaultdict(list)
        for r in reviews:
            text = (r.get('snippet') or r.get('Description') or '').strip()
            rating = r.get('rating') or r.get('Rating')
            for hit in self.classify(
                text, rating=rating, reviewer=r.get('reviewer') or r.get('Name'),
            ):
                out[hit.category].append(hit)
        return dict(out)
