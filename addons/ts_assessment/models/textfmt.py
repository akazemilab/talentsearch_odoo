"""Display-time formatting of the book's band texts (ORM-free, so tools/content can import it without Odoo).

Moved verbatim from models/attempt.py (content v2 step 1); attempt.py imports every name back."""
import re

BAND_WORDS = {'Low': 'کم', 'Medium': 'متوسط', 'High': 'زیاد'}


# Owner decision 2026-10-11: the product speaks the language of counseling. The book's band texts are stored verbatim
# (never edited); these explicit phrases are mapped only when a text is shown. Each pattern needs a non-letter on both
# sides, so درماندگی / درمانده / درمانی / بیماری / بیمارستان are never touched. Order matters (longest first).
# Persian/Arabic letters, diacritics, ZWNJ/ZWJ; NOT punctuation (، ؛ ؟) or digits, which count as boundaries.
_FA_LETTER = '\u0620-\u065F\u066E-\u06D3\u06D5\u06EE\u06EF\u06FA-\u06FC\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF\u200c\u200d'
_COUNSELING_TERMS = [
    (r'روان[\u200c ]?درمانگران', 'مشاوران'),
    (r'روان[\u200c ]?درمانگر', 'مشاور'),
    (r'روان[\u200c ]?درمانی', 'مشاوره'),
    (r'درمانگران', 'مشاوران'),
    (r'درمانگر', 'مشاور'),
    (r'جلسات درمان', 'جلسات مشاوره'),
    (r'جلسه(?:ٔ|\u200cی| ی)? درمان', 'جلسهٔ مشاوره'),
    (r'(فرا?یند|فرآیند) درمان', r'\1 مشاوره'),
    (r'درمان[\u200c]?جویان', 'مراجعان'),
    (r'درمان[\u200c]?جو', 'مراجع'),
    (r'بیماران', 'مراجعان'),
    (r'بیمار', 'مراجع'),
    # UX audit 2026-10-12 (G6-P7-5, owner approved): the counselor guide's «پروتکل پیشنهادی» is medical register
    (r'پروتکل پیشنهادی', 'پیشنهادهای کاربردی برای جلسه'),
]
_COUNSELING_RE = [(re.compile(r'(?<![%s])%s(?![%s])' % (_FA_LETTER, pat, _FA_LETTER)), rep)
                  for pat, rep in _COUNSELING_TERMS]


def counseling_terms(text):
    """Display-time wording map for book texts (headings and bodies); the stored text is unchanged."""
    if not text:
        return text
    for rx, rep in _COUNSELING_RE:
        text = rx.sub(rep, text)
    return text


DEF_HEADING = 'این عامل چه چیزی را توصیف می‌کند'      # «تعریف عامل» (glossary §4: عامل, never بُعد)
PARTICIPANT_HEADING = 'تفسیر نتیجهٔ شما'             # «تفسیر سطح X» and, for the participant, its «تحلیل» / «تفسیر» parts
_SUB_HEADS = ('تحلیل', 'تفسیر')
_RANGE_HEAD = re.compile(r'نمرات\s*[\d۰-۹]')          # «تحلیل و تفسیر نمرات 60-80»: a block of the source's older 5-range scheme
_GLUED_HEAD = re.compile(r'(?<=[^\s#])\s*(?=#{2,}\s)')    # «… راهکارها### تحلیل و تفسیر نمرات 80-100:» (heading glued to a line)


def _heading_of(line):
    """A short line ending with ':' is a heading; markdown marks around it (#### / **) are ignored. None otherwise."""
    core = re.sub(r'^[#\s]+', '', line.strip()).replace('**', '').strip()
    if core.endswith(':') and len(core) < 60:
        return core[:-1].strip()
    return None


def _is_band_head(h):
    return bool(h) and (h.startswith('تفسیر سطح') or h.startswith('تحلیل و تفسیر سطح'))


def split_interpretation(text, participant=False):
    """The approved source texts follow a fixed shape:
        تفسیر نتیجه برای مراجع | راهنمای تخصصی درمانگر   (title line)
        عامل: <name>                                       (dropped: the factor heading is already on the page)
        تعریف عامل:  <definition>
        تفسیر سطح Low: / تحلیل و تفسیر سطح Low:  <body>, sometimes split into «تحلیل:» / «تفسیر:» parts
        پروتکل پیشنهادی: <counselor suggestions>           (therapist text only)
    Returns [(heading, body)], headings in Persian, bodies verbatim except the counseling word map (counseling_terms)
    and markdown marks (** and leading #).

    Display-time clean-up of the book texts (UX audit 2026-10-12, G6-PT3; data facts in docs/clinic/06_data_issues.md),
    the stored text is never changed:
    * Many band texts hold TWO variants of the band text (the source system had five score ranges and merged them into
      three bands): a band body of two blank-line-separated paragraphs, or a second «تحلیل:» / «تفسیر:» pair. Only the
      first variant is shown; it is the one written for the band.
    * A stray «تحلیل و تفسیر نمرات 60-80:» block (older range scheme) is not shown.
    * participant=True (the participant's own report): the band text and its «تحلیل» / «تفسیر» parts are one section
      «تفسیر نتیجهٔ شما» (one heading, one voice for the reader)."""
    if not text:
        return []
    lines = text.replace('\r', '').split('\n')
    lines = lines[1:] if lines and ':' not in lines[0] else lines
    flat = []
    for line in lines:
        flat.extend(_GLUED_HEAD.split(line) if '##' in line else [line])
    sections, head, buf = [], None, []
    for line in flat:
        s = line.strip()
        if re.match(r'^عامل\s*:', s) or re.fullmatch(r'-{3,}', s):
            continue
        h = _heading_of(s)
        if h is not None:
            if head is not None or buf:
                sections.append((head, '\n'.join(buf).strip()))
            head, buf = h, []
        else:
            buf.append(line.replace('**', ''))
    if head is not None or buf:
        sections.append((head, '\n'.join(buf).strip()))

    kept, in_band, seen_sub, dropping = [], False, set(), False
    for h, body in sections:
        if h and _RANGE_HEAD.search(h):
            dropping = True
            continue
        if h in _SUB_HEADS:
            if dropping or not body:       # an empty «تحلیل:» line is not a variant of its own
                continue
            if in_band:
                if h in seen_sub:          # second «تحلیل» / «تفسیر»: the next variant starts here
                    dropping = True
                    continue
                seen_sub.add(h)
            kept.append((h, body, in_band))
            continue
        dropping = False
        in_band = _is_band_head(h)
        seen_sub = set()
        if in_band:
            paras = [p.strip() for p in re.split(r'\n\s*\n', body) if p.strip()]
            body = paras[0] if paras else ''
        kept.append((h, body, False))

    out = []
    for h, body, band_part in kept:
        if not body:
            continue
        if h:
            for en, fa in BAND_WORDS.items():
                h = re.sub(r'\b%s\b' % en, fa, h)
            if h.startswith('تعریف عامل'):
                h = DEF_HEADING
            elif h.startswith('تفسیر سطح'):
                h = PARTICIPANT_HEADING
            elif participant and band_part:
                if out and out[-1][0] == PARTICIPANT_HEADING:
                    out[-1] = (PARTICIPANT_HEADING, out[-1][1] + '\n\n' + counseling_terms(body))
                    continue
                h = PARTICIPANT_HEADING
        out.append((counseling_terms(h), counseling_terms(body)))
    return out
