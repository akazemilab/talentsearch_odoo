#!/usr/bin/env python3
"""Apply a copy-replacement file safely (UX writing passes).

Format of the data file:
    @@ relative/path/to/file
    <<<
    old text (one line)
    ===
    new text (one line)
    >>> N          (expected occurrences of old text; default 1)
    # comment lines outside blocks are ignored

Every block must match exactly N times or nothing is written. --apply writes the files; without it, a dry run.
--md PATH writes a before/after table (Markdown) of the blocks under ts_website / ts_career views and models.
"""
import sys
from pathlib import Path

ROOT = Path('/root/talentsearch_odoo')


def parse(path):
    blocks, cur, mode = [], None, None
    for raw in Path(path).read_text(encoding='utf-8').split('\n'):
        if raw.startswith('@@ '):
            cur_file = raw[3:].strip()
            continue
        if raw == '<<<':
            cur, mode = {'file': cur_file, 'old': [], 'new': [], 'n': 1}, 'old'
            continue
        if raw == '===' and cur is not None:
            mode = 'new'
            continue
        if raw.startswith('>>>') and cur is not None:
            n = raw[3:].strip()
            cur['n'] = int(n) if n else 1
            cur['old'] = '\n'.join(cur['old'])
            cur['new'] = '\n'.join(cur['new'])
            blocks.append(cur)
            cur, mode = None, None
            continue
        if cur is not None and mode:
            cur[mode].append(raw)
    return blocks


def main():
    data = sys.argv[1]
    apply = '--apply' in sys.argv
    md = sys.argv[sys.argv.index('--md') + 1] if '--md' in sys.argv else None
    blocks = parse(data)
    texts, bad = {}, []
    for i, b in enumerate(blocks, 1):
        p = ROOT / b['file']
        if b['file'] not in texts:
            texts[b['file']] = p.read_text(encoding='utf-8')
        c = texts[b['file']].count(b['old'])
        if c != b['n']:
            bad.append('block %d %s: found %d, expected %d: %s' % (i, b['file'], c, b['n'], b['old'][:70]))
            continue
        texts[b['file']] = texts[b['file']].replace(b['old'], b['new'])
    print('blocks %d, files %d, failures %d' % (len(blocks), len(texts), len(bad)))
    for line in bad:
        print('FAIL', line)
    if bad:
        sys.exit(1)
    if apply:
        for f, t in texts.items():
            (ROOT / f).write_text(t, encoding='utf-8')
        print('APPLIED')
    if md:
        rows = ['| # | فایل | پیش از ویرایش | پس از ویرایش |', '|---|---|---|---|']
        k = 0
        for b in blocks:
            if '/tests' in b['file'] or b['file'].startswith('tools/'):
                continue
            k += 1
            esc = lambda s: s.replace('|', '\\|').strip()
            rows.append('| %d | %s | %s | %s |' % (k, b['file'].split('/')[-1], esc(b['old']), esc(b['new'])))
        Path(md).write_text('\n'.join(rows) + '\n', encoding='utf-8')
        print('MD', md, k)


if __name__ == '__main__':
    main()
