# Outreach — Domain Glossary

> Shared vocabulary for this codebase. Defines **what** things are, not **how** they are built.
> Keep implementation details (file paths, libraries, code) out of this file.

## Core Entities

- **Lead** — one business we may pitch, deduped by its Google Maps identity. Carries contact, review, pain, and reachability data accumulated across pipeline stages.
- **Quality score** — the single number a Lead is ranked by for outreach priority. Blends **service-fit** and **reachability**. Higher = pitch sooner.
- **Tier** — the A/B/C/D bucket a Lead's Quality score falls into, for fast sales triage.

## Rating dimensions

- **Service-fit** — how well Silverthread's services match the pain a Lead exhibits in its reviews. The pre-existing half of the Quality score (weighted pain × breadth × size × rating-gap).
- **Reachability** — how easily our sales team can reach a *decision-maker* at the Lead. The new half of the Quality score. Measured through POCs only — never through the business's own front-door contact details.

## People & Channels

- **POC (point of contact)** — a named person associated with a Lead (owner, partner, named staff) whom we could contact directly. Distinct from the business itself. Reachability is scored on POCs, not on the business.
- **Directly-reachable email** — an email that reaches a *person*: either a personal address (e.g. `j.doe@gmail.com`) or a named work address (e.g. `john-doe@acme.com`). Counts toward Reachability.
- **Business email** — a role/front-door address that does not reach a specific person (e.g. `info@acme.com`, `contact@acme.com`). Kept on the Lead, but does **not** count toward Reachability.
- **POC social** — a social profile belonging to a *person* (most importantly a LinkedIn profile, but also a personal Instagram/Facebook/X profile). Counts toward Reachability.
- **Business social** — a social page belonging to the *business* (its Facebook page, company LinkedIn, etc.). Kept on the Lead, but does **not** count toward Reachability.
- **Representative POC** — the single *best-reachable* POC on a Lead (the one with the strongest set of personal channels) whose channels (LinkedIn / email / socials) are counted toward the per-channel Reachability boost. Prevents every extra POC's channels from stacking; having *more* POCs is rewarded separately via the multi-POC boost.
- **Usable POC** — a POC eligible to count toward Reachability: not flagged invalid, and at or above the confidence bar sales is shown. Reachability and the multi-POC count consider only Usable POCs.

## Score composition

- **Service-fit half** — Service-fit mapped onto a fixed 0–50 scale. The open-ended raw fit number is kept as a hidden tiebreaker.
- **Reachability half** — Reachability expressed on a fixed 0–50 scale, built from the Representative POC's channel boost (LinkedIn > directly-reachable email > personal social, stacked) plus a diminishing, capped multi-POC boost.
- **Blended grade** — Quality score = Service-fit half + Reachability half, on 0–100. Tier is the A/B/C/D bucket of that blended number. The grade refreshes whenever a Lead's pain or Usable POCs change.
