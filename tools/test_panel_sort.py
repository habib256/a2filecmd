"""Run the real panel sort, image directory reader and S (resort) on host tables.

Checks the order of the entries AND where the tags land: a mark left on an
index after the entries moved would point a later delete at another file.
"""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'src/a2fc.c').read_text()


def section(start, end):
    return SOURCE[SOURCE.index(start):SOURCE.index(end, SOURCE.index(start))]


C = r'''
#include <stdio.h>
static void activity_tick(void) {}
static void activity_begin(const char* text) {}
#include <stdlib.h>
#include <string.h>
#define __fastcall__
#include "src/a2fc_plugin.h"
enum { SORT_NAME, SORT_SIZE, SORT_TYPE, SORT_MODES };
static unsigned char sort_mode, dir_error, copy_buf[512];
static struct Panel panels[2];
static struct Entry table[2][MAX_ENTRIES];
static struct DirEntry dir_entry;
static int feed_n, feed_i, rereads;
static char feed_names[200][16];
static unsigned char feed_types[200];
static unsigned char dir_open_image(unsigned int key) { (void)key; feed_i = 0; memset(copy_buf, 0, sizeof copy_buf); return 1; }
static unsigned char dir_next(void) {
    if (feed_i >= feed_n) return 0;
    memset(&dir_entry, 0, sizeof dir_entry);
    strcpy(dir_entry.name, feed_names[feed_i]);
    dir_entry.type = feed_types[feed_i];
    dir_entry.size = feed_i;
    ++feed_i;
    return 1;
}
static void draw_panel(unsigned char p) { (void)p; }
static void draw_info(void) {}
''' + section('static unsigned char is_dir(', 'static unsigned char is_locked(') \
  + section('static unsigned char tagged(', 'unsigned char __fastcall__ tag_count(') \
  + section('static int compare(', 'static struct Entry* add_entry(') \
  + section('static struct Entry* add_entry(', '/* DEVNUM') + r'''
/* What a reread did before: forget the tags, sort the fresh table. */
static unsigned char read_panel(unsigned char p) {
    ++rereads; memset(panels[p].tags, 0, sizeof panels[p].tags); sort_entries(&panels[p]); return 1;
}
''' + section('static unsigned char read_image_dir(struct Panel* pan)', '#pragma rodata-name (pop)') \
  + section('static void set_cursor(', '/* Puts the active panel') \
  + section('static void select_name(', '/* Full path of the entry') \
  + section('static void resort(void)', 'void __fastcall__ text_entry') + r'''
static void show(const struct Panel* pan) {
    unsigned char i;
    for (i = 0; i < pan->count && i < 4; ++i) printf("%s%s ", pan->e[i].name, tagged(pan, i) ? "*" : "");
    for (i = 0; i < pan->count; ++i) if (pan->e[i].name[NAME_LEN - 1] && strlen(pan->e[i].name) < NAME_LEN - 1) printf("SPARE ");
    printf("| more=%u cursor=%s\n", pan->more, pan->count ? pan->e[pan->cursor].name : "");
}
static void feed(const char* list) {
    char copy[400], *t;
    strcpy(copy, list); feed_n = 0;
    for (t = strtok(copy, " "); t; t = strtok(NULL, " ")) {
        size_t n = strlen(t);
        feed_types[feed_n] = t[n - 1] == '/' ? 0x0F : 0x06;
        if (t[n - 1] == '/') t[n - 1] = 0;
        strcpy(feed_names[feed_n++], t);
    }
}
static struct Entry* put(struct Panel* pan, const char* name, unsigned char type, unsigned long size) {
    struct Entry* e = add_entry(pan, name, type); e->size = size; return e;
}
int main(int argc, char** argv) {
    struct Panel* pan = &panels[0], *other = &panels[1];
    int i;
    pan->e = table[0]; other->e = table[1];
    if (!strcmp(argv[1], "image")) {
        pan->fs = FS_IMG; strcpy(pan->path, "/V/DISK.PO"); pan->dir_key = atoi(argv[2]);
        feed(argv[3]);
        if (argc > 4) { feed_n = 0; for (i = 199; i >= 0; --i) { sprintf(feed_names[feed_n], "F%03d", i); feed_types[feed_n++] = 6; } }
        pan->tags[0] = 0;
        printf("%u ", read_image_dir(pan));
        show(pan);
    } else if (!strcmp(argv[1], "resort")) {
        strcpy(pan->path, "/V/DIR");
        put(pan, "..", 0x0F, 0); put(pan, "APPLE", 6, 10); put(pan, "BIG", 6, 30);
        put(pan, "CAT", 6, 20); put(pan, "SUBDIR", 0x0F, 0);
        pan->tags[0] = (1 << 2) | (1 << 4);          /* BIG and SUBDIR */
        pan->cursor = 3;                              /* CAT */
        /* The other panel lists the volumes: 16-character names, no sort. */
        put(other, "/ABCDEFGHIJKLMNO", 0x0F, 0); put(other, "/A", 0x0F, 0);
        other->tags[0] = 1;
        resort();
        printf("mode=%u rereads=%d ", sort_mode, rereads); show(pan); show(other);
    } else if (!strcmp(argv[1], "keep")) {
        /* A later window, a truncated table, a DOS 3.3 catalog: disk order. */
        int mode = atoi(argv[2]);
        strcpy(pan->path, "/V/DIR");
        if (mode == 0) pan->first = 139;
        if (mode == 1) pan->more = 1;
        if (mode == 2) pan->fs = FS_DOS33;
        put(pan, "ZED", 6, 1); put(pan, "ABC", 6, 2);
        pan->tags[0] = 1;
        sort_entries(pan);
        show(pan);
    }
    return 0;
}
'''


class PanelSort(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='panel-sort-')
        p = Path(cls.tmp.name)
        (p / 'test.c').write_text(C)
        cls.exe = p / 'test'
        subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-I', str(ROOT), str(p / 'test.c'),
                        '-o', str(cls.exe)], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_case(self, *args):
        return subprocess.check_output([str(self.exe), *args], text=True, timeout=5).strip()

    def test_image_root_without_parent_sorts_its_first_entry(self):
        self.assertEqual(self.run_case('image', '2', 'ZEBRA APPLE INSIDE/ MIDDLE'),
                         '1 INSIDE APPLE MIDDLE ZEBRA | more=0 cursor=INSIDE')

    def test_image_subdirectory_keeps_parent_first(self):
        self.assertEqual(self.run_case('image', '5', 'ZEBRA APPLE INSIDE/'),
                         '1 .. INSIDE APPLE ZEBRA | more=0 cursor=..')

    def test_truncated_image_directory_keeps_disk_order(self):
        # 200 entries F199..F000 on disk: 140 shown, more set, not sorted.
        self.assertEqual(self.run_case('image', '2', 'X', 'many'),
                         '1 F199 F198 F197 F196 | more=1 cursor=F199')

    def test_resort_moves_tags_with_their_files(self):
        out = self.run_case('resort').split('\n')
        # By size: directories first, then the largest file.
        self.assertEqual(out[0], 'mode=1 rereads=0 .. SUBDIR* BIG* CAT | more=0 cursor=CAT')
        self.assertEqual(out[1], '/ABCDEFGHIJKLMNO* /A | more=0 cursor=/ABCDEFGHIJKLMNO')

    def test_windows_truncated_tables_and_dos_catalogs_keep_order_and_tags(self):
        for mode in ('0', '1', '2'):
            with self.subTest(mode=mode):
                self.assertTrue(self.run_case('keep', mode).startswith('ZED* ABC |'))


if __name__ == '__main__':
    unittest.main()
