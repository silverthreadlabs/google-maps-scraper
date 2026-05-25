# OSINT binding eval — dental_sunbelt

Hand-labeled set used to tune `OSINT_CONFIDENCE_THRESHOLD`.

## Bootstrap (first run)

1. Run `python outreach/lib/cli/osint_enrich.py dentist_sunbelt` on a known-good slice (50–100 leads).
2. Open the resulting `enrichment/osint/<date>.json` and copy 50–100 `(lead, field, candidates)` triples into `gold_set.json`, adding `correct_index` (the index of the correct candidate, or `null` if none is correct).
3. Dispatch the `osint-binder` subagent on `gold_set.json` → write the result to `judgments.json` in the same shape the merge step consumes.
4. Run `python eval_runner.py` — the threshold sweep tells you where precision drops off.

## Gold-set record shape

```json
{
  "lead": {"place_id": "...", "business_name": "...", "city": "...", "domain": "...", ...},
  "field": "linkedin_url_poc",
  "candidates": [{...}, {...}],
  "correct_index": 0
}
```

`correct_index: null` is meaningful — it represents leads where the right answer is "no candidate, skip the field." The eval treats false-matches in this bucket as severe (precision-killers).

## Re-running after threshold change

The gold set + judgments are static. Re-run `eval_runner.py` with new threshold list (edit the call in `main`) — no re-fetching needed.
