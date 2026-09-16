"""Run the real C of FIXIT against controlled ProDOS images.

The whole Read chantier, increments 1 to 8 of docs/FIXIT.md section 8:
volume selection and the refusals, the volume header of block 2, the walker
ported from volinfo.c, the thirty named faults, and the findings screen with
its pages, its R and its verdict. The C is compiled by `cc` with -DFIXIT_HOST
and driven over a mock MLI that reads a .po file and `abort()`s on any write
-- in the Read chantier a write is a test failure -- then the image is read
back and compared byte for byte.

The harness keeps what the overlay wrote on the screen (clrscr is a form
feed), answers a scripted key at every cgetc and, on the R of that script,
puts a second image in the drive: a rescan must believe nothing of the pass
before it, which is the whole point of offering it.

Two oracles, and both are used:

  * tools/prodos_check.py on the images tools/corrupt_prodos.py breaks on
    purpose. Only the identifiers the C implements are compared (COMPARED
    below); every other identifier of the oracle is named in CLOSED_BY with
    the increment that will close it, never ignored in silence. A corruption
    whose expected set mixes COMPARED and NOT_YET identifiers is compared on
    the COMPARED ones alone -- plus `complete`, which is a property of the
    whole pass and must always agree.
  * the walker of src/plugins/volinfo.c, compiled from tools/test_volinfo.py's
    own harness and run over the same hand-made images. FIXIT's findings must
    add up to VOLINFO's anonymous counters: `shared` is XLINK, `usedfree` is
    BM_USED_FREE, `lost` is BM_LOST, and `bad` + `counts` is the sum of the
    named faults -- minus, case by case, the arithmetic FIXIT deliberately
    drops for a partial entry (docs/FIXIT.md section 3).
"""
import json
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import corrupt_prodos
import prodos_check
import test_volinfo
from prodos_check import BLOCK, ENTRY_LEN
# The hand-made 280-block helpers, in the shape ProDOS really writes: the
# volume directory over blocks 2 to 5 and the bitmap at 6. test_volinfo.py's
# own copy puts the bitmap at 3 and a single directory block, which FIXIT --
# unlike VOLINFO -- would rightly call VOLDIR_SIZE.
from test_prodos_check import BITMAP, allocated, entry, fixture, mini_entry, ptr, word

# The identifiers the C implements and that match the oracle exactly on
# every corruption of tools/corrupt_prodos.py. Increments 4 to 7 closed the
# last eight: DIR_PARENT, ENT_HEADER_PTR, HDR_NAME, DIR_EOF, FILE_EOF,
# ENT_NAME, ENT_ACCESS and BM_TAIL -- the whole list of the oracle.
COMPARED = {
    'HDR_STORAGE', 'HDR_ENTRY_LEN', 'HDR_PER_BLOCK', 'HDR_BITMAP', 'HDR_TOTAL',
    'DIR_CHAIN', 'DIR_LOOP', 'DIR_HEADER', 'DIR_DEPTH', 'ENT_STORAGE',
    'ENT_KEY', 'FILE_COUNT', 'DIR_BLOCKS', 'FILE_BLOCKS',
    'IDX_RANGE', 'FORK_STORAGE', 'XLINK', 'BM_USED_FREE', 'BM_LOST',
    'IO_ERROR', 'VOLDIR_SIZE', 'BM_RESERVED',
    'DIR_PARENT', 'ENT_HEADER_PTR', 'HDR_NAME', 'DIR_EOF', 'FILE_EOF',
    'ENT_NAME', 'ENT_ACCESS', 'BM_TAIL',
}
# Everything the oracle can still report, and the increment of section 8
# that closes it. Widening COMPARED empties this table; nothing may leave
# it without being implemented. It is empty: the walker names every fault
# tools/prodos_check.py names.
CLOSED_BY = {}
NOT_YET = set(prodos_check.CHECKS) - COMPARED

# What VOLINFO's `bad` and `counts` become once the causes are named.
STRUCTURE = ('DIR_CHAIN', 'DIR_LOOP', 'DIR_HEADER', 'DIR_DEPTH', 'ENT_STORAGE',
             'ENT_KEY', 'IDX_RANGE', 'FORK_STORAGE', 'VOLDIR_SIZE',
             'FILE_COUNT', 'DIR_BLOCKS', 'FILE_BLOCKS')

# The user-facing messages of src/plugins/fixit.c, 79 characters at most.
M_NOTVOL = 'Select a real ProDOS volume.'
M_NOVOL = 'Volume not on line.'
M_BADHDR = 'Invalid volume header: nothing checked.'
M_NOREAD = 'Block 2 could not be read: nothing checked.'
M_CLEAN = 'This volume is consistent: nothing to repair.'
M_FOUND = '%u findings, nothing written: FIXIT only reads.'
M_UNSURE = 'Scan incomplete: lost blocks unconfirmed, freeing refused.'
M_IOERR = 'Read error: this volume was not fully checked.'
M_CANCEL = 'Scan cancelled: no plan from an incomplete scan.'
# The summary line of the findings screen, and the paging prompt. No P and
# no F: those keys belong to the WRITE chantier (docs/FIXIT.md section 6).
M_KEYS = '%u findings.  R rescan  ESC/RETURN back'
M_MORE = 'Key: next / ESC: back'

# Seventeen kinds of fault on one volume, none of them cutting the pass
# short: with the overflow line that is eighteen lines, the page exactly.
# The corruptions left out clobber one another's target entry.
MANY = ('bitmap_free_used', 'bitmap_lost', 'crosslink', 'index_out_of_range',
        'file_count_high', 'dir_blocks_wrong', 'dir_eof_wrong', 'chain_broken',
        'parent_wrong', 'header_ptr_wrong', 'bad_name', 'eof_too_big',
        'fork_bad', 'voldir_size', 'bad_access', 'bitmap_reserved_free',
        'bitmap_tail_set')

HARNESS = r'''
#define __fastcall__
#define FIXIT_HOST
#include "src/plugins/fixit.c"
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>

#define TARGET_UNIT 0xE0
#define BOOT_UNIT   0x50

static FILE* disk;
static FILE* swapped;               /* the disk R will find in the drive */
static FILE* second;                /* a second volume, same session, same BSS */
static const char* keys = "";       /* what cgetc answers, then Escape */
static int keyi, keyn;                 /* how many keys the screen asked for */
static unsigned int reject = 65535U;
static int reads;
static int online = 1;
static int poison;
static char volname[17];

/* READ_BLOCK and ON_LINE only. Any other call -- a WRITE_BLOCK above all --
 * ends the process: the Read chantier writes nothing. A block past the end
 * of the file fails, exactly as a short medium fails on the Apple II. */
static unsigned char mock_mli(unsigned char cmd, void* p) {
    if (cmd == 0xC5) {
        struct Onl* o = p;
        const char* name = online ? volname : "OTHER";
        memset(o->buf, 0, 256);
        o->buf[0] = TARGET_UNIT | (unsigned char)strlen(name);
        memcpy(o->buf + 1, name, strlen(name));
        o->buf[16] = BOOT_UNIT | 6;             /* the program's own volume */
        memcpy(o->buf + 17, "BOOTVL", 6);
        return 0;
    }
    if (cmd != 0x80) abort();
    {
        struct Blk* b = p;
        if (b->unit != TARGET_UNIT) abort();
        ++reads;
        if (b->block == reject) return 0x27;
        if (fseek(disk, (long)b->block * 512, SEEK_SET)) return 0x27;
        return fread(b->buf, 1, 512, disk) == 512 ? 0 : 0x27;
    }
}

static void noop_gotoxy(unsigned char x, unsigned char y) { (void)x; (void)y; }

/* The screen, kept as it was written: the tests read the findings lines,
 * the paging prompt and the summary line off it, exactly as an Apple II
 * shows them. clrscr is a form feed, so a page break is visible. */
static char screen[16384];
static size_t screenn;
static void cap_puts(const char* s) {
    size_t n = strlen(s);
    if (screenn + n < sizeof screen) { memcpy(screen + screenn, s, n); screenn += n; }
}
static void cap_clrscr(void) { cap_puts("\f"); }
static int cap_printf(const char* f, ...) {
    char line[256];
    va_list ap;
    int n;
    va_start(ap, f);
    n = vsnprintf(line, sizeof line, f, ap);
    va_end(ap);
    cap_puts(line);
    return n;
}
/* Nothing zeroes the BSS of an overlay: the core reads the file over
 * whatever the overlay before it left there, and the same FIXIT re-entered
 * from the menu finds its own leftovers. Every static is filled with $AA
 * here, so a field read before it is written shows up as a different
 * answer -- which a fresh host process never could. */
static void poison_bss(void) {
    memset(counts, 0xAA, sizeof counts);
    memset(sample, 0xAA, sizeof sample);
    memset(seen, 0xAA, sizeof seen);
    memset(blk, 0xAA, sizeof blk);
    memset(stack, 0xAA, sizeof stack);
    memset(forks, 0xAA, sizeof forks);
    memset(volume, 0xAA, sizeof volume);
    memset(boot, 0xAA, sizeof boot);
    memset(nm, 0xAA, sizeof nm);
    memset(&io, 0xAA, sizeof io);
    memset(&onl, 0xAA, sizeof onl);
    nsample = overflow = complete = failed = cancelled = 0xAA;
    depth = partial = row = curslot = unit = isboot = 0xAA;
    found = curblock = total = bitmap = pages = base = span = 0xAAAA;
    budget = cached = fileblocks = 0xAAAA;
    rootbad = rootfifth = rootlen = rootlast = 0xAAAA;
    rootdone = 0xAA;
    entry = 0; buf = 0;                 /* a premature read faults, not drifts */
}

static void print_screen(void) {
    size_t i;
    for (i = 0; i < screenn; ++i) {
        unsigned char c = (unsigned char)screen[i];
        if (c == '\r') printf("\\r");
        else if (c == '\n') printf("\\n");
        else if (c == '\f') printf("\\f");
        else if (c == '"' || c == '\\') printf("\\%c", c);
        else if (c < 32 || c > 126) printf("\\u%04x", c);
        else putchar(c);
    }
}

/* The keys of the findings screen, then Escape for ever. A rescan is what
 * the user asks for after changing the disk, so the R of the script also
 * puts the second image in the drive: the pass that follows must believe
 * nothing of the one before it. */
static char key_script(void) {
    char k = 27;
    ++keyn;
    if (keys[keyi]) k = keys[keyi++];
    if ((k == 'R' || k == 'r') && swapped) {
        fclose(disk); disk = swapped; swapped = 0;
    }
    return k;
}

int main(int argc, char** argv) {
    static struct A2fcApi api;
    static struct Panel panels[2];
    static struct Entry selected;
    static unsigned char active;
    static unsigned char scratch[512];
    static char note[80];
    static unsigned char head[512];
    const char* mode;
    int i, first;

    if (argc < 2) return 2;
    disk = fopen(argv[1], "rb");
    if (!disk) return 2;
    mode = argc > 2 ? argv[2] : "run";
    if (argc > 3 && argv[3][0]) reject = (unsigned int)atoi(argv[3]);
    if (argc > 4) keys = argv[4];
    if (argc > 5 && argv[5][0]) {
        swapped = fopen(argv[5], "rb");
        if (!swapped) return 2;
    }
    if (argc > 6 && argv[6][0]) {       /* a second volume in the same session */
        second = fopen(argv[6], "rb");
        if (!second) return 2;
    }
    if (argc > 7 && argv[7][0]) poison = 1;

    /* The volume name ON_LINE answers with, straight from block 2 -- not
     * through mock_mli, so it does not count as a read of the overlay. */
    if (fseek(disk, 1024, SEEK_SET) || fread(head, 1, 512, disk) != 512) return 2;
    i = head[4] & 15;
    memcpy(volname, head + 5, i);
    volname[i] = 0;

    api.mli = mock_mli; api.memset = memset; api.memcpy = memcpy;
    api.strcpy = strcpy; api.strcmp = strcmp;
    api.clrscr = cap_clrscr; api.cputs = cap_puts; api.cprintf = cap_printf;
    api.gotoxy = noop_gotoxy; api.cgetc = key_script; api.sprintf = sprintf;
    api.panels = panels; api.active = &active; api.selected = &selected;
    api.copy_buf = scratch; api.note = note;
    api.cfg_path = "/BOOTVL/A2FILE/A2FILE.CFG";

    /* One session, one or two volumes: the second run of plugin_entry finds
     * the BSS the first one left, exactly as the cached overlay does when
     * the menu calls it again. Only the last run is reported. */
    for (;;) {
        memset(panels, 0, sizeof panels);
        memset(&selected, 0, sizeof selected);
        if (!strcmp(mode, "fs")) {
            panels[0].fs = 1;
            sprintf(panels[0].path, "/%s", volname);
        } else if (!strcmp(mode, "notvol")) {
            strcpy(selected.name, "NOTAVOL");
        } else if (!strcmp(mode, "vlist")) {
            sprintf(selected.name, "/%s", volname);
            selected.mdate = TARGET_UNIT >> 4;
        } else {
            if (!strcmp(mode, "offline")) online = 0;
            if (!strcmp(mode, "subdir")) sprintf(panels[0].path, "/%s/SUB", volname);
            else sprintf(panels[0].path, "/%s", volname);
        }
        if (poison) poison_bss();
        plugin_entry(&api);
        if (!second) break;
        fclose(disk); disk = second; second = 0;
        if (fseek(disk, 1024, SEEK_SET) || fread(head, 1, 512, disk) != 512) return 2;
        i = head[4] & 15;
        memcpy(volname, head + 5, i);
        volname[i] = 0;
        screenn = 0; keyi = 0; keyn = 0; reads = 0;
    }

    printf("{\"complete\":%u,\"overflow\":%u,\"failed\":%u,\"reads\":%d,"
           "\"unit\":%u,\"isboot\":%u,\"found\":%u,\"keys\":%d,\"note\":\"%s\",\"counts\":{",
           complete, overflow, failed, reads, unit, isboot, found, keyn, note);
    for (i = 0, first = 1; i < CHK_COUNT; ++i) {
        if (!counts[i]) continue;
        printf("%s\"%s\":%u", first ? "" : ",", chkname(i), counts[i]);
        first = 0;
    }
    printf("},\"samples\":[");
    for (i = 0; i < nsample; ++i) {
        printf("%s{\"id\":\"%s\",\"block\":%u,\"slot\":", i ? "," : "",
               chkname(sample[i].id & ~NO_SLOT_BIT), sample[i].block);
        if (sample[i].id & NO_SLOT_BIT) printf("null}");
        else printf("%u}", sample[i].slot);
    }
    printf("],\"screen\":\"");
    print_screen();
    printf("\"}\n");
    fclose(disk);
    return 0;
}
'''


def only_compared(counts):
    """The counters of the identifiers these increments implement."""
    return {k: v for k, v in counts.items() if k in COMPARED}


def oracle_counts(findings):
    return only_compared(Counter(f.id for f in findings))


def first_samples(samples):
    """The first sample of each identifier, in the order FIXIT found them."""
    out = {}
    for s in samples:
        out.setdefault(s['id'], (s['block'], s['slot']))
    return out


def strip_repair(text):
    """The text with every `#ifdef REPAIR` part taken out, as cpp takes it.

    The walker lives in src/plugins/fixit_walk.h and is shared with
    src/plugins/repair.c; only the parts REPAIR does not select are FIXIT's.
    Conditions that name anything else are left alone, body and all.
    """
    out, stack = [], []
    for line in text.split('\n'):
        bare = line.strip()
        if bare.startswith('#if'):
            if bare in ('#ifdef REPAIR', '#if defined(REPAIR)'):
                stack.append(False)
            elif bare == '#ifndef REPAIR':
                stack.append(True)
            else:
                stack.append(None)
            continue
        if bare == '#else' and stack and stack[-1] is not None:
            stack[-1] = not stack[-1]
            continue
        if bare == '#endif' and stack:
            if stack.pop() is not None:
                continue
        if False not in stack:
            out.append(line)
    return '\n'.join(out)


def fixit_source():
    """The C that FIXIT really compiles: its own file and its walker."""
    return ((ROOT / 'src/plugins/fixit.c').read_text()
            + strip_repair((ROOT / 'src/plugins/fixit_walk.h').read_text()))


def pages(screen):
    """The screen, cut where clrscr cleared it: the pages the user saw."""
    return [p.split('\r\n') for p in screen.split('\f') if p]


def first_findings(findings):
    """The oracle's first finding per identifier, in the order it walked."""
    out = {}
    for f in findings:
        out.setdefault(f.id, (f.block, f.slot))
    return out


# -- the hand-made images, the ones test_volinfo.py walks --------------------
def subdir_header(d, block, parent, pslot, count=1):
    """The header of a subdirectory in its key block: $E, 39, 13."""
    head = entry(0xE, b'D', key=0, blocks=0, eof=0, header=0)
    head[0x1F], head[0x20] = ENTRY_LEN, 13
    word(head, 0x21, count)
    word(head, 0x23, parent)
    head[0x25], head[0x26] = pslot + 1, ENTRY_LEN
    d[block * BLOCK + 4:block * BLOCK + 4 + ENTRY_LEN] = head


def f_empty():
    return fixture()


def f_seedling():
    d = fixture(entries=[entry(1, b'A', key=7)])
    allocated(d, 7)
    return d


def f_lost():
    d = fixture()
    allocated(d, 40)
    return d


def f_used_marked_free():
    return fixture(entries=[entry(1, b'A', key=7)])      # block 7 stays free


def f_shared():
    d = fixture(entries=[entry(1, b'A', key=7), entry(1, b'B', key=7)])
    allocated(d, 7)
    return d


def f_sapling_sparse():
    d = fixture(entries=[entry(2, b'S', key=11, blocks=3, eof=1536)])
    ptr(d, 11, 0, 12)
    ptr(d, 11, 2, 14)
    for b in (11, 12, 14):
        allocated(d, b)
    return d


def f_tree():
    d = fixture(entries=[entry(3, b'T', key=11, blocks=3, eof=1024)])
    ptr(d, 11, 0, 12)
    ptr(d, 12, 0, 13)
    for b in (11, 12, 13):
        allocated(d, b)
    return d


def f_extended():
    d = fixture(entries=[entry(5, b'E', key=11, blocks=3, eof=300)])
    mini_entry(d, 11, 0, 1, 12, 1, 300)
    mini_entry(d, 11, 256, 1, 13, 1, 64)
    for b in (11, 12, 13):
        allocated(d, b)
    return d


def f_subdirectory():
    d = fixture(entries=[entry(0xD, b'D', key=11, blocks=1, eof=BLOCK)])
    subdir_header(d, 11, 2, 1)
    d[11 * BLOCK + 4 + ENTRY_LEN:11 * BLOCK + 4 + 2 * ENTRY_LEN] = \
        entry(1, b'N', key=12, header=11)
    allocated(d, 11)
    allocated(d, 12)
    return d


def f_counts():
    d = fixture(entries=[entry(1, b'A', key=7, blocks=2)])
    allocated(d, 7)
    word(d, 1061, 2)                                     # one entry, two claimed
    return d


def f_out_of_range():
    return fixture(entries=[entry(1, b'A', key=280)])


def f_cycle():
    d = fixture()
    word(d, 5 * BLOCK + 2, 2)                            # block 5 loops back
    return d


def f_unknown_storage():
    return fixture(entries=[entry(4, b'A', key=7)])


def f_missing_key():
    return fixture(entries=[entry(1, b'A', key=0, blocks=0)])


def f_index_out_of_range():
    d = fixture(entries=[entry(2, b'S', key=11, blocks=2, eof=1024)])
    ptr(d, 11, 0, 12)
    ptr(d, 11, 1, 300)                                   # past the volume
    for b in (11, 12):
        allocated(d, b)
    return d


def f_fork_bad():
    d = fixture(entries=[entry(5, b'E', key=11, blocks=3, eof=300)])
    mini_entry(d, 11, 0, 4, 12, 1, 300)                  # an impossible type
    mini_entry(d, 11, 256, 1, 13, 1, 64)
    for b in (11, 12, 13):
        allocated(d, b)
    return d


def f_depth():
    """Seventeen nested directories: the walk stops at the sixteenth."""
    first = BITMAP + 1
    d = fixture(64, [entry(0xD, b'D', key=first, blocks=1, eof=BLOCK)])
    parent, pslot = 2, 1
    for level in range(17):
        block = first + level
        allocated(d, block)
        if level:
            e = entry(0xD, b'D', key=block, blocks=1, eof=BLOCK, header=parent)
            d[parent * BLOCK + 4 + pslot * ENTRY_LEN:
              parent * BLOCK + 4 + (pslot + 1) * ENTRY_LEN] = e
        subdir_header(d, block, parent, pslot)
        parent, pslot = block, 1
    d[parent * BLOCK + 4 + ENTRY_LEN] = 0                # the deepest is empty
    word(d, parent * BLOCK + 4 + 0x21, 0)
    return d


def f_window_boundary_shared():
    d = fixture(8193, [entry(1, b'A', key=4096), entry(1, b'B', key=4096)])
    allocated(d, 4096)
    return d


def put(d, block, slot, e):
    """One entry at a chosen slot of a chosen directory block."""
    off = block * BLOCK + 4 + slot * ENTRY_LEN
    d[off:off + ENTRY_LEN] = e


def f_extended_two_saplings():
    """Both forks are saplings: the key block and an index share copy_buf."""
    d = fixture(entries=[entry(5, b'E', key=11, blocks=7, eof=300)])
    mini_entry(d, 11, 0, 2, 12, 3, 1024)
    ptr(d, 12, 0, 13)
    ptr(d, 12, 1, 14)
    mini_entry(d, 11, 256, 2, 15, 3, 1024)
    ptr(d, 15, 0, 16)
    ptr(d, 15, 1, 17)
    for b in (11, 12, 13, 14, 15, 16, 17):
        allocated(d, b)
    return d


def f_extended_tree_fork():
    """A tree fork: its master index lands in blk, over the directory block."""
    d = fixture(entries=[entry(5, b'E', key=11, blocks=5, eof=300),
                         entry(1, b'B', key=30)])
    mini_entry(d, 11, 0, 3, 12, 3, 1024)
    ptr(d, 12, 0, 13)
    ptr(d, 13, 0, 14)
    mini_entry(d, 11, 256, 1, 15, 1, 200)
    for b in (11, 12, 13, 14, 15, 30):
        allocated(d, b)
    return d


def f_tree_then_files():
    """A tree, then two more entries of the same directory block."""
    d = fixture(entries=[entry(3, b'T', key=11, blocks=3, eof=1024),
                         entry(1, b'A', key=20),
                         entry(2, b'S', key=21, blocks=2, eof=600)])
    ptr(d, 11, 0, 12)
    ptr(d, 12, 0, 13)
    ptr(d, 21, 0, 22)
    for b in (11, 12, 13, 20, 21, 22):
        allocated(d, b)
    return d


def f_tree_last_of_a_block():
    """The last entry of block 2 is a tree, and the chain goes on to block 3."""
    d = fixture()
    put(d, 2, 12, entry(3, b'T', key=11, blocks=3, eof=1024))
    ptr(d, 11, 0, 12)
    ptr(d, 12, 0, 13)
    put(d, 3, 0, entry(1, b'A', key=20))
    for b in (11, 12, 13, 20):
        allocated(d, b)
    word(d, 1061, 2)
    return d


# (name, image, the VOLINFO increments FIXIT names otherwise or not at all)
#
# `drops` is the arithmetic of a partial entry: VOLINFO counts the cause AND
# the block total that follows from it, FIXIT names the cause alone
# (docs/FIXIT.md section 3, "entree partielle").
# `shared` is a directory block VOLINFO discovers by claiming it twice and
# calls a shared block; FIXIT sees the chain lead back into what it has
# already walked and calls it DIR_LOOP, as tools/prodos_check.py does.
CASES = (
    ('empty', f_empty, 0, 0),
    ('seedling', f_seedling, 0, 0),
    ('lost block', f_lost, 0, 0),
    ('used marked free', f_used_marked_free, 0, 0),
    ('shared block', f_shared, 0, 0),
    ('sapling with a hole', f_sapling_sparse, 0, 0),
    ('tree', f_tree, 0, 0),
    ('extended forks', f_extended, 0, 0),
    ('subdirectory', f_subdirectory, 0, 0),
    ('count mismatches', f_counts, 0, 0),
    ('key out of range', f_out_of_range, 0, 0),
    ('directory cycle', f_cycle, 0, 1),
    ('unknown storage', f_unknown_storage, 1, 0),
    ('missing key', f_missing_key, 0, 0),
    ('index pointer out of range', f_index_out_of_range, 1, 0),
    ('bad extended fork', f_fork_bad, 1, 0),
    ('depth limit', f_depth, 0, 0),
    ('window boundary', f_window_boundary_shared, 0, 0),
    ('extended with two saplings', f_extended_two_saplings, 0, 0),
    ('extended with a tree fork', f_extended_tree_fork, 0, 0),
    ('a tree, then more entries', f_tree_then_files, 0, 0),
    ('a tree last in its block', f_tree_last_of_a_block, 0, 0),
)


class Fixit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='fixit-test-')
        cls.work = Path(cls.tmp.name)
        source = cls.work / 'fixit_host.c'
        source.write_text(HARNESS)
        cls.exe = cls.work / 'fixit_host'
        subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-I', str(ROOT),
                        str(source), '-o', str(cls.exe)], check=True, capture_output=True)
        walker = cls.work / 'volinfo_host.c'
        walker.write_text(test_volinfo.HARNESS)
        cls.volinfo = cls.work / 'volinfo_host'
        subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-I', str(ROOT),
                        str(walker), '-o', str(cls.volinfo)], check=True, capture_output=True)
        cls.clean = corrupt_prodos.make_fixture(cls.work).read_bytes()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_fixit(self, data, mode='run', reject=None, keys='', swap=None,
                  after=None, poison=False):
        """FIXIT over `data`; the image must come back byte for byte.

        `keys` is what the findings screen reads, Escape once it runs out;
        `swap` is a second image the R of that script puts in the drive;
        `after` is a second volume plugin_entry is called on in the SAME
        process, with the BSS the first call left -- what the cached overlay
        really sees when the menu runs it again, and what a fresh host
        process can never show. `poison` fills every static with $AA first.
        """
        path = self.work / 'disk.po'
        path.write_bytes(data)
        args = [str(self.exe), str(path), mode, '' if reject is None else str(reject), keys]
        images = [(path, data)]
        for extra, name in ((swap, 'disk2.po'), (after, 'disk3.po')):
            if extra is None:
                args.append('')
                continue
            other = self.work / name
            other.write_bytes(extra)
            images.append((other, extra))
            args.append(str(other))
        args.append('X' if poison else '')
        out = subprocess.check_output(args, timeout=300)
        for where, expected in images:
            self.assertEqual(where.read_bytes(), expected, 'FIXIT must never write')
        return json.loads(out)

    def run_volinfo(self, data):
        """The same image through the walker of volinfo.c."""
        path = self.work / 'volinfo.po'
        path.write_bytes(data)
        out = subprocess.check_output([str(self.volinfo), str(path)], timeout=120)
        self.assertEqual(path.read_bytes(), data, 'the audit must never write')
        return json.loads(out)

    @property
    def volname(self):
        """The name block 2 gives itself, which ON_LINE answers with too."""
        n = self.clean[2 * BLOCK + 4] & 15
        return '/' + self.clean[2 * BLOCK + 5:2 * BLOCK + 5 + n].decode()

    def many_faults(self):
        """Seventeen kinds of fault at once, and a pass that still ends."""
        data = bytearray(self.clean)
        corrupt_prodos.apply(data, list(MANY))
        result = prodos_check.check(bytes(data))
        self.assertEqual(len({f.id for f in result.findings}), 17,
                         'seventeen lines are what this test is about')
        self.assertTrue(result.complete)
        return bytes(data), result

    def corrupted(self, name):
        """The corrupt image, plus the two halves of the host oracle agreeing."""
        data = bytearray(self.clean)
        expect = corrupt_prodos.apply(data, [name])
        result = prodos_check.check(bytes(data))
        self.assertEqual(oracle_counts(expect.findings), oracle_counts(result.findings),
                         (name, 'corrupt_prodos and prodos_check disagree'))
        return bytes(data), result

    # -- the clean volume ---------------------------------------------------
    def test_clean_volume_has_no_finding_at_all(self):
        result = prodos_check.check(self.clean)
        self.assertEqual(result.findings, [], 'the fixture must be healthy')
        r = self.run_fixit(self.clean)
        self.assertEqual(r['counts'], {}, r)
        self.assertEqual(r['samples'], [])
        self.assertEqual(r['complete'], 1)
        self.assertEqual(r['overflow'], 0)
        self.assertEqual(r['note'], M_CLEAN)
        self.assertEqual(r['unit'], 0xE0)
        self.assertEqual(r['isboot'], 0)

    def test_volume_of_a_subdirectory_path_is_the_one_checked(self):
        r = self.run_fixit(self.clean, 'subdir')
        self.assertEqual(r['unit'], 0xE0)
        self.assertEqual(r['counts'], {})

    def test_volume_list_entry_selects_by_unit(self):
        r = self.run_fixit(self.clean, 'vlist')
        self.assertEqual(r['unit'], 0xE0)
        self.assertEqual(r['counts'], {})
        self.assertEqual(r['note'], M_CLEAN)

    # -- increment 2: the walker against the one it comes from --------------
    def test_walker_totals_are_volinfos_totals(self):
        """FIXIT's named findings add up to VOLINFO's anonymous counters."""
        for name, build, drops, shared in CASES:
            with self.subTest(fixture=name):
                data = bytes(build())
                v = self.run_volinfo(data)
                r = self.run_fixit(data)
                c, complete = r['counts'], r['complete']
                self.assertEqual(v['shared'], c.get('XLINK', 0) + shared, (name, v, c))
                self.assertEqual(v['usedfree'], c.get('BM_USED_FREE', 0), (name, v, c))
                if complete:
                    self.assertEqual(v['lost'], c.get('BM_LOST', 0), (name, v, c))
                else:
                    self.assertEqual(c.get('BM_LOST', 0), 0,
                                     (name, 'an incomplete pass never reports a lost block'))
                self.assertEqual(v['bad'] + v['counts'],
                                 sum(c.get(k, 0) for k in STRUCTURE) + drops, (name, v, c))

    def test_an_incomplete_walk_is_one_volinfo_also_refuses(self):
        for name, build, _, _shared in CASES:
            with self.subTest(fixture=name):
                data = bytes(build())
                v = self.run_volinfo(data)
                r = self.run_fixit(data)
                if not r['complete']:
                    self.assertTrue(v['incomplete'] or v['failed'], (name, v, r))

    def test_the_sample_table_keeps_the_first_sixteen_and_says_so(self):
        """Seventeen lost blocks: sixteen samples, the counter, the flag."""
        d = fixture()
        for b in range(40, 57):
            allocated(d, b)
        r = self.run_fixit(bytes(d))
        self.assertEqual(r['counts'], {'BM_LOST': 17}, r)
        self.assertEqual(len(r['samples']), 16)
        self.assertEqual(r['overflow'], 1)
        self.assertEqual(r['samples'][0], {'id': 'BM_LOST', 'block': 40, 'slot': None})

    def test_a_directory_fault_is_reported_once_over_every_window(self):
        """Three windows, one broken back-pointer: one DIR_CHAIN, not three."""
        d = fixture(8193)
        word(d, 3 * BLOCK, 999)
        r = self.run_fixit(bytes(d))
        self.assertEqual(r['counts'].get('DIR_CHAIN'), 1, r)
        self.assertEqual(r['samples'][0], {'id': 'DIR_CHAIN', 'block': 3, 'slot': None})

    # -- increments 1 to 3: every corruption of the oracle -------------------
    def test_every_corruption_matches_the_oracle_on_what_is_implemented(self):
        for name in corrupt_prodos.CORRUPTIONS:
            with self.subTest(corruption=name):
                data, result = self.corrupted(name)
                r = self.run_fixit(data)
                self.assertEqual(only_compared(r['counts']),
                                 oracle_counts(result.findings), (name, r))
                self.assertEqual(bool(r['complete']), result.complete, (name, r))
                mine = first_samples(r['samples'])
                theirs = first_findings(result.findings)
                for id in only_compared(r['counts']):
                    self.assertEqual(mine[id], theirs[id], (name, id, r))

    def test_header_corruptions_stop_before_the_walk(self):
        for name in ('hdr_storage', 'hdr_entry_len', 'hdr_bitmap_bad'):
            with self.subTest(corruption=name):
                data, result = self.corrupted(name)
                r = self.run_fixit(data)
                self.assertEqual(r['note'], M_BADHDR)

    def test_identifiers_left_to_later_increments_are_declared(self):
        """No identifier of the oracle is ignored without being named."""
        self.assertEqual(COMPARED | NOT_YET, set(prodos_check.CHECKS))
        self.assertFalse(COMPARED & NOT_YET)
        self.assertEqual(NOT_YET, set(CLOSED_BY), 'name the increment that closes it')
        self.assertFalse(NOT_YET, 'increments 4 to 7 closed the last eight')

    # -- HDR_TOTAL on a short medium ----------------------------------------
    def short_medium(self, blocks):
        """The image truncated: READ_BLOCK fails past the end, as a disk does."""
        data = self.clean[:blocks * BLOCK]
        result = prodos_check.check(data)
        self.assertIn('HDR_TOTAL', {f.id for f in result.findings},
                      'the oracle must see the medium is shorter than the header says')
        return data, result

    def test_a_medium_shorter_than_the_header_says_is_hdr_total(self):
        """Only the refusal is comparable here.

        FIXIT checks nothing else once the header is refused; the oracle,
        which has the whole image in hand, substitutes its length for the
        impossible total and walks on -- and then calls the bitmap's bits
        for the blocks past that substituted total BM_TAIL. Those are an
        artefact of its substitution, not a fault of the volume: the two
        agree on HDR_TOTAL, which is all this image can be judged on.
        """
        data, result = self.short_medium(1592)
        r = self.run_fixit(data)
        self.assertEqual(r['counts'], {'HDR_TOTAL': 1}, r)
        self.assertEqual(bool(r['complete']), result.complete, r)
        self.assertEqual(r['note'], M_BADHDR)
        self.assertEqual(r['samples'], [{'id': 'HDR_TOTAL', 'block': 2, 'slot': 0}])

    def test_a_declared_total_under_six_blocks_is_hdr_total(self):
        data = bytearray(self.clean)
        word(data, 2 * BLOCK + 4 + 0x25, 5)
        r = self.run_fixit(bytes(data))
        self.assertEqual(r['counts'], {'HDR_TOTAL': 1}, r)
        self.assertEqual(r['reads'], 1, 'the last block is not even looked for')

    # -- the refusals -------------------------------------------------------
    def test_image_or_dos33_panel_is_refused_without_reading(self):
        r = self.run_fixit(self.clean, 'fs')
        self.assertEqual(r['note'], M_NOTVOL)
        self.assertEqual(r['reads'], 0)
        self.assertEqual(r['counts'], {})

    def test_a_path_that_is_not_a_volume_is_refused_without_reading(self):
        r = self.run_fixit(self.clean, 'notvol')
        self.assertEqual(r['note'], M_NOTVOL)
        self.assertEqual(r['reads'], 0)

    def test_a_volume_not_on_line_is_refused_without_reading(self):
        r = self.run_fixit(self.clean, 'offline')
        self.assertEqual(r['note'], M_NOVOL)
        self.assertEqual(r['reads'], 0)
        self.assertEqual(r['unit'], 0)

    # -- read errors ---------------------------------------------------------
    def test_read_error_on_block_two_is_io_error(self):
        r = self.run_fixit(self.clean, 'run', 2)
        self.assertEqual(r['counts'], {'IO_ERROR': 1})
        self.assertEqual(r['complete'], 0)
        self.assertEqual(r['failed'], 1)
        self.assertEqual(r['samples'], [{'id': 'IO_ERROR', 'block': 2, 'slot': None}])
        self.assertEqual(r['note'], M_NOREAD)
        self.assertEqual(r['reads'], 1, 'nothing is read past the failed block 2')

    def test_read_error_during_the_walk_stops_the_pass(self):
        """One IO_ERROR naming the block, no lost blocks, an incomplete pass."""
        inv = corrupt_prodos.Inventory(self.clean)
        target = inv.first(prodos_check.SUBDIR).key
        r = self.run_fixit(self.clean, 'run', target)
        self.assertEqual(r['counts'], {'IO_ERROR': 1}, r)
        self.assertEqual(r['complete'], 0)
        self.assertEqual(r['failed'], 1)
        self.assertEqual(r['samples'], [{'id': 'IO_ERROR', 'block': target, 'slot': None}])
        self.assertEqual(r['note'], M_IOERR)

    def test_a_read_error_never_becomes_a_lost_block(self):
        d = f_lost()                                     # block 40 would be lost
        r = self.run_fixit(bytes(d), 'run', 4)           # a volume directory block
        self.assertEqual(r['counts'], {'IO_ERROR': 1}, r)
        self.assertEqual(r['complete'], 0)

    # -- the program's own volume -------------------------------------------
    def test_the_program_volume_is_recognised_for_the_write_chantier(self):
        """Reading it is allowed; the flag is what the WRITE chantier needs."""
        data = bytearray(self.clean)
        name = b'BOOTVL'
        offset = 2 * BLOCK + 4
        data[offset] = 0xF0 | len(name)
        data[offset + 1:offset + 1 + len(name)] = name
        r = self.run_fixit(bytes(data))
        self.assertEqual(r['isboot'], 1, r)
        self.assertEqual(r['note'], M_CLEAN)

    # -- increment 8: the findings screen, its keys and R --------------------
    def test_the_screen_is_the_one_section_six_describes(self):
        """A clean volume: the scan page, then the findings page and its keys."""
        r = self.run_fixit(self.clean)
        scan, screen = pages(r['screen'])
        self.assertEqual(scan, ['FIXIT %s - READ ONLY' % self.volname, '',
                                'Scanning... ESC cancels.', ''], scan)
        self.assertEqual(screen, ['FIXIT %s - READ ONLY' % self.volname, '', '',
                                  M_KEYS % 0], screen)

    def test_a_finding_line_names_the_check_its_count_and_where(self):
        """One line per non-zero check: id, count, first block, slot if any."""
        data = bytearray(self.clean)
        corrupt_prodos.apply(data, ['bitmap_lost', 'file_count_high'])
        r = self.run_fixit(bytes(data))
        screen = pages(r['screen'])[-1]
        self.assertEqual(screen[2:], ['FILE_COUNT  1  block 2 slot 0',
                                      'BM_LOST  1  block 322', '',
                                      M_KEYS % 2], screen)

    def test_seventeen_kinds_of_fault_at_once_still_match_the_oracle(self):
        data, result = self.many_faults()
        r = self.run_fixit(data)
        self.assertEqual(r['counts'], oracle_counts(result.findings), r)
        self.assertEqual(bool(r['complete']), result.complete, r)
        self.assertEqual(r['found'], len(result.findings), r)

    def test_eighteen_lines_fill_a_page_and_the_rest_waits_for_a_key(self):
        """The sixteen samples run out too: the last check shows a count alone."""
        data, result = self.many_faults()
        r = self.run_fixit(data, keys='X')
        self.assertEqual(r['overflow'], 1, 'more findings than the table holds')
        page = pages(r['screen'])[1]
        body = page[2:2 + 18]
        self.assertEqual(len(body), 18, page)
        self.assertEqual(body[-1], 'more findings than the table holds', body)
        self.assertEqual({l.split()[0] for l in body[:-1]},
                         {f.id for f in result.findings}, body)
        self.assertEqual(body[-2], 'BM_TAIL  1',
                         'no sample left: the counter alone, as section 4 says')
        self.assertEqual(page[2 + 18], M_MORE, page)
        self.assertEqual(r['keys'], 2, 'the page key, then the key of the summary')
        self.assertEqual(pages(r['screen'])[2], ['', M_KEYS % r['found']])

    def test_escape_on_a_full_page_leaves_at_once(self):
        data, _ = self.many_faults()
        r = self.run_fixit(data, keys='')
        self.assertEqual(r['keys'], 1, 'Escape at the page prompt is the way out')
        self.assertEqual(pages(r['screen'])[-1][-1], M_MORE)
        self.assertEqual(r['note'], M_FOUND % r['found'])

    def test_the_verdict_of_a_broken_volume_counts_the_findings(self):
        data, result = self.corrupted('bitmap_lost')
        r = self.run_fixit(data)
        self.assertEqual(r['found'], sum(r['counts'].values()), r)
        self.assertEqual(r['found'], len(result.findings), r)
        self.assertEqual(r['note'], M_FOUND % r['found'], r)

    def test_r_scans_again_and_keeps_nothing_of_the_pass_before(self):
        """The disk may have been swapped: the second pass believes nothing."""
        broken, result = self.corrupted('bitmap_lost')
        r = self.run_fixit(broken, keys='R', swap=self.clean)
        self.assertEqual(r['counts'], {}, ('a clean disk after a broken one', r))
        self.assertEqual(r['samples'], [], 'no sample of the pass before')
        self.assertEqual(r['found'], 0, r)
        self.assertEqual(r['complete'], 1)
        self.assertEqual(r['note'], M_CLEAN, r)

    def test_r_reports_the_disk_that_is_there_now(self):
        broken, result = self.corrupted('bitmap_lost')
        r = self.run_fixit(self.clean, keys='R', swap=broken)
        self.assertEqual(only_compared(r['counts']), oracle_counts(result.findings), r)
        self.assertEqual(bool(r['complete']), result.complete, r)
        mine = first_samples(r['samples'])
        theirs = first_findings(result.findings)
        for id in only_compared(r['counts']):
            self.assertEqual(mine[id], theirs[id], (id, r))
        self.assertEqual(r['note'], M_FOUND % r['found'], r)

    def test_two_rescans_of_the_same_broken_disk_report_the_same_thing(self):
        """Nothing accumulates: the counters are emptied by every pass."""
        broken, _ = self.corrupted('file_count_high')
        once = self.run_fixit(broken)
        twice = self.run_fixit(broken, keys='rr')
        self.assertEqual(twice['counts'], once['counts'], (once, twice))
        self.assertEqual(twice['samples'], once['samples'])
        self.assertEqual(twice['found'], once['found'])
        self.assertEqual(twice['note'], once['note'])

    def test_an_unknown_key_only_redraws_the_findings(self):
        data, _ = self.corrupted('bitmap_lost')
        once = self.run_fixit(data)
        again = self.run_fixit(data, keys='X')
        self.assertEqual(again['counts'], once['counts'])
        self.assertEqual(again['reads'], once['reads'], 'a redraw reads no block')

    def test_the_summary_line_offers_no_key_the_read_chantier_has_not(self):
        src = fixit_source()
        self.assertIn(M_KEYS, src)
        for absent in ('P plan', 'F fix', 'E export'):
            self.assertNotIn(absent, src, 'that key belongs to a later chantier')

    def test_the_read_chantier_opens_no_file_at_all(self):
        """E export is deferred (docs/FIXIT.md section 4): nothing is written.

        The harness gives FIXIT no fopen and aborts on any MLI call but
        READ_BLOCK and ON_LINE; this pins the source itself.
        """
        src = fixit_source()
        for absent in ('fopen', 'fwrite', 'fclose', 'v_mli(0xC0', 'v_mli(0x81'):
            self.assertNotIn(absent, src, 'the Read chantier creates no file')

    # -- the two buffers: what may be read over what -------------------------
    def test_the_two_buffers_never_lose_what_is_still_needed(self):
        """blk and copy_buf hold four things each: none is read over too soon.

        An extended file whose forks are saplings (key block then index, both
        in copy_buf), a tree whose master index lands in blk over the
        directory block, a tree followed by more entries of that same block,
        and a tree as the last entry of a block whose chain goes on.
        """
        for name, build in (('extended, two saplings', f_extended_two_saplings),
                            ('extended, a tree fork', f_extended_tree_fork),
                            ('a tree, then more entries', f_tree_then_files),
                            ('a tree last in its block', f_tree_last_of_a_block)):
            with self.subTest(fixture=name):
                data = bytes(build())
                self.assertEqual(prodos_check.check(data).findings, [],
                                 (name, 'the fixture must be healthy'))
                r = self.run_fixit(data)
                self.assertEqual(r['counts'], {}, (name, r))
                self.assertEqual(r['complete'], 1, (name, r))

    # -- the frames: the entry that named a directory ------------------------
    def naming_entry(self, places):
        """Subdirectories whose entries sit where `places` says, all wrong.

        DIR_BLOCKS and DIR_EOF are read from the entry in the PARENT, which
        the walk rereads when it pops the child: the block and the slot it
        names must be the entry's own, not the parent's current chain block.
        """
        d = fixture()
        key = 20
        for block, slot in places:
            put(d, block, slot, entry(0xD, b'S', key=key, blocks=7, eof=9999,
                                      header=2))
            subdir_header(d, key, block, slot, count=0)
            allocated(d, key)
            key += 1
        word(d, 1061, len(places))
        data = bytes(d)
        result = prodos_check.check(data)
        r = self.run_fixit(data)
        self.assertEqual(only_compared(r['counts']), oracle_counts(result.findings),
                         (places, r))
        self.assertEqual(first_samples(r['samples']), first_findings(result.findings),
                         (places, r))
        return r

    def test_a_subdirectory_named_from_a_later_block_of_its_parent(self):
        r = self.naming_entry([(3, 0)])
        self.assertEqual(first_samples(r['samples'])['DIR_BLOCKS'], (3, 0))

    def test_two_subdirectories_named_from_two_blocks_of_the_parent(self):
        """One entry last in block 2, one in the middle of block 4."""
        r = self.naming_entry([(2, 12), (4, 3)])
        self.assertEqual(r['counts']['DIR_BLOCKS'], 2, r)
        self.assertEqual([(s['block'], s['slot']) for s in r['samples']
                          if s['id'] == 'DIR_BLOCKS'], [(2, 12), (4, 3)], r)

    # -- the bitmap at the two ends of the window arithmetic -----------------
    def test_the_last_bitmap_page_of_the_largest_volume(self):
        """65 535 blocks: sixteen windows, the last 4 095 wide, one pad bit."""
        d = fixture(65535)
        allocated(d, 65000)                              # lost, in the last window
        last = BITMAP + 15
        d[last * BLOCK + ((65535 - 61440) >> 3)] |= 0x80 >> (65535 & 7)
        data = bytes(d)
        result = prodos_check.check(data)
        r = self.run_fixit(data)
        self.assertEqual(r['complete'], 1, r)
        self.assertEqual(only_compared(r['counts']), oracle_counts(result.findings), r)
        self.assertEqual(first_samples(r['samples']), first_findings(result.findings), r)
        self.assertEqual(first_samples(r['samples'])['BM_TAIL'], (65535, None), r)

    def test_a_total_that_is_a_whole_number_of_windows_has_no_tail(self):
        """61 440 blocks: fifteen full windows, no padding, no page past them."""
        d = fixture(61440)
        allocated(d, 61000)
        data = bytes(d)
        result = prodos_check.check(data)
        r = self.run_fixit(data)
        self.assertEqual(r['complete'], 1, r)
        self.assertEqual(only_compared(r['counts']), oracle_counts(result.findings), r)
        self.assertEqual(r['counts'].get('BM_TAIL', 0), 0, r)
        self.assertEqual(r['counts'].get('IO_ERROR', 0), 0,
                         'no bitmap page is read past the last one')

    # -- the completeness rule holds over every window -----------------------
    def test_a_cut_in_a_later_window_takes_back_the_lost_blocks_of_the_first(self):
        """docs/FIXIT.md section 3: an incomplete pass reports no BM_LOST.

        Window 1 compares its bitmap before window 2 is even walked, so a
        cut discovered later has to take those findings back -- otherwise the
        summary names lost blocks under a verdict that says they cannot be
        trusted. The read of the second window's bitmap page fails here, as
        a bad sector would.
        """
        d = fixture(8193)
        for b in range(40, 44):
            allocated(d, b)                              # four lost, window 1
        data = bytes(d)
        self.assertEqual(self.run_fixit(data)['counts'], {'BM_LOST': 4},
                         'without the cut the four are reported')
        r = self.run_fixit(data, reject=BITMAP + 1)      # the window-2 page
        self.assertEqual(r['complete'], 0, r)
        self.assertEqual(r['counts'], {'IO_ERROR': 1}, r)
        self.assertEqual(r['found'], 1, 'the summary counts what it shows')
        self.assertEqual(r['note'], M_IOERR, r)

    def test_a_loop_found_only_in_a_later_window_takes_them_back_too(self):
        """The same, with no read error at all: two entries, one directory.

        The key block lies past the first window, so window 1 cannot see the
        second reference and walks the directory twice; window 2 does, calls
        it a loop and leaves the pass incomplete. The oracle, which walks the
        whole image once, says incomplete and reports no lost block either.
        """
        key = 5000
        d = fixture(8193, [entry(0xD, b'D', key=key, blocks=1, eof=BLOCK),
                           entry(0xD, b'E', key=key, blocks=1, eof=BLOCK)])
        subdir_header(d, key, 2, 1, count=0)
        allocated(d, key)
        allocated(d, 40)                                 # would be lost, window 1
        data = bytes(d)
        result = prodos_check.check(data)
        self.assertFalse(result.complete, 'the oracle calls this a loop')
        self.assertEqual(oracle_counts(result.findings).get('BM_LOST', 0), 0)
        r = self.run_fixit(data)
        self.assertEqual(r['complete'], 0, r)
        self.assertEqual(r['counts'].get('BM_LOST', 0), 0,
                         'an incomplete pass reports no lost block, in any window')
        self.assertEqual(r['found'], sum(r['counts'].values()), r)
        self.assertEqual(r['note'], M_UNSURE, r)

    # -- the BSS a cached overlay really finds -------------------------------
    def test_a_second_run_in_the_same_session_believes_nothing_of_the_first(self):
        """plugin_entry twice in one process, over every corruption pair.

        The core keeps the overlay in the window and calls it again; nothing
        zeroes its BSS in between. A fresh process per run -- what every
        other test here does -- cannot see a counter, a flag or a cache
        marker that survived. Each second run must answer exactly what the
        single run over that same image answers.
        """
        images = [('clean', self.clean)]
        for name in ('bitmap_lost', 'crosslink', 'chain_loop', 'hdr_storage',
                     'index_out_of_range', 'file_count_high', 'bad_storage'):
            data = bytearray(self.clean)
            corrupt_prodos.apply(data, [name])
            images.append((name, bytes(data)))
        images.append(('a big volume', bytes(f_window_boundary_shared())))
        alone = {name: self.run_fixit(data) for name, data in images}
        for first, a in images:
            for then, b in images:
                if first == then:
                    continue
                with self.subTest(first=first, then=then):
                    self.assertEqual(self.run_fixit(a, after=b), alone[then])

    def test_a_bss_full_of_garbage_changes_nothing(self):
        """Every static filled with $AA before the call: the same answers.

        reset() only clears what a pass must not inherit; the rest -- total,
        bitmap, pages, base, span, the frames, the caches -- is written
        before it is read, and this is what holds that claim (docs/FIXIT.md
        section 4, the ten dead stores that paid for the retraction above).
        """
        images = [('clean', self.clean), ('big', bytes(f_window_boundary_shared()))]
        for name in corrupt_prodos.CORRUPTIONS:
            data = bytearray(self.clean)
            corrupt_prodos.apply(data, [name])
            images.append((name, bytes(data)))
        for name, data in images:
            with self.subTest(image=name):
                self.assertEqual(self.run_fixit(data, poison=True),
                                 self.run_fixit(data), name)
        # The two paths that leave a pass half done: block 2 unreadable, so
        # header() never runs, and a block of the walk unreadable. They are
        # where a total or a page count of the pass before would survive.
        for reject in (2, corrupt_prodos.Inventory(self.clean)
                       .first(prodos_check.SUBDIR).key):
            with self.subTest(reject=reject):
                self.assertEqual(self.run_fixit(self.clean, reject=reject, poison=True),
                                 self.run_fixit(self.clean, reject=reject), reject)

    def test_messages_stay_inside_the_message_line(self):
        for message in (M_NOTVOL, M_NOVOL, M_BADHDR, M_NOREAD, M_CLEAN, M_FOUND,
                        M_UNSURE, M_IOERR, M_CANCEL, M_KEYS, M_MORE):
            self.assertLessEqual(len(message), 79, message)
            self.assertIn(message, fixit_source())


if __name__ == '__main__':
    unittest.main()
