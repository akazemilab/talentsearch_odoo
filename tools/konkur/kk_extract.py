"""Booklet and curriculum PDFs -> raw row CSVs (deterministic). Column meaning is decided by parse rules in
ref/parse_rules.json after a page was peeked; the raw rows keep everything so a rule change never needs the PDF again."""
import csv
import json
import os
import re

import kk_pdf
from kk_text import digits, norm, unshape

HERE = os.path.dirname(os.path.abspath(__file__))
RULES = os.path.join(HERE, 'ref', 'parse_rules.json')
NUM = re.compile(r'(?<![\d.])-?\d+(?:\.\d+)?(?![\d.])')


def rules():
    if os.path.exists(RULES):
        with open(RULES, encoding='utf-8') as f:
            return json.load(f)
    return {}


def clean_line(line):
    return norm(unshape(line))


def booklet_rows(pdf, group, code_rx=None):
    """Every line that carries a major code (default: a standalone 4-5 digit number)."""
    r = rules().get('booklet', {})
    rx = re.compile(code_rx or r.get('code_rx', r'(?<!\d)(\d{4,5})(?!\d)'))
    rows, pages, coded_pages = [], 0, set()
    for page, text in kk_pdf.iter_pages(pdf, layout=r.get('layout', True)):
        pages += 1
        for ln in text.splitlines():
            c = clean_line(digits(ln))
            m = rx.search(c)
            if not m:
                continue
            rows.append({'group': group, 'page': page, 'code': m.group(1), 'line': c})
            coded_pages.add(page)
    return rows, pages, len(coded_pages)


def curriculum_rows(pdf, family):
    """Every line with Persian letters and at least one small number (course name + units/hours)."""
    r = rules().get('curriculum', {})
    rows, pages = [], 0
    fa = re.compile('[؀-ۿ]{2,}')
    for page, text in kk_pdf.iter_pages(pdf, layout=r.get('layout', True)):
        pages += 1
        for ln in text.splitlines():
            c = clean_line(digits(ln))
            nums = [float(x) for x in NUM.findall(c)]
            if not fa.search(c) or not nums or not any(0 < x <= 16 for x in nums):
                continue
            name = NUM.sub(' ', c)
            name = re.sub(r'\s+', ' ', name).strip(' -|')
            rows.append({'family_id': family, 'page': page, 'name': name, 'numbers': ' '.join(str(x).rstrip('0').rstrip('.') for x in nums), 'line': c})
    return rows, pages


def write_csv(rows, path, fields):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.part'
    with open(tmp, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)
