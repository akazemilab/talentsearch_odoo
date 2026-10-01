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
