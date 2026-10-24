"""Gallery photos for the site: crop, resize, convert to sRGB, and drop all metadata (iPhone photos carry GPS).
Usage: python3 tools/site/make_photos.py <folder with the HEIC files> img
Needs: pip install pillow pillow-heif"""
import io, sys, pathlib
from PIL import Image, ImageOps, ImageCms
import pillow_heif
pillow_heif.register_heif_opener()
SRC = pathlib.Path(sys.argv[1]); OUT = pathlib.Path(sys.argv[2]); OUT.mkdir(parents=True, exist_ok=True)
SRGB = ImageCms.createProfile('sRGB')
# name, source, aspect (w/h), focus: fraction of the spare height (portrait) or width (landscape) cut before the crop
JOBS = [
    ('about', 'FullSizeRender', 4 / 5, 0.5, (720, 1200)),
    ('w01', 'IMG_7948', 1, 0.35, (640, 1080)),
    ('w02', 'IMG_7826', 1, 0.9, (640, 1080)),
    ('w03', 'IMG_8953', 3 / 4, 0.5, (640, 1080)),
    ('w04', 'IMG_8255', 1, 0.3, (640, 1080)),
    ('w05', 'IMG_8203', 1, 0.45, (640, 1080)),
    ('w06', 'IMG_8352', 3 / 4, 0.5, (640, 1080)),
    ('w07', 'IMG_8114', 3 / 4, 0.5, (640, 1080)),
    ('w08', 'IMG_8408', 4 / 5, 0.4, (640, 1080)),
    ('w09', 'IMG_8369', 3 / 4, 0.6, (640, 1080)),
]
def load(stem):
    f = next(SRC.glob(f'*-{stem}.HEIC'))
    im = Image.open(f)
    icc = im.info.get('icc_profile')
    im = ImageOps.exif_transpose(im)
    if im.mode != 'RGB': im = im.convert('RGB')
    if icc:
        im = ImageCms.profileToProfile(im, ImageCms.ImageCmsProfile(io.BytesIO(icc)), SRGB, outputMode='RGB')
    return im, bool(icc)
for name, stem, aspect, focus, widths in JOBS:
    im, had_icc = load(stem)
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
        out.save(p, 'JPEG', quality=80, optimize=True, progressive=True)  # no exif, no icc: plain sRGB
        print(p.name, out.size, f'{p.stat().st_size // 1024}KB', 'icc->srgb' if had_icc else 'no-icc')
