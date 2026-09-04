import { RunDetailResponse } from '../models/run-state';

/**
 * Frozen demo fixture — a REAL `RunDetailResponse`, dumped verbatim from a
 * deterministic replay run of the pipeline on `main`:
 *
 *     LLM_MODE=replay DEMO_MODE=true uvicorn app.main:app --port 8000
 *     POST /v1/analysis/runs {"journey":"pd_checkout"}
 *     GET  /v1/analysis/runs/1        <- this file
 *
 * It is NOT hand-transcribed. That was the previous version's bug (PR #5,
 * B1): it was built from the Build Plan's hand-run, so every number on the
 * screen disagreed with the numbers in the generated report and PRD —
 * created 643,626 here vs 647,191 from the backend, a window starting a day
 * early, and findings that the real Analyst never produces.
 *
 * Because this is the API's own response shape, fixture mode and live mode
 * now run through exactly the same adapter (`toRunState` in run.service.ts).
 * A contract change breaks both together instead of letting the fixture
 * drift quietly, and regenerating is a re-dump rather than a re-type.
 *
 * To refresh: run the two commands above and replace the object below.
 */
export const RUN_47_RESPONSE: RunDetailResponse = {
  "run_id": 1,
  "journey": "pd_checkout",
  "window_start": "2026-08-04",
  "window_end": "2026-09-03",
  "status": "completed",
  "failed_stage": null,
  "config": {
    "dimensions": []
  },
  "snapshots": [
    {
      "stage": "created",
      "dimension": "all",
      "segment": "all",
      "entered": 647191,
      "converted": 229622,
      "suppressed": false,
      "window": "current"
    },
    {
      "stage": "confirmed",
      "dimension": "all",
      "segment": "all",
      "entered": 229622,
      "converted": 158976,
      "suppressed": false,
      "window": "current"
    },
    {
      "stage": "delivered",
      "dimension": "all",
      "segment": "all",
      "entered": 158976,
      "converted": 158976,
      "suppressed": false,
      "window": "current"
    },
    {
      "stage": "created",
      "dimension": "all",
      "segment": "all",
      "entered": 614252,
      "converted": 213273,
      "suppressed": false,
      "window": "previous"
    },
    {
      "stage": "confirmed",
      "dimension": "all",
      "segment": "all",
      "entered": 213273,
      "converted": 201617,
      "suppressed": false,
      "window": "previous"
    },
    {
      "stage": "delivered",
      "dimension": "all",
      "segment": "all",
      "entered": 201617,
      "converted": 201617,
      "suppressed": false,
      "window": "previous"
    }
  ],
  "findings": [
    {
      "rank": 1,
      "origin": "warehouse",
      "stage": "pharmacy_checkout",
      "hypothesis": "A sizable portion of the created -> confirmed gap is not captured by existing reason clusters (about ~176,045 orders remain unallocated), so measurement/labeling gaps (unrecorded abandon reasons or missing instrumentation) are a major contributor to our inability to explain the gap. If this is true, improving capture of abandonment reason data will re-allocate much of the 417,569 loss into labeled buckets.",
      "segments": [],
      "evidence": [
        {
          "type": "drilldown",
          "metric": "The top gap (created -> confirmed) is large: lost 417,569 (share_of_prev 0.6452)",
          "value": 0.6452
        },
        {
          "type": "drilldown",
          "metric": "user_total: 199,417",
          "value": 199417.0
        },
        {
          "type": "drilldown",
          "metric": "artifact_total: 42,107",
          "value": 42107.0
        },
        {
          "type": "drilldown",
          "metric": "leaving ~176,045 losses unallocated",
          "value": 176045.0
        }
      ],
      "confidence": "medium",
      "confirm_via": "For a randomized sample of users, enable mandatory lightweight exit reason capture (or server-side event logging that records final page/action + context) and measure how many of the ~176,045 previously-unallocated losses are reclassified into explicit reasons versus remaining unknown. Compare conversion and reason distribution between the instrumented and control groups."
    },
    {
      "rank": 2,
      "origin": "warehouse",
      "stage": "pharmacy_checkout",
      "hypothesis": "Among the labeled reasons, most of the user-side loss is concentrated in 'user abandon the cart' (111,993) and 'user clicked back' (83,517), suggesting UX, perceived price/value, or interruption flows are correlated with abandonment. If true, targeted UX interventions or pricing messaging should reduce these labeled abandon counts.",
      "segments": [],
      "evidence": [
        {
          "type": "drilldown",
          "metric": "user_total: 199,417",
          "value": 199417.0
        },
        {
          "type": "drilldown",
          "metric": "user abandon the cart: 111,993",
          "value": 111993.0
        },
        {
          "type": "drilldown",
          "metric": "user clicked back: 83,517",
          "value": 83517.0
        },
        {
          "type": "drilldown",
          "metric": "address changed: 35,111",
          "value": 35111.0
        },
        {
          "type": "drilldown",
          "metric": "add items: 6,996",
          "value": 6996.0
        },
        {
          "type": "drilldown",
          "metric": "items unavailable: 3,907",
          "value": 3907.0
        },
        {
          "type": "drilldown",
          "metric": "artifact_total: 42,107",
          "value": 42107.0
        }
      ],
      "confidence": "medium",
      "confirm_via": "Run an A/B test where users in the treatment get targeted interventions when they show abandonment signals: e.g., context-sensitive cart messaging, persistent price/benefit callouts, or an exit intent prompt for those who 'click back'. Randomize at user-session level and measure reductions in 'user abandon the cart' and overall conversion uplift vs control."
    },
    {
      "rank": 3,
      "origin": "warehouse",
      "stage": "pharmacy_checkout",
      "hypothesis": "Loss from created -> confirmed is concentrated in higher price bands (75k_200k and gte_200k total 157,071 entered) and the rx_gated (consultation-required) segment converts materially worse (rate 0.3002) than non_rx (rate 0.3904), so price sensitivity and consultation friction are correlated with the top gap.",
      "segments": [],
      "evidence": [
        {
          "type": "drilldown",
          "metric": "price_band: 75k_200k: 90,851",
          "value": 90851.0
        },
        {
          "type": "drilldown",
          "metric": "price_band: gte_200k: 66,220",
          "value": 66220.0
        },
        {
          "type": "drilldown",
          "metric": "price_band: 25k_75k: 62,875",
          "value": 62875.0
        },
        {
          "type": "drilldown",
          "metric": "price_band: lt_25k: 24,769",
          "value": 24769.0
        },
        {
          "type": "drilldown",
          "metric": "consultation_required: rx_gated entered: 255,293 converted: 76,641 rate: 0.3002",
          "value": 0.3002
        },
        {
          "type": "drilldown",
          "metric": "consultation_required: non_rx entered: 391,898 converted: 152,981 rate: 0.3904",
          "value": 0.3904
        },
        {
          "type": "drilldown",
          "metric": "funnel: confirmed count: 229,622 conversion_from_previous: 0.3548",
          "value": 0.3548
        }
      ],
      "confidence": "medium",
      "confirm_via": "Run two randomized experiments: (A) For a sample of high price-band users (e.g., 75k_200k and gte_200k), offer a targeted incentive (discount or financing messaging) and measure incremental confirmed conversion vs control; (B) For rx_gated orders, randomize a streamlined/expedited consultation flow (faster approvals, clearer status messaging) and measure whether rx_gated conversion approaches non_rx levels. Improvements in confirmed conversion in these treatments would support causality."
    },
    {
      "rank": 4,
      "origin": "voc",
      "stage": "payments",
      "hypothesis": "41 of 92 negative Play Store reviews in the window share the theme 'payment/refund' — users repeatedly report this problem",
      "segments": [],
      "evidence": [],
      "confidence": "high",
      "confirm_via": "Correlate the reviews' dates/app versions with the matching funnel segment; then A/B the proposed fix and watch the theme count fall",
      "theme": "payment/refund",
      "theme_search_terms": ["payment", "refund"],
      "review_count": 41,
      "top_quotes": [
        "konsultasi mulai dari 24:26 dokter masih bertanya dan saya sedang mengetik jawaban. tapi di menit 23:54 sesi berakhir dan masalah belum selesai. sangat tidak membantu sia-sia membayar hanya untuk bikin tambah emosi. sangat marah sekali. permasalahan masih gantuk, padahal harga tidak sedikit dan wakt",
        "jelek bngt pelayanannya, saya sudah bayar. Pas mulai konsul dokternya suruh kirim foto, sampai waktu habis ga ada jawaban sama sekali, sia sia saya ngeluarin uang, meskipun cuma 61rb tapi itu banyak loh. 61rb tanpa dapat apapun solusi dari dokternya???"
      ]
    },
    {
      "rank": 5,
      "origin": "voc",
      "stage": "consultation",
      "hypothesis": "21 of 92 negative Play Store reviews in the window share the theme 'consultation/doctor' — users repeatedly report this problem",
      "segments": [],
      "evidence": [],
      "confidence": "medium",
      "confirm_via": "Correlate the reviews' dates/app versions with the matching funnel segment; then A/B the proposed fix and watch the theme count fall",
      "theme": "consultation/doctor",
      "theme_search_terms": ["consultation", "doctor"],
      "review_count": 21,
      "top_quotes": [
        "saya konsultasi dgn dokternya, tpi responnya sangat lambat hanya menjawab 2 pertanyaan itu pun dengan singkat. Sy merasa kecewa karna mash ada beberapa pertanyaan yang belum dijawab sesi sudah berakhir.",
        "Konsultasinya rata rata enak. cuman pas mau beli obat yang ada di resep, terakhir dokter bilang kalau resepnya hanya berlaku online. Artinya harus beli via halodoc, lebih mahal dari apotek langganan, ditambah lagi ongkos kirimnya 12rb via ojol kirim ke rumah. Padahal saya lagi di luar ada keperluan."
      ]
    }
  ],
  "code_gaps": [
    {
      "finding_rank": 1,
      "origin": "warehouse",
      "stage": "pharmacy_checkout",
      "service": "oms",
      "repo": "timor/oms",
      "mechanism_found": true,
      "gap_class": "missing_retention_hook",
      "gap_statement": "abandonOrderV2 — the method the timer-driven abandon job actually calls — reverses benefits/payment-links/delivery-fee and marks the order failed, but calls zero notification/communication methods anywhere in its body. Garuda is never called before the kill; sendCommunication exists in this same file but 82 lines away, in an unrelated method never reached by this path.",
      "file": "src/main/java/com/halodoc/timor/oms/service/factory/impl/BaseCancellationTypeAdapterService.java",
      "line": 298,
      "snippet": "    @Override\n    public Order abandonOrderV2(final String customerOrderId, final CancelRequest cancelRequest) {\n        final String lockKey = customerOrderId;\n        final boolean isLockAcquired = lockUtil.lock(lockKey);\n        try {\n            if (isLockAcquired) {\n                final Order order = getOrderService().findbyCustOrderIdFromDao(customerOrderId);\n                checkPaymentStatus(order);\n                getOrderService().setRefundToWalletAttribute(order);\n                if (!order.canCancel(cancelRequest)) {\n                    log.error(\"Order with id = {}, status = {} not in valid to abandon\", customerOrderId, order.getStatus());\n                    throw new HalodocWebException(ORDER + customerOrderId + \" cannot be abandoned\", \"3011\", CONSTRAINT_VIOLATION, 422);\n                }\n                if (!order.shouldSwallowAbandonAction()) {",
      "proposed_change_location": "src/main/java/com/halodoc/timor/oms/service/factory/impl/BaseCancellationTypeAdapterService.java: call Garuda before abandonOrderV2 marks the order failed",
      "search_terms_used": [
        "order_placed",
        "order_abandoned"
      ],
      "searches_run": 3,
      "no_match_reason": null,
      "remedies": [
        {
          "proposal": "Pre-abandon retention hook — re-engage the user before the batch kills the cart",
          "signature": "RetentionService.tryReengage in the abandon path",
          "search_terms": [
            "CartAbandonAdapterService",
            "RetentionService.tryReengage"
          ],
          "status": "absent",
          "evidence_file": null,
          "evidence_line": null,
          "evidence_snippet": null,
          "searched_terms": [
            "timor/oms:CartAbandonAdapterService",
            "timor/fulfilment:CartAbandonAdapterService",
            "timor/oms:RetentionService.tryReengage",
            "timor/fulfilment:RetentionService.tryReengage"
          ],
          "iterations": 1
        },
        {
          "proposal": "Soft-abandon grace state (SOFT_ABANDONED) before final abandonment",
          "signature": "a SOFT_ABANDONED state set before the final kill",
          "search_terms": [
            "CartState",
            "SOFT_ABANDONED",
            "markSoftAbandoned"
          ],
          "status": "absent",
          "evidence_file": null,
          "evidence_line": null,
          "evidence_snippet": null,
          "searched_terms": [
            "timor/oms:CartState",
            "timor/fulfilment:CartState",
            "timor/oms:SOFT_ABANDONED",
            "timor/fulfilment:SOFT_ABANDONED"
          ],
          "iterations": 1
        },
        {
          "proposal": "Longer / excluded abandon timeout for prescription-gated carts",
          "signature": "an rx-aware abandon timeout override",
          "search_terms": [
            "InternalAbandonOrderResource"
          ],
          "status": "partial",
          "evidence_file": "InternalAbandonOrderResource.java",
          "evidence_line": null,
          "evidence_snippet": "abandon reversal exists internally, no rx-aware timeout",
          "searched_terms": [
            "timor/oms:InternalAbandonOrderResource",
            "timor/fulfilment:InternalAbandonOrderResource"
          ],
          "iterations": 1
        }
      ]
    },
    {
      "finding_rank": 2,
      "origin": "warehouse",
      "stage": "pharmacy_checkout",
      "service": "oms",
      "repo": "timor/oms",
      "mechanism_found": true,
      "gap_class": "missing_retention_hook",
      "gap_statement": "abandonOrderV2 — the method the timer-driven abandon job actually calls — reverses benefits/payment-links/delivery-fee and marks the order failed, but calls zero notification/communication methods anywhere in its body. Garuda is never called before the kill; sendCommunication exists in this same file but 82 lines away, in an unrelated method never reached by this path.",
      "file": "src/main/java/com/halodoc/timor/oms/service/factory/impl/BaseCancellationTypeAdapterService.java",
      "line": 298,
      "snippet": "    @Override\n    public Order abandonOrderV2(final String customerOrderId, final CancelRequest cancelRequest) {\n        final String lockKey = customerOrderId;\n        final boolean isLockAcquired = lockUtil.lock(lockKey);\n        try {\n            if (isLockAcquired) {\n                final Order order = getOrderService().findbyCustOrderIdFromDao(customerOrderId);\n                checkPaymentStatus(order);\n                getOrderService().setRefundToWalletAttribute(order);\n                if (!order.canCancel(cancelRequest)) {\n                    log.error(\"Order with id = {}, status = {} not in valid to abandon\", customerOrderId, order.getStatus());\n                    throw new HalodocWebException(ORDER + customerOrderId + \" cannot be abandoned\", \"3011\", CONSTRAINT_VIOLATION, 422);\n                }\n                if (!order.shouldSwallowAbandonAction()) {",
      "proposed_change_location": "src/main/java/com/halodoc/timor/oms/service/factory/impl/BaseCancellationTypeAdapterService.java: call Garuda before abandonOrderV2 marks the order failed",
      "search_terms_used": [
        "cart_add",
        "cart_view",
        "order_abandoned"
      ],
      "searches_run": 3,
      "no_match_reason": null,
      "remedies": [
        {
          "proposal": "Pre-abandon retention hook — re-engage the user before the batch kills the cart",
          "signature": "RetentionService.tryReengage in the abandon path",
          "search_terms": [
            "CartAbandonAdapterService",
            "RetentionService.tryReengage"
          ],
          "status": "absent",
          "evidence_file": null,
          "evidence_line": null,
          "evidence_snippet": null,
          "searched_terms": [
            "timor/oms:CartAbandonAdapterService",
            "timor/fulfilment:CartAbandonAdapterService",
            "timor/oms:RetentionService.tryReengage",
            "timor/fulfilment:RetentionService.tryReengage"
          ],
          "iterations": 1
        },
        {
          "proposal": "Soft-abandon grace state (SOFT_ABANDONED) before final abandonment",
          "signature": "a SOFT_ABANDONED state set before the final kill",
          "search_terms": [
            "CartState",
            "SOFT_ABANDONED",
            "markSoftAbandoned"
          ],
          "status": "absent",
          "evidence_file": null,
          "evidence_line": null,
          "evidence_snippet": null,
          "searched_terms": [
            "timor/oms:CartState",
            "timor/fulfilment:CartState",
            "timor/oms:SOFT_ABANDONED",
            "timor/fulfilment:SOFT_ABANDONED"
          ],
          "iterations": 1
        },
        {
          "proposal": "Longer / excluded abandon timeout for prescription-gated carts",
          "signature": "an rx-aware abandon timeout override",
          "search_terms": [
            "InternalAbandonOrderResource"
          ],
          "status": "partial",
          "evidence_file": "InternalAbandonOrderResource.java",
          "evidence_line": null,
          "evidence_snippet": "abandon reversal exists internally, no rx-aware timeout",
          "searched_terms": [
            "timor/oms:InternalAbandonOrderResource",
            "timor/fulfilment:InternalAbandonOrderResource"
          ],
          "iterations": 1
        }
      ]
    },
    {
      "finding_rank": 3,
      "origin": "warehouse",
      "stage": "pharmacy_checkout",
      "service": "oms",
      "repo": "timor/oms",
      "mechanism_found": false,
      "gap_class": null,
      "gap_statement": "No mechanism located for this finding within the search budget.",
      "file": null,
      "line": null,
      "snippet": null,
      "proposed_change_location": null,
      "search_terms_used": [
        "created",
        "confirmed",
        "concentrated",
        "higher",
        "price"
      ],
      "searches_run": 2,
      "no_match_reason": "no_results",
      "remedies": []
    },
    {
      "finding_rank": 4,
      "origin": "voc",
      "stage": "payments",
      "service": "payment-service",
      "repo": "scrooge/payment-service",
      "mechanism_found": false,
      "gap_class": null,
      "gap_statement": "No mechanism located for this finding within the search budget.",
      "file": null,
      "line": null,
      "snippet": null,
      "proposed_change_location": null,
      "search_terms_used": [
        "payment_failed",
        "refund",
        "abandon",
        "payment timeout"
      ],
      "searches_run": 2,
      "no_match_reason": "no_results",
      "remedies": []
    },
    {
      "finding_rank": 5,
      "origin": "voc",
      "stage": "consultation",
      "service": "consultation",
      "repo": "bintan/consultation",
      "mechanism_found": false,
      "gap_class": null,
      "gap_statement": "No mechanism located for this finding within the search budget.",
      "file": null,
      "line": null,
      "snippet": null,
      "proposed_change_location": null,
      "search_terms_used": [
        "session end",
        "doctor response",
        "missed_by_doctor"
      ],
      "searches_run": 1,
      "no_match_reason": "no_results",
      "remedies": []
    }
  ],
  "voc": {
    "reviews_meta": {
      "total": 600,
      "negatives": 92,
      "threshold": 20
    },
    "themes": [
      {
        "theme": "payment/refund",
        "count": 41,
        "escalated": true
      },
      {
        "theme": "consultation/doctor",
        "count": 21,
        "escalated": true
      },
      {
        "theme": "unmapped",
        "count": 9,
        "escalated": false
      },
      {
        "theme": "delivery/order",
        "count": 9,
        "escalated": false
      },
      {
        "theme": "app/technical",
        "count": 8,
        "escalated": false
      },
      {
        "theme": "price",
        "count": 3,
        "escalated": false
      },
      {
        "theme": "cs/support",
        "count": 1,
        "escalated": false
      }
    ],
    "per_finding_quotes": {
      "4": [
        {
          "rating": 1,
          "date": "2026-05-09",
          "text": "konsultasi mulai dari 24:26 dokter masih bertanya dan saya sedang mengetik jawaban. tapi di menit 23:54 sesi berakhir dan masalah belum selesai. sangat tidak membantu sia-sia membayar hanya untuk bikin tambah emosi. sangat marah sekali. permasalahan masih gantuk, padahal harga tidak sedikit dan wakt",
          "theme": "payment/refund"
        },
        {
          "rating": 1,
          "date": "2026-06-09",
          "text": "jelek bngt pelayanannya, saya sudah bayar. Pas mulai konsul dokternya suruh kirim foto, sampai waktu habis ga ada jawaban sama sekali, sia sia saya ngeluarin uang, meskipun cuma 61rb tapi itu banyak loh. 61rb tanpa dapat apapun solusi dari dokternya???",
          "theme": "payment/refund"
        },
        {
          "rating": 1,
          "date": "2026-05-30",
          "text": "sudah cekout obatnya, berkali-kali bayar berkali-kali gagal sekalinya bisa malahan lama banget nyampe nya, namun pas di history pesanan tidak muncul? firstime lho pengguna baru tp mlh dibikin ribet bgt ky gni, klau org nya btuh obat asma tp ga nyampe²keburu kolaps dluan orang yg pny skt asma, cepet ",
          "theme": "payment/refund"
        }
      ],
      "5": [
        {
          "rating": 1,
          "date": "2026-07-30",
          "text": "saya konsultasi dgn dokternya, tpi responnya sangat lambat hanya menjawab 2 pertanyaan itu pun dengan singkat. Sy merasa kecewa karna mash ada beberapa pertanyaan yang belum dijawab sesi sudah berakhir.",
          "theme": "consultation/doctor"
        },
        {
          "rating": 2,
          "date": "2026-07-01",
          "text": "Konsultasinya rata rata enak. cuman pas mau beli obat yang ada di resep, terakhir dokter bilang kalau resepnya hanya berlaku online. Artinya harus beli via halodoc, lebih mahal dari apotek langganan, ditambah lagi ongkos kirimnya 12rb via ojol kirim ke rumah. Padahal saya lagi di luar ada keperluan.",
          "theme": "consultation/doctor"
        },
        {
          "rating": 1,
          "date": "2026-08-27",
          "text": "after konsul , mau co obat tiba2 aplikasi minta update tapi ga bisa diupdate, semua jaringan aman, tpi tetep ga bisa, gmn sh halodoc? tolong perbaiki sistem nya, GA JELAS.",
          "theme": "consultation/doctor"
        }
      ]
    }
  },
  "drilldown_trail": [
    {
      "question": "The top gap (created -> confirmed) is large: lost 417,569 (share_of_prev 0.6452). The provided reason clusters only account for a subset of that loss: user_total 199,417 + artifact_total 42,107 = 241,524, and artifact_share is 0.1743 — so known artifact reasons are a minority of known reasons. Request a cut by 'abandon_reason' to allocate the 417,569 losses across specific abandonment reasons (so we can see which labeled abandon reasons — e.g., price, shipping, UX, payment failures — drive the gap) before drilling by product/price or consultation. This will tell us whether further cuts (price_band, pd_category, consultation_required) are likely to pinpoint remediable segments.",
      "dimension": "abandon_reason",
      "result_rows": [
        {
          "segment": "user abandon the cart",
          "entered": 111993
        },
        {
          "segment": "user clicked back",
          "entered": 83517
        },
        {
          "segment": "address changed",
          "entered": 35111
        },
        {
          "segment": "add items",
          "entered": 6996
        },
        {
          "segment": "items unavailable",
          "entered": 3907
        }
      ],
      "note": "distribution_only"
    },
    {
      "question": "The top gap (created -> confirmed) is large: lost 417,569 (share_of_prev 0.6452). The provided reason clusters only account for part of that loss: user_total 199,417 + artifact_total 42,107 = 241,524, leaving ~176,045 losses unallocated. The abandon_reason drill shows fragments: \"user abandon the cart\" 111,993; \"user clicked back\" 83,517; \"address changed\" 35,111; \"add items\" 6,996; \"items unavailable\" 3,907, and was marked distribution_only. Cut by price_band next to see whether the remaining/total loss concentrates in higher price bands (which would point to price sensitivity) versus being spread evenly (which would point toward UX/flow issues or category effects). If price_band shows concentration, confirm via an A/B experiment offering targeted discounts or price messaging to that band.",
      "dimension": "price_band",
      "result_rows": [
        {
          "segment": "75k_200k",
          "entered": 90851
        },
        {
          "segment": "gte_200k",
          "entered": 66220
        },
        {
          "segment": "25k_75k",
          "entered": 62875
        },
        {
          "segment": "lt_25k",
          "entered": 24769
        }
      ],
      "note": "distribution_only"
    },
    {
      "question": "We still have a large unexplained chunk of the top gap: total lost from created->confirmed is 417,569 (share_of_prev 0.6452) but known reason clusters only sum to 199,417 (user_total) + 42,107 (artifact_total) = 241,524 — leaving ~176,045 unallocated. The price_band cut shows loss concentrated in higher bands (75k_200k: 90,851; gte_200k: 66,220; 25k_75k: 62,875; lt_25k: 24,769), suggesting price / category may matter. Cut by pd_category next to see whether the remaining/unallocated loss (and the bulk of the price-band losses) concentrates in specific product categories (which would point toward category-specific issues like pricing, stock, or messaging) versus being spread across categories (which would point more to UX/flow or funnel-level problems). This will tell us whether to pursue category-targeted fixes (e.g., pricing/inventory experiments) or platform-level experiments.",
      "dimension": "pd_category",
      "result_rows": [
        {
          "segment": "Contraceptions & Hormone",
          "entered": 8704
        },
        {
          "segment": "Antibiotics & Antifungal",
          "entered": 4153
        },
        {
          "segment": "Digital Clinic",
          "entered": 3889
        },
        {
          "segment": "Cough and Flu",
          "entered": 2965
        },
        {
          "segment": "Skin",
          "entered": 2900
        },
        {
          "segment": "Halofit (Halodiet)",
          "entered": 1729
        },
        {
          "segment": "Pain Killer",
          "entered": 1385
        },
        {
          "segment": "Mental Health",
          "entered": 1075
        },
        {
          "segment": "small_segment_example",
          "suppressed": true
        }
      ],
      "note": "distribution_only"
    },
    {
      "question": "We still have ~176k of the created->confirmed loss unallocated (top_gap lost 417569 vs known reasons summing to user_total 199417 + artifact_total 42107 = 241524). Price bands concentrate loss in higher bands (75k_200k: 90851; gte_200k: 66220), and a plausible untested explanation is that many high-value orders require consultation/approval which causes abandonment. consultation_required is the only allowed dimension not yet tried — cut by consultation_required to see whether the unexplained loss and the high-price-band losses concentrate on orders that required consultation (which would point to streamlining/auto-approval or UX fixes) versus being spread across both consultation-required and not-required orders (which would point more to price or platform-level issues).",
      "dimension": "consultation_required",
      "result_rows": [
        {
          "segment": "rx_gated",
          "entered": 255293,
          "converted": 76641,
          "rate": 0.3002
        },
        {
          "segment": "non_rx",
          "entered": 391898,
          "converted": 152981,
          "rate": 0.3904
        }
      ],
      "note": null
    }
  ],
  "artifacts": [
    {
      "kind": "report_md",
      "uri": "data/artifacts/1/report.md"
    },
    {
      "kind": "prd_md",
      "uri": "data/artifacts/1/prd.md"
    }
  ],
  "report_markdown": "# CareLoop Analysis Report — run 1\n\n**Window:** 2026-08-04 to 2026-09-03\n\n## Funnel\n\n| Stage | Entered | Converted | CVR | Suppressed |\n|---|---|---|---|---|\n| created | 647191 | 229622 | 35.5% | no |\n| confirmed | 229622 | 158976 | 69.2% | no |\n| delivered | 158976 | 158976 | 100.0% | no |\n\n## Ranked drop-off reasons\n\n- User abandon the cart: 79515\n- USER CLICKED BACK: 61393\n- ADDRESS CHANGED: 33898\n- User abandon the cart: 32478\n- USER CLICKED BACK: 22124\n- ADD ITEMS: 6996\n- Items unavailable: 2474\n- ITEMS UNAVAILABLE: 1433\n- Address changed: 1213\n\n## Findings\n\n**#1 [warehouse] pharmacy_checkout** — A sizable portion of the created -> confirmed gap is not captured by existing reason clusters (about ~176,045 orders remain unallocated), so measurement/labeling gaps (unrecorded abandon reasons or missing instrumentation) are a major contributor to our inability to explain the gap. If this is true, improving capture of abandonment reason data will re-allocate much of the 417,569 loss into labeled buckets. (confidence medium; The top gap (created -> confirmed) is large: lost 417,569 (share_of_prev 0.6452)=0.6452, user_total: 199,417=199417.0, artifact_total: 42,107=42107.0, leaving ~176,045 losses unallocated=176045.0)\n\n**#2 [warehouse] pharmacy_checkout** — Among the labeled reasons, most of the user-side loss is concentrated in 'user abandon the cart' (111,993) and 'user clicked back' (83,517), suggesting UX, perceived price/value, or interruption flows are correlated with abandonment. If true, targeted UX interventions or pricing messaging should reduce these labeled abandon counts. (confidence medium; user_total: 199,417=199417.0, user abandon the cart: 111,993=111993.0, user clicked back: 83,517=83517.0, address changed: 35,111=35111.0, add items: 6,996=6996.0, items unavailable: 3,907=3907.0, artifact_total: 42,107=42107.0)\n\n**#3 [warehouse] pharmacy_checkout** — Loss from created -> confirmed is concentrated in higher price bands (75k_200k and gte_200k total 157,071 entered) and the rx_gated (consultation-required) segment converts materially worse (rate 0.3002) than non_rx (rate 0.3904), so price sensitivity and consultation friction are correlated with the top gap. (confidence medium; price_band: 75k_200k: 90,851=90851.0, price_band: gte_200k: 66,220=66220.0, price_band: 25k_75k: 62,875=62875.0, price_band: lt_25k: 24,769=24769.0, consultation_required: rx_gated entered: 255,293 converted: 76,641 rate: 0.3002=0.3002, consultation_required: non_rx entered: 391,898 converted: 152,981 rate: 0.3904=0.3904, funnel: confirmed count: 229,622 conversion_from_previous: 0.3548=0.3548)\n\n**#4 [voc] payments** — 41 of 92 negative Play Store reviews in the window share the theme 'payment/refund' — users repeatedly report this problem (confidence high; 41 users report this in reviews (theme: payment/refund))\n\n**#5 [voc] consultation** — 21 of 92 negative Play Store reviews in the window share the theme 'consultation/doctor' — users repeatedly report this problem (confidence medium; 21 users report this in reviews (theme: consultation/doctor))\n\n## Trend\n\nThe biggest mover is 'created' (all), which improved by 0.76pp (34.7% -> 35.5%). VoC theme volume this window (no prior-window comparison available yet): 'payment/refund' 41 negative reviews.\n\n## Data-quality notes\n\n- Segments below k=25 suppressed per privacy policy and marked above.\n- 5 finding(s) produced this run.\n",
  "prd_markdown": "# Fix: A sizable portion of the created -> confirmed gap is not captured by existing re\n\n> **DRAFT — needs human review.** Generated by CareLoop run `1` on `2026-08-04`–`2026-09-03`. Hypothesis confidence: `medium`. Never auto-filed as a ticket or MR.\n\n## 1. Overview\nCareLoop-generated fix proposal for the #1 ranked drop-off finding.\n\n## 2. Background\nRouting category `pharmacy_checkout` (segments: all). Trend context: The biggest mover is 'created' (all), which improved by 0.76pp (34.7% -> 35.5%). VoC theme volume this window (no prior-window comparison available yet): 'payment/refund' 41 negative reviews.\n\n## 3. Problem\nA sizable portion of the created -> confirmed gap is not captured by existing reason clusters (about ~176,045 orders remain unallocated), so measurement/labeling gaps (unrecorded abandon reasons or missing instrumentation) are a major contributor to our inability to explain the gap. If this is true, improving capture of abandonment reason data will re-allocate much of the 417,569 loss into labeled buckets. Evidence: The top gap (created -> confirmed) is large: lost 417,569 (share_of_prev 0.6452)=0.6452; user_total: 199,417=199417.0; artifact_total: 42,107=42107.0; leaving ~176,045 losses unallocated=176045.0. Confirm via: For a randomized sample of users, enable mandatory lightweight exit reason capture (or server-side event logging that records final page/action + context) and measure how many of the ~176,045 previously-unallocated losses are reclassified into explicit reasons versus remaining unknown. Compare conversion and reason distribution between the instrumented and control groups..\n\n## 4. Goals\nClose the `missing_retention_hook` gap at `timor/oms/src/main/java/com/halodoc/timor/oms/service/factory/impl/BaseCancellationTypeAdapterService.java:298` without regressing existing behaviour.\n\n## 5. Proposed Solution\n**Gap classification:** `missing_retention_hook`\n\nAdd the missing re-engagement hook at the cited line so the user is proactively reached (push/WA/email) before the flow terminates, instead of silently killing it.\n\n**Gap statement:** abandonOrderV2 — the method the timer-driven abandon job actually calls — reverses benefits/payment-links/delivery-fee and marks the order failed, but calls zero notification/communication methods anywhere in its body. Garuda is never called before the kill; sendCommunication exists in this same file but 82 lines away, in an unrelated method never reached by this path.\n\n**Location:** `timor/oms/src/main/java/com/halodoc/timor/oms/service/factory/impl/BaseCancellationTypeAdapterService.java:298`\n\n**Proposed change location:** src/main/java/com/halodoc/timor/oms/service/factory/impl/BaseCancellationTypeAdapterService.java: call Garuda before abandonOrderV2 marks the order failed\n\n**Remedy Loop verdicts (proposed fixes, verified against the code):**\n- **[FR candidate — not found in 4 searches]** Pre-abandon retention hook — re-engage the user before the batch kills the cart\n- **[FR candidate — not found in 4 searches]** Soft-abandon grace state (SOFT_ABANDONED) before final abandonment\n- **[Needs a closer look — partial match]** Longer / excluded abandon timeout for prescription-gated carts — InternalAbandonOrderResource.java\n\n## 6. Scope\nIn scope: routing category `pharmacy_checkout` in `oms`. Out of scope: unrelated stages.\n\n## 7. Success Metrics\nStage conversion for routing category `pharmacy_checkout` moves within ±2pp of the Power BI baseline post-fix; no regression in adjacent stages.\n\n## 8. Open Questions & Unconfirmed Assumptions\n- For a randomized sample of users, enable mandatory lightweight exit reason capture (or server-side event logging that records final page/action + context) and measure how many of the ~176,045 previously-unallocated losses are reclassified into explicit reasons versus remaining unknown. Compare conversion and reason distribution between the instrumented and control groups.\n"
};
