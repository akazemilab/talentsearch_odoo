"""Item generators for the timed tasks (docs/hr/01_architecture.md section 4). Pure and seeded: the same seed always
gives the same items, so a block can be re-sent after a reload and every result can be re-scored.

Every generator returns (client_items, keys): client_items go to the browser (no answers), keys stay on the server.
Items are generated per candidate (no fixed bank to leak); content is ours (matrices, series, syllogisms, orderings,
rotations, word problems) or classic open paradigms (perceptual comparison, digit span, flanker, choice reaction).
"""
import random

FA_DIGITS = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')


def fa(n):
    return str(n).translate(FA_DIGITS)


# ====================================================================== figural matrices (Inductive Reasoning)
SHAPES = ['circle', 'square', 'triangle', 'diamond']
FILLS = ['none', 'solid', 'half']
COUNTS = [1, 2, 3]
ATTRS = {'shape': SHAPES, 'fill': FILLS, 'count': COUNTS}


def _shape_svg(shape, fill, cx, cy, r, uid):
    stroke = 'stroke="currentColor" stroke-width="2"'
    if fill == 'solid':
        f = 'fill="currentColor"'
    elif fill == 'half':
        f = 'fill="url(#h%s)"' % uid
    else:
        f = 'fill="none"'
    if shape == 'circle':
        return '<circle cx="%.1f" cy="%.1f" r="%.1f" %s %s/>' % (cx, cy, r, f, stroke)
    if shape == 'square':
        return '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" %s %s/>' % (cx - r, cy - r, 2 * r, 2 * r, f, stroke)
    if shape == 'triangle':
        return '<polygon points="%.1f,%.1f %.1f,%.1f %.1f,%.1f" %s %s/>' % (
            cx, cy - r, cx + r, cy + r * 0.9, cx - r, cy + r * 0.9, f, stroke)
    return '<polygon points="%.1f,%.1f %.1f,%.1f %.1f,%.1f %.1f,%.1f" %s %s/>' % (
        cx, cy - r, cx + r, cy, cx, cy + r, cx - r, cy, f, stroke)


def cell_svg(cell, uid, size=72):
    """One matrix cell (or answer option) as a self-contained SVG; colour follows the page (currentColor)."""
    n = cell['count']
    r = size * (0.2 if n == 1 else 0.14)
    xs = {1: [0.5], 2: [0.3, 0.7], 3: [0.2, 0.5, 0.8]}[n]
    body = ''.join(_shape_svg(cell['shape'], cell['fill'], size * x, size * 0.5, r, uid) for x in xs)
    pat = ('<defs><pattern id="h%s" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
           '<line x1="0" y1="0" x2="0" y2="6" stroke="currentColor" stroke-width="2"/></pattern></defs>' % uid)
    return '<svg viewBox="0 0 %d %d" width="%d" height="%d" aria-hidden="true">%s%s</svg>' % (
        size, size, size, size, pat, body)


# Text alternatives (owner decision 2026-10-13, WCAG 1.1.1): every drawing has a Persian description built from the same
# structure the SVG is drawn from, so a screen-reader user meets the same item. Display only: they draw no random numbers
# (the items, their order and the keys stay exactly as before) and say nothing a sighted person does not see.
SHAPE_EZ = {'circle': 'دایرهٔ', 'square': 'مربع', 'triangle': 'مثلث', 'diamond': 'لوزی'}
FILL_FA = {'none': 'توخالی', 'solid': 'توپر', 'half': 'هاشوردار'}
COUNT_FA = {1: 'یک', 2: 'دو', 3: 'سه'}


def cell_text(cell):
    """«دو مربع توپر»: one matrix cell or answer option in words."""
    return '%s %s %s' % (COUNT_FA[cell['count']], SHAPE_EZ[cell['shape']], FILL_FA[cell['fill']])


def matrix_text(cells):
    """The 8 drawn cells row by row (the grid is drawn left to right), the ninth is the empty one."""
    rows = []
    for r_ in range(3):
        parts = [cell_text(c) for c in cells[r_ * 3:r_ * 3 + 3]]
        if r_ == 2:
            parts.append('خانهٔ خالی (؟)')
        rows.append('ردیف %s: %s' % (fa(r_ + 1), '، '.join(parts)))
    return 'جدول سه در سه؛ خانه‌های هر ردیف از چپ به راست. %s.' % '؛ '.join(rows)


def _matrix(rnd, n_vary):
    attrs = list(ATTRS)
    rnd.shuffle(attrs)
    vary, rest = attrs[:n_vary], attrs[n_vary:]
    rule = {}
    for a in vary:
        vals = ATTRS[a][:]
        rnd.shuffle(vals)
        vals = vals[:3]
        if a == 'count' and rnd.random() < 0.5:
            rule[a] = ('progress', sorted(vals) if rnd.random() < 0.5 else sorted(vals, reverse=True))
        else:
            rule[a] = ('latin', vals)
    for a in rest:
        vals = ATTRS[a][:]
        rnd.shuffle(vals)
        rule[a] = ('row', vals[:3]) if rnd.random() < 0.4 else ('const', vals[0])
    cells = []
    for r_ in range(3):
        for c in range(3):
            cell = {}
            for a, (kind, v) in rule.items():
                if kind == 'progress':
                    cell[a] = v[c]
                elif kind == 'latin':
                    cell[a] = v[(r_ + c) % 3]
                elif kind == 'row':
                    cell[a] = v[r_]
                else:
                    cell[a] = v
            cells.append(cell)
    answer = cells[8]
    opts = [answer]
    tries = 0
    while len(opts) < 6 and tries < 200:
        tries += 1
        d = dict(answer)
        for a in rnd.sample(attrs, 1 if rnd.random() < 0.7 else 2):
            choices = [x for x in ATTRS[a] if x != answer[a]]
            d[a] = rnd.choice(choices)
        if d not in opts:
            opts.append(d)
    rnd.shuffle(opts)
    return cells[:8], opts, opts.index(answer)


def gen_matrices(seed, n=8, practice=False):
    rnd = random.Random('mx-%s' % seed)
    items, keys = [], []
    for i in range(n):
        n_vary = 1 if practice else (1 if i < 2 else (2 if i < 5 else 3))
        cells, opts, k = _matrix(rnd, n_vary)
        uid = '%s%d' % ('p' if practice else 'm', i)
        items.append({'kind': 'matrix',
                      'cells': [cell_svg(c, '%sc%d' % (uid, j)) for j, c in enumerate(cells)],
                      'options': [cell_svg(o, '%so%d' % (uid, j)) for j, o in enumerate(opts)],
                      'cells_text': matrix_text(cells), 'options_text': [cell_text(o) for o in opts]})
        keys.append(k)
    return items, keys


# ====================================================================== number series (Inductive / Information Ordering)
def _series(rnd, level):
    kinds = {0: ['arith', 'geom'], 1: ['arith', 'alt', 'second'], 2: ['second', 'alt', 'fib', 'mixed']}[level]
    kind = rnd.choice(kinds)
    if kind == 'arith':
        a, d = rnd.randint(2, 30), rnd.choice([-7, -5, -4, -3, 3, 4, 5, 6, 7, 9, 11])
        if d < 0:
            a += 60
        s = [a + d * i for i in range(6)]
    elif kind == 'geom':
        a, q = rnd.randint(1, 5), rnd.choice([2, 3])
        s = [a * q ** i for i in range(6)]
    elif kind == 'alt':
        a, b, d1, d2 = rnd.randint(1, 20), rnd.randint(30, 60), rnd.choice([2, 3, 4]), rnd.choice([-2, -3, 5])
        s = [(a + d1 * (i // 2)) if i % 2 == 0 else (b + d2 * (i // 2)) for i in range(6)]
    elif kind == 'second':
        a, d, k = rnd.randint(1, 15), rnd.randint(1, 4), rnd.choice([1, 2, 3])
        s, cur = [], a
        for i in range(6):
            s.append(cur)
            cur += d + k * i
    elif kind == 'fib':
        a, b = rnd.randint(1, 5), rnd.randint(2, 7)
        s = [a, b]
        while len(s) < 6:
            s.append(s[-1] + s[-2])
    else:  # mixed: x2 then +k alternately
        a, k = rnd.randint(1, 4), rnd.choice([1, 2, 3])
        s = [a]
        for i in range(5):
            s.append(s[-1] * 2 if i % 2 == 0 else s[-1] + k)
    ans = s[5]
    deltas = [d for d in (-3, -2, -1, 1, 2, 3, 4, -4, 5, 6) if ans + d >= 0]
    rnd.shuffle(deltas)
    opts = [ans] + [ans + d for d in deltas[:4]]
    rnd.shuffle(opts)
    return s[:5], opts, opts.index(ans)


def gen_series(seed, n=8, practice=False):
    rnd = random.Random('sr-%s' % seed)
    items, keys = [], []
    for i in range(n):
        level = 0 if practice or i < 2 else (1 if i < 5 else 2)
        terms, opts, k = _series(rnd, level)
        items.append({'kind': 'series', 'terms': [fa(t) for t in terms], 'options': [fa(o) for o in opts]})
        keys.append(k)
    return items, keys


# ====================================================================== deductive reasoning (syllogisms, orderings)
PSEUDO = ['سارپ', 'تلوم', 'کرینا', 'موتال', 'پیرد', 'داسک', 'لونیف', 'رباک', 'فرمون', 'زیلات', 'نوبار', 'کاتیس']
NAMES = ['آرش', 'بهار', 'کاوه', 'نگار', 'سینا', 'مینا', 'پویا', 'ترانه', 'رضا', 'شیوا']
COMPARATIVES = [('بلندقدتر', 'بلندقدترین', 'کوتاه‌قدترین'), ('مسن‌تر', 'مسن‌ترین', 'جوان‌ترین'),
                ('سریع‌تر', 'سریع‌ترین', 'کندترین'), ('سنگین‌تر', 'سنگین‌ترین', 'سبک‌ترین')]
CANNOT = 'نمی‌توان نتیجهٔ قطعی گرفت'


def _syllogism(rnd):
    a, b, c = rnd.sample(PSEUDO, 3)
    form = rnd.choice(['barbara', 'celarent', 'darii', 'ferio', 'inv1', 'inv2'])
    P = {
        'all': lambda x, y: 'همهٔ %s‌ها %s هستند.' % (x, y),
        'no': lambda x, y: 'هیچ %sی %s نیست.' % (x, y),
        'some': lambda x, y: 'بعضی از %s‌ها %s هستند.' % (x, y),
        'somenot': lambda x, y: 'بعضی از %s‌ها %s نیستند.' % (x, y),
    }
    if form == 'barbara':
        prem, ans, wrong = [P['all'](a, b), P['all'](b, c)], P['all'](a, c), [P['all'](c, a), P['no'](a, c)]
    elif form == 'celarent':
        prem, ans, wrong = [P['all'](a, b), P['no'](b, c)], P['no'](a, c), [P['some'](a, c), P['all'](c, a)]
    elif form == 'darii':
        prem, ans, wrong = [P['all'](b, c), P['some'](a, b)], P['some'](a, c), [P['all'](a, c), P['no'](a, c)]
    elif form == 'ferio':
        prem, ans, wrong = [P['no'](b, c), P['some'](a, b)], P['somenot'](a, c), [P['no'](a, c), P['all'](a, c)]
    elif form == 'inv1':
        prem, ans, wrong = [P['all'](a, b), P['all'](c, b)], CANNOT, [P['all'](a, c), P['some'](a, c)]
    else:
        prem, ans, wrong = [P['some'](a, b), P['some'](b, c)], CANNOT, [P['some'](a, c), P['all'](a, c)]
    opts = [ans] + wrong + ([CANNOT] if ans != CANNOT else [P['no'](c, a)])
    rnd.shuffle(opts)
    return {'kind': 'logic', 'stem': ' '.join(prem), 'question': 'کدام نتیجه حتماً درست است؟', 'options': opts}, \
        opts.index(ans)


def _ordering(rnd, n_people):
    people = rnd.sample(NAMES, n_people)
    comp, most, least = rnd.choice(COMPARATIVES)
    order = people[:]               # order[0] is the most
    pairs = [(order[i], order[i + 1]) for i in range(n_people - 1)]
    rnd.shuffle(pairs)
    stem = ' '.join('%s از %s %s است.' % (x, y, comp) for x, y in pairs)
    ask_most = rnd.random() < 0.5
    ans = order[0] if ask_most else order[-1]
    opts = people[:]
    rnd.shuffle(opts)
    return {'kind': 'logic', 'stem': stem, 'question': 'چه کسی %s است؟' % (most if ask_most else least),
            'options': opts}, opts.index(ans)


def gen_logic(seed, n=8, practice=False):
    rnd = random.Random('lg-%s' % seed)
    items, keys = [], []
    for i in range(n):
        it, k = (_ordering(rnd, 3) if practice else
                 (_ordering(rnd, 3 if i < 2 else 4) if i % 2 == 0 else _syllogism(rnd)))
        items.append(it)
        keys.append(k)
    return items, keys


# ====================================================================== mental rotation (Visualization)
POLYS = [
    [(0, 0), (1, 0), (2, 0), (2, 1), (0, 1)], [(0, 0), (1, 0), (1, 1), (1, 2), (2, 2)],
    [(0, 0), (0, 1), (1, 1), (2, 1), (2, 2), (3, 2)], [(0, 0), (1, 0), (2, 0), (3, 0), (1, 1)],
    [(0, 1), (1, 1), (1, 0), (2, 0), (2, 1), (2, 2)], [(0, 0), (1, 0), (1, 1), (2, 1), (2, 2)],
    [(0, 0), (0, 1), (0, 2), (1, 2), (2, 2), (2, 1)], [(1, 0), (0, 1), (1, 1), (2, 1), (1, 2), (2, 2)],
]


def _norm(cells):
    mx, my = min(x for x, _ in cells), min(y for _, y in cells)
    return sorted((x - mx, y - my) for x, y in cells)


def _rot(cells, k):
    for _ in range(k % 4):
        cells = [(y, -x) for x, y in cells]
    return _norm(cells)


def _mirror(cells):
    return _norm([(-x, y) for x, y in cells])


def poly_svg(cells, size=120):
    w = max(x for x, _ in cells) + 1
    h = max(y for _, y in cells) + 1
    u = size / max(w, h, 4)
    ox, oy = (size - w * u) / 2, (size - h * u) / 2
    rects = ''.join('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="currentColor" fill-opacity=".85" '
                    'stroke="#ffffff" stroke-width="2"/>' % (ox + x * u, oy + y * u, u, u)
                    for x, y in cells)
    return '<svg viewBox="0 0 %d %d" width="%d" height="%d" aria-hidden="true">%s</svg>' % (size, size, size, size, rects)


def poly_text(cells):
    """A rotation figure in words: its squares on their grid, row by row from the top, each row left to right (the
    drawing's own coordinates, so a mirror image reads mirrored)."""
    w = max(x for x, _ in cells) + 1
    h = max(y for _, y in cells) + 1
    on = set(cells)
    rows = ['ردیف %s: %s' % (fa(y + 1), '، '.join('پر' if (x, y) in on else 'خالی' for x in range(w))) for y in range(h)]
    return 'شکلی از %s مربع در شبکه‌ای با %s ستون و %s ردیف؛ از بالا، خانه‌های هر ردیف از چپ به راست. %s.' % (
        fa(len(cells)), fa(w), fa(h), '؛ '.join(rows))


# only chiral shapes: an achiral one equals its own mirror image after some rotation, so "mirror" would be unanswerable
CHIRAL = [p for p in POLYS if _mirror(_norm(p)) not in [_rot(_norm(p), k) for k in range(4)]]


def gen_rotation(seed, n=16, practice=False):
    rnd = random.Random('rt-%s' % seed)
    items, keys = [], []
    for i in range(n):
        base = _norm(rnd.choice(CHIRAL))
        left = _rot(base, rnd.randint(0, 3))
        mirrored = (i % 2 == 1) if not practice else (i == 1)
        right = _rot(_mirror(base) if mirrored else base, rnd.randint(1, 3))
        items.append({'kind': 'rotation', 'left': poly_svg(left), 'right': poly_svg(right),
                      'left_text': poly_text(left), 'right_text': poly_text(right),
                      'options': ['همان شکل است (فقط چرخیده)', 'قرینهٔ آینه‌ای است']})
        keys.append(1 if mirrored else 0)
    order = list(range(n))
    rnd.shuffle(order)
    return [items[j] for j in order], [keys[j] for j in order]


# ====================================================================== numerical reasoning (Mathematical Reasoning)
def _numeric(rnd):
    t = rnd.choice(['discount', 'rate', 'ratio', 'average', 'work', 'percent_change'])
    if t == 'discount':
        price, pct = rnd.choice([120, 160, 240, 300, 360, 480, 600]), rnd.choice([10, 15, 20, 25, 30])
        ans = price * (100 - pct) // 100
        stem = 'قیمت کالایی %s هزار تومان است و %s درصد تخفیف دارد. قیمت پس از تخفیف چند هزار تومان است؟' % (fa(price), fa(pct))
    elif t == 'rate':
        speed, hours = rnd.choice([40, 50, 60, 70, 80, 90]), rnd.choice([2, 3, 4, 5])
        extra = rnd.choice([0, 30])
        ans = speed * hours + (speed // 2 if extra else 0)
        stem = 'خودرویی با سرعت ثابت %s کیلومتر در ساعت، %s ساعت%s حرکت می‌کند. چند کیلومتر می‌رود؟' % (
            fa(speed), fa(hours), ' و %s دقیقه' % fa(30) if extra else '')
    elif t == 'ratio':
        a, b = rnd.choice([(2, 3), (3, 5), (1, 4), (4, 5), (3, 4)])
        k = rnd.choice([4, 6, 8, 10, 12])
        total = (a + b) * k
        ans = b * k
        stem = 'مبلغ %s میلیون تومان به نسبت %s به %s میان دو نفر تقسیم می‌شود. سهم نفر دوم چند میلیون تومان است؟' % (
            fa(total), fa(a), fa(b))
    elif t == 'average':
        while True:
            vals = [rnd.randint(10, 20) for _ in range(3)]
            target = rnd.randint(14, 18)
            ans = target * 4 - sum(vals)
            if 8 <= ans <= 20:
                break
        stem = 'نمره‌های سه آزمون %s است. نمرهٔ آزمون چهارم چند باشد تا میانگین چهار آزمون %s شود؟' % (
            '، '.join(fa(v) for v in vals), fa(target))
    elif t == 'work':
        a, b = rnd.choice([(6, 3), (12, 6), (10, 15), (12, 4), (20, 30)])
        ans = a * b // (a + b)
        if a * b % (a + b):
            a, b, ans = 6, 3, 2
        stem = 'کاری را نفر اول به‌تنهایی در %s ساعت و نفر دوم در %s ساعت انجام می‌دهد. با هم در چند ساعت تمام می‌کنند؟' % (
            fa(a), fa(b))
    else:
        base, pct = rnd.choice([200, 400, 500, 800]), rnd.choice([10, 20, 25, 50])
        up = rnd.random() < 0.5
        ans = base * (100 + pct) // 100 if up else base * (100 - pct) // 100
        stem = 'تولید ماهانهٔ کارگاهی %s واحد است. اگر %s درصد %s، تولید چند واحد می‌شود؟' % (
            fa(base), fa(pct), 'افزایش یابد' if up else 'کاهش یابد')
    near = sorted({ans + d for d in (-20, -10, -5, -2, 2, 5, 10, 20) if ans + d > 0} - {ans})
    opts = [ans] + rnd.sample(near, 4)
    rnd.shuffle(opts)
    return {'kind': 'numeric', 'stem': stem, 'options': [fa(o) for o in opts]}, opts.index(ans)


def gen_numeric(seed, n=8, practice=False):
    rnd = random.Random('nm-%s' % seed)
    items, keys = [], []
    for _ in range(n):
        it, k = _numeric(rnd)
        items.append(it)
        keys.append(k)
    return items, keys


# ====================================================================== speed tasks (sent whole; scored from responses)
def gen_arith(seed, n=60, practice=False):
    rnd = random.Random('ar-%s' % seed)
    items, keys = [], []
    for _ in range(n if not practice else 3):
        op = rnd.choice(['+', '-', '×'])
        if op == '×':
            a, b = rnd.randint(2, 9), rnd.randint(3, 12)
            ans = a * b
        elif op == '+':
            a, b = rnd.randint(12, 79), rnd.randint(8, 59)
            ans = a + b
        else:
            a, b = rnd.randint(30, 99), rnd.randint(5, 29)
            ans = a - b
        opts = list({ans, ans + rnd.choice([1, 2, 10]), ans - rnd.choice([1, 2, 10]), ans + rnd.choice([3, 11, 9])})
        while len(opts) < 4:
            opts.append(ans + len(opts) * 7)
        rnd.shuffle(opts)
        items.append({'kind': 'arith', 'stem': '%s %s %s' % (fa(a), op, fa(b)), 'options': [fa(o) for o in opts]})
        keys.append(opts.index(ans))
    return items, keys


SYMBOLS = list('بپتجچحخدرزسشصطعفقکگلمنوهی۲۳۴۵۶۷۸۹')


def gen_compare(seed, n=80, practice=False):
    rnd = random.Random('cp-%s' % seed)
    items, keys = [], []
    for _ in range(n if not practice else 3):
        length = rnd.choice([5, 6, 7])
        a = ''.join(rnd.choice(SYMBOLS) for _ in range(length))
        same = rnd.random() < 0.5
        if same:
            b = a
        else:
            j = rnd.randrange(length)
            b = a[:j] + rnd.choice([s for s in SYMBOLS if s != a[j]]) + a[j + 1:]
        items.append({'kind': 'compare', 'a': a, 'b': b, 'options': ['یکسان', 'متفاوت']})
        keys.append(0 if same else 1)
    return items, keys


def gen_span(seed, n=0, practice=False):
    """Digit span, forward: two sequences per length 3..9 (practice: one of length 3). The key is the sequence."""
    rnd = random.Random('sp-%s' % seed)
    lengths = [3] if practice else [L for L in range(3, 10) for _ in (0, 1)]
    items, keys = [], []
    for L in lengths:
        seq = []
        while len(seq) < L:
            d = rnd.randint(1, 9)
            if not seq or d != seq[-1]:
                seq.append(d)
        items.append({'kind': 'span', 'length': L, 'digits': [fa(d) for d in seq]})
        keys.append(''.join(str(d) for d in seq))
    return items, keys


def gen_flanker(seed, n=40, practice=False):
    rnd = random.Random('fl-%s' % seed)
    items, keys = [], []
    for i in range(n if not practice else 4):
        target = rnd.choice(['L', 'R'])
        congruent = (i % 2 == 0) if practice else rnd.random() < 0.5
        flank = target if congruent else ('R' if target == 'L' else 'L')
        a = {'L': '←', 'R': '→'}
        items.append({'kind': 'flanker', 'stim': a[flank] * 2 + a[target] + a[flank] * 2, 'congruent': congruent,
                      'wait': rnd.randint(400, 900)})
        keys.append(0 if target == 'L' else 1)
    return items, keys


def gen_choice_rt(seed, n=30, practice=False):
    rnd = random.Random('cr-%s' % seed)
    items, keys = [], []
    for _ in range(n if not practice else 3):
        side = rnd.randint(0, 1)
        items.append({'kind': 'choice_rt', 'side': side, 'wait': rnd.randint(600, 1500)})
        keys.append(side)
    return items, keys


GENERATORS = {
    'matrices': gen_matrices, 'series': gen_series, 'logic': gen_logic, 'rotation': gen_rotation,
    'numeric': gen_numeric, 'arith': gen_arith, 'compare': gen_compare, 'span': gen_span, 'flanker': gen_flanker,
    'choice_rt': gen_choice_rt,
}
