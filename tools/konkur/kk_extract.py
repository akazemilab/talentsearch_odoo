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
NUMTOK = re.compile(r'^\d+(?:\.\d+)?$')
FA = re.compile('[؀-ۿ]{2,}')


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


def parse_msrt(line):
    """Ministry curriculum table row as pdftotext emits it (LTR token order):
    [prerequisite text] HOURS... UNIT-TYPE... UNITS_TOTAL  COURSE NAME  ROW_NO
    The numeric run right before the name ends with the total units; a 5-number run is
    (hours practice, hours theory, units practice, units theory, total). Returns (name, total, practice) or None."""
    t = line.split()
    if len(t) < 4 or not NUMTOK.match(t[-1]) or not 0 < float(t[-1]) <= 300:
        return None
    best, i = None, 0
    while i < len(t) - 1:
        if NUMTOK.match(t[i]):
            j = i
            while j < len(t) - 1 and NUMTOK.match(t[j]):
                j += 1
            if j - i >= 2 and j < len(t) - 1:
                best = (i, j)
            i = j
        i += 1
    if not best:
        return None
    run = [float(x) for x in t[best[0]:best[1]]]
    name = ' '.join(t[best[1]:-1]).strip(' -|*')
    total = run[-1]
    if not name or not 0 < total <= 16 or not FA.search(name):
        return None
    practice = run[-3] if len(run) >= 5 and run[-3] <= total else 0.0
    return name, total, practice


def curriculum_rows(pdf, family):
    """Every line with Persian letters and a small number; rows the table parser understands carry course/units."""
    r = rules().get('curriculum', {})
    parser = r.get('row_parser', 'msrt')
    rows, pages = [], 0
    for page, text in kk_pdf.iter_pages(pdf, layout=r.get('layout', True)):
        pages += 1
        for ln in text.splitlines():
            c = clean_line(digits(ln))
            nums = [float(x) for x in NUM.findall(c)]
            if not FA.search(c) or not nums or not any(0 < x <= 16 for x in nums):
                continue
            name = re.sub(r'\s+', ' ', NUM.sub(' ', c)).strip(' -|')
            row = {'family_id': family, 'page': page, 'name': name, 'line': c,
                   'numbers': ' '.join(('%g' % x) for x in nums), 'course': '', 'units_total': '', 'units_practice': ''}
            p = parse_msrt(c) if parser == 'msrt' else None
            if p:
                row['course'], row['units_total'], row['units_practice'] = p
            rows.append(row)
    return rows, pages


def write_csv(rows, path, fields):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.part'
    with open(tmp, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)
