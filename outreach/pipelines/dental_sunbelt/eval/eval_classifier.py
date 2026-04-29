"""
Evaluate pain classifiers against the hand-labeled gold set.

Compares:
  - regex (lib/pain/regex.py with patterns from pipelines/dental_sunbelt/config.py)
  - SBERT (lib/pain/sbert.py with anchors from same config)
  - UNION

Reports per-category and micro/macro precision/recall/F1.
"""
import json
import sys
from pathlib import Path

ROOT = Path('/home/fassihhaider/Work/google-maps-scraper')
sys.path.insert(0, str(ROOT / 'outreach'))

from lib.pain.regex import RegexPainClassifier
from pipelines.dental_sunbelt.config import PAIN_REGEX_PATTERNS

regex_classifier = RegexPainClassifier(patterns=PAIN_REGEX_PATTERNS)

EVAL_DIR = ROOT / 'outreach' / 'pipelines' / 'dental_sunbelt' / 'eval'


def regex_predict(text: str, rating: int) -> set[str]:
    return {h.category for h in regex_classifier.classify(text, rating=rating)}


def sbert_predict(clf, text: str, practice: str, rating: int) -> set[str]:
    if rating > 3:
        return set()
    hits = clf.classify(text, practice_title=practice, rating=rating)
    return {h.category for h in hits}


def metrics(gold: list[set[str]], pred: list[set[str]], categories: list[str]) -> dict:
    """Compute per-category and aggregate precision/recall/F1."""
    per_cat = {}
    for cat in categories:
        tp = sum(1 for g, p in zip(gold, pred) if cat in g and cat in p)
        fp = sum(1 for g, p in zip(gold, pred) if cat not in g and cat in p)
        fn = sum(1 for g, p in zip(gold, pred) if cat in g and cat not in p)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        per_cat[cat] = {'tp': tp, 'fp': fp, 'fn': fn, 'P': precision, 'R': recall, 'F1': f1}

    # Micro: aggregate TP/FP/FN across categories
    total_tp = sum(c['tp'] for c in per_cat.values())
    total_fp = sum(c['fp'] for c in per_cat.values())
    total_fn = sum(c['fn'] for c in per_cat.values())
    micro_P = total_tp / (total_tp + total_fp) if (total_tp + total_fp) else 0.0
    micro_R = total_tp / (total_tp + total_fn) if (total_tp + total_fn) else 0.0
    micro_F1 = 2 * micro_P * micro_R / (micro_P + micro_R) if (micro_P + micro_R) else 0.0

    # Macro: average per-cat F1
    cats_with_gold = [c for c in categories if per_cat[c]['tp'] + per_cat[c]['fn'] > 0]
    macro_F1 = sum(per_cat[c]['F1'] for c in cats_with_gold) / len(cats_with_gold) if cats_with_gold else 0.0

    # Exact-match accuracy: how often did pred == gold exactly?
    exact = sum(1 for g, p in zip(gold, pred) if g == p) / len(gold)

    return {'per_cat': per_cat, 'micro_F1': micro_F1, 'micro_P': micro_P, 'micro_R': micro_R,
            'macro_F1': macro_F1, 'exact_match': exact}


def fmt_metrics(name, m):
    print(f"\n=== {name} ===")
    print(f"  micro F1: {m['micro_F1']:.3f}  (P={m['micro_P']:.3f}, R={m['micro_R']:.3f})")
    print(f"  macro F1: {m['macro_F1']:.3f}")
    print(f"  exact match: {m['exact_match']:.3f}")
    print(f"  {'category':<35} {'tp':>3} {'fp':>3} {'fn':>3}  {'P':>5} {'R':>5} {'F1':>5}")
    for cat, c in m['per_cat'].items():
        if c['tp'] + c['fp'] + c['fn'] == 0:
            continue
        print(f"  {cat:<35} {c['tp']:>3} {c['fp']:>3} {c['fn']:>3}  {c['P']:>5.2f} {c['R']:>5.2f} {c['F1']:>5.2f}")


def main():
    samples = json.load(open(EVAL_DIR / 'sample_unlabeled.json'))
    labels_doc = json.load(open(EVAL_DIR / 'labels.json'))
    label_by_id = {l['id']: set(l['categories']) for l in labels_doc['labels']}
    categories = labels_doc['_categories']

    gold = []
    samples_kept = []
    for s in samples:
        if s['id'] in label_by_id:
            gold.append(label_by_id[s['id']])
            samples_kept.append(s)
    print(f"loaded {len(samples_kept)} labeled reviews")

    # 1) Regex
    regex_pred = [regex_predict(s['snippet'], s['rating']) for s in samples_kept]
    fmt_metrics("REGEX (current production)", metrics(gold, regex_pred, categories))

    # 2) SBERT (sentence-level + per-category thresholds + top-3 cap)
    print("\nloading SBERT all-MiniLM-L6-v2 ...", flush=True)
    from lib.pain.sbert import SbertPainClassifier
    from pipelines.dental_sunbelt.config import (
        SBERT_ANCHORS, SBERT_PER_CATEGORY_THRESHOLD, SBERT_TITLE_DENY_RULES,
    )
    clf = SbertPainClassifier(
        anchors=SBERT_ANCHORS,
        per_category_threshold=SBERT_PER_CATEGORY_THRESHOLD,
        title_deny_rules=SBERT_TITLE_DENY_RULES,
    )
    sbert_pred = [sbert_predict(clf, s['snippet'], s['practice'], s['rating']) for s in samples_kept]
    fmt_metrics("SBERT MiniLM (top-3 cap)", metrics(gold, sbert_pred, categories))

    # 3) Combined
    combined_pred = [r | s for r, s in zip(regex_pred, sbert_pred)]
    fmt_metrics("UNION(regex, SBERT MiniLM)", metrics(gold, combined_pred, categories))

    # 5) Mistake analysis: where SBERT@0.45 disagrees with gold
    print("\n=== SBERT disagreements vs gold (worst cases) ===")
    disagreements = []
    for i, (s, g, p) in enumerate(zip(samples_kept, gold, sbert_pred)):
        missed = g - p
        extra = p - g
        if missed or extra:
            disagreements.append((s, g, p, missed, extra))
    print(f"total disagreement count: {len(disagreements)} / {len(samples_kept)}")
    # Show 8 examples
    for s, g, p, missed, extra in disagreements[:8]:
        print(f"\n  id={s['id']} rating={s['rating']}★ practice={s['practice'][:40]}")
        print(f"    snippet: {s['snippet'][:160]}...")
        print(f"    gold: {sorted(g)}")
        print(f"    pred: {sorted(p)}")
        if missed: print(f"    MISSED: {sorted(missed)}")
        if extra:  print(f"    EXTRA:  {sorted(extra)}")


if __name__ == '__main__':
    main()
