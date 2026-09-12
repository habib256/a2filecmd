"""Release metadata must describe the version and overlays actually shipped."""
import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import release_notes as notes
import check_images


class ReleaseNotes(unittest.TestCase):
    def test_launcher_must_display_release_version(self):
        check_images.check_launch_version(('A2 FILE CMD ' + notes.build_version() + ' - 6502').encode())
        for program in (b'', b'A2 FILE CMD 0.6.8 - 6502',
                        ('A2 FILE CMD ' + notes.build_version() + '1 - 6502').encode()):
            with self.subTest(program=program), self.assertRaises(AssertionError):
                check_images.check_launch_version(program)

    def test_current_tag_is_accepted(self):
        notes.check_tag('v' + notes.build_version())

    def test_wrong_or_malformed_tag_is_rejected(self):
        for tag in ('v999.0.0', 'main', 'vv' + notes.build_version(), notes.build_version()):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                notes.check_tag(tag)

    def test_cli_failure_has_no_publishable_notes(self):
        result = subprocess.run([sys.executable, notes.__file__, '--check-tag', 'v999.0.0'],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '')
        self.assertIn('does not match', result.stderr)

    def test_cli_requires_tag(self):
        result = subprocess.run([sys.executable, notes.__file__, '--check-tag'],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Usage:', result.stderr)

    def test_current_notes_list_all_shipped_overlays(self):
        result = subprocess.check_output([sys.executable, notes.__file__, 'main'], text=True)
        # Current distribution inventory, independently checked by check_images.py.
        self.assertIn('XL includes all 60 overlays', result)
        self.assertIn('A2FILECMD-6502-BOOT-%s.dsk' % notes.build_version(), result)
        self.assertNotIn('{overlays}', result)

    def render_fixture(self, ref):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'Makefile').write_text('A2FC_VERSION = 0.8.0\n')
            (root / 'CHANGELOG.md').write_text('## Unreleased\n\n## [0.7.5]\nOld changes.\n')
            output = io.StringIO()
            with patch.object(notes, 'ROOT', root), patch.object(notes, 'overlay_count', return_value=59), \
                    patch.object(sys, 'argv', ['release_notes.py', ref]), contextlib.redirect_stdout(output):
                self.assertEqual(notes.main(), 0)
            return output.getvalue()

    def test_empty_unreleased_keeps_current_asset_version_on_branch(self):
        result = self.render_fixture('main')
        self.assertIn('A2FILECMD-6502-BOOT-0.8.0.dsk', result)
        self.assertNotIn('BOOT-0.7.5.dsk', result)

    def test_historical_notes_can_still_be_generated_explicitly(self):
        result = self.render_fixture('v0.7.5')
        self.assertIn('A2FILECMD-6502-BOOT-0.7.5.dsk', result)
        self.assertIn('Old changes.', result)


if __name__ == '__main__':
    unittest.main()
