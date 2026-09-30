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


# ------------------------------------------------------------------ charts
def field_chart(field):
    """One field: five abilities as dots on a true 20-100 axis with a +-8 band."""
    W, H, L, R, T, B = 320, 152, 10, 96, 8, 24
    pw = W - L - R

    def x(v):
        return L + (v - 20) / 80.0 * pw
    out = ['<svg viewBox="0 0 %d %d" dir="ltr" role="img" aria-label="%s">' % (
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
        out.append('<text class="tt-val" x="%.1f" y="%d">%s</text>' % (x(v) + 10, y + 4, fmt(v)))
        out.append('<text class="tt-name" x="%d" y="%d" text-anchor="end">%s</text>' % (W - 2, y + 4, escape(SHORT[code])))
    out.append('</svg>')
    return Markup(''.join(out))


# ------------------------------------------------------------------ sentences
def _near(names, gap):
    return ('نزدیک به آن (تا %s نمره اختلاف): %s' % (fa(int(gap)), joinfa(names))) if names else ''


def levels(interp, profile):
    """[{key, title, lines:[str], near:[str]}] for the seven levels (book names)."""
    n = interp['n_fields']
    gap = interp.get('gap', 10)
    fields = {f['label']: f for f in profile['fields']}
    out = [{'key': 'overall', 'title': 'کلّی', 'lines': [
        'میانگین کلّی شما در %s زمینه %s از ۱۰۰ است (بازهٔ ممکن ۲۰ تا ۱۰۰).' % (fa(n), fmt(interp['overall']['score']))],
        'near': []}]
    if n < 2:
        return out
    b = interp['brief']
    out.append({'key': 'brief', 'title': 'اجمالی', 'lines': [
        'برجسته‌ترین توانایی %s (%s) و برجسته‌ترین زمینه %s (%s) است؛ میانگین این دو %s می‌شود.' % (
            ab_names(b['abilities']), fmt(b['ability_score']), joinfa(b['fields'], True), fmt(b['field_score']), fmt(b['score']))],
        'near': [x for x in (
            _near([NAMES[c] for c in b['abilities_near']], gap) and 'توانایی‌های نزدیک: ' + joinfa([NAMES[c] for c in b['abilities_near']]),
            b['fields_near'] and 'زمینه‌های نزدیک: ' + joinfa(b['fields_near'], True)) if x]})
    c = interp['composite']
    out.append({'key': 'composite', 'title': 'ترکیبی', 'lines': [
        'برای هوش (میانگین سه هوش) برجسته‌ترین زمینه %s (%s) و برای کنش (میانگین دو کنش) %s (%s) است.' % (
            joinfa(c['intel']['fields'], True), fmt(c['intel']['score']), joinfa(c['action']['fields'], True), fmt(c['action']['score']))],
        'near': [x for x in (c['intel']['near'] and 'برای هوش نزدیک: ' + joinfa(c['intel']['near'], True),
                             c['action']['near'] and 'برای کنش نزدیک: ' + joinfa(c['action']['near'], True)) if x]})
    f = interp['focal']
    fi, fa_ = f['intel'], f['action']
    place = ('در زمینهٔ «%s»' % fi['field']) if fi['field'] == fa_['field'] else ('در زمینهٔ تعاملی «%s» با «%s»' % (fi['field'], fa_['field']))
    out.append({'key': 'focal', 'title': 'کانونی', 'lines': [
        'بالاترین نمرهٔ هوش، %s در «%s» (%s) و بالاترین نمرهٔ کنش، %s در «%s» (%s) است؛ ترکیب کانونی: «%s %s %s».' % (
            NAMES[fi['ability']], fi['field'], fmt(fi['score']), NAMES[fa_['ability']], fa_['field'], fmt(fa_['score']),
            SHORT[fa_['ability']], SHORT[fi['ability']], place)], 'near': []})
    d = interp['detail']
    if d['combined']:
        who = 'ترکیبی (چند حالت هم‌تعداد): %s' % joinfa([SHORT[c] for c in d['action_mode']] + [SHORT[c] for c in d['intel_mode']])
    else:
        who = '«%s %s»' % (SHORT[d['action_mode'][0]], SHORT[d['intel_mode'][0]])
    out.append({'key': 'detail', 'title': 'تفصیلی', 'lines': [
        'ترکیب غالب در زمینه‌های شما %s است. زمینه‌هایی که بالاترین نمرهٔ هر یک از پنج توانایی را دارند: %s.' % (who, joinfa(d['fields'], True))],
        'near': []})
    t = interp['types']
    tl = []
    for code, label in (('CRE', 'خلّاقیّت'), ('SCH', 'استعداد تحصیلی'), ('CRT', 'خلّاقیّت نظری'), ('CRP', 'خلّاقیّت عملی')):
        tl.append('%s: %s (%s)' % (label, joinfa(t[code]['fields'], True), fmt(t[code]['score'])))
    out.append({'key': 'types', 'title': 'نوع استعداد', 'lines': tl, 'near': [
        'نزدیک در %s: %s' % (label, joinfa(t[code]['near'], True))
        for code, label in (('CRE', 'خلّاقیّت'), ('SCH', 'استعداد تحصیلی'), ('CRT', 'خلّاقیّت نظری'), ('CRP', 'خلّاقیّت عملی')) if t[code]['near']]})
    w = interp['weak']
    out.append({'key': 'weak', 'title': 'استعداد ضعیف', 'lines': [
        'کمترین میانگین در توانایی %s (%s) و پایین‌ترین زمینه %s (%s) است؛ تعامل این دو، ضعیف‌ترین استعداد شما در این فهرست را نشان می‌دهد: «%s %s».' % (
            ab_names(w['abilities']), fmt(w['ability_score']), joinfa(w['fields'], True), fmt(w['field_score']),
            SHORT[w['abilities'][0]], w['fields'][0])],
        'near': [x for x in (w['abilities_near'] and 'توانایی‌های نزدیک: ' + ab_names(w['abilities_near']),
                             w['fields_near'] and 'زمینه‌های نزدیک: ' + joinfa(w['fields_near'], True)) if x]})
    return out


def single_field_lines(interp):
    """With one field only the ability order inside it is meaningful."""
    pf = interp['per_field'][0]
    order = [NAMES[c] for c in pf['order']]
    return ['ترتیب نمرهٔ توانایی‌های شما در «%s»: %s.' % (pf['label'], '، '.join(order)),
            'برای مقایسهٔ زمینه‌ها دست‌کم دو زمینه لازم است.']


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
        rows.append({'code': code, 'name': NAMES[code], 'sep': sep, 'vals': vals, 'mean': profile['mean'][code],
                     'top': top, 'best': best, 'is_best': [abs(v - top) < 1e-9 for v in vals]})
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


def tiles(interp, profile):
    """Headline tiles: [{k, v, s}]."""
    out = [{'k': 'میانگین کلّی', 'v': fmt(interp['overall']['score']), 's': 'از ۱۰۰'}]
    if 'brief' in interp:
        b = interp['brief']
        out.append({'k': 'برجسته‌ترین توانایی', 'v': ab_names(b['abilities']), 's': fmt(b['ability_score'])})
        out.append({'k': 'برجسته‌ترین زمینه', 'v': joinfa(b['fields']), 's': fmt(b['field_score'])})
    else:
        pf = interp['per_field'][0]
        out.append({'k': 'برجسته‌ترین توانایی', 'v': NAMES[pf['order'][0]], 's': 'در «%s»' % pf['label']})
    return out


# ------------------------------------------------------------ fields side by side
COMPARE_CODES = ['ANA', 'EXP', 'ACA', 'NOV', 'DUT', 'TOT']


def compare_rows(profile, gap=10):
    """For each ability (and the overall mean) one row across the participant's own fields.

    mark: 'best' = exact top (the engine's tie rule), 'near' = within `gap`
    points of the top, '' otherwise. Comparison is only within the person."""
    rows = []
    for code in COMPARE_CODES:
        vals = [f['scales'][code] if code in SCALES else f['composites'][code] for f in profile['fields']]
        top = max(vals)
        cells = []
        for f, v in zip(profile['fields'], vals):
            if abs(v - top) < 1e-9:
                mark = 'best'
            elif top - v <= gap:
                mark = 'near'
            else:
                mark = ''
            cells.append({'label': f['label'], 'score': v, 'pct': round((v - 20) / 80.0 * 100, 1), 'mark': mark})
        rows.append({'code': code, 'name': NAMES[code], 'total': code == 'TOT', 'cells': cells})
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
            'caution': bool(f['flags'].get('straight') or f['flags'].get('fast')),
        })
    return cards


def compare_lines(interp):
    """Two neutral sentences that only restate the engine's own comparison."""
    if interp['n_fields'] < 2:
        return []
    b, w = interp['brief'], interp['weak']
    return [
        'در این فهرست، زمینهٔ %s بالاترین میانگین را دارد (%s)؛ این فقط مقایسهٔ زمینه‌های خودِ شما با یکدیگر است.' % (
            joinfa(b['fields'], True), fmt(b['field_score'])),
        'پایین‌ترین میانگین به زمینهٔ %s (%s) می‌رسد. این ترتیب توصیهٔ انتخاب یا حذف رشته نیست؛ برای تصمیم، آن را با نمره‌ها، علاقه و مشورت بسنجید.' % (
            joinfa(w['fields'], True), fmt(w['field_score'])),
    ]
