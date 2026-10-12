"""Task instruments, block scoring, norms and integrity flags (docs/hr/01_architecture.md section 4). Pure functions.

Norms: until a block has NORM_MIN real completions, raw scores are turned into percentiles with the provisional
PN-0 parameters below (design assumptions, labelled «برآورد موقت» wherever shown). From NORM_MIN on, the empirical
distribution of real candidates is used (EMP-n, rebuilt by a weekly cron) and the result records which norm it used.
"""
import math
import statistics

SCORING_VERSION = 'TASKS-v1-2026-10-12'
NORM_MIN = 100

# instrument code -> spec. 'limit' in seconds (None = untimed / trial-paced). 'desktop': keyboard tasks.
INSTRUMENTS = {
    'TASK-REASON': {
        'name': 'آزمون استدلال', 'title': 'استدلال', 'minutes': 12, 'desktop': False,
        'intro': 'سه بخش کوتاه: ماتریس‌های تصویری، دنبالهٔ عددی و استدلال منطقی. هر بخش زمان جداگانه دارد.',
        'blocks': [
            {'key': 'matrices', 'title': 'ماتریس‌های تصویری', 'n': 8, 'limit': 240,
             'help': 'در هر ردیف الگویی تکرار می‌شود. خانهٔ خالیِ پایین‌چپ را با گزینه‌ای پر کنید که الگو را کامل می‌کند.'},
            {'key': 'series', 'title': 'دنبالهٔ عددی', 'n': 8, 'limit': 180,
             'help': 'عددها با قاعده‌ای پشت هم آمده‌اند. عدد بعدی را انتخاب کنید.'},
            {'key': 'logic', 'title': 'استدلال منطقی', 'n': 8, 'limit': 210,
             'help': 'فقط بر پایهٔ جمله‌های داده‌شده پاسخ دهید، حتی اگر واژه‌ها برایتان ناآشنا باشند.'},
        ],
        'factors': {'Inductive Reasoning': ['matrices', 'series'], 'Information Ordering': ['series'],
                    'Deductive Reasoning': ['logic']},
    },
    'TASK-SPATIAL': {
        'name': 'آزمون تجسم فضایی', 'title': 'تجسم فضایی', 'minutes': 4, 'desktop': False,
        'intro': 'دو شکل می‌بینید. بگویید شکل راست همان شکل چپ است که چرخیده، یا قرینهٔ آینه‌ای آن است.',
        'blocks': [{'key': 'rotation', 'title': 'چرخش ذهنی', 'n': 16, 'limit': 150,
                    'help': 'شکل را در ذهن بچرخانید. شکلِ قرینه با هیچ چرخشی روی شکل اول نمی‌نشیند.'}],
        'factors': {'Visualization': ['rotation'], 'Spatial Orientation': ['rotation']},
    },
    'TASK-NUMERIC': {
        'name': 'آزمون عددی', 'title': 'عددی', 'minutes': 7, 'desktop': False,
        'intro': 'دو بخش: مسئله‌های عددی کوتاه، و محاسبه‌های سریع.',
        'blocks': [
            {'key': 'numeric', 'title': 'مسئله‌های عددی', 'n': 8, 'limit': 240,
             'help': 'می‌توانید از کاغذ و قلم استفاده کنید؛ ماشین‌حساب مجاز نیست.'},
            {'key': 'arith', 'title': 'محاسبهٔ سریع', 'n': 60, 'limit': 90, 'speed': True,
             'help': 'در ۹۰ ثانیه هر چند محاسبه که می‌توانید پاسخ دهید؛ پاسخ نادرست امتیاز کم می‌کند. کلیدهای ۱ تا ۴ گزینه‌ها را انتخاب می‌کنند.'},
        ],
        'factors': {'Mathematical Reasoning': ['numeric'], 'Number Facility': ['arith']},
    },
    'TASK-SPEED': {
        'name': 'آزمون سرعت و توجه', 'title': 'سرعت و توجه', 'minutes': 9, 'desktop': True,
        'intro': 'چهار بخش کوتاه با صفحه‌کلید: مقایسهٔ نشانه‌ها، به خاطر سپردن عددها، جهت پیکان و واکنش سریع.',
        'blocks': [
            {'key': 'compare', 'title': 'مقایسهٔ نشانه‌ها', 'n': 80, 'limit': 90, 'speed': True,
             'help': 'اگر دو رشته یکسان‌اند کلید F و اگر متفاوت‌اند کلید J را بزنید؛ دکمه‌های روی صفحه هم کار می‌کنند.'},
            {'key': 'span', 'title': 'حافظهٔ عدد', 'n': 0, 'limit': None, 'speed': True,
             'help': 'عددها یکی‌یکی نمایش داده می‌شوند. پس از پایان، همان عددها را به همان ترتیب وارد کنید.'},
            {'key': 'flanker', 'title': 'جهت پیکان وسط', 'n': 40, 'limit': None, 'speed': True,
             'help': 'فقط به پیکانِ وسط نگاه کنید: کلید جهت‌نمای چپ یا راست را بزنید.'},
            {'key': 'choice_rt', 'title': 'واکنش سریع', 'n': 30, 'limit': None, 'speed': True,
             'help': 'دایره چپ یا راست ظاهر می‌شود؛ هر چه سریع‌تر کلید جهت‌نمای همان سمت را بزنید.'},
        ],
        'factors': {'Perceptual Speed': ['compare'], 'Memorization': ['span'], 'Selective Attention': ['flanker'],
                    'Reaction Time': ['choice_rt'], 'Response Orientation': ['choice_rt']},
    },
    'TASK-VERIFY': {
        'name': 'آزمون تأیید استدلال (حضوری)', 'title': 'تأیید استدلال', 'minutes': 6, 'desktop': False,
        'intro': 'نسخهٔ کوتاه آزمون استدلال با پرسش‌های تازه، زیر نظر سازمان.',
        'blocks': [
            {'key': 'matrices', 'title': 'ماتریس‌های تصویری', 'n': 6, 'limit': 180,
             'help': 'خانهٔ خالی را با گزینه‌ای پر کنید که الگو را کامل می‌کند.'},
            {'key': 'series', 'title': 'دنبالهٔ عددی', 'n': 6, 'limit': 135, 'help': 'عدد بعدی را انتخاب کنید.'},
        ],
        'factors': {'Inductive Reasoning': ['matrices', 'series']},
    },
}

POWER = {'matrices', 'series', 'logic', 'rotation', 'numeric'}
# PN-0 provisional norms: (mean, sd, higher_is_better). Design assumptions, replaced by EMP-n at NORM_MIN real cases.
PN0 = {
    'matrices': (0.55, 0.20, True), 'series': (0.60, 0.20, True), 'logic': (0.60, 0.20, True),
    'rotation': (0.75, 0.13, True), 'numeric': (0.55, 0.22, True), 'arith': (14.0, 5.0, True),
    'compare': (22.0, 7.0, True), 'span': (6.5, 1.2, True), 'flanker': (650.0, 150.0, False),
    'choice_rt': (420.0, 70.0, False),
}
BAND_EDGES = (100 / 3, 200 / 3)


def band_of(pct):
    return 'low' if pct < BAND_EDGES[0] else ('medium' if pct < BAND_EDGES[1] else 'high')


def _phi(z):
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def percentile(block, raw, norm_values=None):
    """(percentile 1-99, norm label). norm_values: sorted raw values of real completions (EMP-n) or None (PN-0)."""
    mean, sd, up = PN0[block]
    if norm_values and len(norm_values) >= NORM_MIN:
        below = sum(1 for v in norm_values if v < raw)
        equal = sum(1 for v in norm_values if v == raw)
        p = 100.0 * (below + 0.5 * equal) / len(norm_values)
        if not up:
            p = 100.0 - p
        return max(1.0, min(99.0, p)), 'EMP-%d' % len(norm_values)
    z = (raw - mean) / sd
    p = 100.0 * _phi(z if up else -z)
    return max(1.0, min(99.0, p)), 'PN-0'


def raw_score(block, keys, responses, limit):
    """responses: list aligned with items: {'c': choice | 'v': typed string, 'rt': ms} or None (not reached)."""
    n = len(keys)
    got = [r for r in responses if r]
    if block in POWER:
        correct = sum(1 for k, r in zip(keys, responses) if r and r.get('c') == k)
        return correct / n if n else 0.0
    if block in ('arith', 'compare'):
        correct = sum(1 for k, r in zip(keys, responses) if r and r.get('c') == k)
        wrong = len(got) - correct
        minutes = (limit or 90) / 60.0
        return max(0.0, (correct - (wrong / 3.0 if block == 'arith' else wrong)) / minutes)
    if block == 'span':
        best = 2
        for k, r in zip(keys, responses):
            if r and str(r.get('v', '')).strip() == k:
                best = max(best, len(k))
        return float(best)
    if block == 'flanker':
        inc = [(k, r) for k, r in zip(keys, responses) if r is not None and r.get('inc')]
        ok = [r['rt'] for k, r in inc if r.get('c') == k and r.get('rt')]
        acc = (len(ok) / len(inc)) if inc else 0.0
        if acc < 0.5 or not ok:
            return 2000.0
        return statistics.median(ok) / acc
    if block == 'choice_rt':
        ok = [r['rt'] for k, r in zip(keys, responses) if r and r.get('c') == k and r.get('rt')]
        acc = len(ok) / n if n else 0.0
        if not ok:
            return 1500.0
        med = statistics.median(ok)
        return med * (1.5 if acc < 0.7 else 1.0)
    raise ValueError(block)


def block_flags(block, keys, responses, meta):
    """Integrity signals for HR (never an automatic decision)."""
    flags = []
    got = [r for r in responses if r]
    if meta.get('focus_lost', 0) >= 3:
        flags.append('focus')
    if meta.get('resumed', 0) >= 1:
        flags.append('resumed')
    if meta.get('late'):
        flags.append('late')
    if meta.get('timing'):
        flags.append('timing')
    if block in POWER and got:
        fast = sum(1 for r in got if (r.get('rt') or 0) < 2000)
        if fast / len(got) > 0.3 and len(got) >= 4:
            flags.append('fast')
    if block in ('flanker', 'choice_rt') and got:
        antic = sum(1 for r in got if (r.get('rt') or 0) < 150)
        if antic / len(got) > 0.1:
            flags.append('anticipation')
    if block in POWER and not got:
        flags.append('empty')
    return flags


FLAG_FA = {
    'focus': 'چند بار از صفحهٔ آزمون خارج شد', 'resumed': 'صفحه در میانهٔ بخش دوباره باز شد',
    'fast': 'بسیاری از پاسخ‌ها کمتر از ۲ ثانیه داده شد', 'anticipation': 'واکنش‌های پیش از نمایش محرک',
    'empty': 'به هیچ پرسشی پاسخ نداد', 'late': 'بخش سرعت دیرتر از زمانش فرستاده شد',
    'timing': 'زمان‌های گزارش‌شده با زمان واقعی جور نبود', 'verify_drop': 'نتیجهٔ آزمون تأیید حضوری بسیار پایین‌تر بود',
}


def factor_scores(spec, block_pcts):
    """{factor: percentile} as the mean of its blocks' percentiles (blocks not taken are skipped)."""
    out = {}
    for factor, blocks in spec['factors'].items():
        vals = [block_pcts[b] for b in blocks if b in block_pcts]
        if vals:
            out[factor] = sum(vals) / len(vals)
    return out
