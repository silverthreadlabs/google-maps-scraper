"""
SBERT-based pain classifier — industry-agnostic.

The classifier itself is universal. Per-vertical configuration (anchor
sentences, thresholds, title-deny rules) is passed in by the caller, typically
from `outreach/pipelines/<vertical>/config.py`.

Sentence-level: review is split into sentences, each encoded, max similarity
to anchors per category yields a per-category score. Categories above their
configured threshold are emitted, capped at top-K by similarity.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Naive sentence splitter — works for review prose. End-of-sentence
# punctuation followed by uppercase, or a newline.
_SENTENCE_RE = re.compile(r'(?<=[\.!?])\s+(?=[A-Z])|\n+')


@dataclass
class PainHit:
    category: str
    similarity: float
    snippet: str
    full_review: str
    rating: int | None
    reviewer: str | None
    matched_anchor: str | None


def split_sentences(text: str) -> list[str]:
    parts = [p.strip() for p in _SENTENCE_RE.split(text) if p and p.strip()]
    return parts if parts else [text.strip()]


class SbertPainClassifier:
    """Multi-label sentence-level pain classifier.

    Args:
        anchors: dict[category -> list[anchor sentence]] — vertical-specific.
        per_category_threshold: dict[category -> float], default 0.45 if missing.
        title_deny_rules: dict[category -> compiled regex]. When the practice
            title matches the regex for a category, the threshold is raised by
            `title_deny_threshold_bonus`. Use this to suppress false positives
            at practices whose business model IS the category (e.g. "Emergency
            Dentist" + `after_hours_emergency`).
        max_categories_per_review: cap on emitted categories per review.
        model_name: SBERT model to use. `all-MiniLM-L6-v2` is the fast default.
    """

    DEFAULT_THRESHOLD = 0.45
    DEFAULT_TITLE_BONUS = 0.10

    def __init__(
        self,
        anchors: dict[str, list[str]],
        per_category_threshold: dict[str, float] | None = None,
        title_deny_rules: dict[str, re.Pattern] | None = None,
        title_deny_threshold_bonus: float = DEFAULT_TITLE_BONUS,
        max_categories_per_review: int = 3,
        model_name: str = 'all-MiniLM-L6-v2',
    ):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(model_name)
        self.anchors = anchors
        self.per_category_threshold = per_category_threshold or {}
        self.title_deny_rules = title_deny_rules or {}
        self.title_deny_threshold_bonus = title_deny_threshold_bonus
        self.max_categories_per_review = max_categories_per_review

        self._anchor_embs: dict[str, list] = {}
        for cat, sentences in anchors.items():
            self._anchor_embs[cat] = self.model.encode(
                sentences, normalize_embeddings=True, show_progress_bar=False
            )

    def _threshold_for(self, category: str, practice_title: str) -> float:
        t = self.per_category_threshold.get(category, self.DEFAULT_THRESHOLD)
        deny = self.title_deny_rules.get(category)
        if deny and practice_title and deny.search(practice_title):
            t += self.title_deny_threshold_bonus
        return t

    def classify(
        self,
        review_text: str,
        practice_title: str = '',
        rating: int | None = None,
        reviewer: str | None = None,
    ) -> list[PainHit]:
        if not review_text or len(review_text.split()) < 4:
            return []

        sentences = [s for s in split_sentences(review_text) if len(s.split()) >= 4]
        if not sentences:
            sentences = [review_text]

        sent_embs = self.model.encode(sentences, normalize_embeddings=True, show_progress_bar=False)

        from sentence_transformers import util
        best_per_cat: dict[str, tuple[float, int, int]] = {}
        for cat, anchor_embs in self._anchor_embs.items():
            sims = util.cos_sim(sent_embs, anchor_embs)
            flat_max = float(sims.max())
            arg = int(sims.argmax())
            n_anchors = sims.shape[1]
            best_per_cat[cat] = (flat_max, arg // n_anchors, arg % n_anchors)

        hits: list[PainHit] = []
        for cat, (sim, sent_idx, anchor_idx) in best_per_cat.items():
            if sim >= self._threshold_for(cat, practice_title):
                hits.append(PainHit(
                    category=cat,
                    similarity=sim,
                    snippet=sentences[sent_idx],
                    full_review=review_text,
                    rating=rating,
                    reviewer=reviewer,
                    matched_anchor=self.anchors[cat][anchor_idx],
                ))

        hits.sort(key=lambda h: -h.similarity)
        return hits[:self.max_categories_per_review]

    def classify_many(
        self,
        reviews: list[dict],
        practice_title: str = '',
    ) -> dict[str, list[PainHit]]:
        out: dict[str, list[PainHit]] = {}
        for r in reviews:
            text = (r.get('snippet') or r.get('Description') or '').strip()
            rating = r.get('rating') or r.get('Rating')
            if rating and rating > 3:
                continue
            for hit in self.classify(
                text, practice_title,
                rating=rating, reviewer=r.get('reviewer') or r.get('Name'),
            ):
                out.setdefault(hit.category, []).append(hit)
        return out
