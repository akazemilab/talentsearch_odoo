"""PDF text access with whatever backend the server has (poppler pdftotext > pdfplumber > pypdf). Deterministic."""
import os
import shutil
import subprocess


def backends():
    have = []
    if shutil.which('pdftotext') and shutil.which('pdfinfo'):
        have.append('pdftotext')
    for mod in ('pdfplumber', 'pypdf', 'fitz'):
        try:
            __import__(mod)
            have.append(mod)
        except Exception:
            pass
    return have


def _backend(pref=None):
    have = backends()
    if pref:
        if pref not in have:
            raise RuntimeError('PDF backend %s not available (have: %s)' % (pref, ', '.join(have) or 'none'))
        return pref
    for b in ('pdftotext', 'fitz', 'pdfplumber', 'pypdf'):
        if b in have:
            return b
    raise RuntimeError('no PDF backend: install poppler-utils (pdftotext) or python3-pdfplumber')


def page_count(path, pref=None):
    b = _backend(pref)
    if b == 'pdftotext':
        out = subprocess.run(['pdfinfo', path], capture_output=True, text=True).stdout
        for line in out.splitlines():
            if line.startswith('Pages:'):
                return int(line.split()[1])
        return 0
    if b == 'fitz':
        import fitz
        with fitz.open(path) as d:
            return d.page_count
    if b == 'pdfplumber':
        import pdfplumber
        with pdfplumber.open(path) as d:
            return len(d.pages)
    import pypdf
    return len(pypdf.PdfReader(path).pages)


def pages_text(path, first, last, pref=None, layout=True):
    """List of page texts for pages first..last (1-based, inclusive)."""
    b = _backend(pref)
    if b == 'pdftotext':
        args = ['pdftotext', '-enc', 'UTF-8', '-f', str(first), '-l', str(last)]
        if layout:
            args.append('-layout')
        out = subprocess.run(args + [path, '-'], capture_output=True, text=True).stdout
        parts = out.split('\f')
        return [p for p in parts[:last - first + 1]]
    if b == 'fitz':
        import fitz
        with fitz.open(path) as d:
            return [d[i - 1].get_text('text', sort=True) for i in range(first, last + 1)]
    if b == 'pdfplumber':
        import pdfplumber
        with pdfplumber.open(path) as d:
            return [(d.pages[i - 1].extract_text(layout=layout) or '') for i in range(first, last + 1)]
    import pypdf
    r = pypdf.PdfReader(path)
    return [(r.pages[i - 1].extract_text() or '') for i in range(first, last + 1)]


def iter_pages(path, chunk=25, pref=None, layout=True):
    n = page_count(path, pref)
    for a in range(1, n + 1, chunk):
        b = min(n, a + chunk - 1)
        for i, t in enumerate(pages_text(path, a, b, pref, layout)):
            yield a + i, t


def size_mb(path):
    return round(os.path.getsize(path) / 1048576, 1)
