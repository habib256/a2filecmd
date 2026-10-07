"""Execute the resident reservation (src/file_output.h) on both CPUs.

reserve_output is one MLI CREATE. Before bug hunt 2 it was cc65's
open(O_CREAT | O_EXCL), which issues CREATE then OPEN and, when OPEN failed,
returned -1 without destroying the entry it had made: a 0-byte A2FC.COPY
stayed in the directory and every later copy there was refused with
"Failed; source kept." (tools/hunt2/probe_reserve_leftover.py: "left in
destination: A2FC.COPY (0 bytes)"). Here open() aborts the program: the
reservation must not go through it, and the CREATE parameter block is
checked byte for byte (count, counted name, access, type, auxtype, seedling
storage, clock dates).
"""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
C = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define PATH_LEN 64
static unsigned char gfi[18], gfi_path[PATH_LEN + 1], _filetype;
static unsigned int _auxtype;
static unsigned char mode, entry, calls;
static int no_open(const char* p, int flags) { abort(); return -1; }
#define open no_open
static unsigned char __fastcall__ mli_call(unsigned char cmd, void* p) {
    unsigned char* b = p;
    ++calls;
    if (cmd != 0xC0 || b != gfi || b[0] != 7 || b[1] != (unsigned char)((unsigned)gfi_path & 0xFF) || b[2] != (unsigned char)((unsigned)gfi_path >> 8)) exit(10);
    if (gfi_path[0] != 6 || memcmp(gfi_path + 1, "/V/OUT", 6)) exit(11);
    if (b[3] != 0xC3 || b[4] != 0x06 || b[5] != 0x34 || b[6] != 0x12 || b[7] != 1) exit(12);
    if (b[8] || b[9] || b[10] || b[11]) exit(13);
    if (mode == 1 || entry) return 0x47;           /* duplicate */
    if (mode == 2) return 0x27;                    /* I/O error: nothing created */
    entry = 'E';
    return 0;
}
#include "src/file_output.h"
int main(void) {
    unsigned char status, i;
    for (i = 0; i < 3; ++i) for (mode = 0; mode < 4; ++mode) {
        entry = mode == 3 ? 'P' : 0; calls = 0;
        memset(gfi, 0xEE, sizeof gfi);             /* a stale GET_FILE_INFO */
        _filetype = 0x06; _auxtype = 0x1234;
        status = reserve_output("/V/OUT");
        if (calls != 1) return 1;
        if (mode == 0) { if (status != OUTPUT_RESERVED || entry != 'E') return 2; }
        else if (status || entry != (mode == 3 ? 'P' : 0)) return 3;
    }
    return 0;
}
'''


class FileOutput(unittest.TestCase):
    def test_native_reservation_ownership(self):
        with tempfile.TemporaryDirectory(prefix='file-output-') as d:
            p = Path(d)
            source = p / 'test.c'
            source.write_text(C)
            for cpu in ('sim6502', 'sim65c02'):
                with self.subTest(cpu=cpu):
                    result = subprocess.run(
                        [shutil.which('cl65'), '-t', cpu, '-O', '-Oirs', '-Cl',
                         '-I', str(ROOT), '-o', str(p / 'test'), str(source)],
                        capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    r = subprocess.run([shutil.which('sim65'), str(p / 'test')], timeout=15)
                    self.assertEqual(r.returncode, 0)


if __name__ == '__main__':
    unittest.main()
