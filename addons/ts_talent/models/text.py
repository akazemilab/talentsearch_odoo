"""Pure text helpers for field names (no ORM)."""
import re

_AR = str.maketrans({'ي': 'ی', 'ك': 'ک', 'ى': 'ی', 'ۀ': 'ه', '‏': '', '‎': '', '‫': '', '‬': ''})
_DIGITS = str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹', '01234567890123456789')
LABEL_MAX = 80
PLACEHOLDER = re.compile(r'این (?:زمینه|قلمرو|عرصه)')


def clean_label(raw):
    """What is stored and shown: trimmed, single spaces, Persian ی/ک."""
    s = (raw or '').translate(_AR)
    s = re.sub(r'[\x00-\x1f\x7f]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s[:LABEL_MAX].strip()


def norm_label(raw):
    """Key for duplicate detection: cleaned, digits unified, no spaces/half-spaces, lowercase."""
    s = clean_label(raw).translate(_DIGITS).replace('‌', '').replace(' ', '')
    return s.lower()


def item_segments(text, label):
    """Split a stored item text at «این زمینه/قلمرو/عرصه»: [(text, is_field_name)].
    Stored text is never changed; only the displayed parts are."""
    out, pos = [], 0
    for m in PLACEHOLDER.finditer(text):
        if m.start() > pos:
            out.append((text[pos:m.start()], False))
        out.append((label, True))
        pos = m.end()
    if pos < len(text):
        out.append((text[pos:], False))
    return out
