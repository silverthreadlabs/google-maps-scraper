"""
Evaluate pain-classifier subagent output against the gold label set.

Pure metric math — no LLM, no SDK. Dispatch the `pain-classifier` subagent
separately (in your Claude Code session) on `sample_unlabeled.json`, save
the JSON output, then run this script against it.

Usage:
    python eval_runner.py <predictions.json> [<labels.json>]

Predictions schema (the subagent emits this):
    [{"id": <int>, "categories": [{"main": str, "sub": str|null,
                                   "confidence": float, "quote": str,
                                   "reasoning": str}]}, ...]

Labels schema (gold):
    {"_categories": {<main>: [<sub>, ...]}, "labels": [
        {"id": <int>, "categories": [{"main": str, "sub": str}, ...]}, ...]}

Reports:
  - Two-level F1 (main-only / strict (main, sub))
  - Per-category P/R/F1 at each level
  - Gold gaps (subs with 0 labeled examples — sub-level metrics there are n/a)
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path


def load_gold(path: Path) -> tuple[dict[int, set[tuple[str, str | None]]], dict]:
    doc = json.loads(path.read_text())
    gold: dict[int, set[tuple[str, str | None]]] = {}
    for entry in doc['labels']:
        gold[entry['id']] = {(c['main'], c.get('sub')) for c in entry['categories']}
    return gold, doc.get('_categories', {})


def load_predictions(path: Path) -> dict[int, set[tuple[str, str | None]]]:
    doc = json.loads(path.read_text())
    out: dict[int, set[tuple[str, str | None]]] = {}
    for entry in doc:
        out[entry['id']] = {(c['main'], c.get('sub')) for c in entry['categories']}
    return out


def metrics(
    gold_by_id: dict[int, set],
    pred_by_id: dict[int, set],
    label_universe: list,
) -> dict:
    """Compute per-label and aggregate P/R/F1.

    label_universe is the list of valid labels (e.g., main strings, or
    (main, sub) tuples). gold/pred sets must contain elements from this
    universe.
    """
    per_label = {}
    for label in label_universe:
        tp = sum(1 for i, g in gold_by_id.items()
                 if label in g and label in pred_by_id.get(i, set()))
        fp = sum(1 for i, p in pred_by_id.items()
                 if label in p and label not in gold_by_id.get(i, set()))
        fn = sum(1 for i, g in gold_by_id.items()
                 if label in g and label not in pred_by_id.get(i, set()))
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        per_label[label] = {'tp': tp, 'fp': fp, 'fn': fn, 'P': precision, 'R': recall, 'F1': f1}

    total_tp = sum(c['tp'] for c in per_label.values())
    total_fp = sum(c['fp'] for c in per_label.values())
    total_fn = sum(c['fn'] for c in per_label.values())
    micro_P = total_tp / (total_tp + total_fp) if (total_tp + total_fp) else 0.0
    micro_R = total_tp / (total_tp + total_fn) if (total_tp + total_fn) else 0.0
    micro_F1 = 2 * micro_P * micro_R / (micro_P + micro_R) if (micro_P + micro_R) else 0.0

    labels_with_gold = [l for l in label_universe if per_label[l]['tp'] + per_label[l]['fn'] > 0]
    macro_F1 = (sum(per_label[l]['F1'] for l in labels_with_gold) / len(labels_with_gold)
                if labels_with_gold else 0.0)

    exact = sum(1 for i in gold_by_id
                if gold_by_id[i] == pred_by_id.get(i, set())) / max(len(gold_by_id), 1)

    return {
        'per_label': per_label,
        'micro_P': micro_P, 'micro_R': micro_R, 'micro_F1': micro_F1,
        'macro_F1': macro_F1,
        'exact_match': exact,
        'labels_with_gold': labels_with_gold,
    }


def fmt_section(title: str, m: dict, label_universe: list) -> None:
    print(f"\n=== {title} ===")
    print(f"  micro F1: {m['micro_F1']:.3f}  (P={m['micro_P']:.3f}, R={m['micro_R']:.3f})")
    print(f"  macro F1: {m['macro_F1']:.3f}  (over {len(m['labels_with_gold'])} labels with ≥1 gold)")
    print(f"  exact match: {m['exact_match']:.3f}")
    print(f"  {'label':<60} {'tp':>3} {'fp':>3} {'fn':>3}  {'P':>5} {'R':>5} {'F1':>5}")
    for label in label_universe:
        c = m['per_label'][label]
        if c['tp'] + c['fp'] + c['fn'] == 0:
            continue
        label_str = label if isinstance(label, str) else f"{label[0]}/{label[1]}"
        print(f"  {label_str:<60} {c['tp']:>3} {c['fp']:>3} {c['fn']:>3}"
              f"  {c['P']:>5.2f} {c['R']:>5.2f} {c['F1']:>5.2f}")


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: eval_runner.py <predictions.json> [<labels.json>]", file=sys.stderr)
        return 2

    pred_path = Path(argv[1])
    labels_path = Path(argv[2]) if len(argv) > 2 else pred_path.parent / 'labels.json'

    gold_strict, taxonomy = load_gold(labels_path)
    pred_strict = load_predictions(pred_path)

    missing_ids = set(gold_strict) - set(pred_strict)
    extra_ids = set(pred_strict) - set(gold_strict)
    if missing_ids:
        print(f"warn: {len(missing_ids)} gold ids missing from predictions: "
              f"{sorted(missing_ids)[:10]}{'...' if len(missing_ids) > 10 else ''}",
              file=sys.stderr)
    if extra_ids:
        print(f"warn: {len(extra_ids)} prediction ids not in gold: "
              f"{sorted(extra_ids)[:10]}{'...' if len(extra_ids) > 10 else ''}",
              file=sys.stderr)

    print(f"loaded {len(gold_strict)} gold entries, {len(pred_strict)} predictions")

    gold_main = {i: {m for m, _ in s} for i, s in gold_strict.items()}
    pred_main = {i: {m for m, _ in s} for i, s in pred_strict.items()}
    main_universe = sorted(taxonomy.keys()) if taxonomy else sorted(
        {m for s in gold_main.values() for m in s})
    fmt_section("MAIN-ONLY (loose)", metrics(gold_main, pred_main, main_universe), main_universe)

    sub_universe = sorted(
        {(m, s) for m, subs in taxonomy.items() for s in subs}
        | {(m, None) for m in taxonomy},
        key=lambda x: (x[0], x[1] or ''),
    )
    fmt_section("STRICT (main, sub)", metrics(gold_strict, pred_strict, sub_universe), sub_universe)

    gold_sub_counts = Counter(c for s in gold_strict.values() for c in s)
    gaps = [c for c in sub_universe if gold_sub_counts.get(c, 0) == 0]
    if gaps:
        print(f"\nGold gaps (no examples — strict-level F1 here is uninformative):")
        for m, s in gaps:
            print(f"  {m}/{s if s is not None else '<no-sub>'}")

    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
