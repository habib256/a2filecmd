"""Category completeness and the real disk-prompt lookup, including bad catalogs."""
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from disk_packages import ROOT, PACKAGES, assignments


class Distribution(unittest.TestCase):
    def test_every_overlay_has_exactly_one_location(self):
        makefile = (ROOT / 'Makefile').read_text()
        native = re.search(r'^PLUGINS = (.+)$', makefile, re.M)[1].split()
        plugins = [p.stem for p in (ROOT / 'src/plugins').glob('*.c')]
        locations = assignments(native, plugins)
        self.assertEqual(set(locations), set(native) | {n.upper() for n in plugins})
        self.assertEqual(locations['COPY'], 'BOOT')
        self.assertEqual(locations['BOOTBLK'], 'DISKTOOLS')
        with patch.dict(PACKAGES, FILES=PACKAGES['FILES'] + ['BOOTBLK']):
            with self.assertRaises(ValueError):
                assignments(native, plugins)
        with self.assertRaises(ValueError):
            assignments(native, plugins + ['new_tool_needing_a_category'])


class DiskPrompt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='package-prompt-')
        cls.root = Path(cls.tmp.name)
        source = (ROOT / 'src/a2fc.c').read_text()
        routine = source[source.index('static unsigned char ask_disk('):source.index('/* Local overlays take precedence.')]
        harness = r'''
#include <stdio.h>
#include <string.h>
static unsigned char copy_buf[512];
static struct { char text[64]; unsigned char guard[16]; } message;
#define question message.text
static char other_full[1024];
static const char *local_path, *companion;
static void a2file_file(const char* n) { (void)n; strcpy(other_full, local_path); }
static unsigned char companion_path(const char* n) {
    (void)n; strcpy(other_full, companion); return 1;
}
static unsigned char disk_question(const char* n) { (void)n; puts(question); return 1; }
''' + routine + r'''
int main(int argc, char** argv) {
    unsigned int i;
    local_path = argv[1]; companion = argv[2];
    memset(message.guard, 0xA5, sizeof message.guard);
    ask_disk(argv[3]);
    for (i = 0; i < sizeof message.guard; ++i) if (message.guard[i] != 0xA5) return 2;
    return 0;
}
'''
        (cls.root / 'test.c').write_text(harness)
        cls.exe = cls.root / 'test'
        subprocess.run(['cc', '-std=c99', str(cls.root / 'test.c'), '-o', str(cls.exe)],
                       check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def prompt(self, data, name='EDIT', companion=False):
        path = self.root / 'catalog'
        path.write_bytes(data)
        absent = self.root / 'absent'
        paths = (absent, path) if companion else (path, absent)
        return subprocess.check_output([str(self.exe), *map(str, paths), name], text=True).strip()

    @staticmethod
    def record(name, text):
        return name.encode().ljust(12, b'\0') + text.encode().ljust(66, b'\0')

    def test_named_category_from_boot_or_swapped_companion(self):
        data = self.record('IMAGE', 'A2MEDIA6502: Image') + self.record('EDIT', 'A2FILES6502: Edit')
        for companion in (False, True):
            self.assertEqual(self.prompt(data, companion=companion), 'A2FILES6502')
            self.assertEqual(self.prompt(data, 'IMAGE', companion), 'A2MEDIA6502')

    def test_basic_runtime_and_hidden_copy_route(self):
        data = self.record('BASIC.SYSTEM', 'A2DEVTOOLS6502: BASIC')
        self.assertEqual(self.prompt(data, 'BASIC.SYSTEM'), 'A2DEVTOOLS6502')
        data = bytearray(self.record('COPY', 'A2FC6502: Internal'))
        data[11] = 1
        self.assertEqual(self.prompt(data, 'COPY'), 'A2FC6502')

    def test_short_unknown_and_malformed_catalogs_use_generic_prompt(self):
        for text in (': empty', 'No volume delimiter', 'X' * 64 + ':', 'A' * 16 + ': too long'):
            with self.subTest(text=text):
                self.assertEqual(self.prompt(self.record('EDIT', text)), 'tool disk')
        self.assertEqual(self.prompt(self.record('EDIT', 'A2FILES6502: Edit')[:-1]), 'tool disk')
        self.assertEqual(self.prompt(self.record('IMAGE', 'A2MEDIA6502: Image')), 'tool disk')
        self.assertEqual(self.prompt(b''), 'tool disk')


if __name__ == '__main__':
    unittest.main()
