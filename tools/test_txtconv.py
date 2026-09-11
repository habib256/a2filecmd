"""Run TXTCONV's entry point with file I/O failures, checking source survival."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from test_six_plugins import PREFIX, ROOT

HARNESS = PREFIX + r'''
#include <errno.h>
#include "src/plugins/txtconv.c"
static unsigned char fault;
static char operation;
static unsigned char inplace_answer, overwrite_answer, questions;
static unsigned long fail_at;
static char key(void) { return operation; }
static unsigned char yes(const char* s) { (void)s; return questions++ ? overwrite_answer : inplace_answer; }
static FILE* open_file(const char* path, const char* mode) {
    if (fault == 4 && strstr(path, "/D/") && !strcmp(mode, "rb")) return NULL;
    return fopen(path, mode);
}
static void message(const char* s) { (void)s; }
static void progress(const char* s, unsigned long d, unsigned long t)
{ (void)s; (void)d; (void)t; }
static size_t read_file(void* p, size_t size, size_t count, FILE* f) {
    if (fault == 1 && (unsigned long)ftell(f) >= fail_at) return 0;
    if (fault == 2 && (unsigned long)ftell(f) >= fail_at) count /= 2;
    return fread(p, size, count, f);
}
static unsigned char mli(unsigned char cmd, void* p) {
    char from[128], to[128];
    if (cmd == 0xC4) {
        struct InfoPath { unsigned char n; unsigned char* path; };
        struct InfoPath* i = p;
        FILE* f;
        if (fault == 3) return 0x27;
        memcpy(from, i->path + 1, i->path[0]); from[i->path[0]] = 0;
        f = fopen(from, "rb");
        if (!f) return errno == ENOENT ? 0x46 : 0x27;
        fclose(f); return 0;
    }
    if (cmd == 0xC0) {
        struct CreatePath { unsigned char n; unsigned char* path; };
        struct CreatePath* c = p;
        FILE* f;
        memcpy(from, c->path + 1, c->path[0]); from[c->path[0]] = 0;
        if (fault == 5) {
            f = fopen(from, "wb"); fputs("arrived after lookup", f); fclose(f);
        }
        f = fopen(from, "wx");
        if (!f) return errno == EEXIST ? 0x47 : 0x27;
        return fclose(f) ? 0x27 : 0;
    }
    if (cmd != 0xC2) return 1;
    memcpy(from, rp.old + 1, rp.old[0]); from[rp.old[0]] = 0;
    memcpy(to, rp.new_ + 1, rp.new_[0]); to[rp.new_[0]] = 0;
    return rename(from, to) ? 0x27 : 0;
}
int main(int argc, char** argv) {
    static struct A2fcApi api;
    static struct Panel panels[2];
    static struct Entry selected;
    static unsigned char active, copy[512], filetype;
    static unsigned int aux;
    static char full[128], other_full[128], note[80], reselect[17];
    strcpy(panels[0].path, argv[1]);
    sprintf(panels[1].path, "%s/D", argv[1]);
    strcpy(selected.name, argv[2]); selected.type = 4;
    selected.size = strtoul(argv[3], 0, 10);
    fault = atoi(argv[4]); fail_at = strtoul(argv[5], 0, 10);
    operation = argv[6][0];
    inplace_answer = atoi(argv[7]);
    overwrite_answer = atoi(argv[8]);
    sprintf(full, "%s/%s", argv[1], argv[2]);
    api.panels = panels; api.active = &active; api.selected = &selected;
    api.full = full; api.other_full = other_full; api.copy_buf = copy;
    api.note = note; api.reselect = reselect; api.filetype = &filetype; api.auxtype = &aux;
    api.memcpy = memcpy; api.strcpy = strcpy; api.strcmp = strcmp;
    api.strlen = strlen; api.sprintf = sprintf;
    api.fopen = open_file; api.fread = read_file; api.fwrite = fwrite;
    api.fclose = fclose; api.remove = remove; api.mli = mli;
    api.cgetc = key; api.confirm = yes; api.message = message; api.progress_bar = progress;
    plugin_entry(&api);
    puts(note);
    return 0;
}
'''


class Txtconv(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='txtconv-', dir='/tmp')
        cls.root = Path(cls.tmp.name)
        source = cls.root / 'test.c'
        source.write_text(HARNESS)
        cls.exe = cls.root / 'test'
        subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-I', str(ROOT),
                        str(source), '-o', str(cls.exe)], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def convert(self, payload, fault=0, fail_at=0, cached_size=None, name='TEXT', mode='H', inplace=True, overwrite=False):
        source = self.root / name
        source.write_bytes(payload)
        result = subprocess.check_output(
            [str(self.exe), str(self.root), name,
             str(len(payload) if cached_size is None else cached_size),
             str(fault), str(fail_at), mode, str(int(inplace)), str(int(overwrite))], text=True).strip()
        return result, source.read_bytes()

    def test_unreadable_destination_still_requires_overwrite_confirmation(self):
        dest = self.root / 'D' / 'TEXT'
        dest.parent.mkdir(exist_ok=True)
        dest.write_bytes(b'existing destination')
        self.addCleanup(dest.unlink, missing_ok=True)
        note, source = self.convert(b'\xC1' * 400, fault=4, inplace=False)
        self.assertNotIn('Converted', note)  # overwrite confirmation was declined
        self.assertEqual(dest.read_bytes(), b'existing destination')
        self.assertEqual(source, b'\xC1' * 400)

    def test_destination_metadata_error_refuses_conversion(self):
        dest = self.root / 'D' / 'TEXT'
        dest.parent.mkdir(exist_ok=True)
        self.addCleanup(dest.unlink, missing_ok=True)
        note, source = self.convert(b'\xC1' * 400, fault=3, inplace=False)
        self.assertIn('Destination check failed', note)
        self.assertEqual(source, b'\xC1' * 400)
        self.assertFalse(dest.exists())

    def test_conversion_to_a_new_destination(self):
        dest = self.root / 'D' / 'TEXT'
        dest.parent.mkdir(exist_ok=True)
        self.addCleanup(dest.unlink, missing_ok=True)
        note, source = self.convert(b'\xC1' * 400, inplace=False)
        self.assertIn('Converted', note)
        self.assertEqual(source, b'\xC1' * 400)
        self.assertEqual(dest.read_bytes(), b'A' * 400)

    def test_confirmed_overwrite_still_converts(self):
        dest = self.root / 'D' / 'TEXT'
        dest.parent.mkdir(exist_ok=True)
        dest.write_bytes(b'old output')
        self.addCleanup(dest.unlink, missing_ok=True)
        note, source = self.convert(b'\xC1' * 400, inplace=False, overwrite=True)
        self.assertIn('Converted', note)
        self.assertEqual(source, b'\xC1' * 400)
        self.assertEqual(dest.read_bytes(), b'A' * 400)

    def test_destination_appearing_after_lookup_is_preserved(self):
        dest = self.root / 'D' / 'TEXT'
        dest.parent.mkdir(exist_ok=True)
        self.addCleanup(dest.unlink, missing_ok=True)
        note, source = self.convert(b'\xC1' * 400, fault=5, inplace=False)
        self.assertIn('Destination already exists', note)
        self.assertEqual(source, b'\xC1' * 400)
        self.assertEqual(dest.read_bytes(), b'arrived after lookup')

    def test_existing_temporary_file_is_preserved(self):
        temporary = self.root / 'TXTCONV.TMP'
        temporary.write_bytes(b'previous conversion to recover')
        self.addCleanup(temporary.unlink, missing_ok=True)
        note, data = self.convert(b'\xC1' * 400)
        self.assertIn('TXTCONV.TMP already exists', note)
        self.assertEqual(data, b'\xC1' * 400)
        self.assertEqual(temporary.read_bytes(), b'previous conversion to recover')

    def test_the_source_cannot_be_its_own_temporary_file(self):
        self.addCleanup((self.root / 'TXTCONV.TMP').unlink, missing_ok=True)
        note, data = self.convert(b'\xC1' * 400, name='TXTCONV.TMP')
        self.assertIn('TXTCONV.TMP already exists', note)
        self.assertEqual(data, b'\xC1' * 400)

    def test_success_including_empty_and_exact_chunk_boundary(self):
        for size in (0, 255, 256, 257, 512, 800):
            with self.subTest(size=size):
                note, data = self.convert(b'\xC1' * size)
                self.assertIn('Converted', note)
                self.assertEqual(data, b'A' * size)
                self.assertFalse((self.root / 'TXTCONV.TMP').exists())

    def test_read_failure_keeps_the_original(self):
        payload = b'\xC1' * 800
        for fault, offset in ((1, 0), (1, 256), (1, 512), (2, 256)):
            with self.subTest(fault=fault, offset=offset):
                note, data = self.convert(payload, fault, offset)
                self.assertIn('Read failed', note)
                self.assertEqual(data, payload)
                self.assertFalse((self.root / 'TXTCONV.TMP').exists())

    def test_changed_source_size_keeps_the_original(self):
        for cached in (0, 256, 801):
            with self.subTest(cached=cached):
                payload = b'\xC1' * 800
                note, data = self.convert(payload, cached_size=cached)
                self.assertIn('Read failed', note)
                self.assertEqual(data, payload)

    def test_accents_do_not_consume_text_after_a_broken_sequence(self):
        cases = ((b'a\xc3Z', b'a?Z'), (b'a\xe2Xb', b'a?Xb'),
                 (b'a\xf0\x9fZ', b'a?Z'), (b'a\xc3\xc3\xa9', b'a?e'),
                 (b'A' * 255 + b'\xc3Z', b'A' * 255 + b'?Z'))
        for payload, expected in cases:
            with self.subTest(payload=payload):
                note, data = self.convert(payload, mode='A')
                self.assertIn('Converted', note)
                self.assertEqual(data, expected)

    def test_accents_mark_an_incomplete_final_sequence(self):
        for suffix in (b'\xc3', b'\xe2', b'\xe2\x82', b'\xf0\x9f\x92'):
            with self.subTest(suffix=suffix):
                note, data = self.convert(b'text' + suffix, mode='A')
                self.assertIn('Converted', note)
                self.assertEqual(data, b'text?')

    def test_valid_accents_and_multibyte_characters_cross_chunks(self):
        payload = b'A' * 255 + b'\xc3\xa9 / \xe2\x82\xac / \xf0\x9f\x98\x80'
        note, data = self.convert(payload, mode='A')
        self.assertIn('Converted', note)
        self.assertEqual(data, b'A' * 255 + b'e / ? / ?')


if __name__ == '__main__':
    unittest.main()
