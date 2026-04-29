# Silverthread Labs — Pain Categories

Derived from `outreach/silverthread/llms.txt` and `llms-full.txt`. The pain
we hunt for in customer reviews maps to the services Silverthread sells.
Re-derive when STL's service catalog changes — pain we can't sell against
doesn't help sales.

The taxonomy is **vertical-agnostic**: dental, plumbing, restaurants,
veterinary, legal, real estate, etc. all share these pains. Vertical
specificity (metro, primary non-English language, regulated industry,
etc.) belongs in lead metadata, not the taxonomy.

## Hierarchy

### 1. `calls_unanswered`

**STL service:** Voice AI Agents — phone-based AI for inbound coverage.

- `missed_calls_during_business_hours` — staff didn't answer during open hours
- `missed_calls_after_hours_or_emergency` — no after-hours line; urgent need turned away
- `voicemail_never_returned` — left a message, never got called back

*Example phrasings:* "I called five times and nobody picked up", "no one
answered the emergency line on Sunday", "left two voicemails, no callback".

### 2. `booking_friction`

**STL service:** Voice AI Agents (inbound booking) / Agentic AI Systems
(online self-service).

- `appointment_unavailable_long_wait` — next slot is weeks/months out
- `scheduling_back_and_forth` — repeated reschedules, hard to confirm
- `no_online_self_service_booking` — must call to book; no portal

*Example phrasings:* "next available appointment was three months away",
"they kept rescheduling me", "you can't book online, you have to call".

### 3. `followup_dropped`

**STL service:** Agentic AI Systems — autonomous follow-up workflows.

- `recall_followup_missing` — overdue checkup/service not flagged
- `no_show_reminder_missing` — no reminder before appointment
- `post_visit_followup_missing` — no check-in after a visit
- `dropped_leads_or_quotes` — quoted/inquired but never heard back

*Example phrasings:* "they never reminded me about my next cleaning",
"got a quote and they never followed up", "no one called to check how
I was doing".

### 4. `billing_or_intake_errors`

**STL service:** Workflow Automation + Systems Integration.

- `insurance_verification_missing` — coverage not checked before service
- `surprise_billing` — unexpected charges; quoted X, billed Y
- `intake_paperwork_duplication` — same forms multiple times
- `payment_issues` — failed/double charges, refund delays

*Example phrasings:* "got a surprise bill weeks later", "they didn't
verify my insurance up front", "filled out the same paperwork three
times".

### 5. `service_quality_in_session`

**STL service:** indirect — signals broader operational issues. Best
routed to the Automation Audit, not a specific build.

- `long_wait_in_chair_or_seat` — waited far past appointment time
- `rushed_or_inattentive_visit` — staff didn't listen, hurried through
- `language_barrier` — couldn't communicate in customer's language

*Example phrasings:* "waited two hours past my appointment time",
"the dentist didn't even listen to me", "nobody spoke Spanish".

### 6. `frontline_communication`

**STL service:** Voice AI Agents (caller-facing) / Agentic AI Systems
(CRM-driven outreach).

- `staff_rude_front_desk` — front-of-house rudeness, dismissive tone
- `poor_communication` — unclear explanations, contradictory info
- `not_listening_to_customer` — concerns ignored, talked over

*Example phrasings:* "front desk was incredibly rude", "no one
explained what was going on", "they didn't listen to anything I said".

## Disambiguation (when subs overlap)

These pairs caused the most agent errors in the first eval run. Pick by
the rule, not by what sounds closest.

### Within `followup_dropped`

- `recall_followup_missing` — the **practice** should have proactively
  scheduled (overdue checkup, periodic recall, treatment-plan recheck)
  but didn't. The patient was passive; the office never reached out.
  Trigger: "they never reminded me", "no proactive update", "nobody
  contacted me about my next cleaning".
- `post_visit_followup_missing` — after a SPECIFIC procedure or visit,
  the practice should have checked in (post-op, post-treatment) but
  didn't. Trigger: "post-surgery, never heard back", "after the
  filling, no one called to check".
- `dropped_leads_or_quotes` — the **patient** actively asked for
  something (a quote, treatment plan, callback to a specific question)
  and never received it. Patient is the one chasing. Trigger: "I asked
  for a treatment plan, never got one", "they said they'd call back,
  they didn't", "requested pricing, no response".

### Within `billing_or_intake_errors`

- `insurance_verification_missing` — coverage wasn't checked BEFORE
  service. The bill that follows is downstream. Trigger: "didn't run
  my insurance", "wasn't told it was out-of-network", "no one verified
  coverage at scheduling", "referred me out-of-network without warning".
  **Do NOT label this just because the review mentions insurance.**
  If the patient was already quoted *with* insurance and the bill diverged
  (verification happened, billing diverged) → that's `surprise_billing`.
  If the patient says insurance is the same as a family member's
  (verification not in question) → also `surprise_billing`. The complaint
  must specifically be about pre-service verification failing.
- `surprise_billing` — unexpected charge after the fact, not
  necessarily insurance-related. Added fees, bait-and-switch, hidden
  upcharges, charges weeks later, undisclosed optional services
  charged anyway. **Often appears as one item in a longer list of
  complaints — don't skip it because the review also mentions
  upselling, treatment quality, or other issues.** Triggers:
  - "quoted X, billed Y" / "10x charge for the same treatment"
  - "got a bill weeks later" / "$X bill out of nowhere"
  - "additional fees for anything and everything"
  - "non-transparent pricing" / "rates seemed inflated"
  - "hidden upcharge" / "they charged me for [optional service]
    without telling me"
  - "got sent to collections" (when the original bill was unexpected)
- These often co-occur (missed verification → surprise bill). Emit
  both when both are clearly evidenced. If only "surprise charge" is
  mentioned with no insurance context, just emit `surprise_billing`.

### Within `frontline_communication`

- `staff_rude_front_desk` — rude or dismissive **tone** from staff
  (most often front-desk, but applies to any non-clinical staff being
  unprofessional). The complaint is about how they spoke or behaved,
  not what they said. Trigger: "receptionist was rude", "billing
  manager was nasty", "front desk attitude".
- `poor_communication` — unclear, contradictory, or missing
  **information** from any staff. Requires evidence of confused
  or absent explanation, not just generic dissatisfaction. Trigger:
  "told me X then billed me Y", "didn't explain the procedure",
  "got conflicting info from two staff members".
- `not_listening_to_customer` — patient raised a SPECIFIC concern
  and it was dismissed or ignored. Distinct from rudeness (about
  tone) and from poor communication (about clarity). Trigger: "I
  told them X but they ignored it", "no one cared about my complaint",
  "my pain was ignored".
- **Default:** if a review just says "rude" or "unfriendly" with no
  detail about clarity or being ignored, prefer `staff_rude_front_desk`.
  Do not reach for `poor_communication` — that requires evidence of
  unclear/contradictory information specifically.

### `service_quality_in_session/rushed_or_inattentive_visit` vs treatment-quality complaints

- IN-taxonomy: short visit, skipped exam steps, didn't physically
  examine, dentist spent <N minutes. The complaint is about
  operational rushing or inattention. Trigger: "less than 2 minutes",
  "took one quick look", "didn't check my teeth properly", "expedited
  cleaning".
- OUT of taxonomy: complaints about the QUALITY of treatment received
  — filling failed, crown chipped, diagnosis later proved wrong,
  procedure went badly. Emit no category for these.

## Output schema (for the classifier)

Each emitted pain hit on a review carries:

- `main_category` — one of the six above
- `sub_category` — one of the leaves under the main; `null` if the main
  is detected but no sub fits confidently
- `confidence` — 0.0–1.0
- `quote` — verbatim span from the review supporting the classification
- `reasoning` — short why-string

A review may emit zero, one, or multiple hits (multi-label).
