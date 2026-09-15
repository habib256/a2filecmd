"""Run the actual D command (delete_targets) on stand-in panels.

The confirmation must name what a tagged directory takes with it, and the
progress counter must start from zero, not from the previous operation.
Nothing is deleted when the question is refused.
"""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT/'src/a2fc.c').read_text()


def section(start, end):
    a = SOURCE.index(start)
    return SOURCE[a:SOURCE.index(end, a)]


C = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#define __fastcall__
#define POOL_SIZE 8
struct A2fcApi { int unused; };
struct Entry { char name[17]; unsigned char type; };
struct Mini { char name[17]; };
struct Panel { char path[64]; struct Entry e[8]; unsigned char count, cursor, tags[8]; };
static struct Panel panels[2];
static struct Mini* pool;
static unsigned char active, picked[8], progress_abort;
static unsigned int progress_total, progress_done, a2fc_ops;
static char question[81], full[81];
static int answer, first_bar = -1, deleted_files, deleted_trees, confirms;
static unsigned char tagged(const struct Panel* p, unsigned char i) { return p->tags[i]; }
static unsigned char is_dir(const struct Entry* e) { return e->type == 0x0F; }
static unsigned char is_up(const struct Entry* e) { return e->name[0] == '.'; }
static void message(const char* s) { printf("message %s\n", s); }
static unsigned char confirm(const char* s) { ++confirms; printf("confirm %s\n", s); return answer; }
static void progress_bar(const char* s, unsigned long d, unsigned long t) { if (first_bar < 0) first_bar = (int)d; }
static unsigned char abort_key(void) { return 0; }
static unsigned char build_full(char* p, const struct Panel* pan, const struct Entry* e) { sprintf(p, "/V/%s", e->name); return 1; }
static unsigned char delete_tree(void) { ++deleted_trees; progress_done += 3; return 1; }
static int remove_stub(const char* p) { ++deleted_files; return 0; }
#define remove remove_stub
static void report_error(const char* s) {}
static void too_long(void) {}
static void drop_entry(struct Panel* pan, unsigned char i)
{
    memmove(&pan->e[i], &pan->e[i + 1], (pan->count - i - 1) * sizeof(struct Entry));
    --pan->count;
}
static void draw_panel(unsigned char p) {}
static void refresh_both(void) {}
static void clear_row(unsigned char r) {}
static void gotoxy(unsigned char x, unsigned char y) {}
static void cprintf(const char* f, ...) { va_list a; va_start(a, f); vprintf(f, a); va_end(a); putchar('\n'); }
''' + section('static unsigned char pick_targets(void)', 'static unsigned char target_check(void)') \
    + section('static const char dl_nothing[]', 'void __fastcall__ delete_entry(') + r'''
int main(int argc, char** argv)
{
    const char* kinds = argv[1];                  /* f: file, d: directory, one letter per tagged entry */
    unsigned char i;
    answer = atoi(argv[2]);
    progress_done = 57;                           /* left over by an earlier copy */
    for (i = 0; kinds[i]; ++i) {
        sprintf(panels[0].e[i].name, "E%u", i);
        panels[0].e[i].type = kinds[i] == 'd' ? 0x0F : 0x04;
        panels[0].tags[i] = kinds[i] != '-';
    }
    panels[0].count = i;
    strcpy(panels[0].path, "/V");
    delete_targets();
    printf("bar=%d files=%d trees=%d confirms=%d left=%u\n", first_bar, deleted_files, deleted_trees, confirms, panels[0].count);
    return 0;
}
'''


class DeleteConfirm(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='delete-confirm-')
        p = Path(cls.tmp.name)
        (p/'test.c').write_text(C)
        cls.exe = p/'test'
        r = subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-fsanitize=address,undefined',
                            str(p/'test.c'), '-o', str(cls.exe)], capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError(r.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_delete(self, kinds, answer=1):
        return subprocess.check_output([self.exe, kinds, str(answer)], text=True)

    def test_tagged_files_only(self):
        out = self.run_delete('ff')
        self.assertIn('confirm Delete 2 tagged files?', out)
        self.assertIn('files=2 trees=0', out)

    def test_a_tagged_directory_is_announced_with_its_contents(self):
        for kinds in ('fdf', 'df', 'fd'):
            with self.subTest(kinds=kinds):
                out = self.run_delete(kinds)
                self.assertIn(f'confirm Delete {len(kinds)} tagged items, directories with everything inside?', out)
                self.assertNotIn('tagged files', out)

    def test_refusal_deletes_nothing(self):
        out = self.run_delete('fdf', 0)
        self.assertIn('files=0 trees=0 confirms=1 left=3', out)

    def test_progress_starts_from_zero(self):
        out = self.run_delete('fdf')
        self.assertIn('bar=0 ', out)
        self.assertIn('files=2 trees=1', out)
        self.assertIn('3 items deleted.', out)


if __name__ == '__main__':
    unittest.main()
