#!/usr/bin/env python3
"""Local photo-to-sticker exporter: one input per output, full-bleed square photos."""
import argparse
import hashlib
import json
import math
import os
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError

EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff'}


def read_image(path):
    with Image.open(path) as image:
        return ImageOps.exif_transpose(image).convert('RGBA')


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def preview(images, labels, target, tile=224, columns=4):
    rows = math.ceil(len(images) / columns)
    sheet = Image.new('RGB', (columns * tile, rows * (tile + 26)), '#ededed')
    draw = ImageDraw.Draw(sheet)
    for i, (image, label) in enumerate(zip(images, labels)):
        thumb = ImageOps.contain(image, (tile - 16, tile - 16), Image.Resampling.LANCZOS)
        x = (i % columns) * tile + (tile - thumb.width) // 2
        y = (i // columns) * (tile + 26) + (tile - thumb.height) // 2
        sheet.paste(thumb, (x, y), thumb if thumb.mode == 'RGBA' else None)
        draw.text(((i % columns) * tile + 8, (i // columns) * (tile + 26) + tile),
                  label, fill='black', font=ImageFont.load_default())
    sheet.save(target, quality=92)


def catalog(args):
    root, out = args.photos.resolve(), args.out.resolve()
    if not root.is_dir():
        raise ValueError('Photos directory does not exist')
    if out == root or out in root.parents:
        raise ValueError('Catalog output cannot equal or contain the input photos directory')
    paths = []
    for directory, folders, filenames in os.walk(root, followlinks=False):
        current = Path(directory)
        folders[:] = sorted(name for name in folders if not (
            name.startswith('.') or name == '表情包结果' or name.startswith('表情包结果-')
            or (current / name).resolve() == out
            or (current / name / '.cat-photo-stickers-output').is_file()))
        paths.extend(current / name for name in filenames
                     if Path(name).suffix.lower() in EXTENSIONS and (current / name).is_file())
    paths.sort()
    entries, thumbnails, skipped = [], [], []
    for path in paths:
        try:
            image = read_image(path)
        except (OSError, UnidentifiedImageError) as error:
            skipped.append({'path': str(path), 'error': str(error)})
            print('Skipping unreadable image: ' + str(path), file=sys.stderr)
            continue
        identifier = f'{len(entries) + 1:04d}'
        entries.append({'id': identifier, 'path': str(path), 'width': image.width, 'height': image.height})
        thumbnails.append(ImageOps.contain(image, (208, 208), Image.Resampling.LANCZOS))
    if not entries:
        raise ValueError('No readable supported photos found; convert HEIC/RAW to PNG/JPEG first')
    out.mkdir(parents=True, exist_ok=False)
    for start in range(0, len(entries), 64):
        preview(thumbnails[start:start + 64], [e['id'] for e in entries[start:start + 64]],
                out / f'contact-{start // 64 + 1:02d}.jpg', columns=8)
    save_json(out / 'catalog.json', {'photos_root': str(root), 'photos': entries, 'skipped': skipped})
    print(f'Indexed {len(entries)} photos: {out}')


def wrap_text(text, font, width, stroke):
    lines = []
    for paragraph in text.split('\n'):
        current = ''
        for character in paragraph:
            candidate = current + character
            box = font.getbbox(candidate, stroke_width=stroke)
            if box[2] - box[0] > width:
                if not current:
                    return None
                lines.append(current)
                current = character
            else:
                current = candidate
        lines.append(current)
    return lines


def rectangle(value, name, normalized=False):
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError(name + ' must be a four-number list [left, top, right, bottom]')
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in value):
        raise ValueError(name + ' must contain finite numbers')
    left, top, right, bottom = value
    if left < 0 or top < 0 or right <= left or bottom <= top:
        raise ValueError(name + ' has invalid bounds')
    if normalized and (right > 1 or bottom > 1):
        raise ValueError(name + ' must use normalized coordinates in [0, 1]')
    return value


def intersects(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def caption_layout(text, font_path, size, width, height, stroke=0):
    if not text.strip() or len(text) > 80:
        raise ValueError('Caption must be nonempty and at most 80 characters')
    for points in range(max(14, round(size * .12)), max(12, round(size * .045)) - 1, -1):
        font = ImageFont.truetype(str(font_path), points)
        lines = wrap_text(text, font, width - 2 * stroke, stroke)
        if lines is None:
            continue
        boxes = [font.getbbox(line or ' ', stroke_width=stroke) for line in lines]
        heights = [b[3] - b[1] for b in boxes]
        gap = max(3, points // 7)
        if sum(heights) + gap * (len(lines) - 1) <= height and len(lines) <= 3:
            return font, lines, boxes, heights, gap, stroke
    raise ValueError('Caption cannot fit legibly inside text_box; shorten text or choose a larger safe area')


def render(source, item, size, font_path):
    image = read_image(source)
    crop = rectangle(item.get('crop'), 'crop')
    if any(int(v) != v for v in crop):
        raise ValueError('crop must contain integer pixels in EXIF-corrected source coordinates')
    left, top, right, bottom = map(int, crop)
    if right > image.width or bottom > image.height or right - left != bottom - top:
        raise ValueError('crop must be square and entirely inside the oriented source photo')
    text_box = rectangle(item.get('text_box'), 'text_box', normalized=True)
    if min(text_box[0], text_box[1]) < .025 or max(text_box[2], text_box[3]) > .975:
        raise ValueError('text_box must leave at least 2.5% margin from the photo edges')
    protected = item.get('protected_regions')
    if not isinstance(protected, list) or not protected:
        raise ValueError('protected_regions must include at least the visible face region after cropping')
    for region in protected:
        rectangle(region, 'protected region', normalized=True)
        if intersects(text_box, region):
            raise ValueError('text_box overlaps a protected face/action region; move it before exporting')
    # Square crop fills every pixel. No border, padding or separate caption panel.
    square = image.crop((left, top, right, bottom)).resize((size, size), Image.Resampling.LANCZOS)
    canvas = Image.new('RGBA', (size, size), 'white')
    canvas.alpha_composite(square)
    box = [round(v * size) for v in text_box]
    style = item.get('text_style', 'white')
    stroke_width = max(2, round(size * .007)) if style in ('white-black', 'black-white') else 0
    font, lines, boxes, heights, gap, stroke = caption_layout(
        item['caption'], font_path, size, box[2] - box[0], box[3] - box[1], stroke_width)
    draw = ImageDraw.Draw(canvas)
    y = box[1] + ((box[3] - box[1]) - sum(heights) - gap * (len(lines) - 1)) // 2
    ink = 'white' if style in ('white', 'white-black') else 'black'
    outline = 'black' if style == 'white-black' else 'white'
    for line, bounds, height in zip(lines, boxes, heights):
        x = box[0] + ((box[2] - box[0]) - (bounds[2] - bounds[0])) // 2 - bounds[0]
        draw.text((x, y - bounds[1]), line, font=font, fill=ink, stroke_width=stroke, stroke_fill=outline)
        y += height + gap
    return canvas.convert('RGB')


def load_jobs(manifest, expected):
    data = json.loads(manifest.read_text(encoding='utf-8'))
    items = data.get('items') if isinstance(data, dict) else None
    if not isinstance(items, list) or len(items) != expected:
        raise ValueError(f'Manifest must contain exactly {expected} items')
    catalog_path = data.get('catalog')
    if not isinstance(catalog_path, str) or not catalog_path:
        raise ValueError('catalog must point to the full folder catalog.json created by index')
    catalog_file = (manifest.parent / catalog_path).resolve()
    catalog_data = json.loads(catalog_file.read_text(encoding='utf-8'))
    if not isinstance(catalog_data, dict) or not isinstance(catalog_data.get('photos'), list):
        raise ValueError('Invalid catalog: run index first')
    if catalog_data.get('skipped'):
        raise ValueError('Catalog contains unreadable photos; resolve them and re-index before exporting')
    entries = catalog_data['photos']
    catalog_sources = [Path(entry['path']).resolve() for entry in entries]
    if len(entries) != expected or len(set(catalog_sources)) != expected:
        raise ValueError(f'Catalog must contain exactly {expected} unique source paths; no selection or omission')
    jobs, ids, sources, hashes = [], set(), set(), set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError('Each manifest item must be an object')
        identifier = item.get('id')
        if not isinstance(identifier, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', identifier):
            raise ValueError('id must contain 1–64 letters, digits, hyphens or underscores')
        if identifier.casefold() in ids:
            raise ValueError('Duplicate id: ' + identifier)
        ids.add(identifier.casefold())
        source = item.get('source')
        if not isinstance(source, str) or not source:
            raise ValueError('Each source must be a nonempty path string')
        path = (manifest.parent / source).resolve()
        if path in sources:
            raise ValueError('Each photo must be used exactly once; duplicate source: ' + str(path))
        sources.add(path)
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
        if digest.digest() in hashes:
            raise ValueError('Identical source files found; resolve duplicate photos before exporting')
        hashes.add(digest.digest())
        if not isinstance(item.get('caption'), str):
            raise ValueError('caption must be a string')
        if item.get('text_style', 'white') not in ('white', 'black', 'white-black', 'black-white'):
            raise ValueError('text_style must be white, black, white-black or black-white')
        jobs.append((path, item))
    if sources != set(catalog_sources):
        raise ValueError('Manifest sources must match the entire catalog one-to-one')
    return jobs


def square_cover(images, size=1024):
    columns = math.ceil(math.sqrt(len(images)))
    cover = Image.new('RGB', (size, size), 'white')
    for index, image in enumerate(images):
        column, row = index % columns, index // columns
        left, top = column * size // columns, row * size // columns
        right, bottom = (column + 1) * size // columns, (row + 1) * size // columns
        cover.paste(image.resize((right - left, bottom - top), Image.Resampling.LANCZOS), (left, top))
    return cover


def render_icon(manifest, jobs, size=512):
    data = json.loads(manifest.read_text(encoding='utf-8'))
    specification = data.get('icon')
    if specification is None:
        source, first = jobs[0]
        crop = first['crop']
    else:
        if not isinstance(specification, dict) or not isinstance(specification.get('source'), str):
            raise ValueError('icon must contain source and crop')
        source = (manifest.parent / specification['source']).resolve()
        if source not in {path for path, _ in jobs}:
            raise ValueError('icon source must be one of the input photos in this pack')
        crop = specification.get('crop')
    crop = rectangle(crop, 'icon crop')
    if any(int(v) != v for v in crop):
        raise ValueError('icon crop must use integer pixels')
    left, top, right, bottom = map(int, crop)
    image = read_image(source)
    if right - left != bottom - top or right > image.width or bottom > image.height:
        raise ValueError('icon crop must be square and inside the oriented source photo')
    canvas = Image.new('RGBA', (size, size), 'white')
    canvas.alpha_composite(image.crop((left, top, right, bottom)).resize((size, size), Image.Resampling.LANCZOS))
    return canvas.convert('RGB')


def default_output(manifest, jobs):
    data = json.loads(manifest.read_text(encoding='utf-8'))
    catalog_file = (manifest.parent / data['catalog']).resolve()
    catalog_data = json.loads(catalog_file.read_text(encoding='utf-8'))
    root = Path(catalog_data.get('photos_root') or os.path.commonpath([str(path.parent) for path, _ in jobs]))
    destination = root / '表情包结果'
    version = 2
    while destination.exists():
        destination = root / f'表情包结果-{version:02d}'
        version += 1
    return destination.resolve()


def build(args):
    if not 128 <= args.size <= 2048 or not 1 <= args.count <= 128:
        raise ValueError('size must be 128–2048 and count must be 1–128')
    if args.font is None or not args.font.is_file():
        raise ValueError('--font must point to a local font supporting all caption characters')
    jobs = load_jobs(args.manifest.resolve(), args.count)
    out = args.out.resolve() if args.out is not None else default_output(args.manifest.resolve(), jobs)
    if out.exists():
        raise ValueError('Output already exists; choose a new directory')
    out.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.photo-sticker-stage-', dir=out.parent))
    try:
        (stage / '.cat-photo-stickers-output').write_text('cat-photo-stickers output\n', encoding='utf-8')
        (stage / 'stickers').mkdir()
        summaries, thumbs, finals = [], [], []
        for path, item in jobs:
            image = render(path, item, args.size, args.font)
            image.save(stage / 'stickers' / (item['id'] + '.png'), format='PNG')
            finals.append(image)
            thumbs.append(ImageOps.contain(image, (208, 208), Image.Resampling.LANCZOS))
            summaries.append({'id': item['id'], 'caption': item['caption']})
        save_json(stage / 'captions.json', {'items': summaries})
        # This private report is intentionally outside the shared ZIP.
        save_json(stage / 'source-map.json', {'items': [
            {'id': item['id'], 'source': str(path), 'crop': item['crop'], 'text_box': item['text_box'],
             'protected_regions': item['protected_regions']} for path, item in jobs]})
        preview(thumbs, [item['id'] for _, item in jobs], stage / 'preview.png')
        square_cover(finals).save(stage / 'cover.png', format='PNG')
        render_icon(args.manifest.resolve(), jobs).save(stage / 'icon.png', format='PNG')
        with zipfile.ZipFile(stage / 'stickers.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
            for path in sorted((stage / 'stickers').iterdir()):
                archive.write(path, 'stickers/' + path.name)
            for name in ['cover.png', 'icon.png', 'captions.json']:
                archive.write(stage / name, name)
        stage.rename(out)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    print(f'Exported {len(jobs)} square photo stickers: {out}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    index = sub.add_parser('index', help='Catalog all photos in a local folder')
    index.add_argument('--photos', type=Path, required=True)
    index.add_argument('--out', type=Path, required=True)
    index.set_defaults(func=catalog)
    pack = sub.add_parser('build', help='Crop each photo square and overlay its caption inside')
    pack.add_argument('--manifest', type=Path, required=True)
    pack.add_argument('--out', type=Path, help='Optional output override; default is INPUT/表情包结果 (versioned if present)')
    pack.add_argument('--font', type=Path, required=True)
    pack.add_argument('--count', type=int, default=16)
    pack.add_argument('--size', type=int, default=512)
    pack.set_defaults(func=build)
    args = parser.parse_args()
    try:
        args.func(args)
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(2, f'Error: {error}\n')


if __name__ == '__main__':
    main()
