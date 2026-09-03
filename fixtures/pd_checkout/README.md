# pd_checkout fixtures — frozen 2026-09-03

All values are k-anonymized production AGGREGATES (no row-level data, no PII;
reviews PII-scrubbed at capture). Sources: Redshift via the de-central proxy
(read-only) + Play Store public reviews. Windows: current 2026-08-27..09-02,
previous 2026-08-20..26, UTC, `created_time >= start AND < end`, all channels.

| file | what |
|---|---|
| snapshot.json | Fetcher-shaped two-window funnel + reasons + CT events |
| cohort_cuts.json | AggregateTool slices (consultation_required has converted counts; category/price/reason are distribution-only — see in-file `source` notes) |
| baseline.json | the full verified baseline incl. the delivered right-censoring caveat |
| reviews_scrubbed.json | 600 newest Play Store reviews, phones/emails masked |
| sphere_ids.json | project 7121 / use-case + template ids (templates @ v4, gpt-5-mini) |

Known golden asserts (tests enforce): confirmed rate 35.48%; rx confirm 30.0%
vs non-rx 39.0% (−9pp); artifact share of abandons ≈15%; VoC escalations at
threshold 20 = payment/refund (41) and consultation/doctor (21).
