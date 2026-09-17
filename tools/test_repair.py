"""Run the real C of REPAIR against controlled ProDOS images.

Increments 9 to 15 of docs/FIXIT.md section 8, the WRITE chantier. The C of
src/plugins/repair.c -- and with it the walker of src/plugins/fixit_walk.h,
compiled with the plan and the writes selected in -- is built by `cc` with
-DFIXIT_HOST and driven over a mock MLI on a .po file that RECORDS every
WRITE_BLOCK: its block, its 512 bytes and its rank. The image is then read
back and compared byte for byte against what the test expects, never
against a message alone.

Where tools/test_fixit.py aborts on a write, this harness injects failures:

  * the n-th write returns a ProDOS error;
  * the read back after the n-th write answers altered bytes;
  * the write that puts the original back fails too;
  * block 2 no longer says what it said when the plan was built;
  * Escape, or a wrong word, at the FIX question.

The two oracles of tools/test_fixit.py are used again: tools/corrupt_prodos.py
declares what a corruption must produce, tools/prodos_check.py reads it back
off the image, and a disagreement between them condemns the fixture. After a
repair, prodos_check.check() must find the volume clean AND the image must
be, byte for byte, the one `corrected()` below builds from the oracle's own
`expected` values -- never the one the C happens to have written.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import corrupt_prodos
import prodos_check
from prodos_check import BLOCK, ENTRY_LEN
from test_prodos_check import allocated, entry, fixture, word

# The user-facing messages of src/plugins/repair.c and fixit_walk.h.
M_NOTVOL = 'Select a real ProDOS volume.'
M_NOVOL = 'Volume not on line.'
M_BADHDR = 'Invalid volume header: nothing checked.'
M_NOREAD = 'Block 2 could not be read: nothing checked.'
M_CLEAN = 'This volume is consistent: nothing to repair.'
M_CANCEL = 'Scan cancelled: no plan from an incomplete scan.'
M_IOERR = 'Read error: this volume was not fully checked.'
M_NOPLAN = 'Scan incomplete: no repair.'
M_BOOTVOL = 'That volume holds the running program: repair it from another boot.'
M_XLINK = 'Cross-linked blocks: copy both files to another volume before any repair.'
M_PARTIAL = 'Broken entries: lost blocks kept.'
M_NOTHING = 'Nothing written.'
M_CHANGED = 'Disk changed: nothing written.'
M_ASK = 'Type FIX to confirm'
M_PLANLN = 'Plan: %u corrections over %u blocks. Nothing written yet.'
M_DONE = 'Applied %u of %u blocks; rescan clean: repaired.'
M_LEFT = 'Applied %u of %u blocks; rescan still reports %u findings.'
M_NOREST = 'Block %u not restored: recover this volume before using it.'
M_RKEYS = 'F fix  ESC back'
M_AUXASK = 'ALL /RAM files will be LOST. Continue?'

# The eleven corrections REPAIR applies: four in the bitmap, seven in the
# directory tree.
BITMAP_IDS = ('BM_USED_FREE', 'BM_RESERVED', 'BM_TAIL', 'BM_LOST')
DIR_IDS = ('FILE_COUNT', 'DIR_BLOCKS', 'FILE_BLOCKS', 'DIR_EOF',
           'DIR_PARENT', 'ENT_HEADER_PTR', 'DIR_CHAIN')
# Every corruption of tools/corrupt_prodos.py that REPAIR can undo whole.
REPAIRABLE = ('bitmap_free_used', 'bitmap_lost', 'bitmap_reserved_free',
              'bitmap_tail_set', 'file_count_high', 'blocks_used_wrong',
              'dir_blocks_wrong', 'dir_eof_wrong', 'header_ptr_wrong',
              'parent_wrong', 'chain_broken')
# The checks REPAIR deliberately does not carry: it repairs none of them and
# FIXIT names them all (docs/FIXIT.md section 4, the forms measured).
DROPPED = ('ENT_NAME', 'ENT_ACCESS', 'FILE_EOF', 'HDR_NAME', 'VOLDIR_SIZE',
           'DIR_HEADER')

HARNESS = r'''
#define __fastcall__
#define FIXIT_HOST
#include "src/plugins/repair.c"
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>

#define BOOT_UNIT   0x50
static unsigned char TARGET_UNIT = 0xE0;    /* S6,D2; S3,D2 is $B0 */

static FILE* disk;
static FILE* second;                /* a second volume, same session, same BSS */
static const char* keys = "";       /* what cgetc answers, then Escape */
static int keyi, keyn;
static unsigned int reject = 65535U;
static int reads;
static int online = 1;
static int poison;
static char volname[17];

/* The injections. `errwrite` is the rank of the write that fails, `failall`
 * makes every write fail (so the restoring one fails too), `badread` the
 * rank after which the read back answers altered bytes, `changed` a block 2
 * that stops agreeing once the question has been asked. */
static int errwrite, failall, badread, changed;
static const char* answer = "FIX";  /* what prompt() types, "" = Escape */
static int prompted;
/* A volume of more than 4 096 blocks: the answer to the question on the
 * /RAM files, how often it was asked, how often /RAM was rebuilt. */
static int consent = 1, confirms, rams;
static unsigned char mock_confirm(const char* q) {
    (void)q;
    ++confirms;
    return (unsigned char)consent;
}
static unsigned char mock_ram_format(void) { ++rams; return 1; }

/* Every WRITE_BLOCK: its block, whether it succeeded, and its bytes. */
#define MAXW 64
static unsigned int wblock[MAXW];
static int wok[MAXW];
static int nwrite;

static int seek_block(unsigned int b) {
    return fseek(disk, (long)b * 512, SEEK_SET);
}

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
    if (cmd == 0x81) {
        struct Blk* b = p;
        int rank;
        if (b->unit != TARGET_UNIT) abort();
        rank = ++nwrite;
        if (rank <= MAXW) { wblock[rank - 1] = b->block; wok[rank - 1] = 0; }
        if (failall || rank == errwrite) return 0x27;
        if (seek_block(b->block)) return 0x27;
        if (fwrite(b->buf, 1, 512, disk) != 512) return 0x27;
        fflush(disk);
        if (rank <= MAXW) wok[rank - 1] = 1;
        return 0;
    }
    if (cmd != 0x80) abort();
    {
        struct Blk* b = p;
        if (b->unit != TARGET_UNIT) abort();
        ++reads;
        if (b->block == reject) return 0x27;
        if (seek_block(b->block)) return 0x27;
        if (fread(b->buf, 1, 512, disk) != 512) return 0x27;
        /* The read back that follows the n-th write answers something the
         * write never put there. */
        if (badread && nwrite == badread && b->block == wblock[badread - 1])
            b->buf[0] ^= 0xFF;
        /* A floppy swapped while the question was on the screen. */
        if (changed && prompted && b->block == 2) b->buf[5] = 'Z';
        return 0;
    }
}

static void noop_gotoxy(unsigned char x, unsigned char y) { (void)x; (void)y; }

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

static char inputbuf[17];
static unsigned char cap_prompt(const char* label, const char* initial,
                                unsigned char hex) {
    (void)initial; (void)hex;
    cap_puts(label); cap_puts("\r\n");
    prompted = 1;
    if (!answer[0]) return 0;                   /* Escape */
    strcpy(inputbuf, answer);
    return 1;
}

/* Nothing zeroes the BSS of an overlay: the same REPAIR re-entered from the
 * menu finds its own leftovers. */
static void poison_bss(void) {
    memset(counts, 0xAA, sizeof counts);
    memset(seen, 0xAA, sizeof seen);
    memset(blk, 0xAA, sizeof blk);
    memset(stack, 0xAA, sizeof stack);
    memset(forks, 0xAA, sizeof forks);
    memset(volume, 0xAA, sizeof volume);
    memset(boot, 0xAA, sizeof boot);
    memset(&io, 0xAA, sizeof io);
    memset(&onl, 0xAA, sizeof onl);
    memset(zz, 0xAA, sizeof zz);        /* the plan counters, hdr is in stack */
    memset(nv, 0xAA, sizeof nv);
    memset(auxbits, 0xAA, sizeof auxbits);
    granted = aux = 0xAA;
    complete = failed = cancelled = 0xAA;
    depth = partial = curslot = unit = isboot = 0xAA;
    mode = on = hurt = 0xAA;
    found = curblock = total = bitmap = pages = base = span = 0xAAAA;
    budget = cached = fileblocks = 0xAAAA;
    entry = 0; buf = 0;
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

static char key_script(void) {
    char k = 27;
    ++keyn;
    if (keys[keyi]) k = keys[keyi++];
    return k;
}

static int opt(const char* a, const char* name, const char** value) {
    size_t n = strlen(name);
    if (strncmp(a, name, n) || a[n] != '=') return 0;
    *value = a + n + 1;
    return 1;
}

int main(int argc, char** argv) {
    static struct A2fcApi api;
    static struct Panel panels[2];
    static struct Entry selected;
    static unsigned char active;
    static unsigned char scratch[512];
    static char note[80];
    static unsigned char head[512];
    const char* mode_s = "run";
    const char* v;
    const char* other = "";
    int i, first;

    if (argc < 2) return 2;
    disk = fopen(argv[1], "r+b");
    if (!disk) return 2;
    for (i = 2; i < argc; ++i) {
        if (opt(argv[i], "mode", &v)) mode_s = v;
        else if (opt(argv[i], "reject", &v)) reject = (unsigned int)atoi(v);
        else if (opt(argv[i], "keys", &v)) keys = v;
        else if (opt(argv[i], "answer", &v)) answer = v;
        else if (opt(argv[i], "errwrite", &v)) errwrite = atoi(v);
        else if (opt(argv[i], "failall", &v)) failall = atoi(v);
        else if (opt(argv[i], "badread", &v)) badread = atoi(v);
        else if (opt(argv[i], "changed", &v)) changed = atoi(v);
        else if (opt(argv[i], "poison", &v)) poison = atoi(v);
        else if (opt(argv[i], "after", &v)) other = v;
        else if (opt(argv[i], "consent", &v)) consent = atoi(v);
        else if (opt(argv[i], "unit", &v)) TARGET_UNIT = (unsigned char)strtol(v, 0, 16);
        else return 2;
    }
    if (other[0]) {
        second = fopen(other, "r+b");
        if (!second) return 2;
    }

    /* The name ON_LINE answers with, straight from block 2. */
    if (fseek(disk, 1024, SEEK_SET) || fread(head, 1, 512, disk) != 512) return 2;
    i = head[4] & 15;
    memcpy(volname, head + 5, i);
    volname[i] = 0;

    api.mli = mock_mli; api.memset = memset; api.memcpy = memcpy;
    api.strcpy = strcpy; api.strcmp = strcmp;
    api.clrscr = cap_clrscr; api.cputs = cap_puts; api.cprintf = cap_printf;
    api.gotoxy = noop_gotoxy; api.cgetc = key_script; api.sprintf = sprintf;
    api.prompt = cap_prompt; api.input = inputbuf;
    api.panels = panels; api.active = &active; api.selected = &selected;
    api.copy_buf = scratch; api.note = note;
    api.confirm = mock_confirm; api.ram_format = mock_ram_format;
    api.cfg_path = "/BOOTVL/A2FILE/A2FILE.CFG";

    for (;;) {
        memset(panels, 0, sizeof panels);
        memset(&selected, 0, sizeof selected);
        if (!strcmp(mode_s, "fs")) {
            panels[0].fs = 1;
            sprintf(panels[0].path, "/%s", volname);
        } else if (!strcmp(mode_s, "notvol")) {
            strcpy(selected.name, "NOTAVOL");
        } else if (!strcmp(mode_s, "vlist")) {
            sprintf(selected.name, "/%s", volname);
            selected.mdate = TARGET_UNIT >> 4;
        } else {
            if (!strcmp(mode_s, "offline")) online = 0;
            if (!strcmp(mode_s, "subdir")) sprintf(panels[0].path, "/%s/SUB", volname);
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
        screenn = 0; keyi = 0; keyn = 0; reads = 0; nwrite = 0; prompted = 0;
        confirms = 0; rams = 0;
    }

    printf("{\"complete\":%u,\"failed\":%u,\"reads\":%d,\"unit\":%u,"
           "\"isboot\":%u,\"found\":%u,\"keys\":%d,\"applied\":%u,"
           "\"corr\":%u,\"blocks\":%u,\"dblocks\":%u,\"on\":%u,\"hurt\":%u,"
           "\"prompted\":%d,\"confirms\":%d,\"rams\":%d,\"note\":\"%s\",\"counts\":{",
           complete, failed, reads, unit, isboot, found, keyn, applied,
           corr, blocks, dblocks, on, hurt, prompted, confirms, rams, note);
    for (i = 0, first = 1; i < CHK_COUNT; ++i) {
        if (!counts[i]) continue;
        printf("%s\"%d\":%u", first ? "" : ",", i, counts[i]);
        first = 0;
    }
    printf("},\"writes\":[");
    for (i = 0; i < nwrite && i < MAXW; ++i)
        printf("%s{\"block\":%u,\"ok\":%d}", i ? "," : "", wblock[i], wok[i]);
    printf("],\"nwrite\":%d,\"screen\":\"", nwrite);
    print_screen();
    printf("\"}\n");
    fclose(disk);
    return 0;
}
'''

# The thirty identifiers, in the order of the enum of fixit_walk.h, so the
# harness can print an index and the test read a name.
IDS = ('HDR_STORAGE', 'HDR_ENTRY_LEN', 'HDR_PER_BLOCK', 'HDR_BITMAP',
       'HDR_TOTAL', 'DIR_CHAIN', 'DIR_LOOP', 'DIR_HEADER',
       'DIR_PARENT', 'DIR_DEPTH', 'ENT_STORAGE', 'ENT_NAME',
       'ENT_HEADER_PTR', 'ENT_KEY', 'FILE_COUNT', 'DIR_BLOCKS',
       'DIR_EOF', 'FILE_BLOCKS', 'FILE_EOF', 'IDX_RANGE',
       'FORK_STORAGE', 'XLINK', 'BM_USED_FREE', 'BM_LOST',
       'IO_ERROR', 'HDR_NAME', 'VOLDIR_SIZE', 'ENT_ACCESS',
       'BM_RESERVED', 'BM_TAIL')


def pages(screen):
    return [p.split('\r\n') for p in screen.split('\f') if p]


def put_word(data, offset, value):
    data[offset:offset + 2] = value.to_bytes(2, 'little')


def put24(data, offset, value):
    data[offset:offset + 3] = value.to_bytes(3, 'little')


def entry_at(data, block, slot):
    return block * BLOCK + 4 + slot * ENTRY_LEN


def corrected(data, findings):
    """The image REPAIR must leave behind, built from the oracle alone.

    Every repairable finding carries what the check COMPUTED, in its
    `expected` field; docs/FIXIT.md section 5 says where that value goes.
    Nothing here reads the C, and nothing here reads the repaired image, so
    a repair that writes the right message and the wrong bytes fails.

    DIR_BLOCKS and DIR_EOF are one patch of five contiguous bytes, +$13..$17
    of the entry: whichever of the two the walk reports, both fields are
    written off the same block count, and the one that was already right
    keeps its own bytes. DIR_PARENT is the three fields +$23..$26 of a
    subdirectory header; the oracle names the first of them that is wrong,
    which is the rank for the corruption this suite applies.
    """
    out = bytearray(data)
    bitmap = int.from_bytes(out[2 * BLOCK + 4 + 0x23:2 * BLOCK + 4 + 0x25], 'little')
    for f in findings:
        if f.id == 'FILE_COUNT':
            put_word(out, f.block * BLOCK + 4 + 0x21, f.expected)
        elif f.id in ('FILE_BLOCKS', 'DIR_BLOCKS'):
            off = entry_at(out, f.block, f.slot)
            put_word(out, off + 0x13, f.expected)
            if f.id == 'DIR_BLOCKS':
                put24(out, off + 0x15, f.expected * BLOCK)
        elif f.id == 'DIR_EOF':
            off = entry_at(out, f.block, f.slot)
            put24(out, off + 0x15, f.expected)
            put_word(out, off + 0x13, f.expected // BLOCK)
        elif f.id == 'ENT_HEADER_PTR':
            put_word(out, entry_at(out, f.block, f.slot) + 0x25, f.expected)
        elif f.id == 'DIR_PARENT':
            out[f.block * BLOCK + 4 + 0x25] = f.expected
        elif f.id == 'DIR_CHAIN':
            put_word(out, f.block * BLOCK, f.expected)
        elif f.id in BITMAP_IDS:
            offset = bitmap * BLOCK + (f.block >> 3)
            mask = 0x80 >> (f.block & 7)
            if f.id == 'BM_LOST':
                out[offset] |= mask               # give the block back
            else:
                out[offset] &= 0xFF ^ mask        # it is used, or it is past the end
        else:
            raise AssertionError('no correction is declared for ' + f.id)
    return bytes(out)


def bitmap_range(data):
    """The blocks of the volume bitmap, the only ones a repair may rewrite."""
    head = data[2 * BLOCK + 4:2 * BLOCK + 4 + 39]
    bitmap = int.from_bytes(head[0x23:0x25], 'little')
    total = int.from_bytes(head[0x25:0x27], 'little')
    return range(bitmap, bitmap + (total + 4095) // 4096)


class Repair(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='repair-test-')
        cls.work = Path(cls.tmp.name)
        source = cls.work / 'repair_host.c'
        source.write_text(HARNESS)
        cls.exe = cls.work / 'repair_host'
        subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-I', str(ROOT),
                        str(source), '-o', str(cls.exe)], check=True, capture_output=True)
        cls.clean = corrupt_prodos.make_fixture(cls.work).read_bytes()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_repair(self, data, after=None, **kw):
        """REPAIR over `data`; returns (result, the image as it is now)."""
        path = self.work / 'disk.po'
        path.write_bytes(data)
        args = [str(self.exe), str(path)]
        if after is not None:
            other = self.work / 'disk3.po'
            other.write_bytes(after)
            args.append('after=' + str(other))
        for k, v in kw.items():
            args.append('%s=%s' % (k, v))
        out = subprocess.check_output(args, timeout=300)
        r = json.loads(out)
        r['counts'] = {IDS[int(k)]: v for k, v in r['counts'].items()}
        return r, path.read_bytes()

    def fix(self, data, **kw):
        """The plan accepted: F on the plan screen, then the word FIX."""
        kw.setdefault('keys', 'F')
        kw.setdefault('answer', 'FIX')
        return self.run_repair(data, **kw)

    def corrupted(self, *names):
        """The corrupt image, the two halves of the host oracle agreeing."""
        data = bytearray(self.clean)
        expect = corrupt_prodos.apply(data, list(names))
        result = prodos_check.check(bytes(data))
        self.assertEqual(prodos_check.to_json(expect.findings),
                         prodos_check.to_json(result.findings),
                         (names, 'corrupt_prodos and prodos_check disagree'))
        return bytes(data), result

    def plan_lines(self, r):
        """The check lines of the plan screen: {id: count}."""
        out = {}
        page = next((p for p in pages(r['screen']) if any('Plan:' in l for l in p)), [])
        for row in page:
            parts = row.split()
            if len(parts) == 2 and parts[0] in IDS:
                out[parts[0]] = int(parts[1])
        return out

    def assertNoWrite(self, r, data, after):
        self.assertEqual(r['nwrite'], 0, r['note'])
        self.assertEqual(after, data, 'nothing may change on the disk')

    # -- (a) a clean volume --------------------------------------------------
    def test_a_clean_volume_is_left_alone(self):
        self.assertEqual(prodos_check.check(self.clean).findings, [])
        r, after = self.fix(self.clean)
        self.assertEqual(r['counts'], {}, r)
        self.assertEqual(r['corr'], 0)
        self.assertEqual(r['dblocks'], 0)
        self.assertEqual(r['note'], M_CLEAN)
        self.assertNoWrite(r, self.clean, after)

    def test_the_plan_screen_is_never_drawn_for_a_clean_volume(self):
        r, _ = self.fix(self.clean)
        self.assertNotIn('Plan:', r['screen'])
        self.assertEqual(r['keys'], 0, 'no key is asked for')

    # -- (b) each bitmap corruption, planned then applied --------------------
    def check_bitmap_repair(self, name, id):
        data, result = self.corrupted(name)
        self.assertIn(id, {f.id for f in result.findings}, name)

        # the plan names it, and nothing is written before the word
        r, after = self.run_repair(data)
        self.assertNoWrite(r, data, after)
        lines = self.plan_lines(r)
        self.assertIn(id, lines, (name, r['screen']))
        self.assertEqual(lines[id], sum(1 for f in result.findings if f.id == id))
        self.assertIn(M_PLANLN % (r['corr'], r['blocks']), r['screen'])
        self.assertEqual(r['blocks'], 1, r['screen'])
        self.assertEqual(r['note'], M_NOTHING)

        # F then FIX: exactly the planned pages are written and read back
        r, after = self.fix(data)
        planned = sorted(bitmap_range(data))
        self.assertEqual([w['block'] for w in r['writes']], [planned[0]], r)
        self.assertTrue(all(w['ok'] for w in r['writes']))
        self.assertEqual(r['applied'], 1, r)
        self.assertEqual(r['note'], M_DONE % (1, 1), r)
        # the volume is clean again, and only the bitmap moved
        self.assertEqual(prodos_check.check(after).findings, [], name)
        changed = {i // BLOCK for i in range(len(data)) if data[i] != after[i]}
        self.assertTrue(changed, 'the repair must have written something')
        self.assertTrue(changed <= set(bitmap_range(data)), (name, sorted(changed)))
        self.assertEqual(after, corrected(data, result.findings), name)
        return r, after

    def test_a_block_a_file_uses_and_the_bitmap_calls_free(self):
        self.check_bitmap_repair('bitmap_free_used', 'BM_USED_FREE')

    def test_a_block_nobody_claims_and_the_bitmap_calls_used(self):
        self.check_bitmap_repair('bitmap_lost', 'BM_LOST')

    def test_a_reserved_block_the_bitmap_calls_free(self):
        self.check_bitmap_repair('bitmap_reserved_free', 'BM_RESERVED')

    def test_a_bit_set_past_the_last_block_of_the_volume(self):
        self.check_bitmap_repair('bitmap_tail_set', 'BM_TAIL')

    def test_two_bitmap_faults_are_one_write_of_one_page(self):
        data, result = self.corrupted('bitmap_lost', 'bitmap_free_used',
                                      'bitmap_reserved_free')
        r, after = self.fix(data)
        self.assertEqual(r['nwrite'], 1, 'one page, written once with all of it')
        self.assertEqual(r['applied'], 1)
        self.assertEqual(r['note'], M_DONE % (1, 1), r)
        self.assertEqual(prodos_check.check(after).findings, [])

    # -- (c) what a plan refuses ---------------------------------------------
    def test_a_cross_link_refuses_the_freeing_and_writes_nothing(self):
        data, result = self.corrupted('crosslink')
        self.assertIn('XLINK', {f.id for f in result.findings})
        self.assertIn('BM_LOST', {f.id for f in result.findings})
        r, after = self.fix(data)
        self.assertNoWrite(r, data, after)
        self.assertEqual(r['note'], M_XLINK)
        self.assertEqual(r['on'] & 8, 0, 'BM_LOST is off')
        self.assertEqual(r['corr'], 0, 'nothing is left to repair')
        self.assertNotIn('Plan:', r['screen'], 'no plan is even offered')

    def test_a_broken_entry_refuses_the_freeing_and_writes_nothing(self):
        data, result = self.corrupted('key_out_of_range')
        self.assertIn('ENT_KEY', {f.id for f in result.findings})
        self.assertIn('BM_LOST', {f.id for f in result.findings})
        r, after = self.fix(data)
        self.assertNoWrite(r, data, after)
        self.assertEqual(r['on'] & 8, 0, 'BM_LOST is off')
        self.assertEqual(r['note'], M_PARTIAL)

    def test_a_cross_link_beside_a_bitmap_fault_writes_nothing_either(self):
        """A cross-link refuses the whole plan, the bitmap page included."""
        data, result = self.corrupted('crosslink', 'bitmap_reserved_free')
        r, after = self.fix(data)
        self.assertNoWrite(r, data, after)
        self.assertEqual(r['note'], M_XLINK)
        self.assertEqual(r['corr'], 0, 'nothing is offered')
        self.assertEqual(r['on'] & 8, 0)
        self.assertNotIn('Plan:', r['screen'], 'no plan is even offered')
        self.assertEqual(prodos_check.to_json(prodos_check.check(after).findings),
                         prodos_check.to_json(result.findings))

    def test_a_directory_loop_refuses_the_whole_plan(self):
        data, result = self.corrupted('chain_loop')
        self.assertFalse(result.complete)
        r, after = self.fix(data)
        self.assertNoWrite(r, data, after)
        self.assertEqual(r['note'], M_NOPLAN)

    def test_a_refused_header_refuses_the_whole_plan(self):
        for name in ('hdr_storage', 'hdr_entry_len', 'hdr_bitmap_bad'):
            with self.subTest(corruption=name):
                data, _ = self.corrupted(name)
                r, after = self.fix(data)
                self.assertNoWrite(r, data, after)
                self.assertEqual(r['note'], M_BADHDR)

    def test_a_read_error_refuses_the_whole_plan(self):
        inv = corrupt_prodos.Inventory(self.clean)
        target = inv.first(prodos_check.SUBDIR).key
        r, after = self.fix(self.clean, reject=target)
        self.assertNoWrite(r, self.clean, after)
        self.assertEqual(r['note'], M_IOERR)

    def test_block_two_unreadable_refuses_the_whole_plan(self):
        r, after = self.fix(self.clean, reject=2)
        self.assertNoWrite(r, self.clean, after)
        self.assertEqual(r['note'], M_NOREAD)

    # -- (d) the three failure injections ------------------------------------
    def test_a_write_error_puts_the_original_back_and_repairs_nothing(self):
        data, _ = self.corrupted('bitmap_lost')
        r, after = self.fix(data, errwrite=1)
        self.assertEqual([w['ok'] for w in r['writes']], [0, 1],
                         'the failed write, then the original restored')
        self.assertEqual(r['applied'], 0, r)
        self.assertEqual(r['hurt'], 1)
        self.assertEqual(after, data, 'the disk is what it was')
        self.assertTrue(r['note'].startswith('Applied 0 of 1 blocks'), r['note'])

    def test_a_read_back_that_differs_puts_the_original_back(self):
        data, _ = self.corrupted('bitmap_lost')
        r, after = self.fix(data, badread=1)
        self.assertEqual([w['ok'] for w in r['writes']], [1, 1], r)
        self.assertEqual(r['applied'], 0, r)
        self.assertEqual(after, data, 'the original was written back')
        self.assertTrue(r['note'].startswith('Applied 0 of 1 blocks'), r['note'])

    def test_a_restore_that_fails_names_the_block_and_stops(self):
        data, _ = self.corrupted('bitmap_lost')
        r, after = self.fix(data, failall=1)
        self.assertEqual(r['nwrite'], 2, 'the write, the restore, then nothing')
        self.assertEqual([w['ok'] for w in r['writes']], [0, 0])
        self.assertEqual(r['hurt'], 2)
        block = sorted(bitmap_range(data))[0]
        self.assertEqual(r['note'], M_NOREST % block, r['note'])
        self.assertEqual(after, data)

    # -- (e) the confirmation ------------------------------------------------
    def test_escape_at_the_question_writes_nothing(self):
        data, _ = self.corrupted('bitmap_lost')
        r, after = self.fix(data, answer='')
        self.assertNoWrite(r, data, after)
        self.assertEqual(r['note'], M_NOTHING)
        self.assertEqual(r['prompted'], 1, 'the question was asked')
        self.assertIn(M_ASK, r['screen'])

    def test_a_wrong_word_writes_nothing(self):
        data, _ = self.corrupted('bitmap_lost')
        for word in ('ERASE', 'fix', 'FI', 'FIXX'):
            with self.subTest(word=word):
                r, after = self.fix(data, answer=word)
                self.assertNoWrite(r, data, after)
                self.assertEqual(r['note'], M_NOTHING)

    def test_escape_on_the_plan_screen_never_asks_the_question(self):
        data, _ = self.corrupted('bitmap_lost')
        for keys in ('', '\r', 'X\r'):
            with self.subTest(keys=repr(keys)):
                r, after = self.run_repair(data, keys=keys)
                self.assertNoWrite(r, data, after)
                self.assertEqual(r['prompted'], 0)
                self.assertEqual(r['note'], M_NOTHING)

    def test_the_plan_screen_offers_the_keys_it_has(self):
        data, _ = self.corrupted('bitmap_lost')
        r, _ = self.run_repair(data)
        self.assertIn(M_RKEYS, r['screen'])
        for absent in ('R rescan', 'P plan', 'E export'):
            self.assertNotIn(absent, r['screen'])

    # -- (f) the disk changed between the plan and the word ------------------
    def test_a_disk_changed_at_the_question_writes_nothing(self):
        data, _ = self.corrupted('bitmap_lost')
        r, after = self.fix(data, changed=1)
        self.assertNoWrite(r, data, after)
        self.assertEqual(r['note'], M_CHANGED)
        self.assertEqual(r['prompted'], 1, 'the guard is after the question')

    # -- (g) the seven directory corrections, applied ------------------------
    def check_dir_repair(self, name, id):
        """One directory corruption: planned, applied, and the bytes judged.

        The image REPAIR has to leave behind is built in Python from the
        oracle's own expected values (`corrected`), so a repair that writes
        the right number of blocks and the wrong bytes fails here.
        """
        data, result = self.corrupted(name)
        expect = [f for f in result.findings if f.id == id]
        self.assertTrue(expect, (name, id))
        self.assertEqual(len(result.findings), len(expect),
                         (name, 'this corruption must produce that check alone'))
        blocks = [f.block for f in expect]

        # the plan names it, counts it, and writes nothing
        r, after = self.run_repair(data)
        self.assertNoWrite(r, data, after)
        self.assertEqual(self.plan_lines(r).get(id), len(expect),
                         (name, r['screen']))
        self.assertEqual(r['corr'], len(expect), r)
        self.assertEqual(r['dblocks'], len(expect), r)
        self.assertEqual(r['blocks'], len(expect), r)
        self.assertIn(M_PLANLN % (r['corr'], r['blocks']), r['screen'])
        self.assertEqual(r['note'], M_NOTHING)

        # F then FIX: one verified write per correction, on the named blocks
        r, after = self.fix(data)
        self.assertEqual([w['block'] for w in r['writes']], blocks, r)
        self.assertTrue(all(w['ok'] for w in r['writes']), r)
        self.assertEqual(r['applied'], len(expect), r)
        self.assertEqual(r['note'], M_DONE % (len(expect), len(expect)), r)

        # the volume checks clean, only the written blocks moved, and the
        # bytes that moved are exactly the correction
        self.assertEqual(prodos_check.check(after).findings, [], name)
        self.assertEqual(after, corrected(data, expect), name)
        changed = {i // BLOCK for i in range(len(data)) if data[i] != after[i]}
        self.assertTrue(changed, 'the repair must have written something')
        self.assertTrue(changed <= set(blocks), (name, sorted(changed)))
        return r, after

    def test_a_header_that_counts_one_file_too_many(self):
        self.check_dir_repair('file_count_high', 'FILE_COUNT')

    def test_a_header_that_counts_one_file_too_few(self):
        self.check_dir_repair('file_count_low', 'FILE_COUNT')

    def test_a_file_entry_that_claims_a_block_it_does_not_reach(self):
        self.check_dir_repair('blocks_used_wrong', 'FILE_BLOCKS')

    def test_a_subdirectory_entry_that_claims_too_many_blocks(self):
        self.check_dir_repair('dir_blocks_wrong', 'DIR_BLOCKS')

    def test_a_subdirectory_entry_whose_eof_is_not_its_blocks_times_512(self):
        self.check_dir_repair('dir_eof_wrong', 'DIR_EOF')

    def test_an_entry_that_no_longer_points_at_its_own_directory(self):
        self.check_dir_repair('header_ptr_wrong', 'ENT_HEADER_PTR')

    def test_a_subdirectory_header_that_names_the_wrong_parent_entry(self):
        self.check_dir_repair('parent_wrong', 'DIR_PARENT')

    def test_a_directory_block_whose_back_pointer_is_wrong(self):
        self.check_dir_repair('chain_broken', 'DIR_CHAIN')

    def test_a_directory_fault_beside_a_bitmap_one_repairs_both(self):
        data, result = self.corrupted('bitmap_lost', 'file_count_high')
        r, after = self.run_repair(data)
        lines = self.plan_lines(r)
        self.assertIn('BM_LOST', lines, 'the plan shows both')
        self.assertIn('FILE_COUNT', lines)
        r, after = self.fix(data)
        self.assertEqual(prodos_check.check(after).findings, [])
        self.assertEqual(after, corrected(data, result.findings))
        self.assertEqual(r['note'], M_DONE % (2, 2), r)

    def test_every_repairable_fault_at_once(self):
        """All eleven together: one run, and the second pass finds nothing."""
        data, result = self.corrupted(*REPAIRABLE)
        for id in BITMAP_IDS + DIR_IDS:
            self.assertIn(id, {f.id for f in result.findings}, id)
        r, after = self.fix(data)
        self.assertTrue(all(w['ok'] for w in r['writes']), r)
        self.assertEqual(prodos_check.check(after).findings, [], 'a clean volume')
        self.assertEqual(after, corrected(data, result.findings))
        self.assertEqual(r['note'], M_DONE % (r['applied'], r['blocks']), r)
        self.assertEqual(r['applied'], r['nwrite'], 'every write was verified')

        # the argued order: every directory block before the bitmap page,
        # and the pages of the bitmap written once each
        written = [w['block'] for w in r['writes']]
        page = sorted(bitmap_range(data))[0]
        self.assertEqual(written[-1], page, ('the bitmap page is last', written))
        self.assertNotIn(page, written[:-1])
        self.assertEqual(set(written),
                         {f.block for f in result.findings if f.id in DIR_IDS} | {page},
                         written)
        # A block carrying several corrections is written once per
        # correction, not once in all: docs/FIXIT.md section 5 says why
        # (there is no patch list, and blk carries every patch already
        # applied, so each write includes the ones before it). The only
        # pair that shares a write is DIR_BLOCKS with DIR_EOF, five
        # contiguous bytes of one entry.
        sites = set()
        for f in result.findings:
            if f.id in DIR_IDS:
                kind = 'DIR_BLOCKS' if f.id in ('DIR_BLOCKS', 'DIR_EOF') else f.id
                sites.add((kind, f.block, f.slot))
        self.assertEqual(len(written), len(sites) + 1, written)
        self.assertLess(len(set(written)), len(written),
                        'this fixture really does write block 2 more than once')

    def test_a_tree_file_whose_walk_took_the_directory_block(self):
        """The reread inside fix(): a tree's master index lives in blk.

        Walking a tree file reads its master index into the very buffer the
        directory block was in, so the correction has to read that block
        again before patching it -- and patch the right forty bytes of it.
        """
        data = bytearray(self.clean)
        inv = corrupt_prodos.Inventory(bytes(data))
        ref = inv.first(prodos_check.TREE)
        self.assertGreater(len(ref.blocks), 256, 'the fixture tree needs a master index')
        corrupt_prodos.put_word(data, ref.offset + 0x13, ref.used + 7)
        data = bytes(data)
        found = prodos_check.check(data).findings
        self.assertEqual([f.id for f in found], ['FILE_BLOCKS'])
        r, after = self.fix(data)
        self.assertEqual([w['block'] for w in r['writes']], [ref.block], r)
        self.assertEqual(r['note'], M_DONE % (1, 1), r)
        self.assertEqual(prodos_check.check(after).findings, [])
        self.assertEqual(after, corrected(data, found))

    def test_a_second_run_over_a_repaired_volume_writes_nothing(self):
        data, _ = self.corrupted(*REPAIRABLE)
        _, after = self.fix(data)
        r, again = self.fix(after)
        self.assertNoWrite(r, after, again)
        self.assertEqual(r['note'], M_CLEAN)

    # -- (h) the injections, on a directory write ----------------------------
    def test_a_directory_write_error_puts_the_original_back(self):
        for name in ('file_count_high', 'parent_wrong', 'chain_broken'):
            with self.subTest(corruption=name):
                data, _ = self.corrupted(name)
                r, after = self.fix(data, errwrite=1)
                self.assertEqual([w['ok'] for w in r['writes']], [0, 1],
                                 'the failed write, then the original restored')
                self.assertEqual(r['applied'], 0, r)
                self.assertEqual(r['hurt'], 1)
                self.assertEqual(after, data, 'the disk is what it was')
                self.assertTrue(r['note'].startswith('Applied 0 of 1 blocks'),
                                r['note'])

    def test_a_directory_read_back_that_differs_puts_the_original_back(self):
        data, _ = self.corrupted('file_count_high')
        r, after = self.fix(data, badread=1)
        self.assertEqual([w['ok'] for w in r['writes']], [1, 1], r)
        self.assertEqual(r['applied'], 0, r)
        self.assertEqual(r['hurt'], 1)
        self.assertEqual(after, data, 'the original was written back')

    def test_a_directory_restore_that_fails_names_the_block_and_stops(self):
        data, result = self.corrupted('parent_wrong')
        r, after = self.fix(data, failall=1)
        self.assertEqual(r['nwrite'], 2, 'the write, the restore, then nothing')
        self.assertEqual([w['ok'] for w in r['writes']], [0, 0])
        self.assertEqual(r['hurt'], 2)
        self.assertEqual(r['note'], M_NOREST % result.findings[0].block, r['note'])
        self.assertEqual(after, data)

    def test_a_restore_that_fails_stops_a_plan_that_had_more_to_write(self):
        """Nothing is written after a block that could not be put back."""
        data, _ = self.corrupted(*REPAIRABLE)
        r, after = self.fix(data, failall=1)
        self.assertEqual(r['nwrite'], 2, r)
        self.assertEqual(r['hurt'], 2)
        self.assertEqual(after, data, 'not one byte reached the disk')
        self.assertIn('not restored', r['note'])

    def two_faults_on_one_entry(self):
        """One entry with a wrong header pointer AND a wrong block count.

        Both corrections land in the same directory block, and the second is
        reached with that block still in hand: no reread stands between them.
        """
        data = bytearray(self.clean)
        inv = corrupt_prodos.Inventory(bytes(data))
        ref = inv.first(prodos_check.SAPLING)
        corrupt_prodos.put_word(data, ref.offset + 0x25, 0xFFFF)
        corrupt_prodos.put_word(data, ref.offset + 0x13, ref.used + 1)
        data = bytes(data)
        self.assertEqual(sorted(f.id for f in prodos_check.check(data).findings),
                         ['ENT_HEADER_PTR', 'FILE_BLOCKS'])
        return data, ref.block

    def test_two_corrections_on_one_block_are_two_writes_of_that_block(self):
        data, block = self.two_faults_on_one_entry()
        r, after = self.fix(data)
        self.assertEqual([w['block'] for w in r['writes']], [block, block], r)
        self.assertEqual(r['corr'], 2)
        self.assertEqual(r['blocks'], 2, 'one write per correction')
        self.assertEqual(r['note'], M_DONE % (2, 2), r)
        self.assertEqual(prodos_check.check(after).findings, [])
        self.assertEqual(after, corrected(data, prodos_check.check(data).findings))

    def test_nothing_is_written_after_a_block_that_could_not_be_put_back(self):
        """The second correction must not slip past on a block still in hand."""
        data, block = self.two_faults_on_one_entry()
        r, after = self.fix(data, failall=1)
        self.assertEqual(r['nwrite'], 2, 'the write, the restore, then nothing')
        self.assertEqual(r['hurt'], 2)
        self.assertEqual(r['note'], M_NOREST % block, r['note'])
        self.assertEqual(after, data, 'not one byte reached the disk')

    def test_escape_or_a_wrong_word_writes_no_directory_block(self):
        data, _ = self.corrupted('file_count_high', 'parent_wrong')
        for kw in ({'answer': ''}, {'answer': 'ERASE'}, {'keys': ''}):
            with self.subTest(**kw):
                r, after = self.fix(data, **kw)
                self.assertNoWrite(r, data, after)
                self.assertEqual(r['note'], M_NOTHING)

    # -- (i) what a cross-link refuses ---------------------------------------
    def test_a_cross_link_refuses_the_whole_plan(self):
        """Section 5: a block two things claim stops every repair.

        Until the campaign of tools/fuzz_prodos.py only BM_LOST waited on a
        cross-link, and the seven directory corrections went out anyway.
        Invariant 5 of that campaign showed the cost: a block a file claims
        as data is a block a counter repair rewrites, and the file loses
        those bytes. The message said "before any repair" and the code
        repaired; it refuses now, and eleven corrections wait with it.
        """
        data, result = self.corrupted(*(REPAIRABLE + ('crosslink',)))
        r, after = self.fix(data)
        self.assertNoWrite(r, data, after)
        self.assertEqual(r['note'], M_XLINK)
        self.assertEqual(r['corr'], 0, 'nothing is offered')
        self.assertEqual(r['on'] & 8, 0, 'BM_LOST is off')
        self.assertNotIn('Plan:', r['screen'], 'no plan is even offered')
        self.assertEqual(prodos_check.to_json(prodos_check.check(after).findings),
                         prodos_check.to_json(result.findings))

    def cross_linked_directory_block(self, block_of):
        """A file whose key is a directory block, and a fault on that block.

        The two shapes tools/fuzz_prodos.py found: the volume directory
        block 2 miscounted, and a subdirectory header naming the wrong
        parent. In both, the block the repair would rewrite is the block the
        file reads.
        """
        data = bytearray(self.clean)
        inv = corrupt_prodos.Inventory(bytes(data))
        block = block_of(data, inv)
        data = bytes(data)
        found = {f.id for f in prodos_check.check(data).findings}
        self.assertIn('XLINK', found)
        r, after = self.fix(data)
        self.assertNoWrite(r, data, after)
        self.assertEqual(r['note'], M_XLINK)
        self.assertEqual(after[block * BLOCK:(block + 1) * BLOCK],
                         data[block * BLOCK:(block + 1) * BLOCK],
                         'the block the file reads keeps its bytes')

    def test_a_file_that_claims_the_volume_directory_keeps_its_bytes(self):
        def build(data, inv):
            ref = inv.first(prodos_check.SEEDLING)
            corrupt_prodos.put_word(data, ref.offset + 0x11, 2)
            corrupt_prodos.put_word(data, 2 * BLOCK + 4 + 0x21, inv.file_count + 1)
            return 2
        self.cross_linked_directory_block(build)

    def test_a_file_that_claims_a_subdirectory_header_keeps_its_bytes(self):
        def build(data, inv):
            sub = inv.first(prodos_check.SUBDIR)
            ref = inv.seedlings()[-1]       # walked after the subdirectory
            corrupt_prodos.put_word(data, ref.offset + 0x11, sub.key)
            data[sub.key * BLOCK + 4 + 0x25] = sub.slot + 2
            return sub.key
        self.cross_linked_directory_block(build)

    def test_the_checks_repair_does_not_carry_are_the_declared_ones(self):
        """Dropping one is a measurement, never a silent omission."""
        source = (ROOT / 'src/plugins/fixit_walk.h').read_text()
        doc = (ROOT / 'docs/FIXIT.md').read_text()
        for id in DROPPED:
            with self.subTest(check=id):
                self.assertIn(id, doc, 'docs/FIXIT.md must say REPAIR drops it')
        for name in ('bad_name', 'bad_access', 'eof_too_big'):
            data, result = self.corrupted(name)
            r, after = self.fix(data)
            self.assertNoWrite(r, data, after)
            self.assertEqual(r['note'], M_CLEAN, (name, r))
        self.assertIn('#ifndef REPAIR', source)

    # -- (h) the program's own volume ----------------------------------------
    def test_the_program_volume_is_refused_before_any_read(self):
        data = bytearray(self.clean)
        name = b'BOOTVL'
        offset = 2 * BLOCK + 4
        data[offset] = 0xF0 | len(name)
        data[offset + 1:offset + 1 + len(name)] = name
        corrupt_prodos.apply(data, ['bitmap_lost'])
        data = bytes(data)
        r, after = self.fix(data)
        self.assertNoWrite(r, data, after)
        self.assertEqual(r['isboot'], 1)
        self.assertEqual(r['note'], M_BOOTVOL)
        self.assertEqual(r['reads'], 0, 'refused before a single block is read')

    # -- the refusals of the selection ---------------------------------------
    def test_an_image_or_dos33_panel_is_refused_without_reading(self):
        r, after = self.fix(self.clean, mode='fs')
        self.assertNoWrite(r, self.clean, after)
        self.assertEqual(r['note'], M_NOTVOL)
        self.assertEqual(r['reads'], 0)

    def test_a_volume_not_on_line_is_refused_without_reading(self):
        r, after = self.fix(self.clean, mode='offline')
        self.assertNoWrite(r, self.clean, after)
        self.assertEqual(r['note'], M_NOVOL)

    def test_a_volume_list_entry_and_a_subdirectory_reach_the_same_volume(self):
        for mode in ('vlist', 'subdir'):
            with self.subTest(mode=mode):
                data, _ = self.corrupted('bitmap_lost')
                r, after = self.fix(data, mode=mode)
                self.assertEqual(r['unit'], 0xE0)
                self.assertEqual(r['note'], M_DONE % (1, 1), r)
                self.assertEqual(prodos_check.check(after).findings, [])

    # -- (i) the BSS a cached overlay really finds ---------------------------
    def test_a_second_run_in_the_same_session_believes_nothing_of_the_first(self):
        images = [('clean', self.clean)]
        for name in ('bitmap_lost', 'bitmap_free_used', 'crosslink',
                     'chain_loop', 'file_count_high', 'key_out_of_range',
                     'parent_wrong', 'chain_broken', 'dir_eof_wrong'):
            data = bytearray(self.clean)
            corrupt_prodos.apply(data, [name])
            images.append((name, bytes(data)))
        alone = {name: self.run_repair(data)[0] for name, data in images}
        for first, a in images:
            for then, b in images:
                if first == then:
                    continue
                with self.subTest(first=first, then=then):
                    r, _ = self.run_repair(a, after=b)
                    self.assertEqual(r, alone[then])

    def test_a_bss_full_of_garbage_changes_nothing(self):
        images = [('clean', self.clean)]
        for name in corrupt_prodos.CORRUPTIONS:
            data = bytearray(self.clean)
            corrupt_prodos.apply(data, [name])
            images.append((name, bytes(data)))
        for name, data in images:
            with self.subTest(image=name):
                a, _ = self.run_repair(data, poison=1)
                b, _ = self.run_repair(data)
                self.assertEqual(a, b, name)

    def test_a_poisoned_bss_repairs_exactly_the_same_blocks(self):
        for name in ('bitmap_lost', 'bitmap_free_used', 'bitmap_reserved_free',
                     'file_count_high', 'parent_wrong', 'header_ptr_wrong',
                     'chain_broken', 'dir_eof_wrong', 'blocks_used_wrong'):
            with self.subTest(corruption=name):
                data, _ = self.corrupted(name)
                a, ia = self.fix(data, poison=1)
                b, ib = self.fix(data)
                self.assertEqual(a, b, name)
                self.assertEqual(ia, ib, name)

    # -- the messages --------------------------------------------------------
    def test_messages_stay_inside_the_message_line(self):
        source = ((ROOT / 'src/plugins/repair.c').read_text()
                  + (ROOT / 'src/plugins/fixit_walk.h').read_text())
        for message in (M_NOTVOL, M_NOVOL, M_BADHDR, M_NOREAD, M_CLEAN, M_CANCEL,
                        M_IOERR, M_NOPLAN, M_BOOTVOL, M_XLINK, M_PARTIAL,
                        M_NOTHING, M_CHANGED, M_ASK, M_PLANLN,
                        M_DONE, M_LEFT, M_NOREST, M_RKEYS, M_AUXASK):
            self.assertLessEqual(len(message % ((65535,) * message.count('%u'))
                                     if '%u' in message else message), 79, message)
            self.assertIn(message, source, message)

    def test_the_overlay_writes_through_one_function_only(self):
        """One WRITE_BLOCK, one readblock: no second variant of a loop."""
        source = ((ROOT / 'src/plugins/repair.c').read_text()
                  + (ROOT / 'src/plugins/fixit_walk.h').read_text())
        self.assertEqual(source.count('v_mli(0x81'), 1,
                         'every write, and every restore, goes through verified()')
        self.assertEqual(source.count('static unsigned char verified'), 1)
        self.assertEqual(source.count('static void fix('), 1,
                         'the seven directory corrections share one function')
        self.assertEqual(source.count('static unsigned char readblock'), 1)
        for absent in ('fopen', 'fwrite(', 'v_mli(0xC0'):
            self.assertNotIn(absent, source, 'REPAIR creates no file')
        # The one write elsewhere: /RAM rebuilt empty once the user agreed to
        # lose it for the claims of a big volume (test_a_big_volume_*).
        self.assertEqual(source.count('ram_format()'), 1)
        self.assertIn('if (granted) api->ram_format();', source)

    # -- more than 4 096 blocks: the claims in the auxiliary bank ------------
    def big_volume(self):
        """8 193 blocks: a lost block in the second bitmap page, a seedling in
        the third, and a root that counts five files for one."""
        d = fixture(8193, [entry(1, b'A', key=8100)])
        allocated(d, 8100)
        allocated(d, 5000)                               # lost
        word(d, 1061, 5)                                 # FILE_COUNT
        data = bytes(d)
        self.assertEqual({f.id for f in prodos_check.check(data).findings},
                         {'BM_LOST', 'FILE_COUNT'}, 'the fixture')
        return data

    def test_a_big_volume_is_repaired_in_three_walks(self):
        data = self.big_volume()
        r, image = self.fix(data)
        self.assertEqual(r['note'], M_DONE % (2, 2), r)
        self.assertEqual(prodos_check.check(image).findings, [])
        self.assertEqual((r['confirms'], r['rams']), (1, 1), r)
        self.assertEqual([w['block'] for w in r['writes']], [2, 7], r)
        # three walks of the root (2 is read again by the walk) and three
        # bitmap pages; block 2 and the last block for the plan and the
        # rescan; the guard's two rereads of block 2; the reread of block 2
        # before its correction and the two read backs.
        self.assertEqual(r['reads'], 3 * (4 + 3) + 2 * 2 + 2 + 3, r)

    def test_keeping_the_ram_files_writes_nothing(self):
        data = self.big_volume()
        r, image = self.fix(data, consent=0)
        self.assertEqual(r['note'], M_NOTHING, r)
        self.assertEqual(image, data)
        self.assertEqual((r['confirms'], r['rams'], r['nwrite']), (1, 0, 0), r)
        self.assertEqual(r['reads'], 2, 'block 2 and the last block only')

    def test_a_big_volume_in_slot_3_drive_2_is_never_repaired(self):
        data = self.big_volume()
        r, image = self.fix(data, unit='B0')
        self.assertEqual(r['unit'], 0xB0, r)
        self.assertEqual(r['note'], M_NOTHING, r)
        self.assertEqual(image, data)
        self.assertEqual((r['confirms'], r['rams'], r['nwrite']), (0, 0, 0), r)

    def test_a_volume_of_one_bitmap_page_asks_nothing(self):
        data, _ = self.corrupted('bitmap_lost')
        r, _ = self.fix(data)
        self.assertEqual((r['confirms'], r['rams']), (0, 0), r)

    def test_a_poisoned_bss_repairs_a_big_volume_the_same(self):
        data = self.big_volume()
        self.assertEqual(self.fix(data, poison=1), self.fix(data))


if __name__ == '__main__':
    unittest.main()
