#!/usr/bin/env python3
"""The tags come back only on the files that carried them; a directory is
never copied onto one of its own ancestors.

Two resident routines of src/a2fc_mli.s, the real assembly under sim65 on
both processors:

keep_tags / panel_hash. A tag is a bit by entry index. A big overlay covers
the entry tables, so the tags are set aside and given back once the panels
are reread. Measured before the fix (0.9.5, the restore was unconditional):
with [.., A, C, D] in a panel and C and D tagged, a MOVE into that
directory made it [.., A, B0, C, D] and the tags came back on B0 and C; D
then asked "Delete 2 tagged files?" -- by number, not by name. GOTO and FIND
(another directory), an extraction, the editor's new file and Left/Right
across the 139-entry window of a large folder did the same. Now a panel
whose names, types, count or path changed comes back untagged, and the
other panel keeps its own.

paths_nested. copy_one refused a directory copied INTO itself, not ONTO an
ancestor: with /V/A/A copied to /V, the target /V/A exists and the
subdirectory /V/A/A/A is written into /V/A/A, the source; the move then
deleted what it had just copied there (tools/test_tree_walk.py plays the
whole move). The same pairs are checked here against the model that test
uses.

    python3 tools/test_keep_tags.py
"""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (full, other_full, nested): one is the other, or lies inside it
PAIRS = [
    ('/V/A/A', '/V/A', 1),          # the move that lost a file
    ('/V/A', '/V/A/A', 1),          # into itself, as before
    ('/V/A', '/V/A', 1),
    ('/V/A/A/A', '/V/A', 1),
    ('/V', '/V/A/B', 1),
    ('/V/AB', '/V/A', 0),           # a longer name is not a child
    ('/V/A', '/V/AB', 0),
    ('/V/A/B', '/V/C/B', 0),
    ('/V/A', '/W/A', 0),
    ('/VOL', '/V', 0),
    ('/V/A/B', '/V/A/C', 0),
    ('/A2345678901234/B2345678901234/C2345678901234/D2345678901234/E234567',
     '/A2345678901234/B2345678901234/C2345678901234/D2345678901234', 1),
]


def nested(full, other):
    """The model: equal, or equal up to the end of one where the other goes
    on with a '/'."""
    short, long_ = sorted((full, other), key=len)
    return int(long_.startswith(short) and (len(long_) == len(short) or long_[len(short)] == '/'))


HARNESS = r'''
#include <string.h>
#include <stddef.h>
#include "a2fc_plugin.h"
struct Panel panels[2];
unsigned char picked[MAX_ENTRIES];
char full[PATH_LEN + NAME_LEN], other_full[PATH_LEN + NAME_LEN];
void __fastcall__ keep_tags(unsigned char save);
unsigned int __fastcall__ panel_hash(const struct Panel* pan);
unsigned char paths_nested(void);
static struct Entry table[2][MAX_ENTRIES], snapshot[MAX_ENTRIES];

static void put(unsigned char p, const char* name, unsigned char type)
{   /* add_entry: the name padded with zeros */
    struct Entry* e = &panels[p].e[panels[p].count++];
    memset(e, 0, sizeof *e);
    strncpy(e->name, name, NAME_LEN - 1);
    e->type = type;
}
static void tag(unsigned char p, unsigned char i) { panels[p].tags[i >> 3] |= 1 << (i & 7); }
static unsigned char tagged(unsigned char p, unsigned char i) { return panels[p].tags[i >> 3] >> (i & 7) & 1; }
static unsigned char any(unsigned char p)
{
    unsigned char i, n = 0;
    for (i = 0; i < sizeof panels[0].tags; ++i) n |= panels[p].tags[i];
    return n;
}
/* What read_panel does to the tags before the entries come back. */
static void reread(void) { memset(panels[0].tags, 0, sizeof panels[0].tags); memset(panels[1].tags, 0, sizeof panels[1].tags); }
static void start(void)
{
    memset(panels, 0, sizeof panels);
    panels[0].e = table[0]; panels[1].e = table[1];
    strcpy(panels[0].path, "/V/A"); strcpy(panels[1].path, "/V/B");
    put(0, "..", 0x0F); put(0, "B0", 4); put(0, "ZED", 6);
    put(1, "..", 0x0F); put(1, "A", 4); put(1, "C", 4); put(1, "D", 4);
    tag(0, 2); tag(1, 2); tag(1, 3);
    keep_tags(1);
    reread();
}
struct Pair { const char* full; const char* other; unsigned char nested; };
static const struct Pair pairs[] = { PAIRS };

int main(void)
{
    unsigned char i;
    /* the three sizes a2fc_mli.s is written for */
    if (sizeof(struct Panel) != 98 || offsetof(struct Panel, tags) != 76 || sizeof panels[0].tags != 18) return 1;
    if (sizeof(struct Entry) != 29 || offsetof(struct Entry, type) != 17) return 2;
    if (offsetof(struct Panel, count) != 64 || offsetof(struct Panel, e) != 74) return 3;

    start(); keep_tags(0);                                  /* nothing changed: every tag back */
    if (!tagged(0, 2) || !tagged(1, 2) || !tagged(1, 3) || tagged(1, 1) || tagged(0, 1)) return 10;

    start();                                                /* MOVE dropped B0 into /V/B */
    panels[1].count = 0;
    put(1, "..", 0x0F); put(1, "A", 4); put(1, "B0", 4); put(1, "C", 4); put(1, "D", 4);
    keep_tags(0);
    if (any(1)) return 20;                                  /* B0 and C used to come back tagged */
    if (!tagged(0, 2)) return 21;                           /* the other panel keeps its own */

    start(); strcpy(panels[0].path, "/V/Z"); keep_tags(0);  /* GOTO, FIND: the same names elsewhere */
    if (any(0) || !tagged(1, 2) || !tagged(1, 3)) return 30;

    start(); panels[1].e[2].name[0] = 'E'; keep_tags(0);    /* a tagged file renamed */
    if (any(1) || !tagged(0, 2)) return 40;
    start(); panels[1].e[1].type = 6; keep_tags(0);         /* a type changed (FIXTYPES) */
    if (any(1)) return 41;
    start(); --panels[1].count; keep_tags(0);               /* the last entry gone */
    if (any(1)) return 42;
    start(); panels[1].e[1].name[1] = 'X'; keep_tags(0);    /* A -> AX: one character more */
    if (any(1)) return 43;

    start();                                                /* the editor saved C: size and date only */
    panels[1].e[2].size = 12345; panels[1].e[2].mdate = 0x1234; panels[1].e[2].blocks = 26;
    panels[1].cursor = 3; panels[1].top = 1;
    keep_tags(0);
    if (!tagged(1, 2) || !tagged(1, 3) || !tagged(0, 2)) return 50;

    start();                                                /* another window of a large folder */
    panels[0].first = 139; panels[0].e[1].name[0] = 'Q'; panels[0].e[2].name[0] = 'R';
    keep_tags(0);
    if (any(0)) return 60;

    start(); start(); keep_tags(0);                         /* saved twice, as a batch does: still back */
    if (!tagged(1, 2) || !tagged(1, 3)) return 70;

    /* The batch: its overlay covers the tables; it re-tags by name against
     * its snapshot and points the panel at that snapshot for the save. */
    start(); memcpy(snapshot, table[1], sizeof snapshot); memset(table, 0xEE, sizeof table);
    tag(1, 3); panels[1].e = snapshot; keep_tags(1); panels[1].e = table[1];
    memset(panels[1].tags, 0, sizeof panels[1].tags); memcpy(table[1], snapshot, sizeof snapshot);
    keep_tags(0);
    if (!tagged(1, 3) || tagged(1, 2)) return 71;

    /* a full table: the last entry and the last tag byte are reached */
    memset(panels, 0, sizeof panels);
    panels[0].e = table[0]; panels[1].e = table[1];
    for (i = 0; i < MAX_ENTRIES; ++i) { put(0, "F", 4); panels[0].e[i].name[1] = '0' + i % 10; panels[0].e[i].name[2] = 'A' + i / 10; }
    tag(0, MAX_ENTRIES - 1);
    keep_tags(1); reread(); keep_tags(0);
    if (!tagged(0, MAX_ENTRIES - 1)) return 80;
    keep_tags(1); reread(); panels[0].e[MAX_ENTRIES - 1].name[2] ^= 1; keep_tags(0);
    if (any(0)) return 81;
    if (panels[1].fs || panels[1].img_len || panels[0].fs) return 82;   /* nothing written past the tags */

    for (i = 0; i < sizeof pairs / sizeof pairs[0]; ++i) {
        strcpy(full, pairs[i].full); strcpy(other_full, pairs[i].other);
        if ((paths_nested() != 0) != pairs[i].nested) return 100 + i;
    }
    return 0;
}
'''


class KeepTags(unittest.TestCase):
    def test_model_and_table_agree(self):
        for full, other, want in PAIRS:
            self.assertEqual(nested(full, other), want, (full, other))

    @unittest.skipUnless(shutil.which('cl65') and shutil.which('sim65'), 'cc65 is not installed')
    def test_tags_and_nesting_on_both_processors(self):
        src = (ROOT / 'src/a2fc_mli.s').read_text()
        a = src.index('; unsigned int __fastcall__ panel_hash')
        b = src.index('; unsigned char __fastcall__ dir_count_block')
        asm = src[a:b].replace('.segment "LOWBSS"', '.bss').replace('.segment "CODE"', '.code')
        self.assertIn('_keep_tags:', asm)
        self.assertIn('_paths_nested:', asm)
        pairs = ', '.join('{ "%s", "%s", %u }' % p for p in PAIRS)
        with tempfile.TemporaryDirectory(prefix='keep-tags-') as tmp:
            p = Path(tmp)
            (p / 'tags.s').write_text('        .setcpu "6502"\n' + asm)
            (p / 'h.c').write_text(HARNESS.replace('PAIRS', pairs))
            for target in ('sim6502', 'sim65c02'):
                exe = p / ('t_' + target)
                subprocess.run(['cl65', '-t', target, '-O', '-I', str(ROOT / 'src'), '-o', str(exe),
                                str(p / 'h.c'), str(p / 'tags.s')], check=True, capture_output=True, cwd=p)
                self.assertEqual(subprocess.run(['sim65', str(exe)]).returncode, 0, target)


if __name__ == '__main__':
    unittest.main()
