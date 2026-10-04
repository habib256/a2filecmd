"""Run the whole NRCLIP overlay (src/plugins/nrclip.s) under sim65.

The entry point runs on both processors as the program calls it, with a
service table whose every disk and file service is answered by this
script through a pipe: the clip-art disk (a .DSK or .2MG file image read
with fseek/fread, or a real drive read with READ_BLOCK through a fake MLI,
in ProDOS block order), and the destination directory, kept here as a
dictionary. Any request can be made to fail.

What is checked, against tools/newsroom_ref.py: every saved file is a BIN
$2000 created exclusively in the other panel's directory, named as the
core names DOS 3.3 files, holding exactly the 8,192 bytes of clip_page; a
damaged page (clip_page refuses it) never gets a file; an existing name is
never opened; at most one file is open at a time (the overlay's code lives
in the second ProDOS buffer, $0C00); a failed write or close removes the
file just created, and a failed removal is reported with the partial file
left; read errors, a missing or damaged index, a non-ProDOS other panel and
Escape stop with nothing else written; no auxiliary-memory switch is ever
touched, and the memory outside the overlay's own areas is left alone.
The real clip-art disks in ~/.cache/a2fc/newsroom are run when present
(only read: the script reads them into memory).
"""
import glob
import os
import random
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import newsroom_ref as ref  # noqa: E402

CORPUS = Path(os.environ.get('A2FC_NEWSROOM', Path.home() / '.cache/a2fc/newsroom'))
DEST = '/WORK/PICS'
UNIT = 0x60
GUARD = 0x5A           # the bytes the overlay must leave alone are filled with it

# argv: active, act_fs, img_len, dir_key, act_path, oth_fs, oth_path, esc_after
# ("-" stands for an empty path). Every service is a request on stdout,
# answered on stdin (see Server).
HARNESS = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include "src/a2fc_plugin.h"
void __fastcall__ plugin_entry(const struct A2fcApi*);
unsigned int getsp(void);
static struct A2fcApi api;
static struct Panel panels[2];
static unsigned char active, esc_after, closes;
static unsigned char copy_buf[512];
static char full[81], other_full[81], input[17], note[80], reselect[17];
static unsigned char fimg[4], fout[4];          /* FILE: f_fd, f_flags, f_pushback */
static void out(const void* p, unsigned n)
{
    const unsigned char* c = p;
    int r;
    while (n) { r = write(1, c, n); if (r <= 0) exit(30); c += r; n -= r; }
}
static void in(void* p, unsigned n)
{
    unsigned char* c = p;
    int r;
    while (n) { r = read(0, c, n); if (r <= 0) exit(31); c += r; n -= r; }
}
static void o8(unsigned char v) { out(&v, 1); }
static void o16(unsigned v) { o8(v & 255); o8(v >> 8); }
static unsigned char i8(void) { unsigned char v; in(&v, 1); return v; }
static unsigned i16(void) { unsigned v = i8(); return v | (unsigned)i8() << 8; }
static void ostr(const char* s) { o8(strlen(s)); out(s, strlen(s)); }
static void odd(const char* what) { o8('Z'); ostr(what); }     /* a contract broken */
static FILE* opn(const char* p, const char* m)
{
    o8('O'); o8(m[0]); ostr(p);
    if (strcmp(m, "rb") && strcmp(m, "wb")) odd("fopen mode");
    if (!i8()) return NULL;
    if (m[0] == 'r') { fimg[1] = 1; return (FILE*)fimg; }    /* _FOPEN */
    fout[1] = 1; return (FILE*)fout;
}
static int sk(FILE* f, long off, int whence)
{
    if (f != (FILE*)fimg || whence != SEEK_SET) odd("fseek");
    o8('S'); o16(off & 0xFFFF); o16(off >> 16);
    return i8() ? -1 : 0;
}
static size_t rd(void* p, size_t s, size_t n, FILE* f)
{
    unsigned got;
    if (f != (FILE*)fimg || s != 1 || p != copy_buf || n > 256) odd("fread");
    o8('R'); o16(n);
    got = i16();
    if (i8()) fimg[1] |= 4;                                  /* _FERROR */
    in(p, got);
    return got;
}
static size_t wr(const void* p, size_t s, size_t n, FILE* f)
{
    unsigned done;
    if (f != (FILE*)fout || s != 1 || p != (void*)0x2000 || n != 0x2000) odd("fwrite");
    o8('W'); o16(n); out(p, n);
    done = i16();
    if (i8()) fout[1] |= 4;
    return done;
}
static int cls(FILE* f)
{
    unsigned char r;
    if (f != (FILE*)fimg && f != (FILE*)fout) odd("fclose");
    o8('K'); o8(f == (FILE*)fimg ? 'I' : 'O');
    r = i8();
    ((unsigned char*)f)[1] = 0;
    if (f == (FILE*)fout && !r && ++closes == esc_after) *(volatile unsigned char*)0xC000 = 0x9B;
    return r ? EOF : 0;
}
static int rm(const char* p) { o8('X'); ostr(p); return i8() ? -1 : 0; }
static unsigned char mli(unsigned char cmd, void* p)
{
    unsigned char* b = p;
    unsigned char r;
    if (cmd == 0x80) {
        if (b[0] != 3 || *(unsigned char**)(b + 2) != copy_buf) odd("READ_BLOCK block");
        o8('B'); o8(b[1]); o16(b[4] | (unsigned)b[5] << 8);
        r = i8();
        if (!r) in(copy_buf, 512);
        return r;
    }
    if (cmd == 0xC0) {
        unsigned char* path = *(unsigned char**)(b + 1);
        if (path != copy_buf + 256) odd("CREATE path buffer");
        o8('C'); o8(b[0]); o8(b[3]); o8(b[4]); o16(b[5] | (unsigned)b[6] << 8); o8(b[7]);
        o16(b[8] | (unsigned)b[9] << 8); o16(b[10] | (unsigned)b[11] << 8);
        o8(path[0]); out(path + 1, path[0]);
        return i8();
    }
    o8('M'); o8(cmd);
    return i8();
}
int main(int argc, char** argv)
{
    unsigned int sp0, sp1;
    unsigned i;
    (void)argc;
    active = atoi(argv[1]);
    panels[active].fs = atoi(argv[2]);
    panels[active].img_len = atoi(argv[3]);
    panels[active].dir_key = atoi(argv[4]);
    strcpy(panels[active].path, argv[5][0] == '-' ? "" : argv[5]);
    panels[!active].fs = atoi(argv[6]);
    strcpy(panels[!active].path, argv[7][0] == '-' ? "" : argv[7]);
    esc_after = atoi(argv[8]);
    api.panels = panels; api.active = &active; api.full = full; api.other_full = other_full;
    api.input = input; api.copy_buf = copy_buf; api.note = note; api.reselect = reselect;
    api.mli = mli; api.fopen = opn; api.fread = rd; api.fwrite = wr; api.fclose = cls;
    api.fseek = sk; api.remove = rm; api.sprintf = sprintf; api.strcpy = strcpy;
    memset((void*)0x0200, 0x5A, 0x0A00);                    /* $0200-$0BFF */
    memset((void*)0x1000, 0x5A, 0x1000);                    /* $1000-$1FFF */
    memset((void*)0x2000, 0xEE, 0x2000);
    memset((void*)0xC000, 0xFF, 0x100);
    *(unsigned char*)0xC000 = 0;                             /* no key */
    sp0 = getsp();
    plugin_entry(&api);
    sp1 = getsp();
    o8('E');
    o8(sp0 == sp1);
    out(note, 80);
    out((void*)0xC000, 0x100);
    for (i = 0x0200; i < 0x0C00; ++i) if (*(unsigned char*)i != 0x5A) break;
    o16(i);
    for (i = 0x1000; i < 0x2000; ++i) if (*(unsigned char*)i != 0x5A) break;
    o16(i);
    out((void*)0x2000, 0x2000);
    return 0;
}
'''

GETSP = '''
        .export _getsp
        .importzp sp
_getsp: lda sp
        ldx sp+1
        rts
'''


def prodos_name(page):
    """The name the core gives a DOS 3.3 file, applied to a page name."""
    n = len(page)
    while n > 1 and page[n - 1] == ' ':
        n -= 1
    out = ''
    for c in page[:min(n, 15)]:
        if 'a' <= c <= 'z':
            c = c.upper()
        out += c if ('A' <= c <= 'Z' or '0' <= c <= '9') else '.'
    if not out or not 'A' <= out[0] <= 'Z':
        out = 'X' + out[1:]
    return out


def dos_to_po(disk):
    """The ProDOS blocks a real drive returns for a DOS-order disk."""
    po = bytearray()
    for block in range(280):
        for x in (block % 8 * 2, block % 8 * 2 + 1):
            s = x if x in (0, 15) else 15 - x
            at = (block // 8) * 4096 + s * 256
            po += disk[at:at + 256]
    return bytes(po)


def wrap_2mg(disk, fmt=0, length=143360, offset=64):
    h = bytearray(64)
    h[0:4] = b'2IMG'
    h[4:8] = b'A2FC'
    h[8:10] = (64).to_bytes(2, 'little')
    h[10:12] = (1).to_bytes(2, 'little')
    h[12:16] = fmt.to_bytes(4, 'little')
    h[20:24] = (280).to_bytes(4, 'little')
    h[24:28] = offset.to_bytes(4, 'little')
    h[28:32] = length.to_bytes(4, 'little')
    return bytes(h) + bytes(offset - 64) + disk


def set_names(disk, names):
    """The same disk, its index naming the pages `names`."""
    d = bytearray(disk)
    idx = bytearray(d[34 * 4096:34 * 4096 + 512])
    p = 0x1C
    for nm in names:
        raw = bytes((ord(c) | 0x80) for c in nm) + b'\0'
        idx[p:p + len(raw)] = raw
        p += len(raw)
    assert p <= 512
    idx[0x1B] = len(names)
    d[34 * 4096:34 * 4096 + 512] = idx
    return bytes(d)


def expected(disk, existing=()):
    """(saved {name: page}, there, damaged) of a whole run, by the reference."""
    _, _, names = ref.clip_index(disk)
    saved, there, damaged = {}, 0, 0
    taken = set(existing)
    for nm, locs in zip(names, ref.clip_table(disk, len(names))):
        try:
            page = ref.clip_page(disk, locs)
        except ValueError:
            damaged += 1
            continue
        fn = prodos_name(nm)
        if fn in taken:
            there += 1
            continue
        taken.add(fn)
        saved[fn] = page
    return saved, there, damaged


def note_of(prefix, saved, there, damaged, name=''):
    return '%s%s %d saved, %d already there, %d damaged.' % (name, prefix, saved, there, damaged)


class Run:
    """One run of the overlay, the disk and the directory served from here.

    kind: 'dsk' (a DOS-order file image), '2mg', or 'unit' (a real drive).
    faults: {op: (nth, how)}, op one of O (image open), S, R, B, C, W, K
    (image close), Q (output close), X, P (output open); how a code, or
    'short'/'flag'/'fullflag' for R, 'short'/'flag' for W."""

    def __init__(self, exe, disk, kind='dsk', existing=None, faults=None, esc_after=0,
                 active=0, act_fs=2, oth_fs=0, dest=DEST, image_path=None, img_len=None):
        self.disk = disk
        self.kind = kind
        self.files = dict(existing or {})
        self.existing = dict(self.files)
        self.faults = dict(faults or {})
        self.counts = {}
        self.events = []
        self.created = set()
        self.img_open = False
        self.out_open = None
        self.pos = 0
        self.dest = dest
        self.max_open = 0
        if kind == 'unit':
            self.image = None
            self.po = dos_to_po(disk)
            path, ilen, key = '-', 0, UNIT
        else:
            self.image = wrap_2mg(disk) if kind == '2mg' and isinstance(disk, bytes) and len(disk) == 143360 else disk
            path = image_path or ('/IMG/CLIP.2MG' if kind == '2mg' else '/IMG/CLIP.DSK')
            ilen = len(path) if img_len is None else img_len
            key = 0
        self.image_path = path[:ilen] if kind != 'unit' else None
        argv = ['sim65', str(exe), str(active), str(act_fs), str(ilen), str(key), path,
                str(oth_fs), dest or '-', str(esc_after)]
        self.proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        timer = threading.Timer(600, self.proc.kill)
        timer.start()
        try:
            self.serve()
        finally:
            timer.cancel()
            if self.proc.poll() is None:
                self.proc.kill()
            self.proc.wait()
            self.proc.stdin.close()
            self.proc.stdout.close()

    # -- the pipe
    def rd(self, n):
        b = self.proc.stdout.read(n)
        if len(b) != n:
            raise AssertionError('the simulator stopped (%r)' % self.events[-5:])
        return b

    def u8(self):
        return self.rd(1)[0]

    def u16(self):
        return int.from_bytes(self.rd(2), 'little')

    def text(self):
        return self.rd(self.u8()).decode('latin1')

    def reply(self, data):
        self.proc.stdin.write(bytes(data))
        self.proc.stdin.flush()

    def fault(self, op):
        self.counts[op] = self.counts.get(op, 0) + 1
        f = self.faults.get(op)
        return f[1] if f and f[0] == self.counts[op] else None

    def opened(self):
        self.max_open = max(self.max_open, int(self.img_open) + int(self.out_open is not None))

    def name_of(self, path):
        assert path.startswith(self.dest + '/'), path
        return path[len(self.dest) + 1:]

    def serve(self):
        while True:
            op = chr(self.u8())
            if op == 'Z':
                raise AssertionError('service contract broken: ' + self.text())
            if op == 'E':
                self.sp_ok = self.u8()
                self.note = self.rd(80).split(b'\0')[0].decode('latin1')
                self.io = self.rd(256)
                self.low_untouched = self.u16() == 0x0C00
                self.mid_untouched = self.u16() == 0x2000
                self.hgr = self.rd(0x2000)
                return
            self.events.append(op)
            if op == 'O':
                mode, path = chr(self.u8()), self.text()
                self.events[-1] = 'O' + mode
                if mode == 'r':
                    assert path == self.image_path, path
                    assert not self.img_open and self.out_open is None, 'two files open'
                    if self.fault('O') is not None:
                        self.reply([0])
                        continue
                    self.img_open = True
                else:
                    name = self.name_of(path)
                    assert name in self.created and name in self.files, 'fopen wb of %s' % name
                    assert not self.img_open and self.out_open is None, 'two files open'
                    if self.fault('P') is not None:
                        self.reply([0])
                        continue
                    self.out_open = name
                    self.files[name] = b''
                self.opened()
                self.reply([1])
            elif op == 'S':
                off = self.u16() | self.u16() << 16
                assert self.img_open
                if self.fault('S') is not None:
                    self.reply([1])
                    continue
                self.pos = off
                self.reply([0])
            elif op == 'R':
                n = self.u16()
                assert self.img_open
                data = self.image[self.pos:self.pos + n]
                err = 0
                how = self.fault('R')
                if how == 'short':
                    data = data[:max(0, len(data) - 1)]
                elif how == 'flag':
                    data, err = b'', 1
                elif how == 'fullflag':
                    err = 1                     # all the bytes, and the error flag
                self.pos += len(data)
                self.reply(len(data).to_bytes(2, 'little') + bytes([err]) + data)
            elif op == 'B':
                unit, block = self.u8(), self.u16()
                assert self.kind == 'unit' and unit == UNIT and block < 280, (unit, block)
                code = self.fault('B')
                if code is not None:
                    self.reply([code])
                    continue
                self.reply(b'\0' + self.po[block * 512:block * 512 + 512])
            elif op == 'C':
                n, access, typ, aux, storage, date, time = (self.u8(), self.u8(), self.u8(),
                                                            self.u16(), self.u8(), self.u16(), self.u16())
                path = self.rd(self.u8()).decode('latin1')
                assert (n, access, typ, aux, storage, date, time) == (7, 0xC3, 0x06, 0x2000, 1, 0, 0)
                name = self.name_of(path)
                assert 1 <= len(name) <= 15 and name[0].isalpha() and \
                    all(c.isupper() or c.isdigit() or c == '.' for c in name), name
                if name in self.files:
                    self.reply([0x47])
                    continue
                code = self.fault('C')
                if code is not None:
                    self.reply([code])
                    continue
                self.files[name] = b''
                self.created.add(name)
                self.reply([0])
            elif op == 'W':
                n = self.u16()
                data = self.rd(n)
                assert self.out_open
                how = self.fault('W')
                done, err = n, 0
                if how == 'short':
                    done = n - 512              # the disk filled up
                elif how == 'flag':
                    err = 1                     # all taken, the stream says otherwise
                self.files[self.out_open] += data[:done]
                self.reply(done.to_bytes(2, 'little') + bytes([err]))
            elif op == 'K':
                which = chr(self.u8())
                if which == 'I':
                    assert self.img_open
                    self.img_open = False
                    self.reply([1 if self.fault('K') is not None else 0])
                else:
                    assert self.out_open
                    self.out_open = None
                    self.reply([1 if self.fault('Q') is not None else 0])
            elif op == 'X':
                name = self.name_of(self.text())
                assert name in self.created, 'removed %s, which this run did not create' % name
                assert self.out_open != name
                if self.fault('X') is not None:
                    self.reply([1])
                    continue
                del self.files[name]
                self.created.discard(name)
                self.reply([0])
            elif op == 'M':
                raise AssertionError('unexpected MLI call $%02X' % self.u8())
            else:
                raise AssertionError('unknown request %r' % op)


class Nrclip(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='a2fc-nrclip-')
        d = Path(cls.tmp.name)
        target = Path(subprocess.check_output([shutil.which('cl65'), '--print-target-path'],
                                              text=True).strip())
        (d / 'harness.c').write_text(HARNESS)
        (d / 'getsp.s').write_text(GETSP)
        # Copies, under other names: cl65 turns a .c into a .s beside it,
        # and would overwrite nrclip.s in the source tree.
        shutil.copyfile(ROOT / 'src/plugins/nrclip.c', d / 'nr_ofs.c')
        shutil.copyfile(ROOT / 'src/plugins/nrclip.s', d / 'nrclip.s')
        cls.programs = {}
        for cpu in ('6502', '65c02'):
            base = 'sim65c02' if cpu == '65c02' else 'sim6502'
            cfg = (target.parent / f'cfg/{base}.cfg').read_text()
            # The harness above $4000, as the program is; the overlay's
            # $0C00 part where it runs, its COLD part anywhere.
            cfg = cfg.replace('start = $0200, size = $FDF0 - __STACKSIZE__',
                              'start = $4000, size = $BF00 - $4000 - __STACKSIZE__')
            cfg = cfg.replace('MEMORY {', 'MEMORY {\n    LOW: file = "", define = yes, start = $0C00, size = $0400;')
            cfg = cfg.replace('SEGMENTS {', 'SEGMENTS {\n    COLD: load = MAIN, type = ro;\n'
                              '    NRLOW: load = MAIN, run = LOW, type = ro, define = yes;')
            (d / f'{cpu}.cfg').write_text(cfg)
            exe = d / f'harness-{cpu}'
            subprocess.run(['cl65', '-t', base, '-I', str(ROOT), '-I', str(ROOT / 'src/plugins'), '-DNR_TEST', '-C', str(d / f'{cpu}.cfg'),
                            '-O', '-o', str(exe), str(d / 'harness.c'), str(d / 'nr_ofs.c'),
                            str(d / 'nrclip.s'), str(d / 'getsp.s')],
                           check=True, cwd=d)
            cls.programs[cpu] = exe

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    # -- common checks
    def common(self, r):
        self.assertEqual(r.sp_ok, 1, 'the C stack is balanced')
        self.assertTrue(r.low_untouched and r.mid_untouched, 'memory outside the overlay left alone')
        for sw in (0xC001, 0xC003, 0xC005, 0xC009, 0xC00D, 0xC055):    # 80STORE, AUX, ALTZP, 80COL, PAGE2
            self.assertEqual(r.io[sw - 0xC000], 0xFF, 'soft switch $%04X untouched' % sw)
        self.assertFalse(r.img_open or r.out_open, 'every file closed')
        self.assertLessEqual(r.max_open, 1, 'one file open at a time')
        for name in r.existing:
            self.assertEqual(r.files.get(name), r.existing[name], 'an existing file is never touched')

    def whole(self, cpu, disk, kind='dsk', existing=None, **kw):
        r = Run(self.programs[cpu], disk, kind, existing=existing, **kw)
        self.common(r)
        saved, there, damaged = expected(disk, existing or {})
        self.assertEqual(r.note, note_of('Clip art:', len(saved), there, damaged))
        self.assertEqual(set(r.files), set(saved) | set(existing or {}))
        for name, page in saved.items():
            self.assertEqual(len(r.files[name]), 8192)
            self.assertEqual(r.files[name], page, name)
        self.assertEqual(r.io[0x57], 0, 'the pages were shown in hi-res')
        return r

    def refused(self, cpu, disk, note, kind='dsk', **kw):
        r = Run(self.programs[cpu], disk, kind, **kw)
        self.common(r)
        self.assertEqual(r.note, note)
        self.assertEqual(r.files, r.existing, 'nothing written')
        self.assertNotIn('C', r.events)
        self.assertEqual(r.hgr, b'\xee' * 0x2000, 'nothing drawn')
        return r

    # -- synthetic disks
    def test_synthetic_disks_in_every_form(self):
        rng = random.Random(1985)
        for i in range(4):
            disk, names, spec = ref.make_clip_disk(rng, npages=rng.randint(1, 6), pieces=(1, 6))
            for cpu in self.programs:
                for kind in ('dsk', '2mg', 'unit'):
                    with self.subTest(disk=i, cpu=cpu, kind=kind):
                        r = self.whole(cpu, disk, kind)
                        if kind == 'unit':
                            self.assertNotIn('Or', r.events, 'a real drive opens no file to read')

    def test_last_page_stays_on_screen(self):
        rng = random.Random(7)
        disk, names, spec = ref.make_clip_disk(rng, npages=2, pieces=(3, 5))
        r = self.whole('65c02', disk)
        locs = ref.clip_table(disk, 2)[1]
        self.assertEqual(r.hgr, ref.clip_page(disk, locs))

    def test_large_pieces_and_many_pieces(self):
        # More than 16 pieces a page (the table is read 16 entries at a
        # time), full-height pieces, runs across strips and sectors.
        rng = random.Random(11)
        disk, names, spec = ref.make_clip_disk(rng, npages=3, pieces=(17, 40))
        for cpu in self.programs:
            with self.subTest(cpu=cpu):
                self.whole(cpu, disk)

    def test_names_reduced_as_the_core_does(self):
        rng = random.Random(12)
        disk, names, spec = ref.make_clip_disk(rng, npages=8, pieces=(1, 2))
        pages = ['men 1', '1ST PAGE', 'A-B/C*D', 'WAY TOO LONG A PAGE NAME', '   ',
                 'TRAIL   ', 'AB' + ' ' * 20 + 'C', '']
        disk = set_names(disk, pages)
        self.assertEqual([prodos_name(p) for p in pages],
                         ['MEN.1', 'XST.PAGE', 'A.B.C.D', 'WAY.TOO.LONG.A.', 'X', 'TRAIL',
                          'AB.............', 'X'])
        for cpu in self.programs:
            with self.subTest(cpu=cpu):
                # 'X' twice: the second is already there.
                self.whole(cpu, disk)

    def test_existing_names_are_skipped_never_opened(self):
        rng = random.Random(13)
        disk, names, spec = ref.make_clip_disk(rng, npages=4)
        existing = {'PAGE.2': b'mine', 'PAGE.4': b''}
        for cpu in self.programs:
            with self.subTest(cpu=cpu):
                r = self.whole(cpu, disk, existing=existing)
                self.assertEqual(r.files['PAGE.2'], b'mine')

    def damaged_disk(self):
        """Six pages, pages 2-6 damaged in each way clip_piece refuses."""
        rng = random.Random(14)
        disk, names, spec = ref.make_clip_disk(rng, npages=6, pieces=(2, 3))
        d = bytearray(disk)
        table = ref.clip_table(disk, 6)

        def at(loc, k=0):                   # the k-th byte of a piece
            r = ref._Clip(disk, *loc)
            for _ in range(k):
                r.byte()
            return (r.t * 16 + r.s) * 256 + r.o
        loc = table[1][1]
        d[at(loc, 0)], d[at(loc, 1)] = 100, 50                  # y1 > y2
        loc = table[2][0]
        d[at(loc, 3)] = 252                                     # x2 past the page
        loc = table[3][1]
        d[at(loc, 4)], d[at(loc, 5)] = 0, 0                     # a run of 0 copies
        loc = table[4][0]
        d[at(loc, 0)], d[at(loc, 1)], d[at(loc, 2)], d[at(loc, 3)] = 5, 5, 3, 3
        d[at(loc, 4)], d[at(loc, 5)], d[at(loc, 6)] = 0, 9, 0x7F   # 9 copies for 1 byte
        # page 6: its first piece moved to the end of track 33, where it
        # runs past the data tracks.
        tail = 33 * 4096 + 15 * 256 + 250
        d[tail:tail + 6] = bytes([0, 191, 0, 251, 0x7F, 0x7F])
        tpos = 34 * 4096 + 6 * 256
        k = sum(3 * len(p) + 1 for p in table[:5])
        d[tpos + k:tpos + k + 3] = bytes([33, 15, 250])
        disk = bytes(d)
        _, _, nm = ref.clip_index(disk)
        tab = ref.clip_table(disk, 6)
        for p in range(1, 6):
            with self.assertRaises(ValueError):
                ref.clip_page(disk, tab[p])
        ref.clip_page(disk, tab[0])
        return disk

    def test_damaged_pages_are_counted_and_never_created(self):
        disk = self.damaged_disk()
        for cpu in self.programs:
            for kind in ('dsk', 'unit'):
                with self.subTest(cpu=cpu, kind=kind):
                    r = self.whole(cpu, disk, kind)
                    self.assertEqual(r.note, note_of('Clip art:', 1, 0, 5))
                    self.assertEqual(r.events.count('C'), 1, 'no CREATE for a damaged page')

    # -- refusals before anything is written
    def test_preconditions(self):
        rng = random.Random(15)
        disk, names, spec = ref.make_clip_disk(rng, npages=2)
        noidx = bytearray(disk)
        noidx[34 * 4096] = 0xC1
        runaway = bytearray(disk)                 # names that never end
        runaway[34 * 4096 + 0x1B] = 3
        runaway[34 * 4096 + 0x1C:34 * 4096 + 512] = b'\xc1' * (512 - 0x1C)
        nopages = bytearray(disk)
        nopages[34 * 4096 + 0x1B] = 0
        badtable = bytearray(disk)
        badtable[34 * 4096 + 6 * 256] = 40        # a piece on track 40
        vtoc = bytearray(disk)
        t = ref.clip_table(disk, 2)
        vtoc[34 * 4096 + 6 * 256:34 * 4096 + 6 * 256 + 3] = bytes([17, 1, 0])   # the notice
        notable = bytearray(disk)                 # no $FF before track 35
        notable[34 * 4096 + 6 * 256:] = bytes([1, 1, 0]) * (2560 // 3) + bytes(2560 % 3)
        dos = 'Active panel: not a 140K DOS 3.3 disk.'
        cases = [
            ('no index', bytes(noidx), {}, 'No SSI CLIP index: not a Newsroom clip-art disk.'),
            ('names run past', bytes(runaway), {}, note_of('Clip-art index damaged:', 0, 0, 0)),
            ('no pages', bytes(nopages), {}, note_of('Clip-art index damaged:', 0, 0, 0)),
            ('table off the disk', bytes(badtable), {}, note_of('Clip-art index damaged:', 0, 0, 0)),
            ('table on the VTOC', bytes(vtoc), {}, note_of('Clip-art index damaged:', 0, 0, 0)),
            ('table never ends', bytes(notable), {}, note_of('Clip-art index damaged:', 0, 0, 0)),
            ('other panel an image', disk, {'oth_fs': 1}, 'Other panel: not a ProDOS directory.'),
            ('other panel the volume list', disk, {'dest': ''}, 'Other panel: not a ProDOS directory.'),
            ('active panel ProDOS', disk, {'act_fs': 0}, dos),
            ('active panel a ProDOS image', disk, {'act_fs': 1}, dos),
            ('ProDOS-order .2MG', wrap_2mg(disk, fmt=1), {}, dos),
            ('800K .2MG', wrap_2mg(disk, length=819200), {}, dos),
        ]
        for cpu in self.programs:
            for what, d, kw, note in cases:
                with self.subTest(cpu=cpu, case=what):
                    self.refused(cpu, d, note, kind='2mg' if 'MG' in what else 'dsk', **kw)
            with self.subTest(cpu=cpu, case='second panel active'):
                self.whole(cpu, disk, active=1)
            with self.subTest(cpu=cpu, case='a 2IMG data offset past the header'):
                r = Run(self.programs[cpu], wrap_2mg(disk, offset=128), '2mg')
                self.common(r)
                self.assertEqual(r.note, note_of('Clip art:', 2, 0, 0))
            with self.subTest(cpu=cpu, case='image path cut by img_len'):
                self.whole(cpu, disk, image_path='/IMG/CLIP.DSK/INSIDE', img_len=13)

    # -- failures
    def test_read_failures_stop_with_nothing_half_done(self):
        rng = random.Random(16)
        disk, names, spec = ref.make_clip_disk(rng, npages=4, pieces=(2, 4))
        saved, _, _ = expected(disk)
        for cpu in self.programs:
            cases = []
            for kind in ('dsk', '2mg', 'unit'):
                clean = Run(self.programs[cpu], disk, kind)
                self.assertEqual(clean.note, note_of('Clip art:', 4, 0, 0))
                for op, how in (('O', 0), ('S', 0), ('R', 'short'), ('R', 'flag'), ('R', 'fullflag'),
                                ('B', 0x27), ('K', 0)):
                    n = clean.counts.get(op, 0)
                    for nth in sorted({1, 2, (n + 1) // 2, n} - {0}):
                        if nth <= n:
                            cases.append((kind, {op: (nth, how)}))
            for kind, faults in cases:
                with self.subTest(cpu=cpu, kind=kind, faults=faults):
                    r = Run(self.programs[cpu], disk, kind, faults=faults)
                    self.common(r)
                    n = len(r.files)
                    self.assertEqual(r.note, note_of('Read error:', n, 0, 0))
                    for name, data in r.files.items():
                        self.assertEqual(data, saved[name], 'only whole pages saved')
                    self.assertLess(n, 4)

    def test_image_close_failures_are_read_errors(self):
        rng = random.Random(17)
        disk, names, spec = ref.make_clip_disk(rng, npages=2)
        saved, _, _ = expected(disk)
        for cpu in self.programs:
            with self.subTest(cpu=cpu, close='before the first save'):
                r = Run(self.programs[cpu], disk, faults={'K': (1, 0)})
                self.common(r)
                self.assertEqual((r.note, r.files), (note_of('Read error:', 0, 0, 0), {}))
            with self.subTest(cpu=cpu, close='at the end'):
                # The last page is damaged: the image is still open when
                # the run ends, and that last close fails.
                d = bytearray(disk)
                t, sec, o = ref.clip_table(disk, 2)[1][0]
                d[(t * 16 + sec) * 256 + o] = 200               # y1 past y2
                r = Run(self.programs[cpu], bytes(d), faults={'K': (2, 0)})
                self.common(r)
                self.assertEqual(r.note, note_of('Read error:', 1, 0, 1))
                self.assertEqual(r.files, {'PAGE.1': saved['PAGE.1']})
                r = Run(self.programs[cpu], bytes(d))
                self.assertEqual(r.note, note_of('Clip art:', 1, 0, 1))

    def test_create_failures_stop_before_any_file(self):
        rng = random.Random(18)
        disk, names, spec = ref.make_clip_disk(rng, npages=3)
        saved, _, _ = expected(disk)
        for cpu in self.programs:
            for code in (0x48, 0x49, 0x2B, 0x27):          # disk full, directory full, protected, I/O
                with self.subTest(cpu=cpu, code=code):
                    r = Run(self.programs[cpu], disk, faults={'C': (2, code)})
                    self.common(r)
                    self.assertEqual(r.note, note_of('Create failed:', 1, 0, 0))
                    self.assertEqual(r.files, {'PAGE.1': saved['PAGE.1']})

    def test_write_and_close_failures_remove_the_new_file(self):
        rng = random.Random(19)
        disk, names, spec = ref.make_clip_disk(rng, npages=3)
        saved, _, _ = expected(disk)
        for cpu in self.programs:
            for faults in ({'W': (2, 'short')}, {'W': (2, 'flag')}, {'Q': (2, 0)}, {'P': (2, 0)}):
                with self.subTest(cpu=cpu, faults=faults):
                    r = Run(self.programs[cpu], disk, faults=faults)
                    self.common(r)
                    self.assertEqual(r.note, note_of('Write failed, file removed:', 1, 0, 0))
                    self.assertEqual(r.files, {'PAGE.1': saved['PAGE.1']}, 'no partial file')
                    self.assertEqual(r.events.count('X'), 1)
            for faults in ({'W': (2, 'short'), 'X': (1, 0)}, {'Q': (2, 0), 'X': (1, 0)}):
                with self.subTest(cpu=cpu, faults=faults, removal='fails'):
                    r = Run(self.programs[cpu], disk, faults=faults)
                    self.common(r)
                    self.assertEqual(r.note, note_of(' left incomplete!', 1, 0, 0, name='PAGE.2'))
                    self.assertEqual(set(r.files), {'PAGE.1', 'PAGE.2'})
                    self.assertEqual(r.files['PAGE.1'], saved['PAGE.1'])
                    if 'W' in faults:
                        self.assertEqual(len(r.files['PAGE.2']), 8192 - 512, 'the partial file stays')

    def test_escape_stops_between_pages(self):
        rng = random.Random(20)
        disk, names, spec = ref.make_clip_disk(rng, npages=5)
        saved, _, _ = expected(disk)
        for cpu in self.programs:
            with self.subTest(cpu=cpu):
                r = Run(self.programs[cpu], disk, 'unit', esc_after=2)
                self.common(r)
                self.assertEqual(r.note, note_of('Stopped:', 2, 0, 0))
                self.assertEqual(r.files, {k: saved[k] for k in ('PAGE.1', 'PAGE.2')})
                self.assertNotEqual(r.io[0x10], 0xFF, 'the key was taken')

    # -- the real disks
    def test_real_clip_art_disks(self):
        disks = sorted(glob.glob(str(CORPUS / '*.dsk')) +
                       glob.glob(str(CORPUS / 'clipart_zip/Newsroom Clipart/CLP.ART*.DSK')))
        disks = [p for p in disks if self.is_clip(p)]
        if not disks:
            self.skipTest('no clip-art disks in %s' % CORPUS)
        pages = bad = 0
        sides = {}
        for path in disks:
            disk = Path(path).read_bytes()
            name, side, names = ref.clip_index(disk)
            for cpu in ('6502', '65c02'):
                kind = 'dsk' if cpu == '6502' else 'unit'
                with self.subTest(disk=Path(path).name, cpu=cpu):
                    self.whole(cpu, disk, kind)
            saved, there, damaged = expected(disk)
            if (name, side) not in sides or damaged < sides[(name, side)][1]:
                sides[(name, side)] = (len(names), damaged)
        pages = sum(n for n, _ in sides.values())
        bad = sum(d for _, d in sides.values())
        if len(sides) == 8:
            self.assertEqual((pages, bad), (393, 2), 'the best copy of each side')

    @staticmethod
    def is_clip(path):
        data = Path(path).read_bytes()
        try:
            ref.clip_index(data)
        except ValueError:
            return False
        return True


if __name__ == '__main__':
    unittest.main()
