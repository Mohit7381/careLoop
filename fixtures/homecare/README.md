# homecare fixtures — frozen 2026-09-04

Journey #3: Halolab homecare and lab visits. All values are k-anonymised PRODUCTION AGGREGATES pulled
read-only from `monetization.modeled_fact_homecare_transaction` (is_addon=false) via de-central, window
2026-08-27..09-02 (prev 2026-08-20..26), transaction_created_time (Jakarta), one row per transaction. No PII.
`reviews_scrubbed.json` is the same 600 PII-masked Play Store reviews as the other journeys (none mention homecare).

| file | what |
|---|---|
| snapshot.json | two-window funnel created -> confirmed -> completed, abandonment reasons, 16 real `homecare.*` CT events |
| cohort_cuts.json | 7 rate-bearing cuts (converted = confirmed) + abandon_reason distribution |

## The headline, and why it is demo-grade

created -> confirmed loses **4,804 of 5,899 (81.4%)**. Two things explain almost all of it:

- **4,267 bookings (72%) never choose a time slot** (`lead_time = no_slot_chosen`, 0 confirmed). Once a slot is chosen the
  booking converts 52-80% (under 6 h 80%, same day 64%, 1-3 days 63%).
- **3,520 of the 4,804 recorded abandons are "customer went back from payments page"** — the payment step itself.

Cross-cutting: **Jakarta converts 75% vs West Java 21%, East Java 5%, Sumatera 5%** (service coverage / slot availability
outside Jabodetabek); the app's own flow converts 12.6% while B2B projects (87%), WhatsApp orders (70%) and offline
activation (85%) — flows with a human in the loop — convert far better.

`completed` is a maturing stage: a visit booked for a future date cannot be completed inside the window
(961 of 1,095 confirmed bookings had a past appointment date; 433 of those completed).

## Verified code hints (GitLab blob search 2026-09-04)
halolab/oms (3273): abandon 50 · schedule 50 · slot 50 · reschedule 50 · payment 50 · paymentFailed 9 · notification 50 · timeout 34 ·
expire 50 · insurance 49 · whatsapp 6 · nurse 9 · appointment 3. Zero hits: abandonment, reminder, activate.
halolab/catalog (3272): schedule 50 · slot 50 · nurse 50 · insurance 31 · erx 50. halolab/halolab-bff (4504): timeout 16 · erx 21 · whatsapp 6 · nurse 6.
