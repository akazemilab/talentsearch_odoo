"""Pure helpers for the individual report (no ORM): number formatting, Persian list
joining, inline SVG dot plots and the sentences of the seven diagnosis levels."""
from markupsafe import Markup, escape

from .engine_matrix import ACTION, INTEL, NAMES, SCALES, SHORT

_FA = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')


def fa(value):
    return str(value).translate(_FA)


def fmt(v, digits=1):
    """78.333 -> ۷۸٫۳ (one decimal, Persian digits and decimal separator)."""
    s = ('%.' + str(digits) + 'f') % v
    return fa(s).replace('.', '٫')


def joinfa(items, quote=False):
    items = ['«%s»' % i if quote else i for i in items]
    if not items:
        return ''
    if len(items) == 1:
        return items[0]
    return '، '.join(items[:-1]) + ' و ' + items[-1]


def ab_names(codes):
    return joinfa([NAMES[c] for c in codes])


# Plain meaning of the five book names, shortened from the book's own definitions (talent_texts.json), for the first
# screen of the report: a 15-year-old reads «کنش نوسودمندی» once with its meaning (UX audit T7 P9-1). Book texts and
# names stay unchanged; the full definitions remain in «دربارهٔ این سنجه».
PLAIN = {
    'ANA': 'فهمیدن، تجزیه و دسته‌بندی مطلب‌ها',
    'EXP': 'آزمودن دانسته‌ها با تجربه و کنجکاوی',
    'ACA': 'یادگیری دقیق درس‌ها و مطلب‌های آموزشی',
    'NOV': 'ارائهٔ راه‌حل‌های تازه و سودمند',
    'DUT': 'انجام درست و دقیق کاری که خواسته می‌شود',
}


def ab_plain(codes):
    """«کنش نوسودمندی (ارائهٔ راه‌حل‌های تازه و سودمند)» for each code, joined."""
    return joinfa(['%s (%s)' % (NAMES[c], PLAIN[c]) if c in PLAIN else NAMES[c] for c in codes])


# ------------------------------------------------------------------ charts
def field_chart(field, digits=1):
    """One field: five abilities as dots on a true 20-100 axis with a +-8 band."""
    # direction="ltr" on the svg: the page is RTL and SVG text inherits CSS direction (not the HTML dir attribute),
    # which flips text-anchor; names were clipped at the right edge and values drawn over the dots.
    W, H, L, R, T, B = 320, 152, 10, 100, 8, 24
    pw = W - L - R

    def x(v):
        return L + (v - 20) / 80.0 * pw
    out = ['<svg viewBox="0 0 %d %d" dir="ltr" direction="ltr" style="direction:ltr" role="img" aria-label="%s">' % (
        W, H, escape('نیمرخ توانایی‌ها در زمینهٔ %s' % field['label']))]
    for t in (20, 40, 60, 80, 100):
        out.append('<line class="tt-grid" x1="%.1f" y1="%d" x2="%.1f" y2="%d"/>' % (x(t), T, x(t), H - B))
        out.append('<text class="tt-tick" x="%.1f" y="%d" text-anchor="middle">%s</text>' % (x(t), H - 8, fa(t)))
    for i, code in enumerate(SCALES):
        v = field['scales'][code]
        y = T + 14 + i * 25
        lo, hi = max(20, v - 8), min(100, v + 8)
        out.append('<rect class="tt-band" x="%.1f" y="%d" width="%.1f" height="14" rx="7"/>' % (x(lo), y - 7, x(hi) - x(lo)))
        out.append('<line class="tt-stem tt-s%d" x1="%.1f" y1="%d" x2="%.1f" y2="%d"/>' % (i + 1, x(20), y, x(v), y))
        out.append('<circle class="tt-dot tt-s%d" cx="%.1f" cy="%d" r="5.5"/>' % (i + 1, x(v), y))
        out.append('<text class="tt-val" x="%.1f" y="%d" text-anchor="start">%s</text>' % (x(v) + 9, y + 4, fmt(v, digits)))
        out.append('<text class="tt-name" x="%d" y="%d" text-anchor="end">%s</text>' % (W - 2, y + 4, escape(SHORT[code])))
    out.append('</svg>')
    return Markup(''.join(out))


# ------------------------------------------------------------------ voice and ties
# Copy register of the report (voice.md §2): 'tu' = student's own view, 'shoma' = adult's own view,
# 'org' = a panel member reads about the participant (third person). Sentences are ours; book texts stay verbatim.
VOICE = {
    'tu': {'poss': 'تو', 'fields': 'زمینه‌هایت', 'self': 'خودت', 'abilities': 'توانایی‌هایت',
           'gave': 'دادی', 'have_given': 'داده‌ای'},
    'shoma': {'poss': 'شما', 'fields': 'زمینه‌های شما', 'self': 'خودتان', 'abilities': 'توانایی‌های شما',
              'gave': 'دادید', 'have_given': 'داده‌اید'},
    'org': {'poss': 'او', 'fields': 'زمینه‌های او', 'self': 'خودش', 'abilities': 'توانایی‌های او',
            'gave': 'داده است', 'have_given': 'داده است'},
}

# One-line gloss next to each book level name, the first time a reader meets it (UX audit G2-P3-3).
LEVEL_GLOSS = {
    'overall': 'میانگین همهٔ نمره‌ها در همهٔ زمینه‌ها.',
    'brief': 'بالاترین توانایی و بالاترین زمینه.',
    'composite': 'هوش (سه توانایی فکری) و کنش (نوسودمندی و وظیفه‌مندی)، جدا از هم.',
    'focal': 'بالاترین نمرهٔ هوش و بالاترین نمرهٔ کنش، و اینکه هر کدام در کدام زمینه است.',
    'detail': 'ترکیبی که در بیشتر زمینه‌ها تکرار می‌شود.',
    'types': 'خلّاقیّت و استعداد تحصیلی در هر زمینه.',
    'weak': 'کمترین نمره‌ها؛ جایی برای رشد، نه حکم قطعی.',
}


def _v(voice):
    return VOICE.get(voice) or VOICE['shoma']


def fields_all_tied(interp):
    """True when every field has the same overall mean (then no field is 'highest' or 'lowest')."""
    b = interp.get('brief')
    return bool(b) and interp['n_fields'] > 1 and len(b['fields']) >= interp['n_fields']


def abilities_all_tied(interp):
    b = interp.get('brief')
    return bool(b) and len(b['abilities']) >= len(SCALES)


def _near(names, gap):
    return ('نزدیک به آن (تا %s نمره اختلاف): %s' % (fa(int(gap)), joinfa(names))) if names else ''


def weak_title(voice):
    if voice == 'org':
        return 'استعداد ضعیف'
    return 'جایی که به خودت نمرهٔ کمتری دادی' if voice == 'tu' else 'جایی که به خودتان نمرهٔ کمتری دادید'


def levels(interp, profile, voice='shoma', digits=1):
    """[{key, title, gloss, lines:[str], near:[str]}] for the seven levels (book names).

    Ties are explicit: an element of a tied list is never picked as 'the' highest or lowest, and the same
    fields are never named both highest and lowest (UX audit G2-P3-1, G3-P7-6, G5-P9-4)."""
    V = _v(voice)

    def f(x):
        return fmt(x, digits)
    n = interp['n_fields']
    gap = interp.get('gap', 10)
    all_f = fields_all_tied(interp)
    all_a = abilities_all_tied(interp)
    out = [{'key': 'overall', 'title': 'کلّی', 'lines': [
        'میانگین کلّی %s در %s زمینه %s از ۱۰۰ است (بازهٔ ممکن ۲۰ تا ۱۰۰).' % (V['poss'], fa(n), f(interp['overall']['score']))],
        'near': []}]
    if n < 2:
        return _glossed(out)
    b = interp['brief']
    if all_a:
        ab_txt = 'میانگین هر پنج توانایی برابر است (%s)' % f(b['ability_score'])
    elif len(b['abilities']) > 1:
        ab_txt = 'برجسته‌ترین توانایی‌ها هم‌امتیازند: %s (%s)' % (ab_names(b['abilities']), f(b['ability_score']))
    else:
        ab_txt = 'برجسته‌ترین توانایی %s (%s) است' % (ab_names(b['abilities']), f(b['ability_score']))
    if all_f:
        fl_txt = 'میانگین همهٔ زمینه‌ها برابر است (%s)' % f(b['field_score'])
    elif len(b['fields']) > 1:
        fl_txt = 'برجسته‌ترین زمینه‌ها هم‌امتیازند: %s (%s)' % (joinfa(b['fields'], True), f(b['field_score']))
    else:
        fl_txt = 'برجسته‌ترین زمینه %s (%s) است' % (joinfa(b['fields'], True), f(b['field_score']))
    brief_lines = ['%s؛ %s.' % (ab_txt, fl_txt)]
    if not (all_a or all_f):
        brief_lines.append('میانگین این دو %s می‌شود.' % f(b['score']))
    out.append({'key': 'brief', 'title': 'اجمالی', 'lines': brief_lines,
                'near': [x for x in (
                    (not all_a) and b['abilities_near'] and 'توانایی‌های نزدیک: ' + joinfa([NAMES[c] for c in b['abilities_near']]),
                    (not all_f) and b['fields_near'] and 'زمینه‌های نزدیک: ' + joinfa(b['fields_near'], True)) if x]})
    c = interp['composite']

    def comp(key, word):
        x = c[key]
        if len(x['fields']) >= n:
            return 'برای %s همهٔ زمینه‌ها برابرند (%s)' % (word, f(x['score']))
        if len(x['fields']) > 1:
            return 'برای %s زمینه‌های %s هم‌امتیاز بالاترند (%s)' % (word, joinfa(x['fields'], True), f(x['score']))
        return 'برای %s برجسته‌ترین زمینه %s است (%s)' % (word, joinfa(x['fields'], True), f(x['score']))
    out.append({'key': 'composite', 'title': 'ترکیبی', 'lines': [
        '%s؛ %s.' % (comp('intel', 'هوش (میانگین سه هوش)'), comp('action', 'کنش (میانگین دو کنش)'))],
        'near': [x for x in (len(c['intel']['fields']) < n and c['intel']['near'] and 'برای هوش نزدیک: ' + joinfa(c['intel']['near'], True),
                             len(c['action']['fields']) < n and c['action']['near'] and 'برای کنش نزدیک: ' + joinfa(c['action']['near'], True)) if x]})
    fo = interp['focal']
    fi, fa_ = fo['intel'], fo['action']
    if len(fi.get('ties') or []) > 1 or len(fa_.get('ties') or []) > 1:
        lines = []
        for word, x in (('هوش', fi), ('کنش', fa_)):
            ties = x.get('ties') or [{'ability': x['ability'], 'field': x['field']}]
            if len(ties) > 1:
                lines.append('بالاترین نمرهٔ %s (%s) در چند جا برابر است: %s.' % (
                    word, f(x['score']), joinfa(['%s در «%s»' % (NAMES[t['ability']], t['field']) for t in ties])))
            else:
                lines.append('بالاترین نمرهٔ %s، %s در «%s» (%s) است.' % (word, NAMES[x['ability']], x['field'], f(x['score'])))
        lines.append('چون چند جا هم‌امتیاز است، یک ترکیب کانونی انتخاب نمی‌شود.')
    else:
        place = ('در زمینهٔ «%s»' % fi['field']) if fi['field'] == fa_['field'] else ('در زمینهٔ تعاملی «%s» با «%s»' % (fi['field'], fa_['field']))
        lines = ['بالاترین نمرهٔ هوش، %s در «%s» (%s) و بالاترین نمرهٔ کنش، %s در «%s» (%s) است؛ ترکیب کانونی: %s %s %s.' % (
            NAMES[fi['ability']], fi['field'], f(fi['score']), NAMES[fa_['ability']], fa_['field'], f(fa_['score']),
            SHORT[fa_['ability']], SHORT[fi['ability']], place)]
    out.append({'key': 'focal', 'title': 'کانونی', 'lines': lines, 'near': []})
    d = interp['detail']
    if d['combined']:
        who = 'ترکیبی از چند حالت هم‌تعداد (%s)' % joinfa([SHORT[x] for x in d['action_mode']] + [SHORT[x] for x in d['intel_mode']])
    else:
        who = '«%s %s»' % (SHORT[d['action_mode'][0]], SHORT[d['intel_mode'][0]])
    out.append({'key': 'detail', 'title': 'تفصیلی', 'lines': [
        'ترکیب غالب در %s %s است. زمینه‌هایی که بالاترین نمرهٔ هر یک از پنج توانایی را دارند: %s.' % (V['fields'], who, joinfa(d['fields'], True))],
        'near': []})
    t = interp['types']
    tl = []
    kinds = (('CRE', 'خلّاقیّت'), ('SCH', 'استعداد تحصیلی'), ('CRT', 'خلّاقیّت نظری'), ('CRP', 'خلّاقیّت عملی'))
    for code, label in kinds:
        if len(t[code]['fields']) >= n:
            tl.append('%s: همهٔ زمینه‌ها برابر (%s)' % (label, f(t[code]['score'])))
        else:
            tl.append('%s: %s (%s)' % (label, joinfa(t[code]['fields'], True), f(t[code]['score'])))
    out.append({'key': 'types', 'title': 'نوع استعداد', 'lines': tl, 'near': [
        'نزدیک در %s: %s' % (label, joinfa(t[code]['near'], True))
        for code, label in kinds if t[code]['near'] and len(t[code]['fields']) < n]})
    w = interp['weak']
    lines = []
    if all_a:
        lines.append('میانگین هر پنج توانایی برابر است؛ توانایی پایین‌تری دیده نمی‌شود.')
    elif len(w['abilities']) > 1:
        lines.append('کمترین میانگین در چند توانایی هم‌امتیاز است: %s (%s).' % (ab_names(w['abilities']), f(w['ability_score'])))
    else:
        lines.append('کمترین میانگین در توانایی %s (%s) است.' % (ab_names(w['abilities']), f(w['ability_score'])))
    if all_f:
        lines.append('میانگین همهٔ زمینه‌ها برابر است؛ زمینهٔ پایین‌تری دیده نمی‌شود.')
    elif len(w['fields']) > 1:
        lines.append('پایین‌ترین میانگین در چند زمینهٔ هم‌امتیاز است: %s (%s).' % (joinfa(w['fields'], True), f(w['field_score'])))
    else:
        lines.append('پایین‌ترین زمینه %s (%s) است.' % (joinfa(w['fields'], True), f(w['field_score'])))
    if len(w['abilities']) == 1 and len(w['fields']) == 1 and not (all_a or all_f):
        combo = '«%s %s»' % (SHORT[w['abilities'][0]], w['fields'][0])
        if voice == 'org':
            lines.append('تعامل این دو، ضعیف‌ترین استعداد او در این فهرست را نشان می‌دهد: %s.' % combo)
        else:
            lines.append('این دو با هم جایی را نشان می‌دهند که به %s نمرهٔ کمتری %s: %s. این حکم قطعی نیست؛ جایی برای رشد است.' % (
                V['self'], V['have_given'], combo))
    elif not (all_a and all_f):
        lines.append('چون چند مورد هم‌امتیاز است، یک مورد به‌عنوان «کمترین» انتخاب نمی‌شود.')
    out.append({'key': 'weak', 'title': weak_title(voice), 'lines': lines,
                'near': [x for x in ((not all_a) and w['abilities_near'] and 'توانایی‌های نزدیک: ' + ab_names(w['abilities_near']),
                                     (not all_f) and w['fields_near'] and 'زمینه‌های نزدیک: ' + joinfa(w['fields_near'], True)) if x]})
    return _glossed(out)


def _glossed(out):
    for lv in out:
        lv['gloss'] = LEVEL_GLOSS.get(lv['key'], '')
    return out


def single_field_lines(interp, voice='shoma'):
    """With one field only the ability order inside it is meaningful."""
    V = _v(voice)
    pf = interp['per_field'][0]
    order = [NAMES[c] for c in pf['order']]
    return ['ترتیب نمرهٔ %s در «%s»: %s.' % (V['abilities'], pf['label'], '، '.join(order)),
            'برای مقایسهٔ زمینه‌ها دست‌کم دو زمینه لازم است.']


def summary(interp, profile, voice='shoma', digits=0):
    """At most three plain sentences for the top of the report (UX audit G2-P3-3), from the same interpretation."""
    V = _v(voice)

    def f(x):
        return fmt(x, digits)
    n = interp['n_fields']
    out = []
    if n < 2:
        fld = profile['fields'][0]
        sc = fld['scales']
        top = max(sc.values())
        best = [c for c in SCALES if abs(sc[c] - top) < 1e-9]
        if len(best) == len(SCALES):
            out.append('در «%s» به هر پنج توانایی نمرهٔ برابر (%s) %s.' % (fld['label'], f(top), V['gave']))
        else:
            out.append('در «%s» بیشترین نمره در %s است (%s از ۱۰۰).' % (fld['label'], ab_plain(best), f(top)))
        out.append('برای مقایسهٔ زمینه‌ها دست‌کم دو زمینه لازم است.')
    else:
        b = interp['brief']
        if abilities_all_tied(interp):
            out.append('به هر پنج توانایی به‌طور میانگین نمرهٔ برابر (%s) %s.' % (f(b['ability_score']), V['gave']))
        else:
            out.append('بیشترین نمره را به %s %s (%s از ۱۰۰).' % (ab_plain(b['abilities']), V['gave'], f(b['ability_score'])))
        if fields_all_tied(interp):
            out.append('میانگین همهٔ %s برابر است (%s)؛ این سنجه بین آن‌ها فرقی نشان نمی‌دهد.' % (V['fields'], f(b['field_score'])))
        elif len(b['fields']) > 1:
            out.append('در میان %s، %s هم‌امتیاز و بالاترند (%s).' % (V['fields'], joinfa(b['fields'], True), f(b['field_score'])))
        else:
            out.append('در میان %s، %s بالاترین میانگین را دارد (%s).' % (V['fields'], joinfa(b['fields'], True), f(b['field_score'])))
    if voice == 'tu':
        out.append('این نتیجه را با مشاورت در میان بگذار و ببین با علاقه و نمره‌های مدرسه‌ات جور درمی‌آید یا نه.')
    elif voice == 'org':
        out.append('در گفت‌وگو بپرسید این ترتیب با علاقه و نمره‌های تحصیلی او جور درمی‌آید یا نه.')
    else:
        out.append('این نتیجه را با یک مشاور در میان بگذارید و با علاقه و سابقهٔ تحصیلی‌تان کنار هم بخوانید.')
    return out


TABLE_ROWS = [('ANA', False), ('EXP', False), ('ACA', False), ('NOV', False), ('DUT', False),
              ('TOT', True), ('INT', False), ('ACT', False), ('CRE', False), ('SCH', False), ('CRT', False), ('CRP', False)]


def table_rows(profile, gap):
    """Rows of the book's interactive table: values per field, mean, and the strongest field(s)."""
    labels = [f['label'] for f in profile['fields']]
    rows = []
    for code, sep in TABLE_ROWS:
        vals = []
        for f in profile['fields']:
            vals.append(f['scales'][code] if code in SCALES else f['composites'][code])
        top = max(vals)
        best = [labels[i] for i, v in enumerate(vals) if abs(v - top) < 1e-9]
        equal = len(vals) > 1 and len(best) == len(vals)
        rows.append({'code': code, 'name': NAMES[code], 'sep': sep, 'vals': vals, 'mean': profile['mean'][code],
                     'top': top, 'best': best, 'equal': equal,
                     'is_best': [abs(v - top) < 1e-9 and not equal for v in vals]})
    return rows


def programs_list(interp):
    """[(kind label, program name)] using the book's program names, or [] with one field."""
    p = interp.get('programs')
    if not p:
        return []
    out = []
    for key, label in (('SCH', 'استعداد تحصیلی'), ('CRE', 'خلّاقیّت'), ('CRT', 'خلّاقیّت نظری'), ('CRP', 'خلّاقیّت عملی')):
        for name in p[key]:
            out.append((label, name))
    out.append(('زمینهٔ ضعیف', p['compensatory']))
    out.append(('توانایی ضعیف', p['reinforcing']))
    return out


def programs_view(interp, voice='shoma'):
    """programs_list for display: a program built on an arbitrary pick from a tie is left out (the engine picks the
    first of tied fields/abilities); participant views use growth wording for the two remedial kinds."""
    out = []
    w = interp.get('weak') or {}
    b = interp.get('brief') or {}
    drop_comp = fields_all_tied(interp) or len(w.get('fields') or []) != 1 or len(b.get('abilities') or []) != 1
    drop_reinf = abilities_all_tied(interp) or len(w.get('abilities') or []) != 1
    org = voice == 'org'
    for label, name in programs_list(interp):
        if label == 'زمینهٔ ضعیف':
            if drop_comp:
                continue
            label = label if org else 'برای رشد در یک زمینه'
        elif label == 'توانایی ضعیف':
            if drop_reinf:
                continue
            label = label if org else 'برای رشد یک توانایی'
        out.append((label, name))
    return out


def tiles(interp, profile, voice='shoma', digits=1):
    """Headline tiles: [{k, v, s}]."""
    out = [{'k': 'میانگین کلّی', 'v': fmt(interp['overall']['score'], digits), 's': 'از ۱۰۰'}]
    if 'brief' in interp:
        b = interp['brief']
        if abilities_all_tied(interp):
            out.append({'k': 'برجسته‌ترین توانایی', 'v': 'هر پنج برابر', 's': fmt(b['ability_score'], digits)})
        else:
            out.append({'k': 'برجسته‌ترین توانایی', 'v': ab_names(b['abilities']), 's': fmt(b['ability_score'], digits),
                        'g': PLAIN.get(b['abilities'][0]) if len(b['abilities']) == 1 else ''})
        if fields_all_tied(interp):
            out.append({'k': 'زمینه‌ها', 'v': 'همه برابر', 's': fmt(b['field_score'], digits)})
        else:
            out.append({'k': 'برجسته‌ترین زمینه' if len(b['fields']) == 1 else 'برجسته‌ترین زمینه‌ها (هم‌امتیاز)',
                        'v': joinfa(b['fields']), 's': fmt(b['field_score'], digits)})
    else:
        pf = interp['per_field'][0]
        fld = profile['fields'][0]['scales']
        top = max(fld.values())
        best = [NAMES[c] for c in SCALES if abs(fld[c] - top) < 1e-9]
        top_codes = [c for c in SCALES if abs(fld[c] - top) < 1e-9]
        out.append({'k': 'برجسته‌ترین توانایی', 'v': 'هر پنج برابر' if len(best) == len(SCALES) else joinfa(best),
                    's': 'در «%s»' % pf['label'], 'g': PLAIN.get(top_codes[0]) if len(top_codes) == 1 else ''})
    return out


# ------------------------------------------------------------ fields side by side
COMPARE_CODES = ['ANA', 'EXP', 'ACA', 'NOV', 'DUT', 'TOT']


def compare_rows(profile, gap=10):
    """For each ability (and the overall mean) one row across the participant's own fields.

    mark: 'best' = exact top (the engine's tie rule: every exactly tied value is best, also when all are
    equal; then `equal` is set and the template says «همه برابر» once instead of a label per cell),
    'near' = within `gap` points of the top, '' otherwise. Comparison is only within the person."""
    rows = []
    for code in COMPARE_CODES:
        vals = [f['scales'][code] if code in SCALES else f['composites'][code] for f in profile['fields']]
        top = max(vals)
        equal = len(vals) > 1 and all(abs(v - top) < 1e-9 for v in vals)
        cells = []
        for f, v in zip(profile['fields'], vals):
            if abs(v - top) < 1e-9:
                mark = 'best'
            elif top - v <= gap:
                mark = 'near'
            else:
                mark = ''
            cells.append({'label': f['label'], 'score': v, 'pct': round((v - 20) / 80.0 * 100, 1), 'mark': mark})
        rows.append({'code': code, 'name': NAMES[code], 'total': code == 'TOT', 'cells': cells, 'equal': equal})
    return rows


def field_cards(profile, gap=10):
    """One card per field: overall mean, strongest and weakest ability (ties kept)."""
    cards = []
    for i, f in enumerate(profile['fields']):
        sc = f['scales']
        hi, lo = max(sc.values()), min(sc.values())
        cards.append({
            'label': f['label'], 'idx': i + 1, 'tot': f['composites']['TOT'],
            'high': [NAMES[c] for c in SCALES if abs(sc[c] - hi) < 1e-9], 'high_score': hi,
            'low': [NAMES[c] for c in SCALES if abs(sc[c] - lo) < 1e-9], 'low_score': lo,
            'flat': abs(hi - lo) < 1e-9,
            'caution': bool(f['flags'].get('straight') or f['flags'].get('fast')),
        })
    return cards


def compare_lines(interp, voice='shoma', digits=1):
    """Neutral sentences that only restate the engine's own comparison; a full tie is said once, never as
    'highest' and 'lowest' at the same time."""
    if interp['n_fields'] < 2:
        return []
    V = _v(voice)
    read, weigh = ('بخوان', 'بسنج') if voice == 'tu' else ('بخوانید', 'بسنجید')
    b, w = interp['brief'], interp['weak']
    if fields_all_tied(interp):
        return ['میانگین هر %s زمینه برابر است (%s)؛ این فهرست بین %s فرقی نشان نمی‌دهد. برای تصمیم، آن را با نمره‌ها، علاقه و مشورت کنار هم %s.' % (
            fa(interp['n_fields']), fmt(b['field_score'], digits), V['fields'], read)]
    hi = ('زمینه‌های %s هم‌امتیاز بالاترین میانگین را دارند' if len(b['fields']) > 1 else 'زمینهٔ %s بالاترین میانگین را دارد') % joinfa(b['fields'], True)
    lo = ('پایین‌ترین میانگین به زمینه‌های هم‌امتیاز %s می‌رسد' if len(w['fields']) > 1 else 'پایین‌ترین میانگین به زمینهٔ %s می‌رسد') % joinfa(w['fields'], True)
    return [
        'در این فهرست، %s (%s)؛ این فقط مقایسهٔ زمینه‌های %s با یکدیگر است.' % (hi, fmt(b['field_score'], digits), V['self']),
        '%s (%s). این ترتیب توصیهٔ انتخاب یا حذف رشته نیست؛ برای تصمیم، آن را با نمره‌ها، علاقه و مشورت %s.' % (
            lo, fmt(w['field_score'], digits), weigh),
    ]


# ------------------------------------------------------------ book text display (no stored text changes)
_AR_FIX = str.maketrans({'ي': 'ی', 'ك': 'ک'})
_ZW = '‌'


def norm_text(text):
    """Display-time Persian orthography for book definitions: Arabic ی/ک and the common missing half-spaces
    («تواناییهای»، «دانسته ها»، «می شود»). The stored verbatim text is never changed (UX audit G3-P7-8, G5-P9-6)."""
    import re
    s = (text or '').translate(_AR_FIX)
    s = re.sub(r'(?<=[؀-ۿ]) (ها|های|هایی|هایش)(?=[\s\.،؛:»)]|$)', _ZW + r'\1', s)
    s = re.sub(r'(?<![؀-ۿ])(ن?می) (?=[؀-ۿ])', r'\1' + _ZW, s)
    s = re.sub(r'(یی|ی)(های|ها)(?=[\s\.،؛:»)]|$)', lambda m: m.group(1) + _ZW + m.group(2) if m.group(1) == 'یی' else m.group(0), s)
    s = s.replace('بندیهای', 'بندی' + _ZW + 'های').replace('پنجگانه', 'پنج' + _ZW + 'گانه')
    return s


def split_pair_definition(defs):
    """The book gives «خلّاقیّت نظری» and «خلّاقیّت عملی» one shared sentence; show one sentence per term."""
    out = []
    by = dict(defs)
    a, b = NAMES['CRT'], NAMES['CRP']
    shared = by.get(a) and by.get(a) == by.get(b)
    for name, text in defs:
        if shared and name in (a, b):
            cut = text.find(' و «%s»' % b)
            if cut > 0:
                text = (text[:cut] + '.') if name == a else text[cut + 3:]
        out.append((name, text))
    return out
