import sys
from fontTools.ttLib import TTFont
src, dst = sys.argv[1], sys.argv[2]
f = TTFont(src)
cmap = f.getBestCmap()
for i in range(10):
    g = cmap.get(0x06F0 + i)
    assert g, 'no Persian digit %d' % i
    for t in f['cmap'].tables:
        if t.isUnicode():
            t.cmap[0x30 + i] = g
# drop GSUB locl/ss features that might turn digits back? none expected
f.save(dst)
f2 = TTFont(dst); c = f2.getBestCmap(); print(dst, c[0x30], c[0x6F0], len(f2.getGlyphOrder()))
