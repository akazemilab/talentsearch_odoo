"""Persian text helpers (pure, deterministic). Used by every konkur step so the same name always gives the same key."""
import re
import unicodedata

FA_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')
ARABIC_TO_FA = str.maketrans({'ي': 'ی', 'ى': 'ی', 'ك': 'ک', 'ة': 'ه', 'ۀ': 'ه', 'أ': 'ا', 'إ': 'ا', 'ٱ': 'ا', 'ؤ': 'و'})
DIACRITICS = re.compile('[ً-ٰٟـ]')       # harakat, superscript alef, tatweel
SPACES = re.compile(r'[\s‌‍‎‏‪-‮⁦-⁩\xa0]+')
PUNCT = re.compile(r'[\(\)\[\]\{\}«»"\'`،,؛;:.\-_/\\|*+=…]+')


def digits(s):
    return (s or '').translate(FA_DIGITS)


def norm(s):
    """Display-safe normal form: Persian letters, ASCII digits, single spaces (ZWNJ kept as a space)."""
    s = unicodedata.normalize('NFKC', s or '')
    s = DIACRITICS.sub('', s.translate(ARABIC_TO_FA)).translate(FA_DIGITS)
    return SPACES.sub(' ', s).strip()


def key(s):
    """Matching key: norm + no punctuation + no spaces. Two spellings of one major name give one key."""
    return SPACES.sub('', PUNCT.sub(' ', norm(s)))


def is_rtl_reversed(line):
    """Heuristic for PDF extractors that emit Persian in visual order: common words appear reversed."""
    probes = ('ﻩ', 'ﺍ', 'ﻝ')            # presentation forms usually mean a raw visual-order dump
    return any(p in line for p in probes)


def unshape(s):
    """Map Arabic presentation forms (FB50-FEFF) back to base letters (NFKC does this)."""
    return unicodedata.normalize('NFKC', s or '')
