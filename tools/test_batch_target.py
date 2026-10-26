"""A copy or move batch stops when its target no longer reads.

copy_or_move rereads the other panel after each item. When that directory
no longer opens (a floppy pulled or swapped, an I/O error), read_panel
empties the panel's path, and build_full then makes the next destination a
bare name: under the ProDOS prefix, the program's own directory. Measured
before the fix with this harness: the second item was copied to "" (the
bare name) and, with V, its source deleted afterwards. The real
copy_or_move from src/a2fc.c runs here; the rest is a recording fake.
"""
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_file_safety import section

HARNESS = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define FS_PRODOS 0
#define FS_DOS33 1
#define FS_IMG 2
#define ASK 0
#define WALK_COUNT 0
struct Entry { char name[16]; unsigned char type; unsigned int aux; };
struct Mini { unsigned char b; };
struct Panel { unsigned char fs, img_len, count; char path[65]; struct Entry e[4]; unsigned char tags[8]; };
static struct Panel panels[2];
static unsigned char active, picked[4], over_policy, progress_abort, scenario;
static unsigned int progress_total, progress_done, progress_skipped;
static struct Mini* pool;
static char full[80], other_full[80], question[80], shown[80];
static char copied_to[8][80], removed_path[8][80];
static unsigned copies, removals, tree_deletes, rereads;
static struct Panel* pan_at(unsigned char p) { return &panels[p]; }
static void overlay_run(const char* n, unsigned char c) { (void)n; (void)c; exit(90); }
static void copy_dos(unsigned char m) { (void)m; exit(91); }
static unsigned char target_check(void) { return panels[!active].path[0] != 0; }
static unsigned char pick_targets(void) { picked[0] = 0; picked[1] = 1; picked[2] = 2; return 3; }
static void activity_begin(const char* s) { (void)s; }
static unsigned char is_up(const struct Entry* e) { return !strcmp(e->name, ".."); }
static unsigned char is_dir(const struct Entry* e) { return e->type == 0x0F; }
static unsigned char build_full(char* out, const struct Panel* pan, const struct Entry* e)
{ if (!pan->path[0]) { strcpy(out, e->name); return 1; } sprintf(out, "%s/%s", pan->path, e->name); return 1; }
static unsigned char both_paths(const struct Entry* e)
{ return build_full(full, pan_at(active), e) && build_full(other_full, pan_at(!active), e); }
static unsigned int walk_tree(unsigned char m) { (void)m; return 1; }
static void refresh_both(void) {}
#define KEY_ESC 27
static int kbhit(void) { return 0; }
static char cgetc(void) { return 0; }
''' + section('static unsigned char abort_key(void)\n{', '/* The whole row 22') + r'''
/* Records where each item would be written: the destination path. */
static unsigned char copy_one(const struct Entry* e)
{ both_paths(e); strcpy(copied_to[copies++], other_full); if (scenario == 4) progress_abort = 1; return 1; }
static unsigned char overlay(const char* n) { (void)n; return 1; }
static unsigned char moved_tree_delete(void) { strcpy(removed_path[removals++], full); ++tree_deletes; return 1; }
static int fs_remove(const char* p) { strcpy(removed_path[removals++], p); return 0; }
#define remove fs_remove
static void report_error(const char* s) { (void)s; }
static void drop_entry(struct Panel* p, unsigned char i)
{ memmove(&p->e[i], &p->e[i + 1], (p->count - i - 1) * sizeof p->e[0]); --p->count; }
static void draw_panel(unsigned char p) { (void)p; }
/* The target panel's reread: after the first item it fails as a pulled
 * floppy does, path emptied (scenario 1), or with the path kept and the
 * catalog unreadable (scenario 3). */
static unsigned char read_panel(unsigned char p)
{
    if (p == active) return 1;
    ++rereads;
    if (scenario == 0 || scenario == 4) return 1;
    if (scenario != 3) panels[p].path[0] = 0;
    return 0;
}
static void message(const char* s) { strcpy(shown, s); }
static void open_row22(void) { shown[0] = 0; }
#define cprintf(...) strcat(shown, "summary")
#define cputc(c) strcat(shown, ".")
static const char imgput_plugin[] = "IMGPUT";
''' + section('static void copy_or_move(unsigned char move)\n{', '/* The DELETE overlay, second half') + r'''
int main(int argc, char** argv)
{
    unsigned move;
    (void)argc;
    scenario = (unsigned char)atoi(argv[1]); move = (unsigned)atoi(argv[2]);
    strcpy(panels[0].path, "/HD/SRC"); strcpy(panels[1].path, "/FLOP");
    panels[0].count = 3;
    strcpy(panels[0].e[0].name, "A"); panels[0].e[0].type = 0x04;
    strcpy(panels[0].e[1].name, "B"); panels[0].e[1].type = 0x0F;
    strcpy(panels[0].e[2].name, "C"); panels[0].e[2].type = 0x04;
    copy_or_move((unsigned char)move);
    printf("copies=%u removals=%u trees=%u rereads=%u\n", copies, removals, tree_deletes, rereads);
    { unsigned i; for (i = 0; i < copies; ++i) printf("to=%s\n", copied_to[i]);
      for (i = 0; i < removals; ++i) printf("rm=%s\n", removed_path[i]); }
    printf("shown=%s\n", shown);
    return 0;
}
'''


class BatchTarget(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='batch-target-')
        tmp = Path(cls.tmp.name)
        (tmp / 'h.c').write_text(HARNESS)
        cls.exe = tmp / 'h'
        build = subprocess.run(['cc', '-std=c99', '-Wall', '-Wno-deprecated-declarations', '-fsanitize=address,undefined',
                                '-o', str(cls.exe), str(tmp / 'h.c')], capture_output=True, text=True)
        assert build.returncode == 0, build.stderr

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_case(self, scenario, move):
        run = subprocess.run([str(self.exe), str(scenario), str(move)], capture_output=True, text=True, timeout=10)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        return run.stdout

    def test_whole_batch_when_target_reads(self):
        out = self.run_case(0, 1)
        self.assertIn('copies=3 removals=3 trees=1 rereads=3', out)
        for name in 'ABC':
            self.assertIn('to=/FLOP/' + name, out)
        self.assertNotIn('Interrupted', out)

    def test_lost_target_stops_before_next_item(self):
        """Move and copy alike: only the first item went, to the target;
        nothing was written to a bare name and no other source removed."""
        for scenario in (1, 3):
            for move in (0, 1):
                with self.subTest(scenario=scenario, move=move):
                    out = self.run_case(scenario, move)
                    self.assertIn('copies=1 ', out)
                    self.assertIn('to=/FLOP/A', out)
                    self.assertNotIn('to=B', out)
                    self.assertNotIn('to=C', out)
                    self.assertIn('removals=%d ' % move, out)
                    self.assertNotIn('rm=/HD/SRC/B', out)
                    self.assertNotIn('rm=/HD/SRC/C', out)
                    self.assertIn('shown=Interrupted: 1 of 3 done.', out)

    def test_escape_during_an_item_still_stops(self):
        """ESC read while the first item finished: the target rereads fine,
        and the reread must not clear the request."""
        for move in (0, 1):
            with self.subTest(move=move):
                out = self.run_case(4, move)
                self.assertIn('copies=1 ', out)
                self.assertIn('shown=Interrupted: 1 of 3 done.', out)


if __name__ == '__main__':
    unittest.main()
