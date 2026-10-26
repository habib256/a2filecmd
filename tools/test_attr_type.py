"""A (change_attributes) refuses type $0F on a plain file.

A plain file typed $0F is listed as a directory by its file type: before
the tree walks checked the storage type, one whose first block read as a
directory header was copied as an empty directory and destroyed by V. A
gave a file that type without a word. The real change_attributes runs
here on a mocked GET/SET_FILE_INFO; the bytes SET_FILE_INFO would write
are checked, not only the message.
"""
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_file_safety import section, ROOT

HARNESS = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
struct Entry { char name[16]; unsigned char type, access; unsigned int aux; };
struct Panel { char path[65]; };
static struct Panel panels[2]; static unsigned char active;
static struct Panel* pan_at(unsigned char p) { return &panels[p]; }
static char full[65], input[80], shown[80], answers[2][8];
static unsigned char gfi[18], answer, sets, reads;
static unsigned int a2fc_ops;
static unsigned char is_up(const struct Entry* e) { return !strcmp(e->name, ".."); }
static unsigned char is_dir(const struct Entry* e) { return e->type == 0x0F; }
static unsigned char is_locked(const struct Entry* e) { return !(e->access & 2); }
static unsigned char build_full(char* out, const struct Panel* p, const struct Entry* e) { sprintf(out, "%s/%s", p->path, e->name); return 1; }
static void too_long(void) {}
static void message(const char* s) { strcpy(shown, s); }
static void report_error(const char* s) { strcpy(shown, s); }
static unsigned char prompt(const char* q, const char* init, unsigned char n) { (void)q; (void)init; (void)n; strcpy(input, answers[answer++]); return 1; }
static unsigned int hex_value(const char* s) { return (unsigned int)strtoul(s, NULL, 16); }
static unsigned char file_info(const char* p) { (void)p; memset(gfi, 0, sizeof gfi); gfi[3] = 0xC3; gfi[4] = 0x06; gfi[5] = 0x00; gfi[6] = 0x20; gfi[7] = 1; return 1; }
static unsigned char set_info(void) { ++sets; return 1; }
static void read_panel(unsigned char p) { (void)p; ++reads; }
static void select_name(struct Panel* p, const char* n) { (void)p; (void)n; }
static void show_active(void) {}
''' + section('static const char at_type[]', 'static void rename_selected') + section('/* A: type and auxtype; L: lock.', 'void __fastcall__ attr_entry') + r'''
int main(int argc, char** argv)
{
    struct Entry e = { "PROG", 0x06, 0xC3, 0x2000 };
    (void)argc;
    strcpy(panels[0].path, "/V");
    strcpy(answers[0], argv[1]); strcpy(answers[1], "0300");
    change_attributes(&e, 0);
    printf("sets=%u type=%02X aux=%02X%02X shown=%s\n", sets, gfi[4], gfi[6], gfi[5], shown);
    return 0;
}
'''


class AttrType(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='attr-type-')
        p = Path(cls.tmp.name)
        (p / 't.c').write_text(HARNESS)
        cls.exe = p / 't'
        subprocess.run(['cc', '-std=c99', '-w', '-fsanitize=address,undefined', '-o', str(cls.exe), str(p / 't.c')], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_case(self, typed):
        return subprocess.run([str(self.exe), typed], capture_output=True, text=True, check=True).stdout

    def test_directory_type_refused_on_a_file(self):
        out = self.run_case('0F')
        self.assertIn('sets=0 ', out)
        self.assertIn('shown=$0F is the directory type.', out)

    def test_other_types_still_set(self):
        out = self.run_case('04')
        self.assertIn('sets=1 type=04 aux=0300', out)


if __name__ == '__main__':
    unittest.main()
