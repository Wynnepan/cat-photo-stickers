import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from argparse import Namespace
from pathlib import Path

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'skills/cat-photo-stickers/scripts/photo_stickers.py'
spec = importlib.util.spec_from_file_location('photo_stickers', SCRIPT)
pack = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pack)


class PhotoStickerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.photos = self.root / 'photos'
        self.photos.mkdir()
        self.font = next((p for p in [
            Path('/System/Library/Fonts/STHeiti Medium.ttc'),
            Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'),
        ] if p.is_file()), None)
        if self.font is None:
            self.skipTest('A local test font is required')
        self.items = []
        entries = []
        for i in range(16):
            path = self.photos / f'photo-{i:02d}.png'
            Image.new('RGB', (400, 600), (25 + i * 7, 85, 130)).save(path)
            entries.append({'id': f'{i+1:04d}', 'path': str(path), 'width': 400, 'height': 600})
            self.items.append({'id': f'{i+1:02d}', 'source': str(path), 'caption': f'Cat {i+1}',
                               'crop': [0, 100, 400, 500], 'text_box': [.05, .05, .95, .25],
                               'protected_regions': [[.25, .30, .75, .80]]})
        pack.save_json(self.root / 'catalog.json', {'photos': entries, 'skipped': []})
        self.manifest = self.root / 'manifest.json'
        self.args = Namespace(manifest=self.manifest, out=self.root / 'pack', count=16, size=512, font=self.font)

    def write(self):
        pack.save_json(self.manifest, {'catalog': 'catalog.json', 'items': self.items})

    def reject(self):
        self.write()
        with self.assertRaises((ValueError, OSError)):
            pack.build(self.args)
        self.assertFalse(self.args.out.exists())
        self.assertEqual(list(self.root.glob('.photo-sticker-stage-*')), [])

    def test_sixteen_sources_full_bleed_square_private_zip(self):
        self.write()
        pack.build(self.args)
        self.assertEqual(len(list((self.args.out / 'stickers').glob('*.png'))), 16)
        for i in range(16):
            with Image.open(self.args.out / f'stickers/{i+1:02d}.png') as image:
                self.assertEqual(image.size, (512, 512))
                for point in [(0, 0), (511, 0), (0, 511), (511, 511), (256, 511)]:
                    self.assertEqual(image.getpixel(point), (25 + i * 7, 85, 130))
        with zipfile.ZipFile(self.args.out / 'stickers.zip') as archive:
            self.assertEqual(len(archive.namelist()), 19)
            self.assertIn('cover.png', archive.namelist())
            self.assertIn('icon.png', archive.namelist())
            self.assertNotIn('source-map.json', archive.namelist())
            captions = archive.read('captions.json').decode()
            self.assertNotIn(str(self.root), captions)
            self.assertNotIn('source', captions)
        for name, size in [('cover.png', 1024), ('icon.png', 512)]:
            with Image.open(self.args.out / name) as image:
                self.assertEqual(image.format, 'PNG')
                self.assertEqual(image.size, (size, size))
        with Image.open(self.args.out / 'preview.png') as image:
            self.assertEqual(image.format, 'PNG')
        self.assertFalse((self.args.out / 'preview.jpg').exists())
        mapping = json.loads((self.args.out / 'source-map.json').read_text())
        self.assertEqual(len({row['source'] for row in mapping['items']}), 16)
        with self.assertRaises(ValueError):
            pack.build(self.args)

    def test_text_changes_only_pixels_inside_box(self):
        item = self.items[0]
        image = pack.render(Path(item['source']), item, 512, self.font)
        original = Image.new('RGB', image.size, (25, 85, 130))
        bounds = ImageChops.difference(image, original).getbbox()
        self.assertIsNotNone(bounds)
        self.assertGreaterEqual(bounds[0], round(.05 * 512))
        self.assertGreaterEqual(bounds[1], round(.05 * 512))
        self.assertLessEqual(bounds[2], round(.95 * 512))
        self.assertLessEqual(bounds[3], round(.25 * 512))
        self.assertEqual(ImageChops.difference(image.crop((130, 154, 384, 409)),
                                             original.crop((130, 154, 384, 409))).getbbox(), None)

    def test_plain_text_has_no_outline_or_shadow(self):
        for style in ['white', 'black']:
            item = copy.deepcopy(self.items[0])
            item['text_style'] = style
            image = pack.render(Path(item['source']), item, 512, self.font)
            original = Image.new('RGB', image.size, (25, 85, 130))
            clamped = ImageChops.darker(image, original) if style == 'white' else ImageChops.lighter(image, original)
            self.assertEqual(clamped.tobytes(), original.tobytes())

    def test_default_output_versions_and_reindex_excludes_results(self):
        self.write()
        self.args.out = None
        pack.build(self.args)
        first = self.photos / '表情包结果'
        self.assertEqual(len(list((first / 'stickers').glob('*.png'))), 16)
        self.assertTrue((first / '.cat-photo-stickers-output').is_file())
        # Working contact sheets and custom marked output must also be excluded.
        custom = self.photos / 'custom-export'
        custom.mkdir()
        (custom / '.cat-photo-stickers-output').touch()
        Image.new('RGB', (20, 20), 'yellow').save(custom / 'preview.jpg')
        work = self.photos / '.cat-photo-stickers'
        first_catalog = work / 'run-01/catalog'
        pack.catalog(Namespace(photos=self.photos, out=first_catalog))
        second_catalog = work / 'run-02/catalog'
        pack.catalog(Namespace(photos=self.photos, out=second_catalog))
        rows = json.loads((second_catalog / 'catalog.json').read_text())['photos']
        self.assertEqual(len(rows), 16)
        self.assertEqual({Path(row['path']).resolve() for row in rows}, {Path(item['source']).resolve() for item in self.items})
        pack.build(self.args)
        self.assertTrue((self.photos / '表情包结果-02/stickers.zip').is_file())
        self.assertTrue((first / 'stickers.zip').is_file())

    def test_icon_uses_selected_photo_without_caption(self):
        self.write()
        data = json.loads(self.manifest.read_text())
        data['icon'] = {'source': self.items[7]['source'], 'crop': [0, 0, 400, 400]}
        pack.save_json(self.manifest, data)
        jobs = pack.load_jobs(self.manifest, 16)
        image = pack.render_icon(self.manifest, jobs)
        self.assertEqual(image.size, (512, 512))
        self.assertEqual(image.getextrema(), ((74, 74), (85, 85), (130, 130)))

    def test_icon_rejects_outside_source_or_invalid_crop(self):
        self.write()
        data = json.loads(self.manifest.read_text())
        jobs = pack.load_jobs(self.manifest, 16)
        for icon in [
            {'source': str(self.root / 'outside.png'), 'crop': [0, 0, 100, 100]},
            {'source': self.items[0]['source'], 'crop': [0, 0, 400, 500]},
        ]:
            data['icon'] = icon
            pack.save_json(self.manifest, data)
            with self.assertRaises(ValueError):
                pack.render_icon(self.manifest, jobs)

    def test_duplicate_photo_path_rejected(self):
        self.items[1]['source'] = self.items[0]['source']
        self.reject()

    def test_identical_file_under_different_names_rejected(self):
        Path(self.items[1]['source']).write_bytes(Path(self.items[0]['source']).read_bytes())
        self.reject()

    def test_missing_photo_rejected(self):
        self.items.pop()
        self.reject()

    def test_substitution_outside_catalog_rejected(self):
        path = self.root / 'different.png'
        Image.new('RGB', (400, 600), 'yellow').save(path)
        self.items[1]['source'] = str(path)
        self.reject()

    def test_face_overlap_rejected(self):
        self.items[0]['text_box'] = [.1, .1, .9, .5]
        self.reject()

    def test_missing_face_region_rejected(self):
        self.items[0]['protected_regions'] = []
        self.reject()

    def test_non_square_out_of_bounds_and_nan_rejected(self):
        for crop in [[0, 0, 400, 500], [0, 300, 400, 700], [0, 0, float('nan'), 400]]:
            self.items[0]['crop'] = crop
            self.reject()

    def test_no_text_or_overflow_rejected(self):
        for text in ['', 'long caption ' * 20]:
            self.items[0]['caption'] = text
            self.reject()

    def test_skipped_catalog_photo_rejected(self):
        data = json.loads((self.root / 'catalog.json').read_text())
        data['skipped'] = [{'path': 'broken.jpg'}]
        pack.save_json(self.root / 'catalog.json', data)
        self.reject()

    def test_orientation_index_and_render_agree(self):
        photos = self.root / 'rotated-input'
        photos.mkdir()
        photo = Image.new('RGB', (40, 80), 'blue')
        exif = photo.getexif()
        exif[274] = 6
        photo.save(photos / 'rotated.jpg', exif=exif)
        pack.catalog(Namespace(photos=photos, out=self.root / 'rotated-catalog'))
        row = json.loads((self.root / 'rotated-catalog/catalog.json').read_text())['photos'][0]
        self.assertEqual((row['width'], row['height']), (80, 40))
        item = copy.deepcopy(self.items[0])
        item['crop'] = [40, 0, 80, 40]
        image = pack.render(photos / 'rotated.jpg', item, 512, self.font)
        self.assertEqual(image.size, (512, 512))

    def test_duplicate_identifier_rejected(self):
        self.items[1]['id'] = self.items[0]['id']
        self.reject()

    def test_installer_refuses_overwrite(self):
        command = [sys.executable, str(ROOT / 'install.py'), '--skills-dir', str(self.root / 'skills')]
        first = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        marker = self.root / 'skills/cat-photo-stickers/marker.txt'
        marker.write_text('keep')
        self.assertEqual(subprocess.run(command, capture_output=True).returncode, 2)
        self.assertEqual(marker.read_text(), 'keep')


if __name__ == '__main__':
    unittest.main()
