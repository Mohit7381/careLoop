import { RunState } from '../models/run-state';

/**
 * Frozen demo fixture — run #47, pharmacy delivery order journey,
 * 2026-08-26 → 2026-09-02.
 *
 * Provenance:
 *  - snapshot / findings / drilldown_trail / voc numbers: the 7-day hand-run
 *    (2026-09-02), k≥25 suppression applied at fetch. Matches the "Claude
 *    Design prompt — full text" section of the CareLoop Build Plan verbatim.
 *  - code_gaps[0] (finding_rank 1, bintan/consultation): copied from
 *    impl/codeScout's fixtures/code_scout/gap1_consultation.json — a LIVE
 *    GitLab search verified 2026-09-03 against gitlab.devops.mhealth.tech,
 *    project 311. This is the "money moment" and it is real.
 *  - code_gaps[1] (finding_rank 2, timor/oms): copied from
 *    fixtures/code_scout/gap2_pharmacy_checkout.json. IMPORTANT — this is
 *    NOT the same claim as gap1. Harshit's own fixture note says
 *    BaseCancellationTypeAdapterService.cancelOrderAndNotifyUser DOES call
 *    sendCommunication/notifyUsersWhatsapp on cancel, so "no re-engagement
 *    hook exists" is unconfirmed for pharmacy — possibly false. Kept here
 *    verbatim (including the caveat) rather than silently upgraded to a
 *    clean claim. Do not present this one as settled in the demo without
 *    checking the notification template content first.
 *  - trend_report: illustrative — no previous-window figures were published
 *    for pharmacy delivery. Swap before the demo if real deltas land.
 */
export const RUN_47: RunState = {
  run_id: 47,
  window_start: '2026-08-26',
  window_end: '2026-09-02',
  status: 'completed',

  snapshot: {
    // Two independently-scaled measurements live in one funnel: unique
    // users (app events) and orders (backend). See FunnelComponent — do
    // not plot them on one shared axis, they are different units.
    stages: [
      { stage: 'Viewed medicine', dimension: 'overall', segment: 'all', entered: 167197, converted: 99003 },
      { stage: 'Added to cart', dimension: 'overall', segment: 'all', entered: 99003, converted: 77482 },
      { stage: 'Placed order', dimension: 'overall', segment: 'all', entered: 77482, converted: 77482 },
      { stage: 'Orders created', dimension: 'overall', segment: 'all', entered: 643626, converted: 228214 },
      { stage: 'Orders confirmed', dimension: 'overall', segment: 'all', entered: 228214, converted: 158120 },
      { stage: 'Delivered', dimension: 'overall', segment: 'all', entered: 158120, converted: 158120 },
    ],
    segments: ['all'],
    reasons: [
      { cancellation_reason: 'ADDRESS CHANGED', cancellation_reason_group: 'artifact', count: 35111 },
      { cancellation_reason: 'ADD ITEMS', cancellation_reason_group: 'artifact', count: 6996 },
      { cancellation_reason: 'Items unavailable', cancellation_reason_group: 'stockout', count: 18040 },
      { cancellation_reason: 'ITEMS UNAVAILABLE', cancellation_reason_group: 'stockout', count: 9120 },
    ],
    ct_events: [],
    previous_stages: [],
  },

  findings: [
    {
      rank: 1,
      origin: 'warehouse',
      stage: 'pharmacy_checkout',
      hypothesis: 'Orders die on a silent abandonment timer',
      confidence: 0.9,
      confirm_via: 'Hold the abandon timer for one cohort and measure recovered confirmations.',
      segments: [{ dimension: 'reason', value: 'system_abandoned' }],
      evidence: [
        { type: 'snapshot', metric: 'abandoned', value: 413973 },
        { type: 'snapshot', metric: 'user-abandon', value: 111993 },
        { type: 'snapshot', metric: 'clicked-back', value: 83517 },
      ],
    },
    {
      rank: 2,
      origin: 'warehouse',
      stage: 'pharmacy_checkout',
      hypothesis: 'Prescription-gated carts are the biggest revenue leak',
      confidence: 0.85,
      confirm_via: 'Compare abandon rate for rx-gated vs non-gated carts at equal price band.',
      segments: [{ dimension: 'consultation_required', value: 'true' }],
      evidence: [
        { type: 'drilldown', metric: 'rx_gated_abandons_per_week', value: 68915 },
        { type: 'snapshot', metric: 'erx_share_of_orders_pct', value: 70.6 },
        { type: 'snapshot', metric: 'erx_share_of_gmv_pct', value: 79.2 },
      ],
    },
    {
      rank: 3,
      origin: 'warehouse',
      stage: 'pharmacy_checkout',
      hypothesis: '~15% of "abandonment" is a counting artifact',
      confidence: 0.8,
      confirm_via: 'Normalise reason casing and exclude re-create pairs, then re-run the funnel.',
      segments: [{ dimension: 'cancellation_reason_group', value: 'artifact' }],
      evidence: [
        { type: 'snapshot', metric: 'address_changed_per_week', value: 35111 },
        { type: 'snapshot', metric: 'add_items_per_week', value: 6996 },
      ],
    },
    {
      rank: 4,
      origin: 'voc',
      stage: 'payments',
      hypothesis: '41 negative reviews on payments / refunds in 112 days',
      confidence: 0.6,
      confirm_via: 'Theme-derived search terms routed to Code Scout.',
      theme: 'payment/refund',
      theme_search_terms: ['payment failed', 'refund not received', 'bayar berkali-kali'],
      review_count: 41,
      top_quotes: [
        'sudah cekout obatnya, berkali-kali bayar berkali-kali gagal… pas di history pesanan tidak muncul',
        'Udah bayar 90.000 tapi gak bisa konsultasi. Gak bisa ngirim chat malah error semua.',
      ],
    },
  ],

  drilldown_trail: [
    {
      question: 'category ‘Cough & Flu’ 1.4× base — not significant',
      dimension: 'pd_category',
      note: 'category ‘Cough & Flu’ 1.4× base — not significant',
    },
    {
      question: 'no skew',
      dimension: 'price_band',
      note: 'no skew',
    },
    {
      question: 'prescription-gated carts abandon at 1.6× base — 28.5% of all abandons',
      dimension: 'consultation_required',
      note: 'prescription-gated carts abandon at 1.6× base — 28.5% of all abandons',
    },
    {
      question: 'Pattern',
      dimension: 'conclusion',
      note: 'Stockout in cart → abandonment. Correlation, not proven cause — the PRD proposes the experiment.',
    },
  ],

  // Verbatim from impl/codeScout's fixtures/code_scout/*.json — see the
  // module-level provenance note above for what's confirmed vs. not.
  code_gaps: [
    {
      finding_rank: 1,
      origin: 'warehouse',
      stage: 'consultation',
      service: 'consultation',
      repo: 'bintan/consultation',
      mechanism_found: true,
      gap_class: 'missing_retention_hook',
      gap_statement:
        'A scheduled script silently abandons consultations stuck in payment states. No re-engagement hook exists — Garuda (notifications) is never called before the kill.',
      file: 'src/main/java/com/halodoc/bintan/consultation/dao/ConsultationDao.java',
      line: 146,
      snippet:
        `private final String GET_ABANDON_CONSULTATION = "SELECT customer_consultation_id FROM consultations ` +
        `where ((type in (:type) and updated_at<now() - INTERVAL :interval MINUTE AND updated_at > now() - ` +
        `INTERVAL :max_interval HOUR and status in ('requested','payment_processing','payment_failed')) OR ` +
        `type = 'private_practice' and status = 'requested' and updated_at<now() - INTERVAL :pp_internal MINUTE ` +
        `AND updated_at > now() - INTERVAL :max_interval HOUR) and customer_consultation_id is not NULL LIMIT :limit";`,
      proposed_change_location: 'ConsultationAbandonService.abandon(), before the abandon batch',
      search_terms_used: ['GET_ABANDON_CONSULTATION'],
      searches_run: 1,
    },
    {
      finding_rank: 2,
      origin: 'warehouse',
      stage: 'pharmacy_checkout',
      service: 'oms',
      repo: 'timor/oms',
      mechanism_found: true,
      gap_class: 'missing_retention_hook',
      gap_statement:
        'UNCONFIRMED — cancelOrderAndNotifyUser() calls sendCommunication/notifyUsersWhatsapp on cancellation, ' +
        'so "no hook exists" is NOT a clean claim here (unlike finding #1). Whether the message sent is a ' +
        'generic cancellation notice or an actual cart-recovery nudge is unresolved without reading the ' +
        'notification template itself. Presented as a real, weaker candidate — confirm before using as demo evidence.',
      file: 'src/main/java/com/halodoc/timor/oms/service/factory/impl/BaseCancellationTypeAdapterService.java',
      line: 208,
      snippet:
        `public Order cancelOrderAndNotifyUser(final String customerOrderId, final CancelRequest cancelRequest) {\n` +
        `    final Order order = cancelOrder(customerOrderId, cancelRequest);\n` +
        `    getOrderService().notifyUsersWhatsapp(order, NotificationEvent.order_cancelled);\n` +
        `    getOrderService().setRefundToWalletAttribute(order);\n` +
        `    ...\n` +
        `}`,
      proposed_change_location: null,
      search_terms_used: ['abandon'],
      searches_run: 2,
    },
  ],

  trend_report: {
    deltas: [],
    adoption: [],
    voc_theme_deltas: [],
    narrative: '',
  },

  voc: {
    reviews_meta: {
      pulled: 600,
      negative: 92,
      source: 'Play Store · newest 600 · PII-scrubbed at ingest',
    },
    themes: [
      { name: 'payment/refund', negatives: 41, escalates: true },
      { name: 'consultation/doctor', negatives: 21, escalates: true },
      { name: 'delivery', negatives: 9, escalates: false },
      { name: 'app/technical', negatives: 8, escalates: false },
    ],
    per_finding_quotes: {
      '1': [
        {
          rating: 1,
          date: '30 May 2026',
          text: 'sudah cekout obatnya, berkali-kali bayar berkali-kali gagal… pas di history pesanan tidak muncul',
          theme: 'payment/refund',
        },
        {
          rating: 1,
          date: '7 Aug 2026',
          text: 'Udah bayar 90.000 tapi gak bisa konsultasi. Gak bisa ngirim chat malah error semua.',
          theme: 'payment/refund',
        },
      ],
    },
  },

  prd_draft: null, // structured PRD rendered from findings/code_gaps by PrdComponent; see prd.model.ts
  artifacts: [],
};
