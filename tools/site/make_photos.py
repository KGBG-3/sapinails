"""Photos for the site: crop, resize, convert to sRGB, and drop all metadata (iPhone photos carry GPS).
Usage: python3 tools/site/make_photos.py <folder with the original photos> img [name ...]
       With names (for example: sapir w12) only those are made; without, everything is.
Needs: pip install pillow pillow-heif

Each photo is found by a part of its file name, so the originals can sit in one folder under any prefix.
"""
import io, sys, pathlib
from PIL import Image, ImageOps, ImageCms
import pillow_heif
pillow_heif.register_heif_opener()
SRC = pathlib.Path(sys.argv[1]); OUT = pathlib.Path(sys.argv[2]); OUT.mkdir(parents=True, exist_ok=True)
ONLY = set(sys.argv[3:])
SRGB = ImageCms.createProfile('sRGB')
GAL = (640, 1080)
# name, part of the source file name, aspect (w/h), focus, widths, [crop box before the aspect crop, as fractions x0,y0,x1,y1]
# focus: share of the spare height (or width) that is cut before the crop; 0 keeps the top/left, 1 the bottom/right
JOBS = [
    ('sapir', '144c3c74', 4 / 5, 0.35, (720, 1200)),          # Sapir's own hands, by the flowers ("היי, אני ספיר")
    ('w01', 'IMG_7948.HEIC', 1, 0.35, GAL),
    ('w02', 'IMG_7826.HEIC', 1, 0.9, GAL),
    ('w03', 'IMG_8953.HEIC', 3 / 4, 0.5, GAL),
    ('w04', 'IMG_8255.HEIC', 1, 0.3, GAL),
    ('w05', 'IMG_8203.HEIC', 1, 0.45, GAL),
    ('w06', 'IMG_8352.HEIC', 3 / 4, 0.5, GAL),
    ('w07', 'IMG_8114.HEIC', 3 / 4, 0.5, GAL),
    ('w08', 'IMG_8408.HEIC', 4 / 5, 0.4, GAL),
    ('w09', 'IMG_8369.HEIC', 3 / 4, 0.6, GAL),
    ('w10', 'FullSizeRender.HEIC', 4 / 5, 0.5, GAL),          # cream nails by the plant (was the "about" photo)
    ('w11', 'd61035a7', 1, 0.5, GAL, (0.08, 0.02, 1.0, 0.71)),  # Sapir's hand, white with a bow; crop leaves out the thumb
    ('w12', '365d3692', 3 / 4, 0.5, GAL),                     # pink with leopard print
    ('w13', '8d5fb4bb', 3 / 4, 0.45, GAL),                    # red French tips
]


def load(part):
    found = sorted(p for p in SRC.iterdir() if part.lower() in p.name.lower())
    if len(found) != 1:
        raise SystemExit(f'{part}: expected one source file, found {[p.name for p in found]}')
    im = Image.open(found[0])
    icc = im.info.get('icc_profile')
    im = ImageOps.exif_transpose(im)
    if im.mode != 'RGB': im = im.convert('RGB')
    if icc:
        im = ImageCms.profileToProfile(im, ImageCms.ImageCmsProfile(io.BytesIO(icc)), SRGB, outputMode='RGB')
    return im


for name, part, aspect, focus, widths, *rest in JOBS:
    if ONLY and name not in ONLY: continue
    im = load(part)
    if rest:
        x0, y0, x1, y1 = rest[0]
        im = im.crop((round(im.width * x0), round(im.height * y0), round(im.width * x1), round(im.height * y1)))
    w, h = im.size
    if w / h > aspect:   # too wide: cut the sides
        nw = round(h * aspect); x = round((w - nw) * focus); box = (x, 0, x + nw, h)
    else:                # too tall: cut top/bottom
        nh = round(w / aspect); y = round((h - nh) * focus); box = (0, y, w, y + nh)
    crop = im.crop(box)
    for tw in widths:
        th = round(tw / aspect)
        out = crop.resize((tw, th), Image.LANCZOS)
        p = OUT / f'{name}-{tw}.jpg'
        for q in (80, 72):   # busy photos (leaves, satin) get a slightly lower quality so they stay light on a phone
            out.save(p, 'JPEG', quality=q, optimize=True, progressive=True)  # no exif, no icc: plain sRGB
            if p.stat().st_size <= 250_000: break
        print(p.name, out.size, f'{p.stat().st_size // 1024}KB', f'q{q}')
