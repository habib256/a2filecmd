"""Self-contained release inventories and failure-safe Mini image generation."""
import fnmatch, re
import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import distribution as dist
import build_mini_disk as mini
from mkmini33 import build
import release_assets


class Distribution(unittest.TestCase):
    def test_five_explicit_images(self):
        self.assertEqual(dist.image_names('1.0.0'), [
            'A2FILECMD-XL-1.0.0.2mg', 'A2FILECMD-XL-65C02-enhanced-1.0.0.2mg',
            'A2FILECMD-DOS3.3-1.0.0.dsk', 'A2FILECMD-800K-1.0.0.po', 'A2FILECMD-140K-1.0.0.dsk'])
        with self.assertRaises(ValueError): dist.image_name('FILES')

    def test_essential_operations_are_self_contained(self):
        essential, complete = dist.inventories()
        self.assertTrue({'BATCH', 'NAV', 'CATALOG', 'OPEN', 'COPY', 'DELETE', 'MOVE',
                         'EDIT', 'ATTR', 'RUN', 'MENU', 'HELP', 'TEXT', 'HEX', 'COMPARE',
                         'FORMAT', 'VERIFY'} <= essential)
        self.assertTrue(essential < complete)
        self.assertNotIn('DISKIMG', essential)

    def test_release_uploads_exactly_the_five_image_patterns(self):
        workflow = (dist.ROOT / '.github/workflows/ci.yml').read_text()
        patterns = set(re.findall(r'^\s+(dist/A2FILECMD-\S+\.(?:dsk|po|2mg))$', workflow, re.M))
        # [0-9].* : a version opens with a digit and a period, so the 6502 XL's pattern
        # cannot also take A2FILECMD-XL-65C02-enhanced-*.2mg
        self.assertEqual(patterns, {'dist/' + n.replace(dist.VERSION, '[0-9].*') for n in dist.image_names()})
        for pattern in patterns:
            self.assertEqual(len(fnmatch.filter(['dist/' + n for n in dist.image_names()], pattern)), 1, pattern)
        self.assertIn('python3 tools/release_assets.py', workflow)

    def test_checksums_exclude_stale_or_legacy_images(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'dist').mkdir()
            names = dist.image_names() + [f'A2FILECMD-MANUAL-EN-{dist.VERSION}.pdf']
            for name in names + ['A2FILECMD-6502-FILES-old.dsk', 'personal.po']:
                (root / 'dist' / name).write_bytes(name.encode())
            with patch.object(release_assets, 'ROOT', root), contextlib.redirect_stdout(io.StringIO()):
                release_assets.main()
            manifest = root / 'dist' / f'SHA256SUMS-{dist.VERSION}.txt'
            self.assertEqual([line.split('  ')[1] for line in manifest.read_text().splitlines()], names)

    def test_malformed_template_and_input_alias_preserve_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            template = root / 'boot'; template.write_bytes(b'invalid boot tracks')
            binary = root / 'binary'; binary.write_bytes(b'\x60' * 2048)
            output = root / 'mini'; output.write_bytes(b'previous image')
            for target in (output, template, binary):
                result = subprocess.run([sys.executable, str(Path(mini.__file__)),
                    '--boot-template', str(template), '--binary', str(binary),
                    '--output', str(target)], capture_output=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(template.read_bytes(), b'invalid boot tracks')
                self.assertEqual(binary.read_bytes(), b'\x60' * 2048)
                self.assertEqual(output.read_bytes(), b'previous image')

    def test_template_build_is_deterministic_and_does_not_modify_inputs(self):
        template = (dist.ROOT / 'data/dos33_boot.tmpl').read_bytes()
        master = mini.from_template(template)
        before = bytes(master)
        output = build(master, b'\x60' * 2048)
        self.assertEqual(output[:12288], template)
        self.assertEqual(output, build(master, b'\x60' * 2048))
        self.assertEqual(bytes(master), before)
        for data in (b'', template[:-1], template + b'X'):
            with self.assertRaises(ValueError): mini.from_template(data)

    def test_failed_publication_preserves_previous_image_and_other_files(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            output = folder / 'mini.dsk'; output.write_bytes(b'previous image')
            unrelated = folder / '.mini-existing'; unrelated.write_bytes(b'keep')
            for failure in ('fsync', 'replace'):
                with patch.object(mini.os, failure, side_effect=OSError('injected failure')):
                    with self.assertRaises(OSError): mini.publish(output, b'new image')
                self.assertEqual(output.read_bytes(), b'previous image')
                self.assertEqual(unrelated.read_bytes(), b'keep')
                self.assertEqual(set(folder.iterdir()), {output, unrelated})
            mini.publish(output, b'verified image')
            self.assertEqual(output.read_bytes(), b'verified image')


if __name__ == '__main__':
    unittest.main()
