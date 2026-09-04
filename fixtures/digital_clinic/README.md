# digital_clinic fixtures — frozen 2026-09-04

Journey #4: Haloskin and Halofit treatment plans (digital clinics). All values are k-anonymised PRODUCTION
AGGREGATES pulled read-only from `monetization.modeled_fact_clinic_transaction` via de-central at TREATMENT grain
(one row per treatment_id, stage timestamps = max per treatment), window 2026-08-27..09-02 (prev 08-20..26). No PII.
`reviews_scrubbed.json` is the shared 600-review corpus (3 negatives mention Halofit).

| file | what |
|---|---|
| snapshot.json | two-window funnel created -> confirmed (paid) -> activated, expiry reasons, 31 real `haloskin.*`/`halofit.*` CT events. The initial consultation is a CUT (`initial_consultation`), not a stage: 4,828 of 7,247 plans (67%) never have one and go straight to payment, so a consult stage would misstate the funnel |
| cohort_cuts.json | 5 rate-bearing cuts (converted = treatment paid/confirmed) + plan_type and expiry_reason distributions |

## The headline, and why it is demo-grade

A treatment plan is created for 7,247 users a week and **only 928 (12.8%) ever pay for it**. The consultation part works:
5,812 (80%) get the initial consultation confirmed and 5,553 receive a prescription. The loss is between prescription
and payment: **4,875 completed consults -> 928 paid**.

- **Haloskin converts 18.6% (759 of 4,076) vs Halofit 5.3% (169 of 3,171)**.
- **Free-consultation plans convert 14.3% vs paid-consultation plans 9.8%**; cash payers 7.0% vs free 17.7%.
- Recorded outcomes: 1,312 abandoned, 827 expired at treatment expiry, 361 "Erx expired" — the prescription lapses before
  the user buys. 2,216 "handle missing expired status record" rows are a data-pipeline artifact (`artifact_reasons`).

`activated` is a maturing stage (a paid plan activates on its start date). `interface_type` is not a cut: the consultation
join yields a single value at treatment grain.

## Verified code hints (GitLab blob search 2026-09-04)
digital-clinic/treatment (3914): abandon 50 · expire/expired/expiry 50 · erx 50 · treatment 50 · activate 50 · reminder 50 ·
notification 48 · payment 50 · schedule 50 · consultation 50 · timeout 25 · nurse 44. digital-clinic/digital-clinic-catalog (3913): erx 32 · consultation 26.
