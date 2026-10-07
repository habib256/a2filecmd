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

panel_hash folded h = rol16(h) + byte until bug hunt 2: nearly linear, a
byte's weight depended only on its distance modulo 16 from the end, so two
entries 8 indexes apart exchanged (F02 and F10 of 20 files) or a name "AB"
become "CA" kept the fingerprint, and the tag came back on another file
(tools/probe_keep_tags_collision.py: "swap: index 2 now F10, tagged=1",
"rename: index 2 now CA, tagged=1", on both processors). The fold is now
h = rol16(h); high ^= byte; low += high. Both cases and seeded random swaps,
renames and permutations are played on the real assembly, the assembly is
checked against the Python model hash_model(), and the model's collision
rate is measured on random edits (the 16-bit rate is about 1 in 65,536).

Bug hunt 3: that fold still cancelled two edits two bytes apart in one
name, +4 then +1 ("PIC.00" become "PIG.10"): 21 collisions in the 90,531
two-byte edits of PIC.00-PIC.02 among PIC.00-PIC.19, where 1.4 are
expected. Now low = rol8(low + high). The 21 are played on the assembly
(each one checked to collide under the bug-hunt-2 fold first), and the
model is measured on that set and on every two-byte edit within three
positions of a few names.

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


def fold(h, b):
    """The fold of a2fc_mli.s: h = rol16(h); high ^= b; low = rol8(low + high)."""
    h = ((h << 1) | (h >> 15)) & 0xFFFF
    hi = (h >> 8) ^ b
    lo = ((h & 0xFF) + hi) & 0xFF
    return hi << 8 | ((lo << 1) | (lo >> 7)) & 0xFF


def fold_hunt2(h, b):
    """The bug-hunt-2 fold, without the rotation of low: the reference the
    structured cases were found with."""
    h = ((h << 1) | (h >> 15)) & 0xFFFF
    hi = (h >> 8) ^ b
    return hi << 8 | ((h & 0xFF) + hi) & 0xFF


def entry_bytes(name, typ):
    return name.encode().ljust(17, b'\0') + bytes([typ])


def two_byte_edits(f, names, which, p1s, positions, gap, first, second):
    """Every edit of two bytes of one name (indexes `which`, p1 < p1s, p1 <
    p2 < positions, p2 - p1 <= gap), first byte from `first`, second from
    `second`: (count, [(index, new name) that collide under fold f]).
    Each fold step is a bijection of h for a given byte, so two tables
    that differ in one entry collide iff h is equal right after it."""
    h = 0
    head = b'/V/B'.ljust(64, b'\0') + bytes([len(names)])
    for b in reversed(head):
        h = f(h, b)
    starts = []
    for name, typ in names:
        starts.append(h)
        for b in reversed(entry_bytes(name, typ)):
            h = f(h, b)
    total, found = 0, []
    for i in which:
        raw = entry_bytes(*names[i])
        def after(r, h=starts[i]):
            for b in reversed(r):
                h = f(h, b)
            return h
        base = after(raw)
        for p1 in range(p1s):
            for p2 in range(p1 + 1, min(positions, p1 + gap + 1)):
                for a in first:
                    for b in second:
                        r = bytearray(raw); r[p1] = a; r[p2] = b
                        if r == raw:
                            continue
                        total += 1
                        if after(bytes(r)) == base:
                            found.append((i, bytes(r[:17]).rstrip(b'\0').decode('latin-1')))
    return total, found


PICS = [('PIC.%02d' % k, 6) for k in range(20)]


def hunt3_set(f):
    """The reviewer's set: two bytes of PIC.00-PIC.02, p1 < 6, p2 < 8,
    first A-Z, second 0-Z (probe_hash_structured.py)."""
    return two_byte_edits(f, PICS, range(3), 6, 8, 8, range(0x41, 0x5B), range(0x30, 0x5B))


def hash_model(path, names):
    """panel_hash of a panel with `path` and entries (name, type), padded with
    zeros as add_entry does: bytes 64 (the count) down to 0, then each entry's
    bytes 17 (the type) down to 0."""
    h = 0
    head = path.encode().ljust(64, b'\0') + bytes([len(names)])
    for b in reversed(head):
        h = fold(h, b)
    for name, typ in names:
        e = name.encode().ljust(17, b'\0') + bytes([typ])
        for b in reversed(e):
            h = fold(h, b)
    return h


def random_cases(seed=1966, count=120):
    """Tables of random names, a tag on entry i, then one edit: two entries
    exchanged, one name changed, or the whole table permuted."""
    import random
    r = random.Random(seed)
    cases = []
    while len(cases) < count:
        n = r.randint(3, 40)
        names = []
        while len(names) < n:
            s = r.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ') + ''.join(
                r.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.') for _ in range(r.randint(0, 14)))
            if s not in [x for x, _ in names]:
                names.append((s, r.choice((4, 6, 0x0F, 0xFC))))
        i = r.randrange(n)
        after = list(names)
        kind = len(cases) % 3
        if kind == 0:
            j = r.choice([k for k in range(n) if k != i])
            after[i], after[j] = after[j], after[i]
        elif kind == 1:
            s = list(after[i][0])
            k = r.randrange(len(s))
            s[k] = r.choice([c for c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' if c != s[k]])
            after[i] = (''.join(s), after[i][1])
        else:
            while after[i] == names[i]:
                r.shuffle(after)
        if hash_model('/V/B', after) == hash_model('/V/B', names):
            continue        # a true 16-bit collision of the model: not what this case tests
        cases.append((names, after, i))
    return cases


def c_structured():
    """Bug hunt 3: the renames of one of PIC.00-PIC.19 that the bug-hunt-2
    fold could not tell apart, as { index, new name, hash after } (the
    table itself is built in C: twenty-two copies overflowed sim65)."""
    rows = []
    for i, name in hunt3_set(fold_hunt2)[1]:
        after = list(PICS)
        after[i] = (name, 6)
        rows.append('{ %u, "%s", 0x%04X }' % (i, name, hash_model('/V/B', after)))
    return ',\n'.join(rows)


def c_cases():
    """The random cases as data: each table one string, a name then its type
    byte (4, 6, $0F or $FC: never a name character), and one loop in C."""
    def enc(names):
        return '"' + ''.join(n + '\\%03o' % typ for n, typ in names) + '"'
    rows = []
    for names, after, i in random_cases():
        rows.append('{ %s, %s, %u, 0x%04X }' % (enc(names), enc(after), i, hash_model('/V/B', names)))
    return ',\n'.join(rows)


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
struct Case { const char* before; const char* after; unsigned char tagged; unsigned int hash; };
static const struct Case cases[] = { RANDOM_CASES };
struct Rename { unsigned char tagged; const char* name; unsigned int hash; };
static const struct Rename renames[] = { STRUCTURED };
static void pics(void)
{   /* panel 1 on /V/B: PIC.00 to PIC.19, all of type 6 */
    char n[7] = "PIC.00";
    unsigned char k;
    memset(panels, 0, sizeof panels); panels[0].e = table[0]; panels[1].e = table[1];
    strcpy(panels[1].path, "/V/B");
    for (k = 0; k < 20; ++k) { n[4] = '0' + k / 10; n[5] = '0' + k % 10; put(1, n, 6); }
}
static void fill(const char* s)
{   /* panel 1 on /V/B from "NAME<type>NAME<type>..." */
    char name[NAME_LEN];
    unsigned char n;
    panels[1].count = 0;
    while (*s) {
        for (n = 0; (unsigned char)*s >= 0x20 && (unsigned char)*s < 0x80; ++s) name[n++] = *s;
        name[n] = 0;
        put(1, name, (unsigned char)*s++);
    }
}
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

    /* Bug hunt 2, the reviewer's two collisions: F02 and F10 of twenty
     * files exchanged (8 apart), and "AB" become "CA" at the same index. */
    memset(panels, 0, sizeof panels); panels[0].e = table[0]; panels[1].e = table[1];
    strcpy(panels[1].path, "/V/B");
    for (i = 0; i < 20; ++i) { char n[4] = "F00"; n[1] = '0' + i / 10; n[2] = '0' + i % 10; put(1, n, 4); }
    tag(1, 2); keep_tags(1); reread();
    panels[1].e[2].name[1] = '1'; panels[1].e[10].name[1] = '0';      /* F10 at 2, F02 at 10 */
    keep_tags(0);
    if (any(1)) return 90;
    memset(panels, 0, sizeof panels); panels[0].e = table[0]; panels[1].e = table[1];
    strcpy(panels[1].path, "/V/B");
    put(1, "..", 0x0F); put(1, "A", 4); put(1, "AB", 4); put(1, "D", 4);
    tag(1, 2); keep_tags(1); reread();
    panels[1].e[2].name[0] = 'C'; panels[1].e[2].name[1] = 'A';
    keep_tags(0);
    if (any(1)) return 91;

    /* seeded random tables: one exchange, rename or permutation each */
    for (i = 0; i < sizeof cases / sizeof cases[0]; ++i) {
        memset(panels, 0, sizeof panels); panels[0].e = table[0]; panels[1].e = table[1];
        strcpy(panels[1].path, "/V/B");
        fill(cases[i].before);
        if (panel_hash(&panels[1]) != cases[i].hash) return 92;    /* the Python model is the assembly */
        tag(1, cases[i].tagged); keep_tags(1); reread();
        fill(cases[i].after);
        keep_tags(0);
        if (any(1)) return 93;
    }

    /* Bug hunt 3: two bytes two apart in one name, +4 then +1 ("PIC.00"
     * become "PIG.10"), kept the bug-hunt-2 fingerprint */
    for (i = 0; i < sizeof renames / sizeof renames[0]; ++i) {
        pics();
        tag(1, renames[i].tagged); keep_tags(1); reread();
        strcpy(panels[1].e[renames[i].tagged].name, renames[i].name);
        if (panel_hash(&panels[1]) != renames[i].hash) return 94;   /* the model is the assembly */
        keep_tags(0);
        if (any(1)) return 95;
    }

    for (i = 0; i < sizeof pairs / sizeof pairs[0]; ++i) {
        strcpy(full, pairs[i].full); strcpy(other_full, pairs[i].other);
        if ((paths_nested() != 0) != pairs[i].nested) return 100 + i;
    }
    return 0;
}
'''


class KeepTags(unittest.TestCase):
    def test_model_collision_rate(self):
        """Random tables (3-139 entries, random names and types), one edit:
        two entries exchanged, two 8 apart, one byte of one name, or a new
        name. The old linear fold collided on 85% of the 8-apart exchanges
        and 6% of any exchange (measured on this model, 20,000 trials each);
        a 16-bit fingerprint should collide about once in 65,536."""
        import random
        r = random.Random(7)
        def table(n):
            return [(''.join(r.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.') for _ in range(r.randint(1, 15))),
                     r.choice((4, 6, 0x0F, 0xFC))) for _ in range(n)]
        trials = collisions = 0
        for k in range(8000):
            n = r.randint(9, 139)
            names = table(n)
            after = list(names)
            i = r.randrange(n)
            kind = k % 4
            if kind == 0:
                j = r.randrange(n)
                after[i], after[j] = after[j], after[i]
            elif kind == 1:
                i = r.randrange(n - 8)
                after[i], after[i + 8] = after[i + 8], after[i]
            elif kind == 2:
                s = bytearray(after[i][0].encode()); s[r.randrange(len(s))] ^= r.randint(1, 31)
                after[i] = (s.decode('latin-1'), after[i][1])
            else:
                after[i] = table(1)[0]
            if after == names:
                continue
            trials += 1
            collisions += hash_model('/V/B', after) == hash_model('/V/B', names)
        self.assertGreater(trials, 7000)
        self.assertLessEqual(collisions, 3, '%d collisions in %d trials' % (collisions, trials))


    def test_two_byte_edits_in_one_name(self):
        """Bug hunt 3: two edits two bytes apart in one name, +4 then +1,
        cancelled out under the bug-hunt-2 fold ("PIC.00" -> "PIG.10")."""
        total, old = hunt3_set(fold_hunt2)
        self.assertEqual(total, 90531)
        # the reviewer measured 21 under /V/D (probe_hash_structured.py);
        # under /V/B, the path the assembly test uses, 22
        self.assertEqual(len(old), 22)
        self.assertIn((0, 'PIG.10'), old)
        self.assertNotIn(True, ['\0' in n for _, n in old])   # 22 real names
        new = hunt3_set(fold)[1]
        # 1.4 expected at random; the three left all put a byte after the
        # name's terminating zero, which add_entry never writes
        self.assertLessEqual(len(new), 3, new)
        self.assertEqual([n for _, n in new if '\0' not in n], [])
        # every two-byte edit within three positions inside a few names,
        # from the start states their table gives: the bug-hunt-2 fold
        # collided far above chance there
        names = [('PIC.%02d' % k, 6) for k in range(0, 20, 4)] + [('NOTES.TXT', 4), ('A2FILE.CODE', 6)]
        chars = range(0x2E, 0x5B)
        def wide(f):
            total, found = 0, []
            for k, (name, _) in enumerate(names):
                t, c = two_byte_edits(f, names, [k], len(name) - 1, len(name), 3, chars, chars)
                total += t
                found += c
            return total, found
        total, found = wide(fold_hunt2)
        self.assertEqual(total, 218592)                 # 3.3 collisions expected at random
        self.assertEqual(len(found), 68)
        self.assertEqual(wide(fold)[1], [])

    def test_model_and_table_agree(self):
        for full, other, want in PAIRS:
            self.assertEqual(nested(full, other), want, (full, other))

    def test_the_editor_leaves_the_saved_tags_to_keep_tags(self):
        """Bug hunt 2: after E created a new file, edit_entry wiped picked[],
        and the OTHER panel, whose fingerprint still matched, lost its tags
        too. keep_tags alone decides (the "MOVE dropped B0" case of the
        assembly test: the active panel comes back untagged, the other keeps
        its own)."""
        src = (ROOT / 'src/a2fc.c').read_text()
        body = src[src.index('void __fastcall__ edit_entry('):]
        body = body[:body.index('\n}\n')]
        self.assertNotIn('picked', body.replace('picked[]', ''))

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
            (p / 'h.c').write_text(HARNESS.replace('PAIRS', pairs).replace('RANDOM_CASES', c_cases())
                                    .replace('STRUCTURED', c_structured()))
            for target in ('sim6502', 'sim65c02'):
                exe = p / ('t_' + target)
                subprocess.run(['cl65', '-t', target, '-O', '-I', str(ROOT / 'src'), '-o', str(exe),
                                str(p / 'h.c'), str(p / 'tags.s')], check=True, capture_output=True, cwd=p)
                self.assertEqual(subprocess.run(['sim65', str(exe)]).returncode, 0, target)


if __name__ == '__main__':
    unittest.main()
