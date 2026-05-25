"""OSINT binding eval harness.

Reads gold_set.json, dispatches the osint-binder subagent on each
record, computes precision / recall, and runs a threshold sweep.

Gold-set record shape:
{
  "lead": {...same as orchestrator passes...},
  "field": "linkedin_url_poc",
  "candidates": [...],
  "correct_index": 0 | null    // null = no candidate is the right one
}

Usage:
  python outreach/campaigns/dentist_sunbelt/eval/osint_binding/eval_runner.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))


def evaluate(gold: list[dict], judgments: list[dict], thresholds: list[float]) -> dict:
    """Compare judge selections against `correct_index`. Returns metrics
    per threshold."""
    out: dict[float, dict] = {}
    for t in thresholds:
        tp = fp = fn = tn = 0
        for g, j in zip(gold, judgments):
            correct = g['correct_index']
            sel = j.get('best_match_index') if (j.get('selected_confidence') or 0) >= t else None
            if correct is None and sel is None:
                tn += 1
            elif correct is None and sel is not None:
                fp += 1
            elif correct is not None and sel is None:
                fn += 1
            elif correct == sel:
                tp += 1
            else:
                fp += 1
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        out[t] = {'precision': precision, 'recall': recall, 'f1': f1,
                  'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn}
    return out


def main() -> int:
    gold_path = Path(__file__).parent / 'gold_set.json'
    judgments_path = Path(__file__).parent / 'judgments.json'
    if not gold_path.exists():
        sys.stderr.write(f"missing gold_set: {gold_path}\n")
        return 2
    if not judgments_path.exists():
        sys.stderr.write(
            f"missing judgments: {judgments_path}\n"
            f"  bootstrap: dispatch the osint-binder subagent on {gold_path} → {judgments_path}\n"
        )
        return 2
    gold = json.loads(gold_path.read_text())
    judgments = json.loads(judgments_path.read_text())
    if len(gold) != len(judgments):
        sys.stderr.write(f"length mismatch: gold {len(gold)} vs judgments {len(judgments)}\n")
        return 2
    metrics = evaluate(gold, judgments, [0.70, 0.80, 0.85, 0.90, 0.95])
    print(f"{'threshold':<10} {'precision':>10} {'recall':>10} {'f1':>10} {'tp':>4} {'fp':>4} {'fn':>4} {'tn':>4}")
    for t, m in metrics.items():
        print(f"{t:<10} {m['precision']:>10.3f} {m['recall']:>10.3f} {m['f1']:>10.3f} "
              f"{m['tp']:>4} {m['fp']:>4} {m['fn']:>4} {m['tn']:>4}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
