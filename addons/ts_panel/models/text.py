import re

_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')
_ZWNJ = '‌‍‎‏'


def norm_text(s):
    """Search form of a name or code: ي→ی, ك→ک, Persian/Arabic digits → Latin, ZWNJ and repeated spaces
    collapsed, lower-case (04_data_model.md section 0, rule 7)."""
    s = (s or '').translate(_DIGITS).replace('ي', 'ی').replace('ك', 'ک').replace('ى', 'ی').replace('ۀ', 'ه')
    for c in _ZWNJ:
        s = s.replace(c, ' ' if c == '‌' else '')
    return re.sub(r'\s+', ' ', s).strip().lower()


def people_word(purpose, plural=True):
    """The word for the people a panel serves (glossary §9-3, UX audit G4 PT4): «مراجع» only in clinical panels,
    «شرکت‌کننده» everywhere else."""
    if purpose == 'clinical':
        return 'مراجعان' if plural else 'مراجع'
    return 'شرکت‌کنندگان' if plural else 'شرکت‌کننده'


def mask_phone(value):
    """0912…6789 style: enough to recognise a number, not enough to copy it (import preview)."""
    digits = ''.join(ch for ch in (value or '') if ch.isdigit())
    if len(digits) < 7:
        return value or ''
    return digits[:4] + '…' + digits[-4:]
