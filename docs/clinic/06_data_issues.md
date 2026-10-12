# 06 - Data issues in the book texts (band interpretation texts)

Found while fixing UX audit 2026-10-12 (G6-P7-2, G6-P9-3, pattern G6-PT3). Source: `addons/ts_assessment/data/source/psy_source.json`
(`x_psy_factor_threshold_rule.x_client_text` / `x_therapist_text`, active scoring contracts only, 393 band texts = 131 factors x 3
bands). The stored texts are book texts and are **never edited**; everything below is handled at display time in
`split_interpretation()` (`ts_assessment/models/attempt.py`). Owner questions are at the end.

## 1. What the audit saw, and why it is not a selection bug

- «باور» (فهرست پاکزیستی, inventory_007 / factor_026), score ۲٫۷۵, band «متوسط»: the report showed a second paragraph
  «شما به شدت … به طور کامل اعتقاد دارید» that reads as a high level.
- «استقلال» (فهرست تعهد فردی, inventory_014 / factor_073), score ۳٫۰۰, band «متوسط»: the counselor guide showed two
  «تحلیل / تفسیر» pairs one after another.

Selection is correct: `action_submit()` stores the band chosen by the engine (`f.band_ids.filtered(band == r['band'])`, one
band record per band, 3 per factor, validated by `_validate_contract()`), and the report renders only that stored band's text.
The duplicates are **inside the stored text of the matched band**:

- inventory_007 / factor_026, band Medium (2.5-3.99), client and therapist text: the band body is two paragraphs,
  «شما به طور قابل توجهی … پایبند هستید …» and «شما به شدت … به طور کامل اعتقاد دارید …». The Low band does the same
  («… نداشته باشید …» then «شما به صورت نسبی …»).
- inventory_014 / factor_073, band Medium, therapist text: «تحلیل: … تفسیر: …» twice («فرد هنوز تمایل به انجام کارها
  به‌تنهایی دارد …» and «فرد هنوز به انجام کارها به‌تنهایی تمایل دارد …»).

Evidence of the cause: two therapist texts still carry the source's older five-range headings, e.g. inventory_034 /
factor_164 (High) «### تحلیل و تفسیر نمرات 80-100:» followed by «### تحلیل و تفسیر نمرات 60-80:». The source system had five
score ranges (0-20 … 80-100) and merged them into three bands: Low (1.00-2.49, about 0-37 %) took two range texts, Medium
(2.50-3.99, about 37-75 %) took two, High mostly one.

## 2. What the product shows now (display time, stored text unchanged)

`split_interpretation()`:
1. A band body of two blank-line-separated paragraphs: only the first paragraph is shown.
2. A second «تحلیل:» / «تفسیر:» heading inside one band: the second variant is not shown (from the repeated heading to the
   next other heading, e.g. «پروتکل پیشنهادی»). An empty «تحلیل:» line does not count as a variant.
3. A «… نمرات 60-80:» / «… نمرات 80-100:» block (older range scheme) is not shown.
4. The «عامل: …» line is dropped (the factor name is the section heading), «تعریف عامل» is shown as «این عامل چه چیزی را
   توصیف می‌کند», «پروتکل پیشنهادی» as «پیشنهادهای کاربردی برای جلسه» (`counseling_terms()`), markdown marks (`**`, `####`)
   are removed.
5. The participant's own report shows the band text and its «تحلیل» / «تفسیر» parts as one section «تفسیر نتیجهٔ شما»
   (`client_sections()`, participant=True); the counselor view keeps the sub-headings.

Why the first variant: in every case checked it is the one written for the band (Low: the low text, Medium: the middle
text; the second variant reads like the neighbouring band). The order is not guaranteed for every factor (for some distress
factors the second Medium variant reads lower, not higher), so the owner should confirm (question 1).

## 3. Where it happens (band texts per instrument)

Counts are band texts (out of 3 per factor) with the pattern. «دو پاراگراف» = band body of two paragraphs; «دو جفت» = a
repeated «تحلیل / تفسیر» pair; the last column is participant texts that use the counselor's third-person «تحلیل / تفسیر»
shape («فرد در این بازه …»).

| کد | سنجه | متن مراجع: دو پاراگراف | متن مراجع: دو جفت تحلیل/تفسیر | راهنمای مشاور: دو پاراگراف | راهنمای مشاور: دو جفت تحلیل/تفسیر | بلوک «نمرات ۶۰-۸۰» | متن مراجع با «تحلیل/تفسیر» سوم‌شخص |
|---|---|---|---|---|---|---|---|
| inventory_001 | فهرست آرامش روانی - 33 | 4 | — | — | 2 | — | — |
| inventory_002 | فهرست ارجمندی - 17 | 2 | 3 | — | 4 | — | 9 |
| inventory_003 | فهرست استعداد کودک - 48 | 2 | 7 | 2 | 7 | — | 21 |
| inventory_004 | فهرست استعداد کودک - 72 | — | 1 | — | 1 | — | 3 |
| inventory_005 | فهرست استواری پویش - 32 | — | 1 | — | 2 | — | 3 |
| inventory_006 | فهرست بهداشت روان نوجوان - 46 | 2 | 4 | — | 5 | — | 12 |
| inventory_007 | فهرست پاکزیستی - 20 | 2 | — | 2 | — | — | — |
| inventory_008 | فهرست پایایی - 29 | 2 | 4 | — | 5 | — | 12 |
| inventory_010 | فهرست تعادل - 38 | 2 | 4 | — | 6 | — | 12 |
| inventory_012 | فهرست تعالی فردی - 37 | 6 | — | 2 | 5 | — | — |
| inventory_013 | فهرست تعاملی شخصیت - 62 | 2 | 4 | — | 6 | — | 12 |
| inventory_014 | فهرست تعهد فردی - 12 | — | 1 | — | 3 | — | 3 |
| inventory_015 | فهرست حریم فردی - 24 | 2 | 1 | — | 2 | — | 3 |
| inventory_016 | فهرست حمایت معنوی - 28 | 2 | 2 | — | 3 | — | 6 |
| inventory_017 | فهرست خردمندی - 25 | 2 | 2 | — | 3 | — | 6 |
| inventory_018 | فهرست خود گستری - 62 | 4 | 2 | — | 5 | — | 6 |
| inventory_019 | فهرست درستی - 17 | 2 | 2 | 2 | 3 | — | 6 |
| inventory_020 | فهرست رضایت از زندگی - 24 | 2 | 2 | 2 | 2 | — | 6 |
| inventory_021 | فهرست رضایت زناشویی - 38 | 2 | 1 | — | 2 | — | 3 |
| inventory_022 | فهرست رضایت شغلی - 29 | 2 | 4 | — | 5 | — | 12 |
| inventory_023 | فهرست سر زندگی - 24 | 2 | 1 | — | 2 | — | 3 |
| inventory_025 | فهرست شخصیت کودکان - 50 | 2 | 8 | — | 10 | — | 24 |
| inventory_026 | فهرست ظرفیت تحلیلی شناختی - 24 | — | 3 | — | 3 | — | 9 |
| inventory_027 | فهرست بیتابی - 24 | 2 | — | — | 1 | — | — |
| inventory_028 | فهرست ظرفیت تجربی - 63 | 4 | 1 | — | 5 | 3 | 3 |
| inventory_029 | فهرست ظرفیتهای شناختی - 35 | 2 | 1 | — | 3 | — | 3 |
| inventory_030 | فهرست کرونا - 26 | 2 | 1 | — | 2 | — | 3 |
| inventory_031 | فهرست نیازها - 18 | — | 2 | — | 3 | — | 6 |
| inventory_032 | فهرست وظیفه مندی - 11 | — | 1 | — | 2 | — | 3 |
| inventory_033 | فهرست هدفمندی - 25 | 2 | 2 | — | 3 | — | 6 |
| inventory_034 | فهرست هوش موفق - 49 | 4 | 3 | — | 8 | 3 | 9 |
| inventory_035 | فهرست هیجان اندیشه - 69 | 4 | 11 | — | 13 | — | 30 |
| inventory_036 | فهرست یکپارچگی شناختی - 14 | — | 2 | — | 2 | — | 6 |

Totals: client texts with two paragraphs 66, client texts with two pairs 81, therapist texts with two paragraphs 10,
therapist texts with two pairs 128, older-range blocks 6, participant texts in third person 240.
Recount: parse each band text with `split_interpretation()`'s heading rule (a line under 60 characters ending with «:»,
markdown marks ignored) and count the patterns above.

## 4. Other oddities seen (shown as stored)

- inventory_008 / factor_031 «کنجکاوی» (all bands, therapist): three item sentences ending with «:» after the protocol are
  read as headings («تا چیزی را که می‌دانم تجربه نکنم، آرام نمی‌شوم» …).
- inventory_014 / factor_076 «انضباط فردی» (all bands, therapist): the protocol's items are written as headings
  («ساختن برنامه روزانه»، «ساماندهی فضا» …).
- inventory_001 / factor_002 «بالندگی متعالی» (Medium, therapist): headings «کارنامه تفسیر» and «کارنامه تحلیل».
- inventory_012 (factors 062, 064, 065, High): an extra «نتیجه‌گیری کلی» section.
- inventory_035 / factor_173 «تشنگی گرسنگی» (Medium, client): an empty «#### تحلیل:» line before the real one; (High,
  client and therapist): «تفسیر» twice (the second is not shown).

## 5. Owner questions

1. Confirm the rule «show the first variant» for the 2-variant band texts (or give the score split inside a band, e.g.
   Medium 2.50-3.24 -> first, 3.25-3.99 -> second, if the source's five ranges should be restored).
2. 240 participant texts are written in the counselor's third person («فرد در این بازه …», with «تحلیل» / «تفسیر»).
   The participant now sees them under one heading «تفسیر نتیجهٔ شما». Should third-person texts be shown to participants
   at all, or only the definition and the band (G6-P9-2)?
3. Should the source texts be cleaned in a new content version (a new `ts.instrument.version` with its own content hash),
   so the display-time rules can be retired? Old attempts keep their stored texts either way.
