#!/usr/bin/env python3
"""Self-hosted fonts for the public pages (so visitors' browsers do not call Google).

Input: the Fontsource npm packages (the same files Google Fonts serves):
    npm install @fontsource-variable/assistant @fontsource-variable/frank-ruhl-libre \
                @fontsource-variable/playpen-sans-hebrew @fontsource/ms-madi
Run:   python3 tools/site/make_fonts.py <node_modules dir>     (needs: pip install fonttools brotli)
Output: assets/fonts/*.woff2 and assets/fonts.css

To keep the pages light, the two heavy families are cut down to what the site uses:
- Frank Ruhl Libre: weight 500 only; Latin part limited to basic Latin and punctuation.
- Playpen Sans Hebrew: weight 400 only; Latin part limited to basic Latin and punctuation,
  without the "calt" handwriting alternates (they are 3/4 of the file and only affect Latin letters and digits).
All four families are under the SIL Open Font License 1.1 (see assets/fonts/LICENSES.txt).
"""
import io, pathlib, sys
from fontTools.ttLib import TTFont
from fontTools import subset
from fontTools.varLib import instancer

NM = pathlib.Path(sys.argv[1])
ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / 'assets' / 'fonts'
OUT.mkdir(parents=True, exist_ok=True)
V, S = NM / '@fontsource-variable', NM / '@fontsource'
BASIC = 'U+0020-007E,U+00A0,U+00AB,U+00B7,U+00BB,U+2013,U+2014,U+2018-201D,U+2022,U+2026'
HEBREW = 'U+0307-0308,U+0590-05FF,U+200C-2010,U+20AA,U+25CC,U+FB1D-FB4F'
LATIN = 'U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD'


def uni(spec):
    out = set()
    for part in spec.split(','):
        a, _, b = part.replace('U+', '').partition('-')
        out.update(range(int(a, 16), int(b or a, 16) + 1))
    return out


def save(font, name):
    font.flavor = 'woff2'
    buf = io.BytesIO(); font.save(buf)
    (OUT / name).write_bytes(buf.getvalue())
    return len(buf.getvalue())


def make(src, name, weight=None, keep=None, features=None):
    font = TTFont(src)
    if weight is not None:
        font = instancer.instantiateVariableFont(font, {'wght': weight})
    if keep is not None:
        opt = subset.Options()
        opt.layout_features = features or ['*']
        opt.notdef_outline = True
        sub = subset.Subsetter(opt)
        sub.populate(unicodes=sorted(uni(keep)))
        sub.subset(font)
    size = save(font, name)
    cmap = set(TTFont(OUT / name).getBestCmap())
    print(f'{name}: {size // 1024} KB, {len(cmap)} characters')
    return cmap


def ascii_range(cmap):
    """Basic Latin characters the Hebrew file already has (space, punctuation), as a unicode-range list."""
    have = sorted(c for c in cmap if (0x20 <= c <= 0x7E or c == 0xA0) and not chr(c).isalnum())
    runs, start, prev = [], None, None
    for c in have:
        if start is None: start = prev = c
        elif c == prev + 1: prev = c
        else: runs.append((start, prev)); start = prev = c
    if start is not None: runs.append((start, prev))
    return ','.join(f'U+{a:04X}' if a == b else f'U+{a:04X}-{b:04X}' for a, b in runs)


faces = []  # (family, weight descriptor, file, unicode-range)

def family(fam, weight_desc, latin_cmap_file, hebrew_cmap, hebrew_file, latin_range=LATIN):
    faces.append((fam, weight_desc, latin_cmap_file, latin_range))
    extra = ascii_range(hebrew_cmap)
    # declared after the Latin face, so Hebrew text with spaces and punctuation needs only this file
    faces.append((fam, weight_desc, hebrew_file, HEBREW + (',' + extra if extra else '')))


a = V / 'assistant' / 'files'
make(a / 'assistant-latin-wght-normal.woff2', 'assistant-latin.woff2')
h = make(a / 'assistant-hebrew-wght-normal.woff2', 'assistant-hebrew.woff2')
family('Assistant', '200 800', 'assistant-latin.woff2', h, 'assistant-hebrew.woff2')

f = V / 'frank-ruhl-libre' / 'files'
make(f / 'frank-ruhl-libre-latin-wght-normal.woff2', 'frank-ruhl-libre-500-latin.woff2', weight=500, keep=BASIC)
h = make(f / 'frank-ruhl-libre-hebrew-wght-normal.woff2', 'frank-ruhl-libre-500-hebrew.woff2', weight=500)
family('Frank Ruhl Libre', '500', 'frank-ruhl-libre-500-latin.woff2', h, 'frank-ruhl-libre-500-hebrew.woff2', BASIC)

p = V / 'playpen-sans-hebrew' / 'files'
make(p / 'playpen-sans-hebrew-latin-wght-normal.woff2', 'playpen-sans-hebrew-400-latin.woff2', weight=400, keep=BASIC,
     features=['kern', 'mark', 'mkmk', 'liga', 'ccmp', 'locl'])
h = make(p / 'playpen-sans-hebrew-hebrew-wght-normal.woff2', 'playpen-sans-hebrew-400-hebrew.woff2', weight=400)
family('Playpen Sans Hebrew', '400', 'playpen-sans-hebrew-400-latin.woff2', h, 'playpen-sans-hebrew-400-hebrew.woff2', BASIC)

make(S / 'ms-madi' / 'files' / 'ms-madi-latin-400-normal.woff2', 'ms-madi-latin.woff2')
faces.append(('Ms Madi', '400', 'ms-madi-latin.woff2', LATIN))

css = ['/* Fonts served from this site (no request to Google). Built by tools/site/make_fonts.py. Licences: fonts/LICENSES.txt */']
for fam, w, file, rng in faces:
    css.append(f'@font-face{{font-family:"{fam}";font-style:normal;font-weight:{w};font-display:swap;'
               f'src:url(fonts/{file}) format("woff2");unicode-range:{rng}}}')
(ROOT / 'assets' / 'fonts.css').write_text('\n'.join(css) + '\n', encoding='utf-8')

lic = ['Fonts in this folder, all under the SIL Open Font License, Version 1.1 (full text below).', '',
       'Assistant - Copyright 2020 The Assistant Project Authors (https://github.com/hafontia/Assistant).',
       "  Copyright 2010 The Source Sans Pro Authors (https://github.com/adobe-fonts/source-sans-pro), with Reserved Font Name 'Source'.",
       '  Files: unmodified subsets as distributed by Google Fonts / Fontsource.',
       'Frank Ruhl Libre - Copyright 2015 The Frank Ruhl Libre Project Authors (https://github.com/fontef/frankruhllibre).',
       '  Files: modified (weight 500 only; Latin file reduced to basic Latin).',
       'Playpen Sans Hebrew - Copyright 2023 The Playpen Sans Project Authors (https://github.com/TypeTogether/Playpen-Sans).',
       '  Files: modified (weight 400 only; Latin file reduced to basic Latin, without contextual alternates).',
       'Ms Madi - Copyright 2018 The Ms Madi Project Authors (https://github.com/googlefonts/ms-madi).',
       '  File: unmodified subset as distributed by Google Fonts / Fontsource.', '',
       '-' * 70, '']
ofl = (V / 'frank-ruhl-libre' / 'LICENSE').read_text(encoding='utf-8')
lic.append(ofl[ofl.index('This Font Software is licensed'):].strip())
(OUT / 'LICENSES.txt').write_text('\n'.join(lic) + '\n', encoding='utf-8')
print('wrote assets/fonts.css with', len(faces), 'faces')
