/**
 * contracts.py v2's VocQuote has no `gloss` field — only
 * {rating, date, text, theme}. The design prompt's "Users say" panel needs
 * an English gloss under each Indonesian quote (the human moment). Rather
 * than inventing a fifth contract field unilaterally, this keeps the
 * lookup client-side, keyed on quote text, until the team adds
 * VocQuote.gloss to the shared contract. See README "Known contract gaps".
 */
export const VOC_GLOSS: Record<string, string> = {
  'sudah cekout obatnya, berkali-kali bayar berkali-kali gagal… pas di history pesanan tidak muncul':
    'Checked out medicine, paid multiple times, failed multiple times… order missing from history.',
  'Udah bayar 90.000 tapi gak bisa konsultasi. Gak bisa ngirim chat malah error semua.':
    "Paid 90k but couldn't consult — chat errored out.",
};

export function glossFor(text: string): string | null {
  return VOC_GLOSS[text] ?? null;
}
