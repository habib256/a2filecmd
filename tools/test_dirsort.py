"""Run DIRSORT's actual C (src/plugins/dirsort.c) against a block-device
mock and check the BYTES of the volume after every run.

The mock answers ON_LINE, READ_BLOCK and WRITE_BLOCK for one unit and can
fail the Nth write (refused, written then refused, or written wrong), every
write after it, a read of one block, or swap the disk for another one when
the confirmation is answered. Keys are scripted. A refusal, an Escape, a
"no" or a disk changed under the confirmation must leave every byte as it
was; a failed write must be put back to the very bytes it had."""
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_wipe import toolchains

ROOT = Path(__file__).resolve().parents[1]
HARNESS = r'''#define __fastcall__
#define PLUGIN_HOST
#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include <stdarg.h>
#undef memcpy
#undef memset
#undef strcpy
#undef sprintf
struct A2fcApi;
#include "src/plugins/dirsort.c"
static FILE *disk, *swapdisk;
static int nwrite, fail_write, fail_mode, fail_after, read_fail = -1, yes = 1, confirmed, twin, protect;
static int read_pre = -1, read_after_writes = 0;
static const char* keys = "";
static char screen[8192], asked[128];
/* The one unit, $60, named by the volume header of the disk in place. */
static unsigned char mock_mli(unsigned char cmd, void* p) {
    struct Block* b = p;
    if (cmd == 0xC5) {
        struct Online* o = p; unsigned char h[16];
        memset(o->buffer, 0, 256);
        if (fseek(disk, 1028, SEEK_SET) || fread(h, 1, 16, disk) != 16) return 0x27;
        o->buffer[0] = 0x60 | (h[0] & 15); memcpy(o->buffer + 1, h + 1, 15);
        /* twin: a second drive, S6,D2, carries the same name */
        if (twin) { o->buffer[16] = 0xE0 | (h[0] & 15); memcpy(o->buffer + 17, h + 1, 15); }
        return 0;
    }
    if ((cmd != 0x80 && cmd != 0x81) || b->n != 3) abort();
    if (b->unit != 0x60) return 0x28;
    if (fseek(disk, (long)b->block * 512, SEEK_SET)) return 0x27;
    if (cmd == 0x80) {
        /* readfail: after the answer (and after `readw` writes);
         * readpre: before it, while the directory is checked. */
        if (b->block == read_fail && confirmed && nwrite >= read_after_writes) return 0x27;
        if (b->block == read_pre && !confirmed) return 0x27;
        return fread(b->buffer, 1, 512, disk) == 512 ? 0 : 0x27;
    }
    ++nwrite;
    if (protect) return 0x2B;                          /* write-protected: nothing written */
    if (fail_write && (nwrite == fail_write || (fail_after && nwrite > fail_write))) {
        unsigned char bad[512];
        if (fail_mode == 0) return 0x27;              /* refused, nothing written */
        memcpy(bad, b->buffer, 512);
        if (fail_mode == 2) bad[300] ^= 0x55;          /* written wrong, no error */
        fwrite(bad, 1, 512, disk); fflush(disk);
        return fail_mode == 1 ? 0x27 : 0;              /* 1: written, then an error */
    }
    if (fwrite(b->buffer, 1, 512, disk) != 512) return 0x27;
    fflush(disk); return 0;
}
/* The core's directory reader over the disk: the path resolved from the
 * volume directory by name (storage 13 entries only), then its entries. */
static struct DirEntry entry_out;
static unsigned char dblk[512];
static unsigned int dnext, dslot;
static int rdb(unsigned int b, unsigned char* out)
{ return !fseek(disk, (long)b * 512, SEEK_SET) && fread(out, 1, 512, disk) == 512; }
static unsigned char d_open(const char* path) {
    unsigned int b = 2; const char* p = strchr(path + 1, '/');
    while (p) {
        const char* q = strchr(p + 1, '/'); size_t n = q ? (size_t)(q - p - 1) : strlen(p + 1);
        unsigned int found = 0, c = b; unsigned char blk_[512];
        while (c && !found) {
            int s_;
            if (!rdb(c, blk_)) return 0;
            for (s_ = 0; s_ < 13; ++s_) {
                unsigned char* e = blk_ + 4 + 39 * s_;
                if ((e[0] >> 4) == 13 && (e[0] & 15) == n && !memcmp(e + 1, p + 1, n))
                    found = e[17] | e[18] << 8;
            }
            c = blk_[2] | blk_[3] << 8;
        }
        if (!found) return 0;
        b = found; p = q;
    }
    if (!rdb(b, dblk)) return 0;
    dnext = dblk[2] | dblk[3] << 8; dslot = 1;
    return 1;
}
static unsigned char d_next(void) {
    for (;;) {
        unsigned char* e;
        if (dslot == 13) {
            if (!dnext || !rdb(dnext, dblk)) return 0;
            dnext = dblk[2] | dblk[3] << 8; dslot = 0;
        }
        e = dblk + 4 + 39 * dslot++;
        if (!(e[0] >> 4)) continue;
        memcpy(entry_out.name, e + 1, e[0] & 15); entry_out.name[e[0] & 15] = 0;
        entry_out.type = e[16]; entry_out.key = e[17] | e[18] << 8; entry_out.access = e[30];
        return 1;
    }
}
static void d_close(void) {}
static unsigned char confirm(const char* s) {
    strcpy(asked, s); confirmed = 1;
    if (swapdisk) { fclose(disk); disk = swapdisk; swapdisk = 0; }
    return yes;
}
/* u d: Up Down; e: Escape; anything else as typed. Escape when done. */
static char next_key(void) {
    char k = *keys ? *keys++ : 'e';
    return k == 'u' ? 11 : k == 'd' ? 10 : k == 'e' ? 27 : k;
}
static void put(const char* s) { strncat(screen, s, sizeof screen - strlen(screen) - 1); }
static void put_c(char c) { char s[2] = {c, 0}; put(s); }
static void at(unsigned char x, unsigned char y) { (void)x; (void)y; put("\n"); }
static void cls(void) { screen[0] = 0; }
static unsigned char rev(unsigned char on) { (void)on; return 0; }
static void bar(unsigned char x, const char* s) { (void)x; put(s); }
static int show(const char* f, ...) {
    va_list ap; va_start(ap, f);
    vsnprintf(screen + strlen(screen), sizeof screen - strlen(screen), f, ap);
    va_end(ap); return 0;
}
int main(int argc, char** argv) {
    static struct A2fcApi api; static struct Panel panels[2]; static struct Entry selected;
    static unsigned char active, copy[512]; static char note[128];
    int i;
    disk = fopen(argv[1], "r+b"); if (!disk) return 2;
    strcpy(panels[0].path, argv[2]);
    keys = argv[3];
    for (i = 4; i < argc; ++i) {
        char* v = strchr(argv[i], '=') + 1;
        if (!strncmp(argv[i], "no=", 3)) yes = 0;
        else if (!strncmp(argv[i], "failw=", 6)) fail_write = atoi(v);
        else if (!strncmp(argv[i], "mode=", 5)) fail_mode = atoi(v);
        else if (!strncmp(argv[i], "after=", 6)) fail_after = 1;
        else if (!strncmp(argv[i], "readfail=", 9)) read_fail = atoi(v);
        else if (!strncmp(argv[i], "readw=", 6)) read_after_writes = atoi(v);
        else if (!strncmp(argv[i], "readpre=", 8)) read_pre = atoi(v);
        else if (!strncmp(argv[i], "other=", 6)) swapdisk = fopen(v, "r+b");
        else if (!strncmp(argv[i], "fs=", 3)) panels[0].fs = 1;
        else if (!strncmp(argv[i], "twin=", 5)) twin = 1;
        else if (!strncmp(argv[i], "protect=", 8)) protect = 1;
        else return 3;
    }
    api.panels = panels; api.active = &active; api.selected = &selected;
    api.copy_buf = copy; api.note = note;
    api.mli = mock_mli; api.memcpy = memcpy; api.memset = memset; api.strcpy = strcpy;
    api.strcmp = strcmp; api.strlen = strlen; api.sprintf = sprintf;
    api.cprintf = show; api.cputs = put; api.cputc = put_c; api.gotoxy = at;
    api.clrscr = cls; api.revers = rev; api.cgetc = next_key; api.keys_bar = bar;
    api.confirm = confirm;
    api.dir_open = d_open; api.dir_next = d_next; api.dir_close = d_close; api.dir_entry = &entry_out;
    /* The overlay's BSS is not zeroed on the Apple II: it holds what the
     * last occupant of the window left. Its tables start as garbage here
     * too, and the locals (statics under cc65 -Cl) are poisoned by the
     * compiler (-ftrivial-auto-var-init=pattern). */
    /* Stale indexes that name a real entry, the first: the worst case for
     * anything that walks past nent, which must never happen. */
    memset(order, 0, sizeof order); memset(eb, 0, sizeof eb); memset(es, 0, sizeof es);
    memset(csum, 0xAA, sizeof csum); memset(blk, 0xAA, sizeof blk); memset(dir, 0xAA, sizeof dir);
    nblk = nent = cur = top = held = mode = by = 0xAA; lost = lastkey = 0xAAAA;
    plugin_entry(&api);
    printf("%d\n%s\n%s\n%s", nwrite, note, asked, screen);
    fclose(disk); return 0;
}
'''

ACCESS = 0xC3


def word(d, at, v):
    d[at:at+2] = v.to_bytes(2, 'little')


class Volume:
    """A ProDOS volume built entry by entry. Directories are lists of
    blocks; slot s of block b is at b*512 + 4 + 39*s."""

    def __init__(self, name=b'V', total=280, root_blocks=4):
        self.d = bytearray(total * 512)
        self.total = total
        self.root = self.directory(list(range(2, 2 + root_blocks)), name, 0xF, total=total)

    def directory(self, blocks, name, kind, parent=None, total=0):
        d = self.d
        for i, b in enumerate(blocks):
            word(d, b*512, blocks[i-1] if i else 0)
            word(d, b*512+2, blocks[i+1] if i + 1 < len(blocks) else 0)
        h = blocks[0] * 512
        d[h+4] = kind << 4 | len(name)
        d[h+5:h+5+len(name)] = name
        d[h+0x22] = ACCESS
        d[h+0x23:h+0x25] = bytes([39, 13])
        if kind == 0xF:
            word(d, h+0x27, 6)
            word(d, h+0x29, total)
        else:
            word(d, h+0x27, parent[0])
            d[h+0x29] = parent[1] + 1
            d[h+0x2A] = 39
        return blocks

    def slot(self, blocks, i):
        """The ith entry slot of a directory, header excluded: (block, s)."""
        i += 1
        return blocks[i // 13], i % 13

    def entry(self, blocks, i, name, storage=1, ftype=0x06, key=100, access=ACCESS, date=0, time=0):
        b, s = self.slot(blocks, i)
        e = bytearray(39)
        e[0] = storage << 4 | len(name)
        e[1:1+len(name)] = name
        e[16] = ftype
        word(e, 17, key)
        e[30] = access
        word(e, 33, date)
        word(e, 35, time)
        word(e, 37, blocks[0])
        at = b*512 + 4 + 39*s
        self.d[at:at+39] = e
        self.count(blocks, +1)
        return b, s

    def count(self, blocks, n):
        at = blocks[0]*512 + 0x25
        word(self.d, at, int.from_bytes(self.d[at:at+2], 'little') + n)

    def subdir(self, parent, i, name, blocks, access=ACCESS):
        b, s = self.entry(parent, i, name, storage=13, ftype=0x0F, key=blocks[0], access=access)
        return self.directory(blocks, name, 0xE, parent=(b, s))

    def deleted(self, blocks, i, name):
        """A deleted entry: storage nibble 0, the rest left behind."""
        b, s = self.slot(blocks, i)
        at = b*512 + 4 + 39*s
        self.d[at+1:at+1+len(name)] = name
        self.d[at] = len(name)


def listing(d, key):
    """The entries of the directory at `key`, in disk order: (name, block, slot)."""
    out, b = [], key
    while b:
        blk = d[b*512:(b+1)*512]
        for s in range(13):
            if b == key and not s:
                continue
            e = blk[4+39*s:4+39*s+39]
            if e[0] >> 4:
                out.append((bytes(e[1:1+(e[0] & 15)]).decode(), b, s))
        b = int.from_bytes(blk[2:4], 'little')
    return out


def parent_of(d, key):
    h = key * 512
    return int.from_bytes(d[h+0x27:h+0x29], 'little'), d[h+0x29]


class DirSort(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='dirsort-')
        cls.work = Path(cls.tmp.name)
        (cls.work/'h.c').write_text(HARNESS)
        cls.exe = cls.work/'h'
        subprocess.run(['cc', '-std=c99', '-w', '-ftrivial-auto-var-init=pattern', '-I', str(ROOT),
                        str(cls.work/'h.c'), '-o', str(cls.exe)], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_sort(self, vol, path='/V', keys='', *opts, other=None):
        img = self.work/'v.po'
        img.write_bytes(vol.d if isinstance(vol, Volume) else vol)
        args = [str(self.exe), str(img), path, keys, *opts]
        if other is not None:
            (self.work/'o.po').write_bytes(other)
            args.append('other=' + str(self.work/'o.po'))
        out = subprocess.check_output(args, timeout=10).decode()
        writes, note, asked, screen = out.split('\n', 3)
        return int(writes), note, asked, screen, bytearray(img.read_bytes())

    def unchanged(self, vol, *args, **kw):
        writes, note, _, _, after = self.run_sort(vol, *args, **kw)
        self.assertEqual(writes, 0, note)
        self.assertEqual(after, vol.d, note)
        return note

    # -- fixtures ------------------------------------------------------------
    def boot_volume(self):
        """PRODOS, ZED, BASIC.SYSTEM, a deleted slot, A2FILE.SYSTEM, ALPHA."""
        v = Volume()
        r = v.root
        v.entry(r, 0, b'PRODOS', ftype=0xFF)
        v.entry(r, 1, b'ZED', ftype=0x04)
        v.entry(r, 2, b'BASIC.SYSTEM', ftype=0xFF)
        v.deleted(r, 3, b'GONE')
        v.entry(r, 4, b'A2FILE.SYSTEM', ftype=0xFF)
        v.entry(r, 5, b'ALPHA', ftype=0x06)
        return v

    def spread_volume(self):
        """A root of two blocks, entries in both, a subdirectory in each."""
        v = Volume(root_blocks=2)
        r = v.root
        names = [b'M%02d' % i for i in range(20)]
        for i, n in enumerate(names):
            if i in (3, 15):
                continue
            v.entry(r, i, n, key=100+i)
        v.subdir(r, 3, b'ZDIR', [40])
        v.subdir(r, 15, b'ADIR', [41, 42])
        return v

    # -- writes ---------------------------------------------------------------
    def test_sort_by_name_keeps_slots_and_header(self):
        v = self.boot_volume()
        writes, note, asked, _, after = self.run_sort(v, '/V', 'NW')
        self.assertEqual(note, 'Reordered: every block read back.')
        self.assertEqual(asked, 'Write this order to /V?')
        self.assertEqual([n for n, _, _ in listing(after, 2)],
                         ['A2FILE.SYSTEM', 'ALPHA', 'BASIC.SYSTEM', 'PRODOS', 'ZED'])
        # The deleted slot stays where it was, the header is untouched.
        self.assertEqual(after[2*512+4+39*4:2*512+4+39*5], v.d[2*512+4+39*4:2*512+4+39*5])
        self.assertEqual(after[2*512:2*512+4+39], v.d[2*512:2*512+4+39])
        # Each entry moved whole: the same 39 bytes, in another slot.
        before = {bytes(v.d[2*512+4+39*s+1:2*512+4+39*s+16]): v.d[2*512+4+39*s:2*512+4+39*s+39]
                  for s in range(1, 13) if v.d[2*512+4+39*s] >> 4}
        for s in range(1, 13):
            e = after[2*512+4+39*s:2*512+4+39*s+39]
            if e[0] >> 4:
                self.assertEqual(e, before[bytes(e[1:16])])
        self.assertEqual(after[3*512:], v.d[3*512:])
        self.assertEqual(writes, 1)

    def test_boot_mark_follows_the_order(self):
        v = self.boot_volume()
        _, _, _, screen, _ = self.run_sort(v, '/V', '')
        self.assertIn('BASIC.SYSTEM    $FF  <- boots', screen)
        self.assertEqual(screen.count('<- boots'), 1)
        # Carry A2FILE.SYSTEM (4th) above BASIC.SYSTEM: it boots instead.
        _, _, _, screen, _ = self.run_sort(v, '/V', 'ddd uu')
        self.assertIn('>A2FILE.SYSTEM   $FF  <- boots', screen)
        self.assertNotIn('BASIC.SYSTEM    $FF  <- boots', screen)

    def test_sort_by_type_then_name(self):
        v = self.boot_volume()
        writes, note, _, _, after = self.run_sort(v, '/V', 'TW')
        self.assertEqual(note, 'Reordered: every block read back.')
        self.assertEqual([n for n, _, _ in listing(after, 2)],
                         ['ZED', 'ALPHA', 'A2FILE.SYSTEM', 'BASIC.SYSTEM', 'PRODOS'])

    def test_sort_by_date_oldest_first(self):
        """ProDOS years 0-39 are 2000-2039 and come after 40-99; no date
        comes first; same day, the time decides; same date, the name."""
        def date(y, m, d):
            return y << 9 | m << 5 | d
        v = Volume()
        r = v.root
        v.entry(r, 0, b'Y2005', date=date(5, 1, 1))
        v.entry(r, 1, b'Y1999', date=date(99, 12, 31))
        v.entry(r, 2, b'NODATE')
        v.entry(r, 3, b'LATE', date=date(5, 1, 1), time=13 << 8 | 5)
        v.entry(r, 4, b'EARLY', date=date(5, 1, 1), time=9 << 8 | 59)
        v.entry(r, 5, b'Y1985', date=date(85, 6, 2))
        v.entry(r, 6, b'Y1985B', date=date(85, 6, 2))
        v.entry(r, 7, b'Y2005A', date=date(5, 1, 1))
        writes, note, _, _, after = self.run_sort(v, '/V', 'DW')
        self.assertEqual(note, 'Reordered: every block read back.')
        self.assertEqual([n for n, _, _ in listing(after, 2)],
                         ['NODATE', 'Y1985', 'Y1985B', 'Y1999', 'Y2005', 'Y2005A', 'EARLY', 'LATE'])

    def test_nested_subdirectory_target(self):
        v = Volume()
        d = v.subdir(v.root, 0, b'D', [50])
        e = v.subdir(d, 0, b'E', [55])
        v.entry(e, 0, b'B'); v.entry(e, 1, b'A')
        writes, note, _, _, after = self.run_sort(v, '/V/D/E', 'NW')
        self.assertEqual(note, 'Reordered: every block read back.')
        self.assertEqual([n for n, _, _ in listing(after, 55)], ['A', 'B'])
        self.assertEqual(writes, 1)

    def test_target_proved_from_its_parent_entry(self):
        """The core's reader gives a file type, not a storage type: a plain
        file of type $0F, or a header whose parent entry is not this
        directory's, is refused before anything is shown."""
        bad = 'Directory inconsistent (see FIXIT): nothing written.'
        v = Volume()
        d = v.subdir(v.root, 0, b'D', [50])
        v.entry(d, 0, b'B'); v.entry(d, 1, b'A')
        v.d[2*512+4+39] = 0x10 | 1            # D's entry: storage 1, type still $0F
        self.assertEqual(self.unchanged(v, '/V/D', 'NW'), bad)
        v = Volume()
        d = v.subdir(v.root, 0, b'D', [50])
        v.entry(d, 0, b'B'); v.entry(d, 1, b'A')
        v.entry(v.root, 1, b'X')
        v.d[50*512+0x29] = 3                  # D's header names X's slot
        self.assertEqual(self.unchanged(v, '/V/D', 'NW'), bad)

    def test_carry_then_write(self):
        v = self.boot_volume()
        writes, note, _, _, after = self.run_sort(v, '/V', 'ddd uu W')
        self.assertEqual(note, 'Reordered: every block read back.')
        self.assertEqual([n for n, _, _ in listing(after, 2)],
                         ['PRODOS', 'A2FILE.SYSTEM', 'ZED', 'BASIC.SYSTEM', 'ALPHA'])

    def test_moved_subdirectories_point_back_at_their_new_slot(self):
        v = self.spread_volume()
        writes, note, _, _, after = self.run_sort(v, '/V', 'NW')
        self.assertEqual(note, 'Reordered: every block read back.')
        rows = listing(after, 2)
        self.assertEqual([n for n, _, _ in rows], sorted(n for n, _, _ in rows))
        where = {n: (b, s + 1) for n, b, s in rows}
        self.assertEqual(parent_of(after, 40), where['ZDIR'])
        self.assertEqual(parent_of(after, 41), where['ADIR'])
        self.assertNotEqual(parent_of(v.d, 41), where['ADIR'])   # it did move
        # Only the two root blocks and the two child headers were written.
        self.assertEqual(writes, 4)
        self.assertEqual(after[42*512:], v.d[42*512:])

    def test_subdirectory_target(self):
        v = Volume()
        d = v.subdir(v.root, 0, b'D', [50, 51])
        v.entry(d, 0, b'Y')
        v.subdir(d, 1, b'X', [60])
        v.entry(d, 2, b'W')
        writes, note, asked, _, after = self.run_sort(v, '/V/D', 'NW')
        self.assertEqual(asked, 'Write this order to /V/D?')
        rows = listing(after, 50)
        self.assertEqual([n for n, _, _ in rows], ['W', 'X', 'Y'])
        self.assertEqual(parent_of(after, 60), (50, 3))
        self.assertEqual(after[2*512:3*512], v.d[2*512:3*512])

    # -- nothing written ------------------------------------------------------
    def test_escape_no_and_same_order_write_nothing(self):
        v = self.boot_volume()
        self.assertEqual(self.unchanged(v, '/V', 'N'), 'Nothing written.')
        self.assertEqual(self.unchanged(v, '/V', 'NW', 'no=1'), 'Nothing written.')
        self.assertEqual(self.unchanged(v, '/V', 'NRW'), 'Order unchanged: nothing written.')
        self.assertEqual(self.unchanged(v, '/V', 'dddddW'), 'Order unchanged: nothing written.')

    def test_disk_changed_under_the_confirmation(self):
        v = self.boot_volume()
        o = self.boot_volume()
        o.entry(o.root, 6, b'NEW')
        writes, note, _, _, after = self.run_sort(v, '/V', 'NW', other=o.d)
        self.assertEqual(note, 'Directory changed or unreadable: nothing written.')
        self.assertEqual(writes, 0)
        self.assertEqual(bytes((self.work/'o.po').read_bytes()), bytes(o.d))

    def test_child_changed_under_the_confirmation(self):
        v = self.spread_volume()
        o = self.spread_volume()
        word(o.d, 41*512+0x27, 2)          # ADIR's header now names block 2
        writes, note, _, _, _ = self.run_sort(v, '/V', 'NW', other=o.d)
        self.assertEqual(note, 'Directory changed or unreadable: nothing written.')
        self.assertEqual(writes, 0)
        self.assertEqual(bytes((self.work/'o.po').read_bytes()), bytes(o.d))

    def test_refusals(self):
        bad = 'Directory inconsistent (see FIXIT): nothing written.'
        cases = []
        v = self.boot_volume(); word(v.d, 2*512+0x25, 9); cases.append(('file count', v, bad))
        v = self.boot_volume(); v.entry(v.root, 7, b'PASCAL', storage=4); cases.append(('storage 4', v, bad))
        v = self.boot_volume(); word(v.d, 2*512+4+39*1+37, 3); cases.append(('header pointer', v, bad))
        v = self.boot_volume(); v.d[2*512+0x23] = 40; cases.append(('entry length', v, bad))
        v = self.boot_volume(); word(v.d, 3*512, 9); cases.append(('back link', v, bad))
        v = self.boot_volume(); word(v.d, 3*512+2, 300); cases.append(('link off the volume', v, bad))
        v = self.spread_volume(); v.d[41*512+0x29] = 9; cases.append(('child entry number', v, bad))
        v = self.spread_volume(); word(v.d, 40*512+0x27, 3); cases.append(('child parent block', v, bad))
        v = self.boot_volume(); v.d[2*512+0x22] = 0x01
        cases.append(('volume write-protected', v, 'Write-protected: nothing written.'))
        v = Volume(root_blocks=5); v.entry(v.root, 0, b'A'); v.entry(v.root, 1, b'B')
        cases.append(('five blocks', v, 'Directory too big: nothing written.'))
        for what, v, note in cases:
            with self.subTest(what):
                self.assertEqual(self.unchanged(v, '/V', 'NW'), note)

    def test_locked_subdirectory_is_refused(self):
        v = Volume()
        d = v.subdir(v.root, 0, b'D', [50], access=0x01)
        v.entry(d, 0, b'B'); v.entry(d, 1, b'A')
        self.assertEqual(self.unchanged(v, '/V/D', 'NW'), 'Write-protected: nothing written.')

    def test_locked_child_subdirectory_does_not_move(self):
        """Its header is in the subdirectory itself: a locked one is never
        written, so an order that moves it writes nothing. Left in place,
        the rest is sorted; a locked file moves (its entry is the parent's)."""
        v = Volume()
        v.subdir(v.root, 0, b'S', [40], access=0x01)
        v.entry(v.root, 1, b'B'); v.entry(v.root, 2, b'A')
        self.assertEqual(self.unchanged(v, '/V', 'NW'), 'Locked subdirectory: nothing written.')
        v = Volume()
        v.entry(v.root, 0, b'B', access=0x01); v.entry(v.root, 1, b'A')
        v.subdir(v.root, 2, b'S', [40], access=0x01)
        writes, note, _, _, after = self.run_sort(v, '/V', 'NW')
        self.assertEqual(note, 'Reordered: every block read back.')
        self.assertEqual([n for n, _, _ in listing(after, 2)], ['A', 'B', 'S'])
        self.assertEqual(after[40*512:41*512], v.d[40*512:41*512])

    def test_image_panel_and_missing_directory(self):
        v = self.boot_volume()
        self.assertEqual(self.unchanged(v, '/V', 'NW', 'fs=1'), 'Open a ProDOS directory first.')
        self.assertEqual(self.unchanged(v, '', 'NW'), 'Open a ProDOS directory first.')
        self.assertEqual(self.unchanged(v, '/V/NOPE', 'NW'),
                         'Directory inconsistent (see FIXIT): nothing written.')
        self.assertEqual(self.unchanged(v, '/W', 'NW'), 'Volume not on line, or two with this name.')
        self.assertEqual(self.unchanged(v, '/V', 'NW', 'twin=1'), 'Volume not on line, or two with this name.')

    # -- failed writes are put back -------------------------------------------
    def test_failed_writes_are_put_back(self):
        """A block write fails three ways, a child header write fails after
        reaching the disk: every byte comes back as it was."""
        for opts in (('failw=2', 'mode=0'), ('failw=2', 'mode=1'), ('failw=2', 'mode=2'),
                     ('failw=1', 'mode=2'), ('failw=3', 'mode=0'), ('failw=3', 'mode=1'),
                     ('failw=4', 'mode=1')):
            with self.subTest(opts):
                v = self.spread_volume()
                writes, note, _, _, after = self.run_sort(v, '/V', 'NW', *opts)
                self.assertEqual(note, 'Write failed: put back as it was.')
                self.assertEqual(after, v.d)
                self.assertGreater(writes, int(opts[0][6:]))

    def test_restore_that_fails_names_the_block(self):
        v = self.spread_volume()
        writes, note, _, _, after = self.run_sort(v, '/V', 'NW', 'failw=2', 'mode=0', 'after=1')
        # Block 3 was refused and still reads as it was: block 2, written
        # and not put back, is the one named.
        self.assertEqual(note, 'RESTORE FAILED (block 2): copy files off, run FIXIT.')
        self.assertEqual(after[3*512:4*512], v.d[3*512:4*512])
        v = self.spread_volume()
        writes, note, _, _, after = self.run_sort(v, '/V', 'NW', 'failw=3', 'mode=0', 'after=1')
        # The refused child header is as it was; both directory blocks
        # were written and cannot be put back: the first tried is named.
        self.assertEqual(note, 'RESTORE FAILED (block 3): copy files off, run FIXIT.')
        self.assertEqual(after[41*512:42*512], v.d[41*512:42*512])

    def test_failed_first_block_undoes_no_stale_child(self):
        """Before: a failed directory-block write reached the undo with the
        child count never set; on the Apple II (BSS not zeroed) it walked
        stale entries, rewrote a child header and said RESTORE FAILED."""
        for opts in (('protect=1',), ('failw=1', 'mode=0'), ('failw=1', 'mode=2')):
            with self.subTest(opts):
                v = Volume()
                v.subdir(v.root, 0, b'S', [40])
                v.entry(v.root, 1, b'B'); v.entry(v.root, 2, b'A')
                writes, note, _, _, after = self.run_sort(v, '/V', 'NW', *opts)
                self.assertEqual(note, 'Write failed: put back as it was.')
                self.assertEqual(after, v.d)
                self.assertEqual(writes, 1 if opts[-1] != 'mode=2' else 2)

    def test_write_protected_disk_is_not_a_failed_restore(self):
        """Before: the refused first write was followed by a refused
        restore, and an untouched disk was reported RESTORE FAILED."""
        v = self.spread_volume()
        writes, note, _, _, after = self.run_sort(v, '/V', 'NW', 'protect=1')
        self.assertEqual(note, 'Write failed: put back as it was.')
        self.assertEqual(after, v.d)
        self.assertEqual(writes, 1)

    def test_refused_writes_are_not_rewritten(self):
        """A refused write leaves its block as it was: only what reached the
        disk is written again."""
        v = self.spread_volume()
        writes, note, _, _, after = self.run_sort(v, '/V', 'NW', 'failw=2', 'mode=0')
        self.assertEqual(note, 'Write failed: put back as it was.')
        self.assertEqual(after, v.d)
        self.assertEqual(writes, 3)        # block 2, block 3 refused, block 2 put back
        v = self.spread_volume()
        writes, note, _, _, after = self.run_sort(v, '/V', 'NW', 'failw=3', 'mode=0')
        self.assertEqual(note, 'Write failed: put back as it was.')
        self.assertEqual(after, v.d)
        self.assertEqual(writes, 5)        # two blocks, a refused child, two blocks back

    def test_child_header_written_wrong_is_not_called_restored(self):
        """A child header the disk took wrong cannot be rebuilt: its
        original is not in memory. The put back is then checked against the
        sum the header had, and the run says RESTORE FAILED with its block
        instead of "put back"."""
        for failw, block in (('failw=3', 41), ('failw=4', 40)):
            with self.subTest(failw):
                v = self.spread_volume()
                writes, note, _, _, after = self.run_sort(v, '/V', 'NW', failw, 'mode=2')
                self.assertEqual(note, 'RESTORE FAILED (block %d): copy files off, run FIXIT.' % block)
                # The directory blocks themselves came back.
                self.assertEqual(after[2*512:4*512], v.d[2*512:4*512])

    def test_read_errors_before_anything_is_shown(self):
        """A block of the chain, a child header, the parent entry's block:
        none can be read, nothing is shown and nothing written."""
        changed = 'Directory changed or unreadable: nothing written.'
        for block, note in ((3, changed), (40, changed), (41, changed)):
            with self.subTest(block=block):
                self.assertEqual(self.unchanged(self.spread_volume(), '/V', 'NW', 'readpre=%d' % block), note)
        v = Volume()
        d = v.subdir(v.root, 0, b'D', [50, 51])
        e = v.subdir(d, 0, b'E', [55])
        v.entry(e, 0, b'B'); v.entry(e, 1, b'A')
        # 55: the target's key block; 50: the block of its parent entry.
        for block in (55, 50):
            with self.subTest(block=block):
                self.assertEqual(self.unchanged(v, '/V/D/E', 'NW', 'readpre=%d' % block), changed)

    def test_child_unreadable_during_the_undo(self):
        """The second child header fails after reaching the disk, and the
        first one can no longer be read: it is named, the blocks still go
        back."""
        v = self.spread_volume()
        writes, note, _, _, after = self.run_sort(v, '/V', 'NW', 'failw=4', 'mode=1',
                                                  'readfail=41', 'readw=4')
        self.assertEqual(note, 'RESTORE FAILED (block 41): copy files off, run FIXIT.')
        self.assertEqual(after[2*512:4*512], v.d[2*512:4*512])

    def test_cross_linked_parent_entry_is_refused(self):
        """D's header names, as its parent, another entry with D's key but
        another name: the listing found D, the header proves X. Refused."""
        v = Volume()
        d = v.subdir(v.root, 0, b'D', [50])
        v.entry(d, 0, b'B'); v.entry(d, 1, b'A')
        v.entry(v.root, 1, b'X', storage=13, ftype=0x0F, key=50)
        v.d[50*512+0x29] = 3                  # D's header: entry 3 of block 2, X
        self.assertEqual(self.unchanged(v, '/V/D', 'NW'),
                         'Directory inconsistent (see FIXIT): nothing written.')

    def test_read_error_after_the_confirmation(self):
        v = self.boot_volume()
        writes, note, _, _, after = self.run_sort(v, '/V', 'NW', 'readfail=2')
        self.assertEqual(note, 'Directory changed or unreadable: nothing written.')
        self.assertEqual(writes, 0)
        self.assertEqual(after, v.d)


class DirSortFuzz(unittest.TestCase):
    """Random volumes made by tools/mkvolume.py (some entries then deleted
    in place), random keys, random failures. Whatever happens, the disk
    either keeps every byte, or is reordered with nothing else changed --
    tools/prodos_check.py finds what it found before, every file keeps its
    bytes -- or the note says RESTORE FAILED. Seeded: a failure replays."""
    # DIRSORT_FUZZ_SEED / DIRSORT_FUZZ_RUNS for a longer campaign.
    RUNS = int(__import__('os').environ.get('DIRSORT_FUZZ_RUNS', 600))

    @classmethod
    def setUpClass(cls):
        DirSort.setUpClass()
        cls.runner = DirSort('run_sort')

    @classmethod
    def tearDownClass(cls):
        DirSort.tearDownClass()

    def volume(self, rnd, work):
        import sys
        sys.path.insert(0, str(ROOT / 'tools'))
        stage = work / 'stage'
        shutil.rmtree(stage, ignore_errors=True)
        dirs = ['']
        for i in range(rnd.randrange(4)):
            dirs.append('S%c%d' % (rnd.choice('ABCZ'), i))
        used = {('', x) for x in dirs[1:]}     # a file never takes a subdirectory's name
        for d in dirs:
            for _ in range(rnd.randrange(3, 40 if d else 45)):
                name = rnd.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ') + ''.join(
                    rnd.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.') for _ in range(rnd.randrange(0, 9)))
                if name.endswith('.') or (d, name) in used:
                    continue
                used.add((d, name))
                kind = rnd.choice(('FF2000', '060000', '040000', 'FC0801', '0F0000'[:0] or '190000'))
                path = stage / d / ('%s#%s' % (name, kind))
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(bytes(rnd.randrange(256) for _ in range(rnd.randrange(0, 1400))))
            (stage / d).mkdir(parents=True, exist_ok=True)
        po = work / 'f.po'
        r = subprocess.run(['python3', str(ROOT / 'tools/mkvolume.py'), str(stage), str(po),
                            '--volume', 'V', '--blocks', '800'], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr[-400:])
        d = bytearray(po.read_bytes())
        # Delete a few entries in place, as ProDOS leaves them: storage 0,
        # the count down; their blocks become lost, before and after alike.
        for key in [2] + [int.from_bytes(e[17:19], 'little') for e in Image(bytes(d)).entries(2) if e[0] >> 4 == 13]:
            for e_at in self.slots(d, key):
                if not d[e_at] >> 4:
                    continue
                # Dates of 1940-2039 and times, not mkvolume's fixed one.
                word(d, e_at+33, rnd.randrange(128) << 9 | rnd.randrange(1, 13) << 5 | rnd.randrange(1, 29))
                word(d, e_at+35, rnd.randrange(24) << 8 | rnd.randrange(60))
                if rnd.random() < 0.08 and d[e_at] >> 4 in (1, 2, 3):
                    d[e_at] &= 0x0F
                    word(d, key*512+0x25, int.from_bytes(d[key*512+0x25:key*512+0x27], 'little') - 1)
        targets = ['/V'] + ['/V/' + x for x in dirs[1:]]
        return d, rnd.choice(targets)

    @staticmethod
    def slots(d, key):
        b, first = key, True
        while b:
            for s in range(13):
                if not (first and not s):
                    yield b*512 + 4 + 39*s
            first = False
            b = int.from_bytes(d[b*512+2:b*512+4], 'little')

    @staticmethod
    def contents(d):
        img, out = Image(bytes(d)), {}
        def walk(key, prefix):
            for e in img.entries(key):
                name = prefix + '/' + e[1:1 + (e[0] & 15)].decode()
                if e[0] >> 4 == 13:
                    out[name] = 'DIR'; walk(int.from_bytes(e[17:19], 'little'), name)
                else:
                    out[name] = (bytes(e[16:17]) + bytes(e[33:37]), img.read(e))
        walk(2, '')
        return out

    @staticmethod
    def findings(d):
        return sorted((f.id, f.block, f.expected, f.found) for f in check(bytes(d)).findings)

    def test_random_volumes_keys_and_failures(self):
        import random, sys
        sys.path.insert(0, str(ROOT / 'tools'))
        global Image, check
        from prodos_read import Image
        from prodos_check import check
        rnd = random.Random(int(__import__('os').environ.get('DIRSORT_FUZZ_SEED', 20261025)))
        work = Path(self.runner.work)
        outcomes = {}
        for run in range(self.RUNS):
            if run % 6 == 0:
                d, target = self.volume(rnd, work)
                before_find, before_files = self.findings(d), self.contents(d)
            keys = ''.join(rnd.choice('NTTDDD  ududdd') for _ in range(rnd.randrange(1, 18))) + rnd.choice((' W', 'W', ' W', 'We'))
            opts = []
            r = rnd.random()
            if r < 0.15:
                opts = ['protect=1']
            elif r < 0.55:
                opts = ['failw=%d' % rnd.randrange(1, 7), 'mode=%d' % rnd.randrange(3)]
                if rnd.random() < 0.3:
                    opts.append('after=1')
            if rnd.random() < 0.1:
                opts.append('no=1')
            writes, note, _, _, after = self.runner.run_sort(bytes(d), target, keys, *opts)
            what = (run, target, keys, opts, note)
            outcomes[note.split(':')[0].split(' (')[0]] = outcomes.get(note.split(':')[0].split(' (')[0], 0) + 1
            if note == 'Reordered: every block read back.':
                self.assertNotIn('protect=1', opts, what)
                self.assertEqual(self.findings(after), before_find, what)
                self.assertEqual(self.contents(after), before_files, what)
            elif note.startswith('RESTORE FAILED (block '):
                self.assertTrue(any(o.startswith(('failw', 'protect')) for o in opts), what)
                # Never a false alarm: the disk really is not as it was.
                self.assertTrue(after != d, what)
            else:
                self.assertIn(note, ('Nothing written.', 'Order unchanged: nothing written.',
                                     'Write failed: put back as it was.',
                                     'Directory too big: nothing written.',
                                     'Locked subdirectory: nothing written.'), what)
                self.assertEqual(after, d, what)
        # The fuzz reached what it is for.
        self.assertGreater(outcomes.get('Reordered', 0), 40, outcomes)
        self.assertGreater(outcomes.get('Write failed', 0), 20, outcomes)


# The same overlay compiled by each edition's cc65 (-Cl, as the Makefile)
# and run under sim65: what the host compiler cannot show -- cc65's code,
# its static locals, and the screen services reached through the stubs of
# service_stubs.h, whose arguments the services below record.
SIM_HARNESS = r"""
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include "p/dirsort.c"
#define NB 24
static unsigned char disk[NB * 512u];
static unsigned int nwrite, fail_write;
static unsigned char fail_mode, protect, yes = 1;
static const char* keys;
static char screen[1600];
static unsigned int sl;
static void out(const char* s) { while (*s && sl < sizeof screen - 1) screen[sl++] = *s++; screen[sl] = 0; }
struct Bk { unsigned char n, u; unsigned char* buf; unsigned int block; };
static unsigned char mock_mli(unsigned char cmd, void* p)
{
    struct Bk* b = p;
    if (cmd == 0xC5) {
        memset(b->buf, 0, 256);
        b->buf[0] = 0x60 | (disk[1028] & 15); memcpy(b->buf + 1, disk + 1029, 15);
        return 0;
    }
    if ((cmd != 0x80 && cmd != 0x81) || b->n != 3) exit(7);
    if (b->u != 0x60) return 0x28;
    if (b->block >= NB) return 0x27;
    if (cmd == 0x80) { memcpy(b->buf, disk + b->block * 512u, 512); return 0; }
    ++nwrite;
    if (protect) return 0x2B;
    if (nwrite == fail_write) {
        if (!fail_mode) return 0x27;
        memcpy(disk + b->block * 512u, b->buf, 512);
        if (fail_mode == 2) { disk[b->block * 512u + 300] ^= 0x55; return 0; }
        return 0x27;
    }
    memcpy(disk + b->block * 512u, b->buf, 512);
    return 0;
}
/* The core's reader: the path resolved by name from block 2. */
static struct DirEntry dent;
static unsigned char dblk[512];
static unsigned int dnext;
static unsigned char dslot;
static unsigned char d_open(const char* path)
{
    unsigned int bl = 2, c, found;
    const char* p = strchr(path + 1, '/');
    const char* q;
    unsigned char n, s, *e;
    while (p) {
        q = strchr(p + 1, '/');
        n = q ? q - p - 1 : strlen(p + 1);
        found = 0;
        for (c = bl; c && !found; c = disk[c * 512u + 2] | disk[c * 512u + 3] << 8)
            for (s = 0; s < 13; ++s) {
                e = disk + c * 512u + 4 + 39 * s;
                if ((e[0] >> 4) == 13 && (e[0] & 15) == n && !memcmp(e + 1, p + 1, n)) found = e[17] | e[18] << 8;
            }
        if (!found) return 0;
        bl = found; p = q;
    }
    memcpy(dblk, disk + bl * 512u, 512);
    dnext = dblk[2] | dblk[3] << 8; dslot = 1;
    return 1;
}
static unsigned char d_next(void)
{
    unsigned char* e;
    for (;;) {
        if (dslot == 13) {
            if (!dnext) return 0;
            memcpy(dblk, disk + dnext * 512u, 512);
            dnext = dblk[2] | dblk[3] << 8; dslot = 0;
        }
        e = dblk + 4 + 39 * dslot++;
        if (!(e[0] >> 4)) continue;
        memcpy(dent.name, e + 1, e[0] & 15); dent.name[e[0] & 15] = 0;
        dent.type = e[16]; dent.key = e[17] | e[18] << 8; dent.access = e[30];
        return 1;
    }
}
static void d_close(void) {}
/* The screen services: what reaches them, through the stubs. */
static void s_gotoxy(unsigned char x, unsigned char y) { char t[12]; sprintf(t, "@%u,%u ", x, y); out(t); }
static unsigned char s_revers(unsigned char on) { out(on ? "[R1]" : "[R0]"); return 0; }
static void s_clrscr(void) { sl = 0; screen[0] = 0; out("[CLS]"); }
static char s_cgetc(void) { char k = *keys ? *keys++ : 'e'; return k == 'u' ? 11 : k == 'd' ? 10 : k == 'e' ? 27 : k; }
static void s_cputs(const char* s) { out(s); }
static void s_bar(unsigned char x, const char* s) { char t[10]; sprintf(t, "<BAR%u>", x); out(t); out(s); }
static int s_cprintf(const char* f, ...) { char t[100]; va_list ap; va_start(ap, f); vsprintf(t, f, ap); va_end(ap); out(t); return 0; }
static unsigned char s_confirm(const char* s) { out("[ASK]"); out(s); return yes; }
int main(int argc, char** argv)
{
    static struct A2fcApi api;
    static struct Panel panels[2];
    static struct Entry selected;
    static unsigned char active, copy[512];
    static char note_[80];
    FILE* f = fopen("disk.bin", "rb");
    (void)argc;
    if (!f || fread(disk, 1, sizeof disk, f) != sizeof disk) return 9;
    fclose(f);
    strcpy(panels[0].path, argv[1]);
    keys = argv[2];
    fail_write = atoi(argv[3]);
    fail_mode = atoi(argv[4]);
    protect = strchr(argv[5], 'p') != 0;
    yes = strchr(argv[5], 'n') == 0;
    api.panels = panels; api.active = &active; api.selected = &selected;
    api.copy_buf = copy; api.note = note_;
    api.mli = mock_mli; api.memcpy = memcpy; api.memset = memset; api.strcpy = strcpy;
    api.strcmp = strcmp; api.strlen = strlen; api.sprintf = sprintf;
    api.cprintf = s_cprintf; api.cputs = s_cputs; api.gotoxy = s_gotoxy;
    api.clrscr = s_clrscr; api.revers = s_revers; api.cgetc = s_cgetc; api.keys_bar = s_bar;
    api.confirm = s_confirm;
    api.dir_open = d_open; api.dir_next = d_next; api.dir_close = d_close; api.dir_entry = &dent;
    /* BSS as the Apple II leaves it: stale indexes that name real entries. */
    memset(order, 0, sizeof order); memset(eb, 0, sizeof eb); memset(es, 0, sizeof es);
    memset(csum, 0xAA, sizeof csum);
    plugin_entry(&api);
    fwrite(disk, 1, sizeof disk, stdout);
    printf("%u\n%s\n%s", nwrite, note_, screen);
    return 0;
}
"""


class DirSortCc65(unittest.TestCase):
    """The cc65 build of each edition, at -Cl, against the same fixtures:
    the bytes on the disk, the note, and the screen as the services saw it."""
    BLOCKS = 24

    @classmethod
    def setUpClass(cls):
        chains = toolchains()
        if not chains:
            raise unittest.SkipTest('no cc65 toolchain')
        cls.tmp = tempfile.TemporaryDirectory(prefix='dirsort-cc65-')
        d = cls.dir = Path(cls.tmp.name)
        (d / 'harness.c').write_text(SIM_HARNESS)
        (d / 'p').mkdir()
        for name in ('dirsort.c', 'util.h', 'service_stubs.h'):
            shutil.copyfile(ROOT / 'src/plugins' / name, d / 'p' / name)
        shutil.copyfile(ROOT / 'src/a2fc_plugin.h', d / 'a2fc_plugin.h')
        cls.exe = {}
        for cpu, cl65, sim65, env, cfgdir in chains:
            cfg, n = re.subn(r'start = \$0200, size = [^;]*;',
                             'start = $2000, size = $C000 - $2000 - __STACKSIZE__;',
                             (cfgdir / f'{cpu}.cfg').read_text())
            assert n == 1, cpu
            cfg = cfg.replace('    RODATA:', '    OVLHDR:   load = MAIN, type = ro;\n    RODATA:', 1)
            (d / f'{cpu}.cfg').write_text(cfg)
            exe = d / f'dirsort-{cpu}'
            env = {**__import__('os').environ, **env}
            subprocess.run([cl65, '-t', cpu, '-C', str(d / f'{cpu}.cfg'), '-O', '-Oirs', '-Cl',
                            '--codesize', '100', '-I', str(d / 'p'), '-o', str(exe), str(d / 'harness.c')],
                           check=True, cwd=d, env=env, capture_output=True)
            cls.exe[cpu] = (sim65, exe, env)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_sim(self, vol, path, keys, failw=0, mode=0, flags='-'):
        """(disk, writes, note, screen), the same for every compiler."""
        size = self.BLOCKS * 512
        (self.dir / 'disk.bin').write_bytes(bytes(vol.d[:size]))
        got = {}
        for cpu, (sim65, exe, env) in self.exe.items():
            r = subprocess.run([sim65, str(exe), path, keys, str(failw), str(mode), flags],
                               cwd=self.dir, env=env, capture_output=True, timeout=300)
            self.assertEqual(r.returncode, 0, (cpu, r.stderr))
            writes, note, screen = r.stdout[size:].decode().split('\n', 2)
            got[cpu] = (bytearray(r.stdout[:size]), int(writes), note, screen)
        values = list(got.values())
        for other in values[1:]:
            self.assertEqual(other, values[0], 'the compilers disagree')
        return values[0]

    def volume(self):
        v = Volume(total=self.BLOCKS, root_blocks=2)
        r = v.root
        v.entry(r, 0, b'PRODOS', ftype=0xFF)
        for i in range(1, 12):
            v.entry(r, i, b'F%02d' % (20 - i), date=(90 - i) << 9 | 1 << 5 | 1)
        v.subdir(r, 12, b'ZDIR', [10])
        v.entry(r, 13, b'BASIC.SYSTEM', ftype=0xFF)
        v.subdir(r, 14, b'ADIR', [11])
        return v

    def test_sort_writes_the_same_bytes_as_the_host_build(self):
        for keys in ('NW', 'TW', 'DW'):
            with self.subTest(keys=keys):
                v = self.volume()
                disk, writes, note, _ = self.run_sim(v, '/V', keys)
                self.assertEqual(note, 'Reordered: every block read back.')
                host = DirSort('run').run_sort
                DirSort.setUpClass()
                try:
                    hw, hn, _, _, hdisk = host(v, '/V', keys)
                finally:
                    DirSort.tearDownClass()
                self.assertEqual((disk, writes, note), (hdisk[:self.BLOCKS * 512], hw, hn))

    def test_moved_subdirectories_point_back(self):
        v = self.volume()
        disk, writes, note, _ = self.run_sim(v, '/V', 'NW')
        where = {n: (b, s + 1) for n, b, s in listing(disk, 2)}
        self.assertEqual(parent_of(disk, 10), where['ZDIR'])
        self.assertEqual(parent_of(disk, 11), where['ADIR'])

    def test_screen_services_through_the_stubs(self):
        """Each stub hands its service the arguments it was given: the
        rows of the list, the reverse line, the key bar at column 0."""
        v = self.volume()
        _, writes, note, screen = self.run_sim(v, '/V', 'dd ')
        self.assertEqual(writes, 0)
        self.assertEqual(note, 'Nothing written.')
        self.assertTrue(screen.startswith('[CLS]DIRSORT /V@0,2 [R0] PRODOS          $FF[R0]@0,3 [R0] F19'), screen)
        self.assertIn('@0,4 [R1]>F18             $06[R0]', screen)
        self.assertIn('@0,23 <BAR0>SPC Drop,ESC Quit', screen)
        self.assertIn('BASIC.SYSTEM    $FF  <- boots', screen)
        _, _, _, screen = self.run_sim(v, '/V', '')
        self.assertIn('@0,23 <BAR0>SPC Carry,N Name,T Type,D Date,R Disk,W Write,ESC Quit', screen)

    def test_confirmation_names_the_directory(self):
        v = self.volume()
        disk, writes, note, screen = self.run_sim(v, '/V', 'NW', flags='n')
        self.assertEqual((writes, note), (0, 'Nothing written.'))
        self.assertEqual(disk, v.d[:self.BLOCKS * 512])
        self.assertIn('@0,21 A power cut while writing can damage this directory.[ASK]Write this order to /V?', screen)

    def test_failures_put_back_or_say_so(self):
        v = self.volume()
        for failw, mode, flags, note in ((0, 0, 'p', 'Write failed: put back as it was.'),
                                         (1, 0, '-', 'Write failed: put back as it was.'),
                                         (2, 2, '-', 'Write failed: put back as it was.'),
                                         (3, 1, '-', 'Write failed: put back as it was.')):
            with self.subTest(failw=failw, mode=mode, flags=flags):
                disk, writes, got, _ = self.run_sim(v, '/V', 'NW', failw, mode, flags)
                self.assertEqual(got, note)
                self.assertEqual(disk, v.d[:self.BLOCKS * 512])

    def test_subdirectory_target(self):
        v = Volume(total=self.BLOCKS)
        d = v.subdir(v.root, 0, b'D', [10, 11])
        e = v.subdir(d, 0, b'E', [12])
        v.entry(e, 0, b'B'); v.entry(e, 1, b'A')
        v.entry(d, 1, b'Z')
        disk, writes, note, _ = self.run_sim(v, '/V/D/E', 'NW')
        self.assertEqual(note, 'Reordered: every block read back.')
        self.assertEqual([n for n, _, _ in listing(disk, 12)], ['A', 'B'])
        disk, writes, note, _ = self.run_sim(v, '/V/D', 'NW')
        self.assertEqual([n for n, _, _ in listing(disk, 10)], ['E', 'Z'])
        self.assertEqual(note, 'Order unchanged: nothing written.')


if __name__ == '__main__':
    unittest.main()
