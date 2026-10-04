#!/usr/bin/env python3
"""Tests of TAKE1.SYSTEM, the Take 1 player (src/take1/), under sim65.

  Take1    the engine (engine.s) linked with a small C program: its hooks
           write out each page shown, each frame wait, each $FC element, the
           shown page at every delay of a fade (and at every tick of fade
           14) and each file read (t1_load / t1_mload read host files);
           tools/take1_ref.py plays the same movie and the two streams must
           be equal, byte for byte. Memory below the pages must be untouched
           and the scene buffer must hold exactly what was read. Refusals:
           the same code and file name as the reference.
  Loader   the command and the files (dos.s) with a fake MLI: images (.DSK,
           .2MG), a real disk (READ_BLOCK), extracted files; only OPEN,
           SET_MARK, READ, CLOSE and READ_BLOCK, READs only into the block
           buffer of the page not shown; injected errors and damaged disks
           are refused, never taken for data; the reference's loaders agree.
  System   the built TAKE1.SYSTEM.SYS at $2000 with a fake MLI, from its start
           to its QUIT: it plays, Escape gives the ProDOS bitmap back and
           loads A2FILE.SYSTEM; a refused movie is named on the text screen.
  Timing   the original speed's frame wait, D(a) and sound steps, counted.

Both processors (6502 and 65C02) for the engine and the loader. cc65 master
(CC65_HEAD, default ~/opt/cc65-head) is needed; without it the tests skip.

    test_take1.py              the tests
    test_take1.py --measure    the original speed: the player's frame time (the
                               engine's own, plus the hold it computes) against
                               the spec's model of the original's
                               (take1_ref.realistic); the engine alone too
    test_take1.py --micro      cycles a row of short codes (line art) and a
                               snapshot's, against the spec's model
    test_take1.py --calibrate [--write]
                               fits OWN_BASE and OWN_* (engine.s) on the
                               engine's own time per frame
"""
import os
import random
import re
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import take1_ref as ref  # noqa: E402

HEAD = Path(os.environ.get('CC65_HEAD', str(Path.home() / 'opt/cc65-head')))
SCENE_AT = 0x8000
FILL_LOW, FILL_PAGES, FILL_SCENE = 0x5A, 0xEE, 0xA5

GLUE = r'''
        .import t1_play, t1_name, t1_err, t1_front
        .import t1_dest, t1_max, t1_len, t1_hold
        .export _t1_hold := t1_hold
        .export _t1_name := t1_name
        .export _t1_err := t1_err, _t1_front := t1_front, _t1_dest := t1_dest
        .export _t1_max := t1_max, _t1_len := t1_len
        .export t1_load, t1_mload, t1_show, t1_wait, t1_fc, t1_delay, t1_tick
        .export _run_play, _ha, _hx
        .import _h_load, _h_mload, _h_show, _h_wait, _h_fc, _h_delay, _h_tick
        .bss
_ha:    .res 1
_hx:    .res 1
        .code
_run_play:
        jsr     t1_play
        bcs     :+
        lda     #0
:       ldx     #0
        rts
t1_load:
        jsr     _h_load
        cmp     #1                      ; C = 1: an error, A its code
        rts
t1_mload:
        jsr     _h_mload
        cmp     #1
        rts
t1_show:
        sta     _ha
        jmp     _h_show
t1_wait:
        sta     _ha
        stx     _hx
        jmp     _h_wait
t1_fc:  sta     _ha
        stx     _hx
        jmp     _h_fc
t1_delay:
        sta     _ha
        jmp     _h_delay
t1_tick:
        jmp     _h_tick
'''

HARNESS = r'''
#include <fcntl.h>
#include <unistd.h>
#include <string.h>
#include <stdlib.h>
extern unsigned char t1_name[24];
extern unsigned char t1_err, t1_front, t1_hold[4];
extern unsigned char* t1_dest;
extern unsigned int t1_max, t1_len;
extern unsigned char ha, hx;
unsigned char run_play(void);
static unsigned char scratch[256];
static char host[64];
static unsigned char rec[4];
static void out(const void* p, unsigned n)
{
    if (write(1, p, n) != (int)n) exit(20);
}
#ifdef MEASURE
#include <sim65.h>
static unsigned long e, x;                      /* cycle stamps, not pages */
#define ENTER() (peripherals.counter.latch = 0, e = peripherals.counter.value32[0])
#define LEAVE() do { out(&e, 4); peripherals.counter.latch = 0; \
                     x = peripherals.counter.value32[0]; out(&x, 4); } while (0)
#define page(hi)
#else
#define ENTER()
#define LEAVE()
static void page(unsigned char hi)
{
    out((void*)(hi << 8), 0x2000);
}
#endif
static const char hexd[] = "0123456789ABCDEF";
static unsigned char rd(char kind)
{
    int fd, n;
    unsigned int size = 0;
    rec[0] = kind;
    out(rec, 1);
    out(t1_name, 24);
    out(&t1_dest, 2);
    out(&t1_max, 2);
    fd = open(host, O_RDONLY);
    if (fd < 0) { rec[0] = 1; out(rec, 3); return 1; }
    while ((n = read(fd, scratch, sizeof scratch)) > 0) size += n;
    close(fd);
    if (size > t1_max) { rec[0] = 3; out(rec, 3); return 3; }
    fd = open(host, O_RDONLY);
    if (fd < 0) return 2;
    if (size && read(fd, t1_dest, size) != (int)size) { close(fd); return 2; }
    close(fd);
    t1_len = size;
    rec[0] = 0;
    out(rec, 1);
    out(&t1_len, 2);
    return 0;
}
unsigned char h_load(void)
{
    unsigned char i, k = t1_name[0];
    host[0] = 'f';
    for (i = 0; i < k; ++i) {
        host[1 + 2 * i] = hexd[t1_name[1 + i] >> 4];
        host[2 + 2 * i] = hexd[t1_name[1 + i] & 15];
    }
    host[1 + 2 * k] = 0;
    return rd('L');
}
unsigned char h_mload(void)
{
    memcpy(t1_name, "\x08MV.MOVIE", 9);
    strcpy(host, "movie.bin");
    return rd('M');
}
void h_show(void)
{
    ENTER();
    rec[0] = 'S';
    rec[1] = ha;
    out(rec, 2);
    page(ha);
    LEAVE();
}
void h_wait(void)
{
    ENTER();
    rec[0] = 'W';
    rec[1] = ha;
    rec[2] = hx;
    out(rec, 3);
    out(t1_hold, 4);
    LEAVE();
}
void h_fc(void)
{
    ENTER();
    rec[0] = 'F';
    rec[1] = ha;
    rec[2] = hx;
    out(rec, 3);
    LEAVE();
}
void h_delay(void)
{
    ENTER();
    rec[0] = 'D';
    rec[1] = ha;
    out(rec, 2);
    page(t1_front);
    LEAVE();
}
void h_tick(void)
{
    ENTER();
    rec[0] = 'K';
    out(rec, 1);
    page(t1_front);
    LEAVE();
}
int main(void)
{
    unsigned char r;
    memset((void*)0x0200, 0x5A, 0x1E00);
    memset((void*)0x2000, 0xEE, 0x6000);
    memset((void*)0x8000, 0xA5, 0x3000);
    r = run_play();
    rec[0] = 'E';
    rec[1] = r;
    out(rec, 2);
    out(t1_name, 24);
    out((void*)0x0200, 0xAE00);
    return 0;
}
'''


def host_name(dosname):
    return 'f' + dosname.hex().upper()


class Sim:
    """The engine harness built for one processor."""

    def __init__(self, cpu, workdir, measure=False):
        self.dir = workdir
        self.measure = measure
        self.psize = 8 if measure else 0x2000           # (measure: 2 cycle stamps)
        env = dict(os.environ, CC65_HOME=str(HEAD / 'share/cc65'))
        target = 'sim65c02' if cpu == '65c02' else 'sim6502'
        cfg = (HEAD / f'share/cc65/cfg/{target}.cfg').read_text()
        cfg, k = re.subn(r'start = \$0200, size = \$FFC0 - \$0200 - __STACKSIZE__',
                         'start = $B000, size = $FFC0 - $B000 - __STACKSIZE__', cfg)
        assert k == 1, 'sim65 config changed'
        cfg, k = re.subn(r'(\n\s*RODATA:[^\n]*\n)', r'\1    HICODE:   load = MAIN,   type = ro;\n'
                         r'    LOWC:     load = MAIN,   type = ro;\n'
                         r'    TXC3:     load = MAIN,   type = ro,  define = yes;\n'
                         r'    TXC5:     load = MAIN,   type = ro;\n    TXC6:     load = MAIN,   type = ro;\n'
                         r'    TXC7:     load = MAIN,   type = ro;\n'
                         r'    TXT0:     load = MAIN,   type = bss;\n    TXT1:     load = MAIN,   type = bss;\n'
                         r'    TXT2:     load = MAIN,   type = bss;\n    TXT3:     load = MAIN,   type = bss;\n', cfg)
        assert k == 1, 'sim65 config: no RODATA line'
        (workdir / f'{cpu}.cfg').write_text(cfg)
        (workdir / 'harness.c').write_text(HARNESS)
        (workdir / 'glue.s').write_text(GLUE)
        self.exe = workdir / f'harness-{cpu}'
        subprocess.run([str(HEAD / 'bin/cl65'), '-t', target, '-C', str(workdir / f'{cpu}.cfg'),
                        '-O', '-Wl', '-D,__STACKSIZE__=0x0400', '-Ln', str(workdir / 'labels.lbl'),
                        '-o', str(self.exe)] + (['-DMEASURE'] if measure else []) + [
                        str(workdir / 'harness.c'), str(workdir / 'glue.s'),
                        str(ROOT / 'src/take1/engine.s')],
                       check=True, cwd=workdir, env=env)
        self.sim = str(HEAD / 'bin/sim65')

    def run(self, movie, files):
        for old in self.dir.glob('f*'):
            if old.name.startswith('f') and old.suffix == '':
                old.unlink()
        (self.dir / 'movie.bin').write_bytes(movie)
        for name, data in files.items():
            (self.dir / host_name(name)).write_bytes(data)
        p = subprocess.run([self.sim, '-x', '4000000000', str(self.exe)],
                           cwd=self.dir, capture_output=True, timeout=1200)
        if p.returncode != 0:
            raise AssertionError('sim65 exit %d: %s' % (p.returncode, p.stderr[-300:]))
        o = p.stdout
        pos = 0
        events, loads = [], []
        while True:
            k = o[pos]
            if k == ord('S'):
                events.append(('show', 1 if o[pos + 1] == 0x20 else 2, o[pos + 2:pos + 2 + self.psize]))
                pos += 2 + self.psize
            elif k == ord('W'):
                ev = ('wait', o[pos + 1] | o[pos + 2] << 8, struct.unpack_from('<I', o, pos + 3)[0])
                pos += 7
                if self.measure:
                    ev += (o[pos:pos + 8],)
                    pos += 8
                events.append(ev)
            elif k == ord('F'):
                ev = ('fc', o[pos + 1], o[pos + 2])
                pos += 3
                if self.measure:
                    ev += (o[pos:pos + 8],)
                    pos += 8
                events.append(ev)
            elif k == ord('D'):
                events.append(('delay', o[pos + 1], o[pos + 2:pos + 2 + self.psize]))
                pos += 2 + self.psize
            elif k == ord('K'):
                events.append(('tick', o[pos + 1:pos + 1 + self.psize]))
                pos += 1 + self.psize
            elif k in (ord('L'), ord('M')):
                name = o[pos + 2:pos + 2 + o[pos + 1]] if k == ord('L') else None
                dest, mx = struct.unpack_from('<HH', o, pos + 25)
                code = o[pos + 29]
                if code == 0:
                    ln = struct.unpack_from('<H', o, pos + 30)[0]
                    pos += 32
                else:
                    ln = None
                    pos += 32
                loads.append((name, dest, mx, code, ln))
            elif k == ord('E'):
                res = {'code': o[pos + 1], 'name': o[pos + 3:pos + 3 + o[pos + 2]]}
                pos += 2 + 24
                mem = o[pos:pos + 0xAE00]
                res['low'] = mem[:0x1E00]
                res['p1'] = mem[0x1E00:0x3E00]
                res['p2'] = mem[0x3E00:0x5E00]
                res['p3'] = mem[0x5E00:0x7E00]
                res['scene'] = mem[0x7E00:0xAE00]
                break
            else:
                raise AssertionError('harness output at %d: %r' % (pos, o[pos:pos + 8]))
        res['events'], res['loads'] = events, loads
        return res


def ref_run(movie, files):
    """The reference's events (without 'fade' and 'end'), loads, refusal."""
    loads = []
    inner = ref.dict_loader(files)

    def loader(name, room):
        try:
            data = inner(name, room)
        except ref.Refused as r:
            loads.append((name, r.code))
            raise
        loads.append((name, 0))
        return data
    player = ref.Player(movie, loader, movie_name=b'MV.MOVIE')
    events = []
    refused = None
    try:
        for e in player.play():
            if e[0] not in ('fade', 'end'):
                events.append(e)
    except ref.Refused as r:
        refused = r
    return player, events, loads, refused


class Take1(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (HEAD / 'bin/sim65').exists():
            raise unittest.SkipTest('cc65 master (CC65_HEAD) is needed for sim65')
        cls.tmp = tempfile.TemporaryDirectory(prefix='a2fc-take1-')
        cls.sims = {}
        for cpu in ('6502', '65c02'):
            d = Path(cls.tmp.name) / cpu
            d.mkdir()
            cls.sims[cpu] = Sim(cpu, d)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def compare(self, cpu, movie, files, label=''):
        res = self.sims[cpu].run(movie, files)
        player, events, loads, refused = ref_run(movie, files)
        got = res['events']
        n = min(len(got), len(events))
        for i in range(n):
            a, b = got[i], events[i]
            where = '%s event %d (%s)' % (label, i, b[0])
            if a[0] != b[0] or a[:-1] != b[:-1] and a[0] in ('show', 'delay'):
                self.fail('%s: %r, ref %r' % (where, a[:2], b[:2]))
            if a[0] in ('show', 'delay', 'tick'):
                pa, pb = a[-1], b[-1]
                if pa != pb:
                    diff = [k for k in range(0x2000) if pa[k] != pb[k]]
                    self.fail('%s: %d bytes differ, first at $%04X: %02X, ref %02X' %
                              (where, len(diff), diff[0], pa[diff[0]], pb[diff[0]]))
            else:
                self.assertEqual(a, b, where)
        self.assertEqual(len(got), len(events), label + ': event count')
        # loads: the same files in the same order, with the same outcome
        self.assertEqual([(nm, c) for nm, _, _, c, _ in res['loads'] if nm is not None], loads,
                         label + ': loads')
        nscenes = sum(1 for nm, *_ in res['loads'] if nm is not None and nm.startswith(b'SN.'))
        self.assertEqual(sum(1 for nm, *_ in res['loads'] if nm is None),
                         1 if refused and refused.name == b'MV.MOVIE' else max(1, nscenes),
                         label + ': the movie read once a scene')
        if refused is None:
            self.assertEqual(res['code'], 0, label)
            self.assertEqual(res['p1'], bytes(player.pages[1]), label + ' page 1')
            self.assertEqual(res['p2'], bytes(player.pages[2]), label + ' page 2')
            self.assertEqual(res['p3'], bytes(player.pages[3]), label + ' page 3')
        else:
            self.assertEqual((res['code'], res['name']), (refused.code, refused.name), label)
        self.assertEqual(res['low'], bytes([FILL_LOW]) * 0x1E00, label + ': memory below $2000')
        scene = bytearray([FILL_SCENE]) * ref.SCENE_MAX
        for name, dest, mx, code, ln in res['loads']:
            if code == 0:
                self.assertGreaterEqual(dest, SCENE_AT, label)
                self.assertLessEqual(dest - SCENE_AT + ln, ref.SCENE_MAX, label)
                scene[dest - SCENE_AT:dest - SCENE_AT + ln] = movie if name is None else files[name]
        self.assertEqual(res['scene'], bytes(scene), label + ': the scene buffer')
        return res, refused

    def test_synthetic(self):
        shows = 0
        for cpu, seeds in (('6502', range(60)), ('65c02', range(0, 60, 3))):
            for seed in seeds:
                mv, files = ref.synthetic(seed)
                res, _ = self.compare(cpu, mv, files, '%s seed %d' % (cpu, seed))
                shows += sum(1 for e in res['events'] if e[0] == 'show')
        print('PASS take1: synthetic movies match the reference (60 on 6502, 20 on 65C02, %d frames)'
              % shows)

    def test_wide_runs(self):
        for cpu, seeds in (('6502', range(100, 120)), ('65c02', range(100, 106))):
            for seed in seeds:
                mv, files = ref.synthetic(seed, wide=True)
                self.compare(cpu, mv, files, '%s wide seed %d' % (cpu, seed))
        print('PASS take1: long runs and extensions match the reference, both processors')

    def test_short_codes(self):
        """The short-code rows of --micro (the quick fill, skip and literal
        paths, split at every bit phase) at every phase, across both edges,
        with and without wrap, both processors."""
        rows = [r for n, r in micro_rows().items() if n != 'end only']
        snaps = [bytes([12, 250, 0, 0, 0, 0, 0]) + r * 12 for r in rows]
        # x16: every phase on the screen, off the left, against the right
        places = [(280 + k, 160 + 9 * k, False) for k in range(7)]
        places += [(262, 200, False), (520, 210, False), (275, 220, True), (540, 230, True)]
        frames = []
        for i in range(len(snaps)):
            frames.append(b''.join(ref.obj(1 + i, x, y, wrap=w, end=(j == len(places) - 1))
                                   for j, (x, y, w) in enumerate(places)))
        files = {b'AC.U': ref.make_actor(snaps),
                 b'SN.U': ref.make_scene(1, [(len(snaps), 'U')], frames)}
        mv = ref.make_movie([('U', '< BLACK >', 1, 1)])
        for cpu in ('6502', '65c02'):
            res, refused = self.compare(cpu, mv, files, '%s short codes' % cpu)
            self.assertIsNone(refused)
            self.assertEqual(sum(1 for e in res['events'] if e[0] == 'show'), len(frames))
        print('PASS take1: short fills, skips and literals at every bit phase, across both edges, '
              'with and without wrap, match the reference, both processors')

    def test_crafted(self):
        kinds = ('fades', 'seam', 'wide', 'many', 'text', 'plant', 'bit6')
        for cpu in ('6502', '65c02'):
            for kind in kinds:
                for seed in range(3 if cpu == '6502' else 1):
                    mv, files = ref.crafted(kind, seed)
                    res, refused = self.compare(cpu, mv, files, '%s %s %d' % (cpu, kind, seed))
                    self.assertIsNone(refused, (kind, seed))
        print('PASS take1: every fade, wrap seams, skips closing on bit 6, wide snapshots, full lists, '
              'text, plants and BLACK/UNCHANGED match the reference, both processors')

    def refusals(self):
        """(label, movie, files, expected code, expected name)."""
        rng = random.Random(9)
        mv, files = ref.crafted('plant', 0)
        cs = ref.make_cs([bytes([0b00_101_101, 0x3F]), b'\x12'])
        act = files[b'AC.P']
        page = bytearray(rng.randrange(256) for _ in range(ref.PAGE))
        bk = ref.encode_bk(page, rng)
        fr = [ref.obj(1, 300, 200, end=True), ref.obj(1, 290, 250, wrap=True, text=True, end=True)]
        sn = ref.make_scene(30, [(4, 'P')], fr, [b'HI'], 'C')
        base = {b'SN.S': sn, b'AC.P': act, b'CS.C': cs, b'BK.B': bk}
        movie = ref.make_movie([('S', 'B', 1, 1), ('S', '< UNCHANGED >', 3, 2)])
        out = []

        def case(label, m=movie, **changes):
            f = dict(base)
            for k, v in changes.items():
                k = k.replace('_', '.').encode()
                if v is None:
                    f.pop(k, None)
                else:
                    f[k] = v
            out.append((label, m, f))
        # the movie
        case('movie short', movie[:-1])
        case('movie long', movie + b'\x00')
        case('movie n 0', b'\x00' + movie[1:])
        case('movie empty', b'')
        for off, v in ((41, 0), (41, 18), (42, 0), (42, 18), (83, 255)):
            m = bytearray(movie)
            m[off] = v
            case('movie fade %d=%d' % (off, v), bytes(m))
        case('movie of 255 scenes', ref.make_movie([('S', '< UNCHANGED >', 1, 1)] * 255))
        case('movie too big', bytes(ref.MOVIE_MAX + 1))
        # missing files
        for k in ('SN_S', 'AC_P', 'CS_C', 'BK_B'):
            case('missing ' + k, **{k: None})
        # backgrounds
        for cut in (0, 1, 2, 50, len(bk) // 2, len(bk) - 1):
            case('BK cut %d' % cut, BK_B=bk[:cut])
        case('BK no $FF', BK_B=b'\xFE' + bk[1:])
        case('BK junk after', BK_B=bk + b'\x01\x02')
        case('BK too big', BK_B=bk + bytes(8193 - len(bk)))
        case('BK zero count', BK_B=b'\xFF\x00\x00' + bk[1:])
        case('BK overflow', BK_B=b'\xFF\x00\xC1' + bytes(193))
        case('BK pattern overflow', BK_B=b'\xFF\x81' + bytes(1) + b'\x00\xC0' + bytes(192))
        case('BK pattern 0 = 256', BK_B=b'\xFF\x80\x00\x55')
        # scenes
        for cut in (0, 0x102, 0x103, 0x104, len(sn) - 1, len(sn) - 2, len(sn) - 5):
            case('SN cut %d' % cut, SN_S=sn[:cut])
        s2 = bytearray(sn)
        s2[0x18] = 11
        case('SN 11 actors', SN_S=bytes(s2))
        s2 = bytearray(sn)
        s2[0x100], s2[0x101] = (len(sn) - 0x100) & 255, (len(sn) - 0x100) >> 8
        case('SN frames outside', SN_S=bytes(s2))
        s2 = bytearray(sn)
        s2[0x103] = 250
        case('SN string past the end', SN_S=bytes(s2))
        for o, f, label in ((5, 0x80, 'snapshot 5'), (0, 0xC0, 'element 0'), (2, 0xD1, 'string 2'),
                            (1, 0xC1, 'text no wrap'), (1, 0xD0, 'text x 0'), (1, 0xD3, 'text x 768'),
                            (1, 0xDA, 'text x 560')):
            body = ref.obj(o, 0, 200) [:0]
            el = bytes([o, (280 if f & 3 == 1 else 0) & 255 if f != 0xDA else 0x30, f, 200])
            s3 = ref.make_scene(30, [(4, 'P')], [el], [b'HI'], 'C')
            case('SN ' + label, SN_S=s3)
        for yl, f, label in ((192, 0xD1, 'text y 192'), (128, 0xD9, 'text y 384'),
                             (193, 0xD1, 'text y 193'), (127, 0xD9, 'text y 383')):
            s3 = ref.make_scene(30, [(4, 'P')], [bytes([1, 24, f, yl])], [b'HI'], 'C')
            case('SN ' + label, SN_S=s3)
        s3 = ref.make_scene(30, [(4, 'P')], [ref.obj(1, 290, 250, wrap=True, text=True, end=True)], [b'HI'])
        case('SN text without a set', SN_S=s3)
        s3 = ref.make_scene(30, [(4, 'P')], [ref.obj(1, 300, 200, end=True)])[:-1]
        case('SN no end marker', SN_S=s3)
        s3 = ref.make_scene(30, [(4, 'P')], [ref.obj(1, 300, 200)[:3]])[:-1]
        case('SN element past the end', SN_S=s3)
        s3 = ref.make_scene(30, [(4, 'P')], [bytes([0xF3, 0xFD]) + ref.obj(1, 300, 200, end=True)])
        case('SN fillers', SN_S=s3)
        s3 = ref.make_scene(30, [(4, 'P')], [])
        case('SN no frames', SN_S=s3)
        s3 = ref.make_scene(30, [(4, 'P')], [ref.obj(1, 300, 200)])
        case('SN unterminated frame', SN_S=s3)
        s3 = ref.make_scene(30, [(5, 'P')], [ref.obj(5, 300, 200, end=True)])
        case('SN snapshot above the actor', SN_S=s3)
        s3 = ref.make_scene(30, [(5, 'P')], [ref.obj(4, 300, 200, end=True)])
        case('SN count above, unused', SN_S=s3)
        # actors
        for cut in (0, 1, 2, 5, 9, 10, 11, len(act) // 2, len(act) - 2):
            case('AC cut %d' % cut, AC_P=act[:cut])
        a2 = bytearray(act)
        a2[1], a2[2] = 0xFF, 0x7F
        case('AC offset far', AC_P=bytes(a2))
        a2 = bytearray(act)
        a2[1], a2[2] = 0xF0, 0xFF
        case('AC offset wraps', AC_P=bytes(a2))
        hdr = bytes([1, 7, 0, 0, 0, 0, 0])
        long_run = hdr + bytes([(25 << 3) | 7] * 4 + [(12 << 3) | 7, 0x80 | (15 << 3), 0x00])
        case('AC run of 127 groups', AC_P=ref.make_actor([long_run] * 4))
        too_long = hdr + bytes([(25 << 3) | 7] * 4 + [(13 << 3) | 7, 0x80 | (15 << 3), 0x00])
        case('AC run of 128 groups', AC_P=ref.make_actor([too_long] * 4))
        fill_long = hdr + bytes([(25 << 3) | 7] * 4 + [(13 << 3) | 7, (15 << 3), 0x55, 0x00])
        case('AC fill of 128 groups', AC_P=ref.make_actor([fill_long] * 4))
        many_ext = bytes([1, 7, 0, 0, 0, 0, 0]) + bytes([(25 << 3) | 7] * 12) + bytes([0xD7, 0x55, 0x00])
        case('AC extensions dropped', AC_P=ref.make_actor([many_ext] * 4))
        case('AC fewer snapshots', AC_P=ref.make_actor([long_run] * 3))
        # character sets
        case('CS empty', CS_C=b'')
        case('CS no shapes', CS_C=b'\x00\x00')
        for cut in (1, 2, 4, 5, 6, len(cs) - 1):
            case('CS cut %d' % cut, CS_C=cs[:cut])
        # memory
        room = ref.SCENE_MAX - len(sn) - len(cs)
        big = ref.make_actor([long_run] * 4, actions=b'')
        big = ref.make_actor([long_run] * 4, actions=bytes(room - len(big)))
        case('memory: fits exactly', AC_P=big)
        case('memory: one byte over', AC_P=big + b'\x00')
        case('memory: scene too big', SN_S=sn + bytes(ref.SCENE_MAX))
        return out

    def test_refused(self):
        n = 0
        for label, m, f in self.refusals():
            for cpu in ('6502', '65c02'):
                if cpu == '65c02' and n % 3:
                    continue
                self.compare(cpu, m, f, '%s: %s' % (cpu, label))
            n += 1
        print('PASS take1: %d damaged or oversized movies refused as the reference, naming the file,'
              ' memory untouched' % n)


# -- dos.s: the command, the movie and the files, with a fake MLI --------------

DGLUE = r"""
        .import dstart, t1_load, t1_mload, _fake_mli, pusha
        .importzp ptr1
        .export t1_name, t1_dest, t1_max, t1_len, t1_front, path0
        .export _t1_name := t1_name, _t1_dest := t1_dest, _t1_max := t1_max
        .export _t1_len := t1_len, _t1_front := t1_front, _path0 := path0
        .export _run_dstart, _run_load, _run_mload
        .bss
t1_name: .res   24
t1_dest: .res   2
t1_max: .res    2
t1_len: .res    2
t1_front: .res  1
path0:  .res    65
mcmd:   .res    1
mpl:    .res    1
mph:    .res    1
        .code
_run_dstart:
        jsr     dstart
        jmp     ret
_run_load:
        jsr     t1_load
        jmp     ret
_run_mload:
        jsr     t1_mload
ret:    bcs     :+
        lda     #0
:       ldx     #0
        rts
; The MLI, at $BF00: jsr $BF00 / .byte cmd / .word params.
        .segment "MLISTUB"
mli:    pla
        sta     ptr1
        pla
        sta     ptr1+1
        ldy     #1
        lda     (ptr1),y
        sta     mcmd
        iny
        lda     (ptr1),y
        sta     mpl
        iny
        lda     (ptr1),y
        sta     mph
        clc
        lda     ptr1
        adc     #3
        tax
        lda     ptr1+1
        adc     #0
        pha
        txa
        pha
        lda     mcmd
        jsr     pusha
        lda     mpl
        ldx     mph
        jsr     _fake_mli
        cmp     #1                      ; C = an error
        rts
"""

DHARNESS = r"""
#include <stdio.h>
#include <fcntl.h>
#include <unistd.h>
#include <string.h>
#include <stdlib.h>
extern unsigned char path0[65], t1_name[24], t1_front;
extern unsigned char* t1_dest;
extern unsigned int t1_max, t1_len;
unsigned char run_dstart(void), run_load(void), run_mload(void);
extern unsigned char _MLISTUB_LOAD__[], _MLISTUB_SIZE__[];
static char fault = '-', host[80], ohost[80];
static unsigned char fnth, calls[256];
static int fd = -1;
static long fsize;
static unsigned char scratch[256];
static unsigned char log[600];
static unsigned int nlog;
static void out(const void* p, unsigned n)
{
    if (write(1, p, n) != (int)n) exit(20);
}
static void logcall(unsigned char cmd, unsigned int a, unsigned int b)
{
    if (nlog + 5 > sizeof log) return;
    log[nlog] = cmd;
    memcpy(log + nlog + 1, &a, 2);
    memcpy(log + nlog + 3, &b, 2);
    nlog += 5;
}
static unsigned char faulty(unsigned char cmd)
{
    ++calls[cmd];
    return fault == cmd && (fnth == 0 || calls[cmd] == fnth);
}
unsigned char __fastcall__ fake_mli(unsigned char cmd, unsigned char* p)
{
    int n;
    unsigned int req, i;
    unsigned char* buf;
    long mark;
    switch (cmd) {
    case 0xC8:                                  /* OPEN */
        buf = *(unsigned char**)(p + 1);
        logcall(cmd, (unsigned int)buf, *(unsigned int*)(p + 3));
        host[0] = 'f';
        for (i = 0; i < buf[0]; ++i) host[i + 1] = buf[i + 1] == '/' ? '_' : buf[i + 1];
        host[buf[0] + 1] = 0;
        if (faulty('O')) return 0x27;
        if (fd >= 0) return 0x42;               /* one file at a time */
        fd = open(host, O_RDONLY);
        if (fd < 0) return 0x46;
        strcpy(ohost, host);
        fsize = 0;
        while ((n = read(fd, scratch, sizeof scratch)) > 0) fsize += n;
        close(fd);
        fd = open(ohost, O_RDONLY);
        p[5] = 1;
        return 0;
    case 0xCA:                                  /* READ */
        buf = *(unsigned char**)(p + 2);
        req = p[4] | (p[5] << 8);
        logcall(cmd, (unsigned int)buf, req);
        if (fd < 0 || p[1] != 1) return 0x43;
        if (faulty('R')) {                      /* part of it, then an error */
            n = read(fd, buf, req / 2);
            p[6] = n & 255; p[7] = n >> 8;
            return 0x27;
        }
        if (faulty('S')) --req;                 /* a short read, no error */
        n = read(fd, buf, req);
        if (n < 0) return 0x27;
        if (!n && req) return 0x4C;
        p[6] = n & 255; p[7] = n >> 8;
        return 0;
    case 0xCE:                                  /* SET_MARK */
        mark = p[2] | ((long)p[3] << 8) | ((long)p[4] << 16);
        logcall(cmd, (unsigned int)mark, (unsigned int)(mark >> 16));
        if (fd < 0 || p[1] != 1) return 0x43;
        if (faulty('M')) return 0x27;
        if (mark > fsize) return 0x4D;
        close(fd);                              /* (sim65's lseek is not used) */
        fd = open(ohost, O_RDONLY);
        while (mark >= 256) { read(fd, scratch, 256); mark -= 256; }
        if (mark) read(fd, scratch, (unsigned)mark);
        return 0;
        return 0;
    case 0xCC:                                  /* CLOSE */
        logcall(cmd, p[1], 0);
        if (fd >= 0) close(fd);
        fd = -1;
        return faulty('C') ? 0x27 : 0;
    case 0x80:                                  /* READ_BLOCK */
        buf = *(unsigned char**)(p + 2);
        req = p[4] | (p[5] << 8);
        logcall(cmd, (unsigned int)buf, req);
        if (faulty('B')) return 0x27;
        strcpy(host, "unit_XX.po");
        host[5] = "0123456789ABCDEF"[p[1] >> 4];
        host[6] = "0123456789ABCDEF"[p[1] & 15];
        n = open(host, O_RDONLY);
        if (n < 0) return 0x28;                 /* no device */
        for (i = 0; i < req; ++i)
            if (read(n, scratch, 256) != 256 || read(n, scratch, 256) != 256) break;
        if (i < req || read(n, buf, 512) != 512) {
            close(n);
            return 0x27;
        }
        close(n);
        return 0;
    }
    logcall(cmd, 0, 0);
    return 0x01;
}
int main(int argc, char** argv)
{
    unsigned char r, i, k;
    int a;
    memcpy((void*)0xBF00, _MLISTUB_LOAD__, (unsigned)_MLISTUB_SIZE__);
    memset((void*)0x0200, 0x5A, 0x1E00);
    memset((void*)0x2000, 0xEE, 0x4000);
    memset((void*)0x6000, 0x77, 0x2000);
    k = strlen(argv[1]);
    if (argv[1][0] == '.') k = 0;
    path0[0] = k;
    memcpy(path0 + 1, argv[1], k);
    if (argv[2][0] != '-') { fault = argv[2][0]; fnth = atoi(argv[2] + 1); }
    t1_front = 0x20;
    r = run_dstart();
    out(&r, 1);
    out(t1_name, 24);
    if (r == 0) {
        for (a = 3; a < argc; ++a) {
            memset((void*)0x8000, 0xA5, 0x3000);
            memset((void*)0x2000, 0xEE, 0x4000);
            t1_front = (a & 1) ? 0x20 : 0x40;
            logcall(0xFF, t1_front, 0);
            t1_dest = (unsigned char*)0x8000;
            t1_max = atoi(argv[a] + 1);
            if (argv[a][0] == 'M') r = run_mload();
            else {
                k = (strlen(argv[a]) - 7) / 2;  /* L<max:5>:<hex name> */
                t1_name[0] = k;
                for (i = 0; i < k; ++i) {
                    char h[3];
                    h[0] = argv[a][7 + 2 * i]; h[1] = argv[a][8 + 2 * i]; h[2] = 0;
                    t1_name[1 + i] = strtoul(h, 0, 16);
                }
                r = run_load();
            }
            out(&r, 1);
            out(t1_name, 24);
            out(&t1_len, 2);
            out((void*)0x8000, 0x3000);
            out((t1_front == 0x20) ? (void*)0x2000 : (void*)0x4000, 0x2000);
            out((t1_front == 0x20) ? (void*)0x4800 : (void*)0x2800, 0x1800);
        }
    }
    out("Z", 1);
    out(&nlog, 2);
    out(log, nlog);
    out((void*)0x0200, 0x1E00);
    out((void*)0x6000, 0x2000);
    return 0;
}
"""


class DosSim:
    """dos.s + a fake MLI, for one processor."""

    def __init__(self, cpu, workdir):
        self.dir = workdir
        env = dict(os.environ, CC65_HOME=str(HEAD / 'share/cc65'))
        target = 'sim65c02' if cpu == '65c02' else 'sim6502'
        cfg = (HEAD / f'share/cc65/cfg/{target}.cfg').read_text()
        cfg, k = re.subn(r'start = \$0200, size = \$FFC0 - \$0200 - __STACKSIZE__',
                         'start = $C000, size = $FFC0 - $C000 - __STACKSIZE__', cfg)
        assert k == 1
        cfg, k = re.subn(r'(\n\s*RODATA:[^\n]*\n)',
                         r'\1    LOADER:   load = MAIN,   type = rw;\n    HICODE:   load = MAIN,   type = rw;\n'
                         r'    HIDATA:   load = MAIN,   type = rw;\n'
                         r'    MLISTUB:  load = MAIN, run = STUB, type = rw, define = yes;\n', cfg)
        assert k == 1
        cfg, k = re.subn(r'(\n\s*BSS:[^\n]*\n)', r'\1    HIBSS:    load = MAIN,   type = bss;\n', cfg)
        assert k == 1
        cfg, k = re.subn(r'(\n\s*MAIN:[^\n]*\n)', r'\1    STUB:   file = "", start = $BF00, size = $0100;\n', cfg)
        assert k == 1
        (workdir / f'{cpu}.cfg').write_text(cfg)
        (workdir / 'dharness.c').write_text(DHARNESS)
        (workdir / 'dglue.s').write_text(DGLUE)
        self.exe = workdir / f'dos-{cpu}'
        subprocess.run([str(HEAD / 'bin/cl65'), '-t', target, '-C', str(workdir / f'{cpu}.cfg'),
                        '-O', '-Wl', '-D,__STACKSIZE__=0x0400', '-o', str(self.exe),
                        str(workdir / 'dharness.c'), str(workdir / 'dglue.s'),
                        str(ROOT / 'src/take1/dos.s')],
                       check=True, cwd=workdir, env=env)

    def run(self, command, files, ops, fault='-'):
        for old in self.dir.glob('f_*'):
            old.unlink()
        for old in self.dir.glob('unit_*'):
            old.unlink()
        for path, data in files.items():
            name = path if path.startswith('unit_') else 'f' + path.replace('/', '_')
            (self.dir / name).write_bytes(data)
        args = []
        for op in ops:
            if op[0] == 'M':
                args.append('M%05d' % op[1])
            else:
                args.append('L%05d:' % op[2] + op[1].hex().upper())
        p = subprocess.run([str(HEAD / 'bin/sim65'), '-x', '2000000000', str(self.exe),
                            command or '.', fault] + args, cwd=self.dir, capture_output=True,
                           timeout=600)
        if p.returncode != 0:
            raise AssertionError('sim65 exit %d: %s' % (p.returncode, p.stderr[-300:]))
        o = p.stdout
        res = {'start': o[0], 'name': o[2:2 + o[1]], 'ops': []}
        pos = 25
        if res['start'] == 0:
            for _ in ops:
                code = o[pos]
                name = o[pos + 2:pos + 2 + o[pos + 1]]
                ln = struct.unpack_from('<H', o, pos + 25)[0]
                pos += 27
                buf = o[pos:pos + 0x3000]
                shown = o[pos + 0x3000:pos + 0x5000]
                spare_rest = o[pos + 0x5000:pos + 0x6800]
                pos += 0x6800
                res['ops'].append({'code': code, 'name': name, 'len': ln, 'buf': buf,
                                   'shown': shown, 'spare_rest': spare_rest})
        assert o[pos] == ord('Z'), o[pos:pos + 4]
        nlog = struct.unpack_from('<H', o, pos + 1)[0]
        log = o[pos + 3:pos + 3 + nlog]
        res['calls'] = [struct.unpack_from('<BHH', log, i) for i in range(0, nlog, 5)]
        pos += 3 + nlog
        res['low'] = o[pos:pos + 0x1E00]
        res['p3'] = o[pos + 0x1E00:pos + 0x3E00]
        return res


def to_po(dsk):
    """A DOS-order 140K image as ProDOS blocks (the design's mapping)."""
    htab = [0, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 15]
    po = bytearray(len(dsk))
    for t in range(len(dsk) // 4096):
        for s in range(16):
            h = htab[s]
            a = (8 * t + (h >> 1)) * 512 + (h & 1) * 256
            po[a:a + 256] = dsk[(16 * t + s) * 256:(16 * t + s + 1) * 256]
    return bytes(po)


class Loader(unittest.TestCase):
    """The command, the movie and the files (dos.s), both processors."""

    @classmethod
    def setUpClass(cls):
        if not (HEAD / 'bin/sim65').exists():
            raise unittest.SkipTest('cc65 master (CC65_HEAD) is needed')
        cls.tmp = tempfile.TemporaryDirectory(prefix='a2fc-take1dos-')
        cls.sims = {}
        for cpu in ('6502', '65c02'):
            d = Path(cls.tmp.name) / cpu
            d.mkdir()
            cls.sims[cpu] = DosSim(cpu, d)
        mv, files = ref.synthetic(7, scenes=2)
        cls.movie, cls.files = mv, files
        big = bytes(random.Random(1).randrange(256) for _ in range(9000))
        cls.files[b'AC.BIG ONE'] = big
        cls.files[b'AC.zero'] = b''
        cls.files[b'AC.HOLES'] = bytes(300) + b'\x01' + bytes(700) + b'\x02'
        allf = dict(cls.files)
        allf[b'MV.FILM'] = mv
        cls.dsk, cls.where = ref.make_dsk(allf)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def check(self, command, files, ops, expect_start=0, fault='-', loader=None, cpus=('6502', '65c02'),
              movie_name=b'THE MOVIE', expect=None):
        """ops: ('M', max) or ('L', name, max); expect: the reference's
        [(code, data)] per op, else computed with loader."""
        for cpu in cpus:
            res = self.sims[cpu].run(command, files, ops, fault)
            where = '%s %s %s' % (cpu, command, fault)
            self.assertEqual(res['start'], expect_start, where)
            # only OPEN, SET_MARK, READ, CLOSE, READ_BLOCK; ProDOS reads only
            # into the block buffer of the page not shown
            spare = 0x4000
            for cmd, a, b in res['calls']:
                if cmd == 0xFF:
                    spare = (a ^ 0x60) << 8
                    continue
                self.assertIn(cmd, (0xC8, 0xCA, 0xCE, 0xCC, 0x80), where)
                if cmd in (0xCA, 0x80):
                    self.assertEqual(a, spare + 0x400, where + ': READ buffer')
                if cmd == 0xC8:
                    self.assertEqual((a, b), (spare + 0x700, spare), where + ': OPEN')
            self.assertEqual(res['low'], b'\x5A' * 0x1E00, where + ': memory below $2000')
            self.assertEqual(res['p3'], b'\x77' * 0x2000, where + ': page 3')
            if expect_start:
                continue
            for i, (op, got) in enumerate(zip(ops, res['ops'])):
                w = '%s op %d %r' % (where, i, op[:2])
                self.assertEqual(got['shown'], b'\xEE' * 0x2000, w + ': the page shown')
                self.assertEqual(got['spare_rest'], b'\xEE' * 0x1800, w + ': the spare page past +$800')
                if expect is not None:
                    code, data = expect[i]
                else:
                    try:
                        data = loader(op[1] if op[0] == 'L' else None, op[-1])
                        code = 0
                    except ref.Refused as r:
                        code, data = r.code, None
                self.assertEqual(got['code'], code, w)
                if op[0] == 'M':
                    self.assertEqual(got['name'], movie_name, w)
                if code == 0:
                    self.assertEqual(got['len'], len(data), w)
                    self.assertEqual(got['buf'][:len(data)], data, w)
                    self.assertEqual(got['buf'][len(data):], b'\xA5' * (0x3000 - len(data)), w + ': past the file')
                else:
                    self.assertEqual(got['buf'][op[-1]:], b'\xA5' * (0x3000 - op[-1]), w + ': past t1_max')

    def image_loader(self, image, base=0):
        inner = ref.image_loader(ref.DosImage(image, base))
        t, s = self.where['MV.FILM'] if 'MV.FILM' in self.where else self.where[b'MV.FILM']

        def load(name, room):
            if name is None:
                try:
                    return ref.DosImage(image, base).read_file(t, s, limit=room)
                except OverflowError:
                    raise ref.Refused(ref.E_BIG, b'THE MOVIE')
                except IOError:
                    raise ref.Refused(ref.E_READ, b'THE MOVIE')
            return inner(name, room)
        return load

    def all_ops(self, room=0x3000):
        ops = [('M', room)]
        for name in self.files:
            ops.append(('L', name, room))
        ops += [('L', b'SN.MISSING', room), ('L', b'AC.BIG ONE', 8999), ('L', b'AC.BIG ONE', 9000),
                ('M', len(self.movie) - 1)]
        return ops

    def test_image(self):
        t, s = self.where[b'MV.FILM']
        ttss = '%02X%02X' % (t, s)
        ops = self.all_ops()
        self.check('/HD/TAKE1/FILMS.DSK,' + ttss, {'/HD/TAKE1/FILMS.DSK': self.dsk}, ops,
                   loader=self.image_loader(self.dsk))
        # a .2MG in DOS order: the data from its header's offset
        hdr = bytearray(64)
        hdr[0:4] = b'2IMG'
        hdr[0x18:0x1C] = (64).to_bytes(4, 'little')
        img2 = bytes(hdr) + self.dsk
        self.check('/V/F.2mg,' + ttss.lower(), {'/V/F.2mg': img2}, ops[:4],
                   loader=self.image_loader(img2, 64), cpus=('6502',))
        bad = bytearray(img2)
        bad[0x0C] = 1                                    # ProDOS order: refused
        self.check('/V/F.2MG,' + ttss, {'/V/F.2MG': bytes(bad)}, [], expect_start=ref.E_READ)
        bad = bytearray(img2)
        bad[0:4] = b'2IMH'
        self.check('/V/F.2MG,' + ttss, {'/V/F.2MG': bytes(bad)}, [], expect_start=ref.E_READ)
        self.check('/V/MISSING.2MG,' + ttss, {}, [], expect_start=ref.E_NOTFOUND)
        # a .DSK named like a 2MG is not read as one: only .2MG is
        self.check('/V/F.DSK,' + ttss, {'/V/F.DSK': self.dsk}, ops[:2], loader=self.image_loader(self.dsk),
                   cpus=('6502',))
        print('PASS take1: DOS 3.3 images (.DSK, .2MG): the movie by its T/S list, files by name')

    def test_unit(self):
        t, s = self.where[b'MV.FILM']
        ttss = '%02X%02X' % (t, s)
        ops = self.all_ops()
        self.check('%60,' + ttss, {'unit_60.po': to_po(self.dsk)}, ops, loader=self.image_loader(self.dsk))
        self.check('%E0,' + ttss, {'unit_E0.po': to_po(self.dsk)}, ops[:3], loader=self.image_loader(self.dsk),
                   cpus=('65c02',))
        # no such unit: every read fails
        self.check('%50,' + ttss, {}, [('M', 0x3000), ('L', b'SN.SC7.0', 0x3000)],
                   expect=[(ref.E_READ, None), (ref.E_READ, None)])
        print('PASS take1: a real disk (READ_BLOCK, the half-block mapping)')

    def test_files(self):
        D = '/HD/MOVIES/'
        files = {D + ref.prodos_name(k).decode(): v for k, v in self.files.items()}
        files[D + 'MV.FILM'] = self.movie
        ops = self.all_ops()

        def loader(name, room):
            if name is None:
                if len(self.movie) > room:
                    raise ref.Refused(ref.E_BIG, b'MV.FILM')
                return self.movie
            return ref.dict_loader({k: v for k, v in self.files.items()})(name, room)
        self.check(D + 'MV.FILM', files, ops, loader=loader, movie_name=b'MV.FILM')
        # names: 15 characters, upper case, punctuation to '.', a letter first
        odd = {b'AC.1st take': b'one', b'AC.A VERY LONG NAME IND': b'two', b'CS.font/x?': b'three'}
        f2 = {D + ref.prodos_name(k).decode(): v for k, v in odd.items()}
        f2[D + 'MV.X'] = self.movie
        self.assertEqual(set(f2), {D + 'AC.1ST.TAKE', D + 'AC.A.VERY.LONG.', D + 'CS.FONT.X.', D + 'MV.X'})
        self.check(D + 'MV.X', f2, [('L', k, 100) for k in odd],
                   expect=[(0, v) for v in odd.values()], cpus=('6502',))
        # a movie in the prefix (no directory)
        self.check('MV.X', {'MV.X': self.movie, 'AC.Q': b'q' * 300}, [('M', 0x3000), ('L', b'AC.Q', 0x3000)],
                   expect=[(0, self.movie), (0, b'q' * 300)], movie_name=b'MV.X', cpus=('6502',))
        print('PASS take1: extracted files under their ProDOS names')

    def test_commands(self):
        for bad in ('', '.', '/V/F.DSK,110', '/V/F.DSK,11003', '/V/F.DSK,11G3', ',1103', '%6,1103',
                    '%60;1103', '%60,11033', '/' + 'A' * 45 + 'B', '%G0,1103'):
            self.check(bad, {}, [], expect_start=5 if bad != '.' else 5, cpus=('6502',))
        self.check('/' + 'A' * 45, {}, [('M', 100)], expect=[(ref.E_NOTFOUND, None)], cpus=('6502',),
                   movie_name=b'A' * 23)
        print('PASS take1: malformed commands refused')

    def test_damaged_and_faults(self):
        t, s = self.where[b'MV.FILM']
        ttss = '%02X%02X' % (t, s)
        cmd = '/V/F.DSK,' + ttss
        name = b'AC.BIG ONE'
        ops = [('M', 0x3000), ('L', name, 0x3000)]
        good = self.image_loader(self.dsk)
        # every MLI failure is a read error, never data
        for fault in ('O1', 'O2', 'R1', 'R3', 'R9', 'S1', 'S5', 'M1', 'M4', 'C1', 'C2'):
            res = self.sims['6502'].run(cmd, {'/V/F.DSK': self.dsk}, ops, fault)
            for i, got in enumerate(res['ops']):
                if got['code'] == 0:
                    data = good(None if ops[i][0] == 'M' else ops[i][1], 0x3000)
                    self.assertEqual(got['buf'][:got['len']], data, (fault, i))
            self.assertTrue(any(g['code'] == ref.E_READ for g in res['ops']), fault)
        # damaged disks, against the reference
        cases = []
        img = bytearray(self.dsk)
        img[17 * 4096 + 15 * 256 + 1:17 * 4096 + 15 * 256 + 3] = bytes([17, 15])   # catalog loop
        cases.append(('catalog loop', bytes(img)))
        img = bytearray(self.dsk)
        img[17 * 4096 + 1:17 * 4096 + 3] = bytes([40, 0])                       # catalog off the disk
        cases.append(('catalog off the disk', bytes(img)))
        tb, sb = self.where[name]
        img = bytearray(self.dsk)
        a = (16 * tb + sb) * 256
        img[a + 12 + 2 * 20:a + 14 + 2 * 20] = bytes([3, 16])                   # sector 16
        cases.append(('sector 16', bytes(img)))
        img = bytearray(self.dsk)
        img[a + 12 + 2 * 30:a + 12 + 2 * 122] = bytes(184)                       # holes
        img[a + 1:a + 3] = bytes(2)
        cases.append(('holes: zeros (122 pairs cover any file that fits)', bytes(img)))
        img = bytearray(self.dsk)
        img[a + 12 + 2 * 3:a + 14 + 2 * 3] = bytes([60, 0])                      # off the image
        cases.append(('data off the image', bytes(img)))
        img = bytearray(self.dsk)
        img[a + 1:a + 3] = bytes([tb, sb])                                       # a list on itself
        cases.append(('loop: a list on itself, never followed', bytes(img)))
        img = bytearray(self.dsk)
        fa = (16 * self.dsk[a + 12] + self.dsk[a + 13]) * 256
        img[fa + 2:fa + 4] = (0x3001).to_bytes(2, 'little')                      # header length
        cases.append(('length over', bytes(img)))
        for label, im in cases:
            codes = []
            for op in ops + [('L', b'SN.SC7.1', 0x3000)]:
                try:
                    self.image_loader(im)(op[1] if op[0] == 'L' else None, 0x3000)
                    codes.append(0)
                except ref.Refused as r:
                    codes.append(r.code)
            self.assertTrue(any(codes) or label.startswith(('holes', 'loop')), (label, codes))
            self.check(cmd, {'/V/F.DSK': im}, ops + [('L', b'SN.SC7.1', 0x3000)],
                       loader=self.image_loader(im), cpus=('6502', '65c02') if label[0] == 'c' else ('6502',))
        # unit faults
        res = self.sims['6502'].run('%60,' + ttss, {'unit_60.po': to_po(self.dsk)}, ops, 'B3')
        self.assertTrue(any(g['code'] == ref.E_READ for g in res['ops']))
        print('PASS take1: damaged disks and I/O errors are refused, never taken for data')


# -- TAKE1.SYSTEM itself, end to end -------------------------------------------

SGLUE = r"""
        .export _go, _mli_stub_start, _mli_stub_end, _do_reset
        .import _fake_mli, pusha
        .importzp ptr1
        .bss
mcmd:   .res    1
mpl:    .res    1
mph:    .res    1
        .code
_go:    jmp     $2000                   ; the interpreter's start
_do_reset:
        jmp     ($03F2)                 ; Ctrl-Reset, a valid PWREDUP: the ROM's jump
; The MLI stub, copied to $BF00: jsr $BF00 / .byte cmd / .word params.
_mli_stub_start:
        .org    $BF00
        pla
        sta     ptr1
        pla
        sta     ptr1+1
        ldy     #1
        lda     (ptr1),y
        sta     mcmd
        iny
        lda     (ptr1),y
        sta     mpl
        iny
        lda     (ptr1),y
        sta     mph
        clc
        lda     ptr1
        adc     #3
        tax
        lda     ptr1+1
        adc     #0
        pha
        txa
        pha
        lda     mcmd
        jsr     pusha
        lda     mpl
        ldx     mph
        jsr     _fake_mli
        cmp     #1
        rts
        .reloc
_mli_stub_end:
"""

SHARNESS = r"""
#include <stdio.h>
#include <fcntl.h>
#include <unistd.h>
#include <string.h>
#include <stdlib.h>
extern unsigned char mli_stub_start[], mli_stub_end[];
void go(void);
void do_reset(void);
static unsigned char reset_mode, thunk_mode;
static void dump(void);
static char host[80], ohost[80];
static int fd = -1;
static long fsize;
static unsigned int opens, ncalls, escape_at;
static unsigned char scratch[256];
static unsigned char log[3000];
static unsigned int nlog;
static const unsigned char bitmap0[24] = {0xCF,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0x01};
static unsigned char marked[24];
static void out(const void* p, unsigned n)
{
    if (write(1, p, n) != (int)n) exit(20);
}
static void logcall(unsigned char cmd, unsigned int a, unsigned int b)
{
    if (nlog + 5 > sizeof log) return;
    log[nlog] = cmd;
    memcpy(log + nlog + 1, &a, 2);
    memcpy(log + nlog + 3, &b, 2);
    nlog += 5;
}
unsigned char __fastcall__ fake_mli(unsigned char cmd, unsigned char* p)
{
    int n;
    unsigned int req, i;
    unsigned char* buf;
    long mark;
    if (++ncalls == escape_at) {
        if (!reset_mode) *(unsigned char*)0xC000 = 0x9B;           /* Escape */
        else {                                  /* Ctrl-Reset, in the middle of a call */
            if (fd >= 0) close(fd);
            fd = -1;
            if (*(unsigned char*)0x3F4 != (*(unsigned char*)0x3F3 ^ 0xA5)) { out("B", 1); exit(0); }
            do_reset();
        }
    }
    switch (cmd) {
    case 0xC8:                                  /* OPEN */
        buf = *(unsigned char**)(p + 1);
        logcall(cmd, (unsigned int)buf, *(unsigned int*)(p + 3));
        if (thunk_mode && *(unsigned int*)(p + 3) == 0xBB00)
            memset((void*)0xBB00, 0x02, 0x400);  /* ProDOS fills its I/O buffer */
        ++opens;
        if (opens == 3) memcpy(marked, (void*)0xBF58, 24);
        host[0] = 'f';
        for (i = 0; i < buf[0]; ++i) host[i + 1] = buf[i + 1] == '/' ? '_' : buf[i + 1];
        host[buf[0] + 1] = 0;
        if (fd >= 0) return 0x42;
        fd = open(host, O_RDONLY);
        if (fd < 0) return 0x46;
        strcpy(ohost, host);
        fsize = 0;
        while ((n = read(fd, scratch, sizeof scratch)) > 0) fsize += n;
        close(fd);
        fd = open(ohost, O_RDONLY);
        p[5] = 1;
        return 0;
    case 0xCA:                                  /* READ */
        buf = *(unsigned char**)(p + 2);
        req = p[4] | (p[5] << 8);
        logcall(cmd, (unsigned int)buf, req);
        if (thunk_mode && (unsigned int)buf == 0x2000 && req == 0x9B00) {
            /* Ctrl-Reset while the thunk reads A2FILE.SYSTEM */
            thunk_mode = 0;
            if (fd >= 0) close(fd);
            fd = -1;
            if (*(unsigned char*)0x3F4 == (*(unsigned char*)0x3F3 ^ 0xA5)) {
                if (*(unsigned int*)0x3F2 == 0xFF59) { logcall(0x59, 0xFF59, 0); dump(); }
                do_reset();
            }
            out("B", 1); exit(0);
        }
        if (fd < 0 || p[1] != 1) return 0x43;
        n = read(fd, buf, req);
        if (n < 0) return 0x27;
        if (!n && req) return 0x4C;
        p[6] = n & 255; p[7] = n >> 8;
        return 0;
    case 0xCE:                                  /* SET_MARK */
        mark = p[2] | ((long)p[3] << 8) | ((long)p[4] << 16);
        logcall(cmd, (unsigned int)mark, (unsigned int)(mark >> 16));
        if (fd < 0 || p[1] != 1) return 0x43;
        if (mark > fsize) return 0x4D;
        close(fd);
        fd = open(ohost, O_RDONLY);
        while (mark >= 256) { read(fd, scratch, 256); mark -= 256; }
        if (mark) read(fd, scratch, (unsigned)mark);
        return 0;
    case 0xCC:                                  /* CLOSE */
        logcall(cmd, p[1], 0);
        if (fd >= 0) close(fd);
        fd = -1;
        return 0;
    case 0x80:                                  /* READ_BLOCK */
        buf = *(unsigned char**)(p + 2);
        req = p[4] | (p[5] << 8);
        logcall(cmd, (unsigned int)buf, req);
        n = open("unit.po", O_RDONLY);
        if (n < 0) return 0x28;
        for (i = 0; i < req; ++i)
            if (read(n, scratch, 256) != 256 || read(n, scratch, 256) != 256) break;
        if (i < req || read(n, buf, 512) != 512) { close(n); return 0x27; }
        close(n);
        return 0;
    case 0x65:                                  /* QUIT: the end */
        logcall(cmd, 0, 0);
        dump();
    }
    logcall(cmd, 0, 0);
    return 0x01;
}
static void dump(void)
{
    {
        out("Q", 1);
        out(&nlog, 2);
        out(log, nlog);
        out(&opens, 2);
        out(marked, 24);
        out((void*)0xBF58, 24);
        out((void*)0x0300, 0xD0);
        out((void*)0x0400, 0x400);
        exit(0);
    }
}
int main(int, char** argv)
{
    int f;
    unsigned char n;
    memcpy((void*)0xBF00, mli_stub_start, mli_stub_end - mli_stub_start);
    memcpy((void*)0xBF58, bitmap0, 24);
    memset((void*)0xC000, 0, 0x100);
    if (argv[2][0] == 'K') *(unsigned char*)0xC000 = 0x8D;      /* a key waiting */
    reset_mode = argv[2][0] == 'R';
    thunk_mode = argv[2][0] == 'T';
    /* the reset vector A2 File Cmd leaves (its crt0's _exit, $400C), valid */
    *(unsigned int*)0x3F2 = 0x400C;
    *(unsigned char*)0x3F4 = 0x40 ^ 0xA5;
    escape_at = atoi(argv[3]);
    f = open("TAKE1.SYSTEM.SYS", O_RDONLY);
    if (f < 0) return 10;
    if (read(f, (void*)0x2000, 0x9F00) <= 0) return 11;
    close(f);
    n = strlen(argv[1]);
    *(unsigned char*)0x2006 = n;
    memcpy((void*)0x2007, argv[1], n);
    go();
    return 12;
}
"""


class SysSim:
    """TAKE1.SYSTEM.SYS as built, at $2000, with a fake MLI (6502)."""

    def __init__(self, workdir, binary):
        self.dir = workdir
        env = dict(os.environ, CC65_HOME=str(HEAD / 'share/cc65'))
        cfg = (HEAD / 'share/cc65/cfg/sim6502.cfg').read_text()
        cfg, k = re.subn(r'start = \$0200, size = \$FFC0 - \$0200 - __STACKSIZE__',
                         'start = $C100, size = $FFC0 - $C100 - __STACKSIZE__', cfg)
        assert k == 1
        (workdir / 'sys.cfg').write_text(cfg)
        (workdir / 'sharness.c').write_text(SHARNESS)
        (workdir / 'sglue.s').write_text(SGLUE)
        # sim65 has one byte at $C000: the 80STORE-off store (sta $C000)
        # would overwrite the key the harness puts there; it goes to $C0FF.
        n = binary.count(bytes([0x8D, 0x00, 0xC0]))
        assert n == 2, 'sta $C000: %d' % n
        binary = binary.replace(bytes([0x8D, 0x00, 0xC0]), bytes([0x8D, 0xFF, 0xC0]))
        (workdir / 'TAKE1.SYSTEM.SYS').write_bytes(binary)
        self.exe = workdir / 'sys'
        subprocess.run([str(HEAD / 'bin/cl65'), '-t', 'sim6502', '-C', str(workdir / 'sys.cfg'),
                        '-O', '-Wl', '-D,__STACKSIZE__=0x0400', '-o', str(self.exe),
                        str(workdir / 'sharness.c'), str(workdir / 'sglue.s')],
                       check=True, cwd=workdir, env=env)

    def run(self, command, files, escape_at, key=False, reset=False, thunk=False):
        for old in self.dir.glob('f_*'):
            old.unlink()
        for path, data in files.items():
            name = path if path == 'unit.po' else 'f' + path.replace('/', '_')
            (self.dir / name).write_bytes(data)
        p = subprocess.run([str(HEAD / 'bin/sim65'), '-x', '4000000000', str(self.exe), command,
                            'T' if thunk else 'R' if reset else 'K' if key else '-', str(escape_at)],
                           cwd=self.dir,
                           capture_output=True, timeout=1200)
        o = p.stdout
        if p.returncode != 0 or not o.startswith(b'Q'):
            raise AssertionError('sim65 exit %d: %r %s' % (p.returncode, o[:40], p.stderr[-300:]))
        nlog = struct.unpack_from('<H', o, 1)[0]
        log = o[3:3 + nlog]
        pos = 3 + nlog
        opens = struct.unpack_from('<H', o, pos)[0]
        return {'calls': [struct.unpack_from('<BHH', log, i) for i in range(0, nlog, 5)],
                'opens': opens, 'marked': o[pos + 2:pos + 26], 'bitmap': o[pos + 26:pos + 50],
                'thunk': o[pos + 50:pos + 50 + 0xD0], 'text': o[pos + 50 + 0xD0:pos + 50 + 0xD0 + 0x400]}


def text_rows(text):
    rows = []
    for y in range(24):
        a = (y & 7) * 0x80 + (y >> 3) * 0x28
        rows.append(bytes(c & 0x7F for c in text[a:a + 40]).decode('latin-1').rstrip())
    return rows


class System(unittest.TestCase):
    """The built TAKE1.SYSTEM, from $2000 to its QUIT, under sim65."""

    @classmethod
    def setUpClass(cls):
        if not (HEAD / 'bin/sim65').exists():
            raise unittest.SkipTest('cc65 master (CC65_HEAD) is needed')
        found = [ROOT / d / 'TAKE1.SYSTEM.SYS' for d in ('build', 'build-6502')
                 if (ROOT / d / 'TAKE1.SYSTEM.SYS').exists()]
        if not found:
            raise unittest.SkipTest('TAKE1.SYSTEM.SYS: run make first')
        binary = max(found, key=lambda p: p.stat().st_mtime)     # (both editions: the same bytes)
        cls.tmp = tempfile.TemporaryDirectory(prefix='a2fc-take1sys-')
        cls.sim = SysSim(Path(cls.tmp.name), binary.read_bytes())

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def common(self, res, label):
        bitmap0 = bytes([0xCF] + [0] * 22 + [0x01])
        # read-only: OPEN, SET_MARK, READ, CLOSE, READ_BLOCK, then QUIT
        cmds = [c for c, _, _ in res['calls']]
        self.assertTrue(set(cmds) <= {0xC8, 0xCA, 0xCE, 0xCC, 0x80, 0x65}, (label, set(cmds)))
        self.assertEqual(cmds[-1], 0x65, label)
        for cmd, a, b in res['calls']:
            if cmd in (0xCA, 0x80) and a != 0x2000:
                self.assertIn(a, (0x2400, 0x4400), label + ': READ buffer')
            if cmd == 0xC8 and b != 0xBB00:
                self.assertIn((a, b), ((0x2700, 0x2000), (0x4700, 0x4000)), label + ': OPEN')
        # the way back: the thunk opened A2FILE.SYSTEM (missing here: QUIT)
        opens = [(a, b) for c, a, b in res['calls'] if c == 0xC8]
        self.assertEqual(opens[-1][1], 0xBB00, label)
        self.assertEqual(res['bitmap'], bitmap0, label + ': the bitmap given back')
        self.assertIn(b'\x0dA2FILE.SYSTEM', res['thunk'], label)

    def test_play_and_escape(self):
        mv, files = ref.crafted('plant', 0)
        D = '/HD/T1/'
        f = {D + ref.prodos_name(k).decode(): v for k, v in files.items()}
        f[D + 'MV.PLANT'] = mv
        res = self.sim.run(D + 'MV.PLANT', f, escape_at=400)
        self.common(res, 'files')
        self.assertGreaterEqual(res['opens'], 24)          # played once, then again
        marked = res['marked']
        for page in list(range(0x02, 0x08)) + list(range(0x08, 0x20)) + list(range(0x80, 0xBF)):
            self.assertTrue(marked[page >> 3] & (0x80 >> (page & 7)), 'page $%02X marked' % page)
        for page in range(0x20, 0x80):
            self.assertFalse(marked[page >> 3] & (0x80 >> (page & 7)), 'page $%02X free' % page)
        # the same movie from a disk image and from a real disk
        allf = dict(files)
        allf[b'MV.PLANT'] = mv
        dsk, where = ref.make_dsk(allf)
        ttss = ''.join(format(v, '02X') for v in where[b'MV.PLANT'])
        res = self.sim.run('/HD/T1/MOVIES.DSK,' + ttss, {'/HD/T1/MOVIES.DSK': dsk}, escape_at=300)
        self.common(res, 'image')
        self.assertTrue(any(c == 0xCE for c, _, _ in res['calls']))
        res = self.sim.run(chr(37) + '60,' + ttss, {'unit.po': to_po(dsk)}, escape_at=150)
        self.common(res, 'unit')
        self.assertGreater(sum(1 for c, _, _ in res['calls'] if c == 0x80), 20)
        print('PASS take1: TAKE1.SYSTEM plays from files, an image and a disk, read-only, Escape gives '
              'the bitmap back and loads A2FILE.SYSTEM')

    def test_reset_returns(self):
        """Ctrl-Reset while a movie plays, in the middle of a read: the
        program's reset vector brings A2FILE.SYSTEM back, bitmap given back.
        Before 0.9.5 the vector was still A2 File Cmd's ($400C, its crt0's
        _exit), in hi-res page 2 which the player fills with pictures and
        its I/O buffer: a reset ran those bytes as code (here sim65 left
        without the QUIT, or after a 4-billion-cycle hang)."""
        mv, files = ref.crafted('plant', 0)
        D = '/HD/T1/'
        f = {D + ref.prodos_name(k).decode(): v for k, v in files.items()}
        f[D + 'MV.PLANT'] = mv
        allf = dict(files)
        allf[b'MV.PLANT'] = mv
        dsk, where = ref.make_dsk(allf)
        ttss = ''.join(format(v, '02X') for v in where[b'MV.PLANT'])
        for label, cmd, fl, at in (('files', D + 'MV.PLANT', f, 5), ('files', D + 'MV.PLANT', f, 60),
                                   ('image', '/HD/T1/MOVIES.DSK,' + ttss, {'/HD/T1/MOVIES.DSK': dsk}, 90),
                                   ('unit', chr(37) + '60,' + ttss, {'unit.po': to_po(dsk)}, 40)):
            res = self.sim.run(cmd, fl, escape_at=at, reset=True)
            self.common(res, 'reset: %s at call %d' % (label, at))
        # Escape, then Ctrl-Reset while the thunk reads A2FILE.SYSTEM: its
        # I/O buffer ($BB00-$BEFF) has covered thunk_src, so the vector must
        # be the monitor's OLDRST, not back -- which copied that buffer to
        # page 3 and ran it (before: sim65 died on its $02 bytes).
        for label, cmd, fl, at in (('files', D + 'MV.PLANT', f, 60),
                                   ('image', '/HD/T1/MOVIES.DSK,' + ttss, {'/HD/T1/MOVIES.DSK': dsk}, 90)):
            res = self.sim.run(cmd, dict(fl, **{'A2FILE.SYSTEM': bytes(300)}), escape_at=at, thunk=True)
            w = 'reset in the thunk: ' + label
            self.assertEqual(res['calls'][-1], (0x59, 0xFF59, 0), w + ': vector at OLDRST')
            self.assertEqual(res['calls'][-3][0], 0xC8, w)
            self.assertEqual(res['calls'][-3][2], 0xBB00, w + ': the thunk\'s OPEN')
            self.assertEqual(res['bitmap'], bytes([0xCF] + [0] * 22 + [0x01]), w + ': bitmap given back')
        print('PASS take1: Ctrl-Reset while a movie plays gives the bitmap back and loads A2FILE.SYSTEM; '
              'from the return thunk on it goes to OLDRST')

    def test_refused_message(self):
        mv, files = ref.crafted('plant', 0)
        D = '/HD/T1/'
        f = {D + ref.prodos_name(k).decode(): v for k, v in files.items()}
        f[D + 'MV.PLANT'] = mv
        del f[D + 'AC.P']
        res = self.sim.run(D + 'MV.PLANT', f, escape_at=0, key=True)
        self.common(res, 'missing')
        rows = text_rows(res['text'])
        self.assertEqual(rows[8], 'TAKE 1')
        self.assertEqual(rows[10], 'FILE NOT FOUND:')
        self.assertEqual(rows[11], 'AC.P')
        self.assertEqual(rows[13], 'PRESS A KEY TO RETURN.')
        f[D + 'AC.P'] = files[b'AC.P'][:20]
        res = self.sim.run(D + 'MV.PLANT', f, escape_at=0, key=True)
        rows = text_rows(res['text'])
        self.assertEqual((rows[10], rows[11]), ('NOT A VALID TAKE 1 FILE:', 'AC.P'))
        res = self.sim.run('/X/F.DSK,11G0', {}, escape_at=0, key=True)
        rows = text_rows(res['text'])
        self.assertEqual((rows[10], rows[11]), ('THE COMMAND IS NOT UNDERSTOOD.', ''))
        self.assertEqual(res['bitmap'], bytes([0xCF] + [0] * 22 + [0x01]))
        print('PASS take1: a refused movie names the file on the text screen, a key returns')


# -- the driver's timing --------------------------------------------------------

TGLUE = r"""
        .import t1_wait, t1_delay, t1_sound, t1_mode, t1_hold
        .export _call_wait, _call_delay, _call_sound, _t1_mode := t1_mode
        .export _t1_hold := t1_hold
_call_wait:                             ; (A/X = n)
        jmp     t1_wait
_call_delay:
        jmp     t1_delay
_call_sound:
        jmp     t1_sound
"""

THARNESS = r"""
#include <unistd.h>
#include <string.h>
#include <stdlib.h>
#include <sim65.h>
extern unsigned char t1_mode;
extern unsigned long t1_hold;
void __fastcall__ call_wait(unsigned n);
void __fastcall__ call_delay(unsigned char a);
void __fastcall__ call_sound(unsigned char t);
static unsigned long c0, c1;
static unsigned long cyc(void)
{
    peripherals.counter.latch = 0;
    return peripherals.counter.value32[0];
}
static void out(unsigned long v)
{
    write(1, &v, 4);
}
int main(int, char** argv)
{
    unsigned i;
    memset((void*)0xC000, 0, 0x100);            /* no key */
    t1_mode = 1;
    c0 = cyc(); c1 = cyc(); out(c1 - c0);
    for (i = 0; i < 6; ++i) {
        static const unsigned long hs[6] = {0, 256, 1024, 1407, 25600, 256000};
        t1_hold = hs[i];
        c0 = cyc(); call_wait(0); c1 = cyc(); out(c1 - c0);
    }
    for (i = 0; i < 4; ++i) {
        static const unsigned char as[4] = {1, 30, 141, 0};
        c0 = cyc(); call_delay(as[i]); c1 = cyc(); out(c1 - c0);
    }
    for (i = 0; i < 18; ++i) {
        c0 = cyc(); call_sound(i); c1 = cyc(); out(c1 - c0);
    }
    t1_mode = 0;
    c0 = cyc(); call_wait(1000); c1 = cyc(); out(c1 - c0);
    c0 = cyc(); call_delay(141); c1 = cyc(); out(c1 - c0);
    return 0;
}
"""


TCFG = """
SYMBOLS {
    __EXEHDR__:    type = import;
    __STACKSIZE__: type = weak, value = $0400;
    _peripherals:  type = export, value = $FFC0;
}
MEMORY {
    ZP:     file = "", start = $0000, size = $0100;
    HEADER: file = %O, start = $0000, size = $000C;
    MAIN:   file = %O, define = yes, start = $C100, size = $FFC0 - $C100 - __STACKSIZE__;
    LRUN:   file = "", start = $2000, size = $2000;
}
SEGMENTS {
    ZEROPAGE: load = ZP,     type = zp;
    EXEHDR:   load = HEADER, type = ro;
    STARTUP:  load = MAIN,   type = ro;
    LOWCODE:  load = MAIN,   type = ro,  optional = yes;
    ONCE:     load = MAIN,   type = ro,  optional = yes;
    TIMED:    load = MAIN,   type = ro,  define = yes, align = $100;
    CODE:     load = MAIN,   type = ro,  define = yes;
    HICODE:   load = MAIN,   type = ro,  define = yes;
    RODATA:   load = MAIN,   type = ro,  define = yes;
    HIDATA:   load = MAIN,   type = rw,  define = yes;
    DATA:     load = MAIN,   type = rw;
    BSS:      load = MAIN,   type = bss, define = yes;
    HIBSS:    load = MAIN,   type = bss, define = yes;
    LOADER:   load = MAIN, run = LRUN, type = rw, define = yes;
    LOWC:     load = MAIN,   type = ro,  define = yes;
    TXC3:     load = MAIN,   type = ro,  define = yes;
    TXC5:     load = MAIN,   type = ro,  define = yes;
    TXC6:     load = MAIN,   type = ro,  define = yes;
    TXC7:     load = MAIN,   type = ro,  define = yes;
    TXT0:     load = MAIN,   type = bss;
    TXT1:     load = MAIN,   type = bss;
    TXT2:     load = MAIN,   type = bss;
    TXT3:     load = MAIN,   type = bss;
}
FEATURES {
    CONDES: type = constructor, label = __CONSTRUCTOR_TABLE__, count = __CONSTRUCTOR_COUNT__,
            segment = ONCE;
    CONDES: type = destructor, label = __DESTRUCTOR_TABLE__, count = __DESTRUCTOR_COUNT__,
            segment = RODATA;
    CONDES: type = interruptor, label = __INTERRUPTOR_TABLE__, count = __INTERRUPTOR_COUNT__,
            segment = RODATA, import = __CALLIRQ__;
}
"""


class Timing(unittest.TestCase):
    """The original speed: the hold (t1_hold cycles, in units of 256), D(a)
    and the sounds' steps, counted by sim65."""

    def test_timing(self):
        if not (HEAD / 'bin/sim65').exists():
            raise unittest.SkipTest('cc65 master (CC65_HEAD) is needed')
        with tempfile.TemporaryDirectory(prefix='a2fc-take1time-') as tmp:
            w = Path(tmp)
            env = dict(os.environ, CC65_HOME=str(HEAD / 'share/cc65'))
            cfg = TCFG
            (w / 't.cfg').write_text(cfg)
            (w / 't.c').write_text(THARNESS)
            (w / 'tglue.s').write_text(TGLUE)
            subprocess.run([str(HEAD / 'bin/cl65'), '-t', 'sim6502', '-C', str(w / 't.cfg'), '-O',
                            '-o', str(w / 't'), str(w / 't.c'), str(w / 'tglue.s'),
                            str(ROOT / 'src/take1/take1.s'), str(ROOT / 'src/take1/dos.s'),
                            str(ROOT / 'src/take1/engine.s')], check=True, cwd=w, env=env)
            p = subprocess.run([str(HEAD / 'bin/sim65'), str(w / 't')], cwd=w, capture_output=True,
                               timeout=300)
            self.assertEqual(p.returncode, 0, p.stderr)
            v = struct.unpack('<%dI' % (len(p.stdout) // 4), p.stdout)
        over, waits, delays, sounds, fast = v[0], v[1:7], v[7:11], v[11:29], v[29:]
        waits = [x - over for x in waits]
        base = waits[0]                                 # the call and the checks
        for h, got in zip((256, 1024, 1407, 25600, 256000), waits[1:]):
            want = (h + 128) // 256 * 256           # units of 256 cycles, rounded
            # (4 when wn's low byte is 0; 2: the harness's code may cross a page)
            self.assertLessEqual(abs(got - base - want), 2 + 4 * (h // 65536), (h, got - base, want))
        def wait(a):
            return (5 * a * a + 27 * a + 26) // 2
        for a, got in zip((30, 141, 256), delays[1:]):          # from D(1): the call
            self.assertLessEqual(abs((got - delays[0]) - (wait(a) - wait(1))), 10, a)
        # sounds: tones of count x p steps take about count (12 p + 9) cycles
        tones = {0: [(24, 8), (24, 6)], 3: [(56, 112), (3, 21)], 7: [(96, 32), (18, 33), (16, 36),
                                                                    (10, 41), (3, 160), (3, 208)],
                 10: [(36, 168)], 17: [(78, 84)]}
        for t, steps in tones.items():
            want = sum(c * (12 * p + 9) for c, p in steps)
            toggles = sum(c for c, _ in steps)          # 2 more a toggle, the steps' reading
            self.assertLessEqual(abs(sounds[t] - over - want), 3 * toggles + 120 * len(steps) + 100,
                                 (t, sounds[t] - over, want))
        self.assertLess(fast[0] - over, 400)                # accelerated: no wait
        self.assertLess(fast[1] - over, 400)
        print('PASS take1: the hold is waited in units of 256 cycles, D(a) the '
              'monitor\'s formula, tones about 12 p + 9 cycles a toggle')


def intervals(sim, movies):
    """The frames of the movies, timed under sim65 (a Sim built with
    measure=True): for each frame shown, from the one before, the engine's
    own cycles (the hooks' time taken off: the cycle stamps at their entry
    and exit), its work (take1_ref's counters, with n, the wait owed) and
    the hold the engine computed before showing it. Frames after a scene's
    loading, a fade or a $FC element are left out."""
    out = []
    for mv, files in movies:
        res = sim.run(mv, files)
        player = ref.Player(mv, ref.dict_loader(files))
        list(player.play())
        last = None             # the last show's exit stamp
        hooks = 0               # the hooks' time since
        hold = None
        clean = False
        k = -1
        for e in res['events']:
            if e[0] == 'show':
                st = struct.unpack('<II', e[2])
                k += 1
                w = player.work_log[k]
                if last is not None and clean and not w['first']:
                    out.append({'work': w, 'own': st[0] - last - hooks, 'hold': hold})
                last, hooks, clean = st[1], 0, True
            elif e[0] in ('wait', 'fc'):
                st = struct.unpack('<II', e[-1])
                hooks += st[1] - st[0]
                if e[0] == 'wait':
                    hold = e[2]
                else:
                    clean = False
            elif e[0] in ('delay', 'tick'):
                clean = False
        assert k + 1 == len(player.work_log)
    return out


def calibrate(write=False):
    """Fits OWN_BASE and OWN_* (engine.s) on the engine's own time per frame:
    least squares, relative, on movies shaped like real ones and on the
    synthetic set. With --write, engine.s is updated."""
    import statistics
    from test_fantavision import lstsq
    with tempfile.TemporaryDirectory(prefix='a2fc-take1c-') as tmp:
        sim = Sim('6502', Path(tmp), measure=True)
        movies = [ref.realistic(seed) for seed in range(20, 60)]
        movies += [ref.synthetic(seed) for seed in range(40)]
        data = intervals(sim, movies)
    names = list(ref.COUNTERS)
    rows = [[d['work'][k] for k in names] + [1] for d in data]
    ys = [d['own'] for d in data]
    coef = lstsq(rows, ys)
    own = {k: round(c) for k, c in zip(names, coef[:-1])}
    base = max(0, round(coef[-1])) + DRIVER
    errs = [(base - DRIVER + sum(own[k] * d['work'][k] for k in names)) / d['own'] - 1 for d in data]
    q = statistics.quantiles(errs, n=10)
    print('take1 --calibrate (%d frames): OWN_BASE %d (+%d for the driver), %s; '
          'relative error median %+.3f, p10 %+.3f, p90 %+.3f'
          % (len(data), base, DRIVER, ', '.join('OWN_%s %d' % (k.upper(), own[k]) for k in names),
             statistics.median(errs), q[0], q[-1]))
    if write:
        path = ROOT / 'src/take1/engine.s'
        text = path.read_text()
        text, nsub = re.subn(r'^OWN_BASE(\s*)=\s*-?\d+', r'OWN_BASE\g<1>= %d' % base, text, flags=re.M)
        assert nsub == 1
        for k in names:
            text, nsub = re.subn(r'^OWN_%s(\s*)=\s*-?\d+' % k.upper(),
                                 r'OWN_%s\g<1>= %d' % (k.upper(), own[k]), text, flags=re.M)
            assert nsub == 1, k
        path.write_text(text)
        print('engine.s updated')


def measure(seeds=range(8), cpu='6502'):
    """The original speed, on movies shaped like real ones
    (take1_ref.realistic): per frame, the player's total time -- the engine's
    own cycles plus the hold it computed, waited by take1.s in units of 256
    cycles -- against the target, the spec's model of the original's time
    (model_cycles of the work, plus the exact frame wait owed). Also the
    engine's own time against the model alone."""
    import statistics
    with tempfile.TemporaryDirectory(prefix='a2fc-take1m-') as tmp:
        sim = Sim(cpu, Path(tmp), measure=True)
        data = intervals(sim, [ref.realistic(seed) for seed in seeds])
    eng, tot, owns, models = [], [], [], []
    for d in data:
        m = ref.model_cycles(d['work'])
        target = m + ref.wait_cycles(d['work']['n'])
        held = ((d['hold'] + 128) >> 8) * 256 + WAIT_OVERHEAD
        eng.append(d['own'] / m)
        tot.append((d['own'] + held) / target)
        owns.append(d['own'])
        models.append(m)
    qe = statistics.quantiles(eng, n=10)
    qt = statistics.quantiles(tot, n=10)
    print('take1 --measure (%s, %d frames): engine %d cycles a frame (median), model %d; '
          'engine/model median %.2f (p10 %.2f, p90 %.2f); with the hold, player/target '
          'median %.3f (p10 %.3f, p90 %.3f)'
          % (cpu, len(data), statistics.median(owns), statistics.median(models),
             statistics.median(eng), qe[0], qe[-1], statistics.median(tot), qt[0], qt[-1]))
    return statistics.median(tot)


def micro_rows():
    """Rows made of short codes, as line art is (take1 --micro): name, codes."""
    import random as rnd
    rng = rnd.Random(77)
    rows = {}
    # 1-7-dot fills and skips, alternating
    r = bytearray()
    for k in range(16):
        n = 1 + k % 7
        r += bytes([n if n < 7 else 0x08, rng.randrange(256)])
        r.append(0x80 | (k * 3) % 7)
    rows['fills 1-7, skips 0-6'] = bytes(r) + b'\x00'
    # single literal bytes at every bit phase (a fill first sets the phase)
    r = bytearray()
    for k in range(14):
        r += bytes([1 + k % 6, rng.randrange(256), 0xD7, rng.randrange(256)])
    rows['literals at every phase'] = bytes(r) + b'\x07'
    # line art: 1-6-dot fills and skips, single literals, at random
    r = bytearray()
    for k in range(24):
        x = rng.random()
        if x < 0.45:
            r += bytes([rng.randrange(1, 7), rng.randrange(256)])
        elif x < 0.8:
            r.append(0x80 | rng.randrange(0, 6))
        else:
            r += bytes([0xD7, rng.randrange(256)])
    rows['line art (mixed)'] = bytes(r) + b'\x00'
    rows['end only'] = b'\x07'
    return rows


def micro():
    """Cycles per row of short codes against the spec's model (140 a code,
    55 a byte written), one 100-row sprite a frame; and per snapshot."""
    import statistics
    with tempfile.TemporaryDirectory(prefix='a2fc-take1u-') as tmp:
        sim = Sim('6502', Path(tmp), measure=True)

        def run(row, h=100, objects=1):
            snap = bytes([h, 250, 0, 0, 0, 0, 0]) + row * h
            files = {b'AC.U': ref.make_actor([snap])}
            els = b''.join(ref.obj(1, 284 + 3 * k, 200 + k, end=(k == objects - 1))
                           for k in range(objects))
            files[b'SN.U'] = ref.make_scene(1, [(1, 'U')], [els] * 6)
            d = intervals(sim, [(ref.make_movie([('U', '< BLACK >', 1, 1)]), files)])
            return statistics.median(x['own'] for x in d), d[0]['work']

        rows = micro_rows()
        base, wb = run(rows['end only'])
        for name, row in rows.items():
            if name == 'end only':
                continue
            own, w = run(row)
            per = (own - base) / 100
            model = (ref.model_cycles(w) - ref.model_cycles(wb)) / 100
            codes = (w['codes'] - wb['codes']) / 100
            print('take1 --micro %-26s %3d codes a row: %6.0f cycles a row, model %6.0f '
                  '(ratio %.2f; %.0f a code against %.0f)'
                  % (name, codes, per, model, per / model, per / codes, model / codes))
        one, w1 = run(rows['end only'], h=1, objects=1)
        six, w6 = run(rows['end only'], h=1, objects=6)
        print('take1 --micro a snapshot (1 row, $07): %.0f cycles, model %.0f'
              % ((six - one) / 5, (ref.model_cycles(w6) - ref.model_cycles(w1)) / 5))


DRIVER = 60             # the driver's own time a frame (t1_show, t1_wait's set-up), cycles
WAIT_OVERHEAD = 40      # take1.s's wait: set-up and exit around its 256-cycle units


if __name__ == '__main__':
    if '--measure' in sys.argv:
        measure()
        sys.exit(0)
    if '--micro' in sys.argv:
        micro()
        sys.exit(0)
    if '--calibrate' in sys.argv:
        calibrate(write='--write' in sys.argv)
        sys.exit(0)
    unittest.main(verbosity=1)
