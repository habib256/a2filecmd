"""Run the resident diagnostics as host C, including every ProDOS byte code."""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Diagnostics(unittest.TestCase):
    def test_all_codes_and_rendered_errors(self):
        source = r'''
#include <assert.h>
#include <errno.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
static unsigned char _oserror;
static unsigned int a2fc_errors, clears, positions;
static char line[128];
static void clear_row(unsigned char row) {
    assert(row == 22); ++clears; memset(line, 0, sizeof line);
}
static void gotoxy(unsigned char x, unsigned char y) {
    assert(x == 0 && y == 22); ++positions;
}
static void cprintf(const char* fmt, ...) {
    va_list ap; va_start(ap, fmt); vsnprintf(line, sizeof line, fmt, ap); va_end(ap);
}
#include "src/errors.h"
int main(void) {
    unsigned int code;
    const char* expected;
    char rendered[128];
    for (code = 0; code < 256; ++code) {
        switch (code) {
        case 0x27: expected = "disk I/O error"; break;
        case 0x2B: expected = "the disk is write-protected"; break;
        case 0x2F: expected = "no disk in the drive"; break;
        case 0x40: expected = "invalid file name"; break;
        case 0x44: expected = "directory not found"; break;
        case 0x45: expected = "volume not found"; break;
        case 0x46: expected = "file not found"; break;
        case 0x47: expected = "name already in use"; break;
        case 0x48: expected = "the disk is full"; break;
        case 0x49: expected = "the directory is full"; break;
        case 0x4E: expected = "the file is locked"; break;
        case 0x52: expected = "not a ProDOS disk"; break;
        default: expected = 0;
        }
        _oserror = code; errno = 7;
        if (expected) {
            assert(prodos_error(code));
            assert(!strcmp(prodos_error(code), expected));
            snprintf(rendered, sizeof rendered, "Save failed: %s.", expected);
        } else {
            assert(!prodos_error(code));
            snprintf(rendered, sizeof rendered, "Save failed (ProDOS $%02X, errno 7).", code);
        }
        report_error("Save");
        assert(!strcmp(line, rendered));
        assert(_oserror == code && errno == 7);
        assert(a2fc_errors == code + 1 && clears == code + 1 && positions == code + 1);
    }
    return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix='a2fc-errors-') as tmp:
            c = Path(tmp) / 'test.c'
            exe = Path(tmp) / 'test'
            c.write_text(source)
            subprocess.run(['cc', '-std=c99', '-Wall', '-Wextra', '-Werror',
                            '-I', str(ROOT), str(c), '-o', str(exe)], check=True)
            subprocess.run([str(exe)], check=True)


if __name__ == '__main__':
    unittest.main()
