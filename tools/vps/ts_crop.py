#!/usr/bin/env python3
"""ts_crop.py IN.png OUT.png X Y W H [SCALE] : cut one region of a screenshot (CSS px of a 1280-wide shot = image px) so
a reviewer looks at the part in question, not the whole page (token budget). SCALE (default 1) enlarges small regions.
Negative X counts from the right edge (RTL pages keep the side menu on the right): -360 = the rightmost 360 px."""
import sys
from PIL import Image

src, out, x, y, w, h = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6])
scale = float(sys.argv[7]) if len(sys.argv) > 7 else 1.0
im = Image.open(src)
if x < 0:
    x = im.width + x
box = (max(0, x), max(0, y), min(im.width, x + w), min(im.height, y + h))
c = im.crop(box)
if scale != 1:
    c = c.resize((int(c.width * scale), int(c.height * scale)), Image.LANCZOS)
c.save(out)
print('CROP %s %dx%d from %s' % (out, c.width, c.height, box))
