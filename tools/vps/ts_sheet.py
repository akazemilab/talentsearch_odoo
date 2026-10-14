#!/root/eot-browser/venv/bin/python
"""ts_sheet.py OUT.png COLS TILE_W PNG... : one contact sheet of many page screenshots (top CROP px of each, labelled),
so a reviewer looks at ONE image per role instead of one per page (token budget, clin9). Renders an HTML grid with the
same headless Chromium as ts_shot.py; no image library needed. TS_SHEET_CROP (default 1400 CSS px of each page)."""
import html, os, sys, tempfile
from playwright.sync_api import sync_playwright

out, cols, tile = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
files = [f for f in sys.argv[4:] if os.path.exists(f)]
if not files:
    sys.exit('no images')
crop = int(os.environ.get('TS_SHEET_CROP', '1400'))
cells = ''.join(
    '<figure><div class="v" style="height:%dpx"><img src="file://%s"></div><figcaption>%s</figcaption></figure>'
    % (int(crop * tile / 1280), html.escape(f), html.escape(os.path.basename(f)[:60])) for f in files)
doc = """<!doctype html><meta charset=utf-8><style>
body{margin:0;background:#888;font:12px sans-serif} .g{display:grid;grid-template-columns:repeat(%d,%dpx);gap:6px;padding:6px}
figure{margin:0;background:#fff} .v{overflow:hidden} img{width:100%%;display:block} figcaption{padding:2px 4px;background:#222;color:#fff}
</style><div class=g>%s</div>""" % (cols, tile, cells)
with tempfile.NamedTemporaryFile('w', suffix='.html', delete=False, dir='/root/ts-jobs') as fh:
    fh.write(doc)
with sync_playwright() as p:
    b = p.chromium.launch(executable_path='/snap/chromium/current/usr/lib/chromium-browser/chrome',
                          args=['--no-sandbox', '--disable-gpu', '--allow-file-access-from-files'])
    pg = b.new_page(viewport={'width': cols * (tile + 6) + 6, 'height': 600})
    pg.goto('file://' + fh.name)
    pg.wait_for_timeout(400)
    pg.screenshot(path=out, full_page=True)
    b.close()
os.unlink(fh.name)
print('SHEET %s (%d tiles)' % (out, len(files)))
