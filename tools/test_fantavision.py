#!/usr/bin/env python3
"""Run the Fantavision engine (src/fanta/engine.s) under sim65 and compare
every frame it shows with tools/fantavision_ref.py, byte for byte.

The harness links the real engine with a small C program: it hands over a
movie, calls fv_check, fv_begin, fv_first and fv_next, and writes out each
page shown with the frame's counters, the original-time target and wait of
fv_timing, and the cycles spent (sim65's cycle counter, cc65 master). At
the end it writes $0200-$7FFF and the movie: memory outside the engine's
own variables and the three 8 KB buffers must be untouched, a refused
movie must leave the buffers untouched too, and the movie is never written.

    test_fantavision.py               the tests, on the 6502 and the 65C02
    test_fantavision.py --measure     cycles per frame on the synthetic set
    test_fantavision.py --calibrate   least-squares fit of the engine's own
                                      cost (OWN_* in engine.s and the ref)

What the SYS program adds -- loading, keys, page flips, the return to
A2 File Cmd -- is checked by bench/fantavision.py in POM2.
"""
import os
import re
import shutil
import statistics
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import fantavision_ref as ref  # noqa: E402

HEAD = Path(os.environ.get('CC65_HEAD', str(Path.home() / 'opt/cc65-head')))


def engine_constants():
    """OWN_* of engine.s: the engine's own-cost estimate."""
    text = (ROOT / 'src/fanta/engine.s').read_text()
    got = {m[1].lower(): int(m[2]) for m in re.finditer(r'^OWN_(\w+)\s*=\s*(\d+)', text, re.M)}
    return got.pop('base'), got


OWN_BASE, OWN = engine_constants()

GLUE = r'''
        .import fv_check, fv_begin, fv_first, fv_next, fv_timing
        .import fv_movie, fv_len, fv_shown, fv_done, fv_frames, fv_end
        .import fv_counts, fv_orig, fv_own, fv_wait, fv_count
        .export _fv_check, _fv_begin, _fv_first, _fv_next, _fv_timing
        .export _fv_movie := fv_movie, _fv_len := fv_len, _fv_shown := fv_shown
        .export _fv_done := fv_done, _fv_frames := fv_frames, _fv_counts := fv_counts
        .export _fv_orig := fv_orig, _fv_own := fv_own, _fv_wait := fv_wait
        .export _fv_count := fv_count, _fv_end := fv_end
        .import fv_bdrop
        .export _fv_bdrop := fv_bdrop
_fv_check:
        jsr     fv_check
        ldx     #0
        rts
_fv_next:
        jsr     fv_next
        ldx     #0
        rts
_fv_begin = fv_begin
_fv_first = fv_first
_fv_timing = fv_timing
'''

HARNESS = r'''
#include <fcntl.h>
#include <unistd.h>
#include <string.h>
#include <stdlib.h>
#include <sim65.h>
extern unsigned char* fv_movie;
extern unsigned int fv_len;
extern unsigned char fv_shown, fv_done, fv_frames;
extern unsigned char fv_counts[45];
extern unsigned long fv_orig, fv_own, fv_wait;
extern unsigned char fv_count;
extern unsigned int fv_end;
extern unsigned char fv_bdrop;
unsigned char fv_check(void);
void fv_begin(void);
void fv_first(void);
unsigned char fv_next(void);
void fv_timing(void);
static unsigned char movie[9400];
static unsigned long c0, c1, cb, ct;
static unsigned long cyc(void)
{
    peripherals.counter.latch = 0;
    return peripherals.counter.value32[0];
}
static void out(const void* p, unsigned n)
{
    if (write(1, p, n) != (int)n) exit(20);
}
int main(int, char** argv)
{
    int fd, n;
    unsigned limit = atoi(argv[1]), f;
    unsigned char r;
    unsigned cfrom = argv[2][0] == 'K' ? atoi(argv[2] + 1) : 0;  /* Tab at frame cfrom */
    fv_count = argv[2][0] == '1';           /* original speed: counts */
    memset((void*)0x0200, 0x5A, 0x1E00);
    memset((void*)0x2000, 0xEE, 0x6000);
    fd = open("movie.bin", O_RDONLY);
    if (fd < 0) return 10;
    n = read(fd, movie, sizeof movie);
    close(fd);
    if (n < 0) return 11;
    fv_movie = movie;
    fv_len = n;
    c0 = cyc(); c1 = cyc(); cb = c1 - c0;       /* the measuring's own cost */
    out(&cb, 4);
    r = fv_check();
    out(&r, 1);
    out(&fv_frames, 1);
    out(&fv_end, 2);
    if (r == 0) {
        fd = open("backdrop.bin", O_RDONLY);   /* the caller's backdrop */
        if (fd >= 0) {
            memset((void*)0x6000, 0, 0x2000);
            if (read(fd, (void*)0x6000, 0x2000) < 0) return 12;
            close(fd);
            fv_bdrop = 1;
        }
        c0 = cyc(); fv_begin(); c1 = cyc(); cb = c1 - c0;
        out(&cb, 4);
        for (f = 0; f < limit; ++f) {
            if (cfrom) fv_count = f >= cfrom;
            c0 = cyc();
            if (f == 0) fv_first();
            else if (fv_next()) break;
            c1 = cyc(); cb = c1 - c0;
            c0 = cyc(); fv_timing(); c1 = cyc(); ct = c1 - c0;
            out(&fv_shown, 1);
            out(fv_counts, 45);
            out(&fv_orig, 4); out(&fv_own, 4); out(&fv_wait, 4);
            out(&cb, 4); out(&ct, 4);
            out((void*)(fv_shown << 8), 0x2000);
        }
    }
    r = 0xFF;
    out(&r, 1);
    out(&fv_done, 1);
    out((void*)0x0200, 0x7E00);
    out(movie, n);
    return 0;
}
'''

# fv_counts: what the original-time formula uses (checked against the
# reference), then what the engine's own-cost estimate uses (engine only).
COUNTERS = ['spans', 'bytes', 'espans', 'ebytes', 'edges']
OWN_COUNTERS = ['spans', 'bytes', 'erows', 'ebytes', 'edges', 'ipoints', 'objects',
                'lrows', 'frows', 'astep']
FRAME = 1 + 45 + 12 + 8 + 0x2000


class Sim:
    """The harness built for one processor."""

    def __init__(self, cpu, workdir):
        self.dir = workdir
        env = dict(os.environ, CC65_HOME=str(HEAD / 'share/cc65'))
        target = 'sim65c02' if cpu == '65c02' else 'sim6502'
        cfg = (HEAD / f'share/cc65/cfg/{target}.cfg').read_text()
        cfg, k = re.subn(r'start = \$0200, size = \$FFC0 - \$0200 - __STACKSIZE__',
                         'start = $8000, size = $FFC0 - $8000 - __STACKSIZE__', cfg)
        assert k == 1, 'sim65 config changed'
        cfg, k = re.subn(r'(\n\s*RODATA:[^\n]*\n)', r'\1    TABLES:   load = MAIN,   type = ro;\n    FCOLD:    load = MAIN,   type = ro;\n', cfg)
        assert k == 1, 'sim65 config: no RODATA line'
        cfg, k = re.subn(r'(\n\s*BSS:[^\n]*\n)', r'\1    EBSS:     load = MAIN,   type = bss;\n', cfg)
        assert k == 1, 'sim65 config: no BSS line'
        (workdir / f'{cpu}.cfg').write_text(cfg)
        (workdir / 'harness.c').write_text(HARNESS)
        (workdir / 'glue.s').write_text(GLUE)
        self.exe = workdir / f'harness-{cpu}'
        subprocess.run([str(HEAD / 'bin/cl65'), '-t', target, '-C', str(workdir / f'{cpu}.cfg'),
                        '-O', '-o', str(self.exe), str(workdir / 'harness.c'),
                        str(workdir / 'glue.s'), str(ROOT / 'src/fanta/engine.s')],
                       check=True, cwd=workdir, env=env)
        self.sim = str(HEAD / 'bin/sim65')

    def run(self, movie, limit=20, count=True, backdrop=None):
        (self.dir / 'movie.bin').write_bytes(movie)
        bd = self.dir / 'backdrop.bin'
        if backdrop is None:
            bd.unlink(missing_ok=True)
        else:
            bd.write_bytes(backdrop)
        # -x: a hang shows as a failure, not as a stuck test
        p = subprocess.run([self.sim, '-x', '1000000000', str(self.exe), str(limit),
                            count if isinstance(count, str) else '1' if count else '0'],
                           cwd=self.dir, capture_output=True, timeout=900)
        if p.returncode != 0:
            raise AssertionError('sim65 exit %d: %s' % (p.returncode, p.stderr[-300:]))
        o = p.stdout
        res = {'overhead': struct.unpack_from('<I', o, 0)[0], 'code': o[4], 'frames': [],
               'nframes': o[5], 'end': struct.unpack_from('<H', o, 6)[0]}
        pos = 8
        if res['code'] == 0:
            res['begin'] = struct.unpack_from('<I', o, pos)[0]
            pos += 4
            while o[pos] != 0xFF:
                shown = o[pos]
                c = {}
                names = COUNTERS + ['own_' + k for k in OWN_COUNTERS]
                for i, name in enumerate(names):
                    b = o[pos + 1 + 3 * i:pos + 4 + 3 * i]
                    c[name] = b[0] | b[1] << 8 | b[2] << 16
                orig, own, wait, cyc, tcyc = struct.unpack_from('<IIIII', o, pos + 46)
                c.update(orig=orig, own=own, wait=wait)
                page = o[pos + 66:pos + 66 + 0x2000]
                res['frames'].append((shown, c, cyc - res['overhead'],
                                      tcyc - res['overhead'], page))
                pos += FRAME
        res['done'] = o[pos + 1]
        mem = o[pos + 2:pos + 2 + 0x7E00]
        res['low'] = mem[:0x1E00]
        res['bg'] = mem[0x5E00:0x7E00]
        res['p1'] = mem[0x1E00:0x3E00]
        res['p2'] = mem[0x3E00:0x5E00]
        res['movie'] = o[pos + 2 + 0x7E00:]
        return res


def ref_frames(movie, limit, backdrop=None):
    player = ref.Player(movie, backdrop)
    frames = list(player.play(limit=limit))
    return player, frames


class Fantavision(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (HEAD / 'bin/sim65').exists():
            raise unittest.SkipTest('cc65 master (CC65_HEAD) is needed for sim65 counters')
        cls.tmp = tempfile.TemporaryDirectory(prefix='a2fc-fanta-')
        cls.sims = {}
        for cpu in ('6502', '65c02'):
            d = Path(cls.tmp.name) / cpu
            d.mkdir()
            cls.sims[cpu] = Sim(cpu, d)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def compare(self, cpu, movie, limit=16, label='', count=None, backdrop=None):
        """Both speeds by default: the original (counting, generic paths)
        and the accelerated (fast paths); the same pages either way."""
        if count is None:
            self.compare(cpu, movie, limit, label + ' (accelerated)', False, backdrop)
            count = True
        res = self.sims[cpu].run(movie, limit, count, backdrop)
        self.assertEqual(res['code'], 0, label)
        _, starts, end = ref.scan(movie)
        self.assertEqual((res['nframes'], res['end']), (len(starts), end), label + ': the frames kept')
        player, frames = ref_frames(movie, limit, backdrop)
        self.assertEqual(len(res['frames']), len(frames), label)
        for i, ((shown, c, _, _, page), (rshown, rpage, rc)) in enumerate(zip(res['frames'], frames)):
            where = '%s frame %d' % (label, i)
            self.assertEqual(shown, 0x20 if rshown == 1 else 0x40, where)
            for k in (COUNTERS + ['orig']) if count else ():
                self.assertEqual(c[k], rc[k], '%s: %s' % (where, k))
            if not count:
                pass
            else:
                self.assertEqual(c['own'], OWN_BASE + sum(OWN[k] * c['own_' + k] for k in OWN_COUNTERS),
                                 where + ': own estimate')
                self.assertEqual(c['wait'], max(0, c['orig'] - c['own']), where + ': wait')
            if page != rpage:
                diff = [a for a in range(0x2000) if page[a] != rpage[a]]
                self.fail('%s: %d bytes differ, first at $%04X: %02X, ref %02X' %
                          (where, len(diff), diff[0], page[diff[0]], rpage[diff[0]]))
        self.assertEqual(res['bg'], bytes(player.bg), label + ' background')
        self.assertEqual(res['p1'], bytes(player.pages[1]), label + ' page 1')
        self.assertEqual(res['p2'], bytes(player.pages[2]), label + ' page 2')
        self.assertEqual(res['low'], b'\x5A' * 0x1E00, label + ' memory below $2000')
        self.assertEqual(res['movie'], movie, label + ' movie written')
        return res

    def test_synthetic(self):
        for cpu, seeds in (('6502', range(80)), ('65c02', range(0, 80, 4))):
            for seed in seeds:
                self.compare(cpu, ref.synthetic(seed), 14, '%s seed %d' % (cpu, seed))
        for seed in range(6):
            self.compare('6502', ref.shaped_movie(seed), 14, 'shaped %d' % seed)
        print('PASS fantavision: synthetic movies match the reference (80 on 6502, 20 on 65C02)')

    def test_accelerated_same_picture(self):
        """Without counting (the accelerated speed) the pages are the same."""
        for seed in range(0, 80, 5):
            self.compare('6502', ref.synthetic(seed), 14, 'uncounted seed %d' % seed, count=False)
        for kind in range(3):
            self.compare('65c02', ref.demo_movie(kind, big=True, n=20), 12, 'uncounted kind %d' % kind,
                         count=False)
        print('PASS fantavision: the accelerated speed (no counting) draws the same frames')

    def test_kinds(self):
        for cpu in ('6502', '65c02'):
            for kind in range(4):
                for anim in (0, 1, 2, 3):
                    for big in (False, True):
                        mv = ref.demo_movie(kind, anim=anim, big=big, n=32 if big else 5)
                        self.compare(cpu, mv, 40, '%s kind %d anim %d big %s' % (cpu, kind, anim, big))
            for kind, modes in ((0, range(16)), (1, range(16)), (2, range(16))):
                for mode in modes:
                    mv = ref.demo_movie(kind, mode=mode, speed=2, n=7, seed=mode)
                    self.compare(cpu, mv, 12, '%s kind %d mode %d' % (cpu, kind, mode))
        print('PASS fantavision: every kind, mode and animation matches, both processors')

    def test_edges_of_the_screen(self):
        rng = __import__('random').Random(5)
        for cpu in ('6502', '65c02'):
            for i in range(12):
                h = ref.header(rng, speed=rng.choice([1, 2, 3]), count=1,
                               clip=ref.random_clip(rng) if i % 2 else (0, 255, 0, 255))
                body = b''
                for f in range(3):
                    for o in range(8):
                        n = rng.randrange(1, 33)
                        xs = [rng.choice([0, 1, 2, 253, 254, 255, rng.randrange(256)]) for _ in range(n)]
                        ys = [rng.choice([0, 1, 190, 191, 192, 250, 255, rng.randrange(256)]) for _ in range(n)]
                        body += ref.record(o % 4, rng.choice([1, 9, 11, 2, 3]), rng.randrange(256),
                                           rng.randrange(4), xs, ys)
                mv = bytes(h) + body + b'\x00'
                self.compare(cpu, mv, 10, '%s corners %d' % (cpu, i))
        print('PASS fantavision: coordinates at the screen edges and odd clip windows')

    def test_play_count_and_end(self):
        for cpu in ('6502',):
            for count, frames, speed in ((1, 3, 2), (2, 2, 3), (3, 1, 1), (1, 1, 4), (0x21, 2, 1)):
                mv = ref.synthetic(100 + count, frames=frames, speed=speed, count=count)
                nf = len(ref.parse(mv))
                total = 1 if nf == 1 else 1 + ((count & 15) * nf - 1) * ref.steps(speed)
                res = self.compare(cpu, mv, total + 5, 'count %d' % count)
                self.assertEqual(len(res['frames']), total)
                self.assertEqual(res['done'], 1)
            mv = ref.synthetic(7, frames=2, speed=1, count=0)
            res = self.compare(cpu, mv, 9, 'forever')
            self.assertEqual(len(res['frames']), 9)
            self.assertEqual(res['done'], 0)
        print('PASS fantavision: play counts, single frames and the end of a counted movie')

    def test_original_timing(self):
        """fv_timing's target is the documented formula on the frame's counts."""
        mv = ref.demo_movie(2, n=6, speed=2, frames=3)
        res = self.sims['6502'].run(mv, 6)
        _, frames = ref_frames(mv, 6)
        for (_, c, _, _, _), (_, _, rc) in zip(res['frames'], frames):
            formula = (6300 + 230 * rc['spans'] + 20 * rc['bytes'] + 270 * rc['espans'] +
                       45 * rc['ebytes'] + 1100 * rc['edges'])
            self.assertEqual(c['orig'], formula)
            self.assertEqual(c['wait'], max(0, formula - c['own']))
        self.assertGreater(frames[2][2]['espans'], 0)
        print('PASS fantavision: the original-time target equals the formula of the reference')

    def test_backdrop(self):
        """A backdrop read into the background copy: the pages start from it,
        whole; erasing restores it; Background-mode objects draw into it."""
        rng = __import__('random').Random(11)
        picture = bytes(rng.randrange(256) for _ in range(8192))
        short = picture[:8184]
        for cpu in ('6502', '65c02'):
            for seed in (1, 4, 9):
                self.compare(cpu, ref.synthetic(seed), 12, '%s backdrop seed %d' % (cpu, seed),
                             backdrop=picture)
            for anim in (0, 2):
                mv = ref.demo_movie(2, anim=anim, n=6, speed=2)
                self.compare(cpu, mv, 12, '%s backdrop anim %d' % (cpu, anim), backdrop=picture)
            res = self.compare(cpu, ref.shaped_movie(2), 10, '%s short backdrop' % cpu, backdrop=short)
        # The picture shows whole, outside the clip window too; the 8,184-byte
        # save leaves the last 8 bytes (screen holes) zero.
        h = ref.header(rng, speed=1, count=1, clip=(100, 120, 90, 100))
        still = bytes(h) + ref.record(0, 2, 0x33, 0, [110], [95]) + b'\x01' * 7 + b'\x00' * 120
        res = self.compare('6502', still, 2, 'backdrop, small window', backdrop=picture)
        page = res['frames'][0][4]
        self.assertEqual(page[:0x1000], picture[:0x1000])
        res = self.compare('6502', still, 2, 'short backdrop, small window', backdrop=short)
        self.assertEqual(res['bg'][0x1FF8:], bytes(8))
        self.assertEqual(res['bg'][:0x1FF8], short)
        print('PASS fantavision: backdrops (8,192 and 8,184 bytes) as the reference, both processors')

    def test_tab_to_original(self):
        """Tab mid-movie: the first counted frame takes its own normal
        objects for what the frame before left to erase; then exact."""
        for cpu in ('6502', '65c02'):
            for seed, at in ((0, 1), (1, 4), (2, 4), (0, 6)):
                mv = ref.synthetic(seed, frames=4, speed=2, count=0)
                limit = at + 5
                res = self.sims[cpu].run(mv, limit, 'K%d' % at)
                frames = list(ref.Player(mv).play(limit=limit, count_from=at))
                exact = list(ref.Player(mv).play(limit=limit))
                self.assertEqual(len(res['frames']), len(frames))
                for i in range(at, limit):
                    c, rc = res['frames'][i][1], frames[i][2]
                    for k in COUNTERS + ['orig']:
                        self.assertEqual(c[k], rc[k], (cpu, seed, i, k))
                    self.assertEqual(res['frames'][i][4], frames[i][1])
                    if i > at:
                        self.assertEqual(rc['orig'], exact[i][2]['orig'])
                # not held short: something to erase is counted, as it
                # would be without Tab
                self.assertGreater(frames[at][2]['espans'], 0, (seed, at))
                self.assertGreater(exact[at][2]['espans'], 0, (seed, at))
        print('PASS fantavision: after Tab, the first counted frame is held by an estimate, then exact')

    def refused(self, movie, why, cpus=('6502', '65c02')):
        expect = ref.CODES[ref.check(movie)]
        self.assertEqual(ref.check(movie), why)
        for cpu in cpus:
            res = self.sims[cpu].run(movie, 3)
            self.assertEqual(res['code'], expect, (why, cpu))
            self.assertEqual(res['frames'], [])
            self.assertEqual(res['low'], b'\x5A' * 0x1E00, why)
            for k in ('p1', 'p2', 'bg'):
                self.assertEqual(res[k], b'\xEE' * 0x2000, (why, k))
            self.assertEqual(res['movie'], movie)

    def test_refused(self):
        rng = __import__('random').Random(9)
        h = bytes(ref.header(rng, clip=(5, 250, 12, 159)))
        good = ref.synthetic(3, frames=3)
        cases = []
        cases.append((good[:512], 'size'))
        cases.append((good + bytes(9217 - len(good)), 'size'))
        cases.append((b'\x01' * 9300, 'size'))
        for i, v in ((3, 5), (5, 0)):
            b = bytearray(good)
            b[i] = v
            cases.append((bytes(b), 'header'))
        b = bytearray(good)
        b[8], b[9] = 200, 100
        cases.append((bytes(b), 'clip'))
        b = bytearray(good)
        b[10], b[11] = 150, 149
        cases.append((bytes(b), 'clip'))
        cases.append((h + b'\x00' * 200, 'empty'))                        # 0 frames
        cases.append((h + b'\x01' * 7 + b'\x00' + b'\x01' * 200, 'empty'))  # first frame damaged
        cases.append((h + b'\x01' * 8 * 128 + b'\x00' * 10, 'frames'))   # 128 frames
        for bad in (2, 3, 5, 69, 70, 71, 72, 254, 255):
            rec = bytes([bad, 2, 0x33, 0]) + bytes(max(0, bad - 4))
            cases.append((h + rec + b'\x01' * 7 + b'\x00' * 100, 'empty'))
        for movie, why in cases:
            self.refused(movie, why)
        print('PASS fantavision: every refusal happens before anything is drawn, both processors')

    def cut(self, movie, whole, label, limit=None, cpus=('6502', '65c02')):
        """A damaged tail: the frames before it play, exactly."""
        why, starts, _ = ref.scan(movie)
        self.assertIsNone(why, label)
        self.assertEqual(len(starts), whole, label)
        for cpu in cpus:
            self.compare(cpu, movie, limit or 3 * whole + 4, '%s %s' % (cpu, label))

    def test_cut(self):
        rng = __import__('random').Random(10)
        h = bytes(ref.header(rng, speed=2, count=1, clip=(5, 250, 12, 159)))
        f1 = ref.record(2, 1, 0x2A, 0, [40, 200, 120], [30, 40, 150]) + b'\x01' * 7
        f2 = ref.record(2, 1, 0x2A, 0, [60, 180, 100], [50, 30, 130]) + b'\x01' * 7
        # a 0 inside frame 2
        self.cut(h + f1 + f1[:12] + b'\x00' * 300, 1, '0 inside frame 2')
        self.cut(h + f1 + f2 + ref.record(0, 3, 0x33, 0, [9], [9]) + b'\x01\x00' + b'\x01' * 200, 2,
                 '0 inside frame 3')
        # every bad length, in frame 3
        for bad in (2, 3, 5, 69, 70, 71, 72, 254, 255):
            rec = bytes([bad, 2, 0x33, 0]) + bytes(max(0, bad - 4))
            self.cut(h + f1 + f2 + b'\x01' * 3 + rec + b'\x01' * 4 + b'\x00' * 60, 2,
                     'length %d in frame 3' % bad, cpus=('6502',))
        # a 68-point record in frame 10
        body = b''.join(ref.record(1, 11, 0x55, 0, [20 + 10 * k + f, 200 - 5 * f], [30 + f, 150 - 8 * k])
                        + b'\x01' * 7 for f, k in zip(range(9), range(9)))
        pts = list(range(10, 146, 2))
        big = bytes([4 + 2 * 68, 2, 0x33, 0]) + bytes(pts) + bytes(p % 190 for p in pts)
        self.cut(h + body + big + b'\x01' * 7 + b'\x00', 9, '68 points in frame 10', limit=40)
        # the end of the file inside frame 5, a record past the end
        self.cut(h + (f1 + f2) * 3 + f1[:10], 6, 'end of file inside frame 7')
        self.cut(h + (f1 + f2) * 3 + bytes([30]) + bytes(10), 6, 'record past the end')
        # an odd length in frame 41 of a 9,216-byte movie (a save cut short)
        frames = []
        for f in range(40):
            n = 30
            xs = [(17 * f + 7 * i) % 240 + 8 for i in range(n)]
            ys = [(11 * f + 5 * i) % 140 + 14 for i in range(n)]
            frames.append(ref.record(f % 3, 11 if f % 3 == 1 else 1, 0x2A + f, 0, xs, ys) +
                          ref.record(0, 2, 0x33, 0, xs[:8], ys[:8]) + b'\x01' * 6)
        body = h + b''.join(frames)
        tail = bytes([2 * 17 + 1]) + bytes(9216)
        movie = (body + tail)[:9216]
        self.assertEqual(len(movie), 9216)
        self.cut(movie, 40, 'odd length in frame 41 of 9,216 bytes', limit=20)
        # the 128th frame damaged: 127 kept
        self.cut(h + b'\x01' * 8 * 127 + b'\x01' * 7 + b'\x00', 127, '128th frame cut', limit=5)
        # ends exactly at the end of the file
        self.cut(h + b'\x01' * 8 * 13, 13, 'end at the end of the file', limit=5)
        # A random damage campaign: flips and cuts, refused or played the same.
        for i in range(60):
            b = bytearray(ref.synthetic(200 + i, frames=3))
            for _ in range(rng.randrange(1, 4)):
                b[rng.randrange(ref.HDR, len(b))] = rng.randrange(256)
            if rng.random() < 0.3:
                b = b[:rng.randrange(513, len(b) + 1)]
            b = bytes(b)
            if ref.check(b) is None:
                self.compare('6502', b, 8, 'damaged %d' % i)
            else:
                self.refused(b, ref.check(b), cpus=('6502',))
        print('PASS fantavision: a damaged tail is cut, the whole frames before it play, both processors')


# -- fload: the command, the movie and the backdrop, with a fake MLI ------------

FGLUE = r"""
        .import fload, _fake_mli, pusha, fv_len, fv_bdrop
        .import cmdbuf, ocl, cdl, nextn, mode, delay, slide
        .importzp ptr1
        .export _run_fload, path0, _path0 := path0
        .export _fv_len := fv_len, _fv_bdrop := fv_bdrop
        .export _cmdbuf := cmdbuf, _ocl := ocl, _cdl := cdl, _nextn := nextn
        .export _mode := mode, _delay := delay, _slide := slide
        .bss
path0:  .res    65
mcmd:   .res    1
mpl:    .res    1
mph:    .res    1
        .code
; unsigned run_fload(void): 0, or the message's address
_run_fload:
        jsr     fload
        bcs     :+
        lda     #0
        tax
:       rts
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

FHARNESS = r"""
#include <fcntl.h>
#include <unistd.h>
#include <string.h>
#include <stdlib.h>
extern unsigned char path0[65];
extern unsigned int fv_len;
extern unsigned char fv_bdrop;
extern unsigned char cmdbuf[67], ocl, cdl, nextn[16], mode, delay, slide;
unsigned int run_fload(void);
extern unsigned char _MLISTUB_LOAD__[], _MLISTUB_SIZE__[];
static char fault = '-', fpath[70], cur[70], host[80];
static int fd = -1;
static unsigned int size, reads;
static unsigned char scratch[256];
static void hostname(const unsigned char* p)
{
    unsigned char i, n = p[0];
    host[0] = 'f';
    for (i = 0; i < n; ++i) host[i + 1] = p[i + 1] == '/' ? '_' : p[i + 1];
    host[n + 1] = 0;
    memcpy(cur, p + 1, n);
    cur[n] = 0;
}
static unsigned char faulty(char kind)
{
    return fault == kind && strcmp(fpath, cur) == 0;
}
unsigned char __fastcall__ fake_mli(unsigned char cmd, unsigned char* p)
{
    int n;
    unsigned int req;
    unsigned char* buf;
    switch (cmd) {
    case 0xC8:                                  /* OPEN */
        hostname(*(unsigned char**)(p + 1));
        if (faulty('O')) return 0x27;
        fd = open(host, O_RDONLY);
        if (fd < 0) return 0x46;
        size = 0;
        while ((n = read(fd, scratch, sizeof scratch)) > 0) size += n;
        close(fd);
        fd = open(host, O_RDONLY);
        p[5] = 1;
        return 0;
    case 0xD1:                                  /* GET_EOF */
        if (faulty('E')) return 0x27;
        p[2] = size & 255; p[3] = size >> 8; p[4] = 0;
        return 0;
    case 0xCA:                                  /* READ */
        buf = *(unsigned char**)(p + 2);
        req = p[4] | (p[5] << 8);
        if (faulty('R')) {                      /* part of it, then an error */
            n = read(fd, buf, req / 2);
            p[6] = n & 255; p[7] = n >> 8;
            return 0x27;
        }
        if (faulty('S')) --req;                 /* a short read, no error */
        if (faulty('T')) req -= 256;            /* 256 bytes short */
        if (faulty('2') && ++reads == 2) return 0x27;   /* the second READ fails */
        n = read(fd, buf, req);
        if (n < 0) return 0x27;
        if (!n && req) return 0x4C;             /* the end of the file */
        p[6] = n & 255; p[7] = n >> 8;
        return 0;
    case 0xCC:                                  /* CLOSE */
        if (fd >= 0) close(fd);
        fd = -1;
        return faulty('C') ? 0x27 : 0;
    }
    return 0x01;
}
int main(int, char** argv)
{
    unsigned int r;
    unsigned char n = strlen(argv[1]);
    if (argv[1][0] == '.') n = 0;               /* "." : an empty command */
    memcpy((void*)0xBF00, _MLISTUB_LOAD__, (unsigned)_MLISTUB_SIZE__);   /* the fake MLI */
    memset((void*)0x0200, 0x5A, 0x1E00);
    memset((void*)0x2000, 0xEE, 0x6000);
    path0[0] = n;
    memcpy(path0 + 1, argv[1], n);
    if (argv[2][0] != '-') { fault = argv[2][0]; strcpy(fpath, argv[2] + 1); }
    r = run_fload();
    write(1, &r, 2);
    write(1, r ? (void*)r : (void*)"", r ? 48 : 0);
    write(1, &fv_len, 2);
    write(1, &fv_bdrop, 1);
    write(1, (void*)0x0200, 0x7E00);
    write(1, cmdbuf, 67);
    write(1, &ocl, 1);
    write(1, &cdl, 1);
    write(1, nextn, 16);
    write(1, &mode, 1);
    write(1, &delay, 1);
    write(1, &slide, 1);
    return 0;
}
"""


class FLoadSim:
    """fload.s + the engine + a fake MLI, for one processor."""

    def __init__(self, cpu, workdir):
        self.dir = workdir
        env = dict(os.environ, CC65_HOME=str(HEAD / 'share/cc65'))
        target = 'sim65c02' if cpu == '65c02' else 'sim6502'
        cfg = (HEAD / f'share/cc65/cfg/{target}.cfg').read_text()
        cfg, k = re.subn(r'start = \$0200, size = \$FFC0 - \$0200 - __STACKSIZE__',
                         'start = $8000, size = $BF00 - $8000 - __STACKSIZE__', cfg)
        assert k == 1
        cfg, k = re.subn(r'(\n\s*RODATA:[^\n]*\n)',
                         r'\1    TABLES:   load = MAIN,   type = ro;\n    FCOLD:    load = MAIN,   type = ro;\n'
                         r'    LOADER:   load = MAIN,   type = rw;\n'
                         r'    MLISTUB:  load = MAIN, run = STUB, type = rw, define = yes;\n', cfg)
        assert k == 1
        cfg, k = re.subn(r'(\n\s*BSS:[^\n]*\n)', r'\1    EBSS:     load = HIGH,   type = bss;\n'
                                                   r'    CMDBUF:   load = HIGH,   type = bss;\n', cfg)
        assert k == 1
        # $C000-$FFBF: plain memory under sim65 (its peripherals are above)
        cfg, k = re.subn(r'(\n\s*MAIN:[^\n]*\n)', r'\1    STUB:   file = "", start = $BF00, size = $0100;\n'
                                                     r'    HIGH:   file = "", start = $C000, size = $3F00;\n', cfg)
        assert k == 1
        (workdir / f'{cpu}.cfg').write_text(cfg)
        (workdir / 'fharness.c').write_text(FHARNESS)
        (workdir / 'fglue.s').write_text(FGLUE)
        self.exe = workdir / f'fload-{cpu}'
        subprocess.run([str(HEAD / 'bin/cl65'), '-t', target, '-C', str(workdir / f'{cpu}.cfg'),
                        '-O', '--asm-define', 'MOVIE_AT=$2000', '-Wl', '-D,__STACKSIZE__=0x0200',
                        '-o', str(self.exe),
                        str(workdir / 'fharness.c'), str(workdir / 'fglue.s'),
                        str(ROOT / 'src/fanta/fload.s'), str(ROOT / 'src/fanta/engine.s')],
                       check=True, cwd=workdir, env=env)

    def run(self, command, files, fault='-'):
        for old in self.dir.glob('f_*'):
            old.unlink()
        for path, data in files.items():
            (self.dir / ('f' + path.replace('/', '_'))).write_bytes(data)
        p = subprocess.run([str(HEAD / 'bin/sim65'), '-x', '100000000', str(self.exe),
                            command or '.', fault], cwd=self.dir, capture_output=True, timeout=300)
        if p.returncode != 0:
            raise AssertionError('sim65 exit %d: %s' % (p.returncode, p.stderr[-300:]))
        o = p.stdout
        r = struct.unpack_from('<H', o, 0)[0]
        pos = 2
        msg = None
        if r:
            msg = o[pos:pos + 48].split(b'\0')[0].decode()
            pos += 48
        length, bdrop = struct.unpack_from('<HB', o, pos)
        mem = o[pos + 3:pos + 3 + 0x7E00]
        pos += 3 + 0x7E00
        cmd = o[pos:pos + 67]
        ocl, cdl = o[pos + 67], o[pos + 68]
        nextn = o[pos + 69:pos + 85]
        mode, delay, slide = o[pos + 85:pos + 88]
        return {'msg': msg, 'len': length, 'bdrop': bdrop, 'low': mem[:0x1E00],
                'movie': mem[0x1E00:0x1E00 + length], 'page2': mem[0x3E00:0x5E00],
                'bg': mem[0x5E00:0x7E00],
                'cmd': cmd[3:3 + ocl].decode('latin-1'), 'ocl': ocl, 'cdl': cdl,
                'next': nextn[1:1 + nextn[0]].decode('latin-1') if nextn[0] else '',
                'mode': mode, 'delay': delay, 'slide': slide}


def prodos_dir(entries, elen=0x27, epb=13, cut=0):
    """A ProDOS directory file as READ returns it: the header, then the
    entries (name, type, aux, eof[, storage]); None is a deleted entry."""
    def entry(name, ftype, aux, eof, storage=1):
        e = bytearray(elen)
        e[0] = storage << 4 | len(name)
        e[1:1 + len(name)] = name.encode()
        e[0x10] = ftype
        e[0x15:0x18] = eof.to_bytes(3, 'little')
        e[0x1F:0x21] = aux.to_bytes(2, 'little')
        return bytes(e)
    header = bytearray(entry('FV', 0, 0, 0, 14))
    header[0x1F], header[0x20] = elen, epb
    slots = [bytes(header)] + [bytes(elen) if e is None else entry(*e) for e in entries]
    blocks = []
    for i in range(0, len(slots), epb):
        b = bytearray(512)
        for j, e in enumerate(slots[i:i + epb]):
            b[4 + j * elen:4 + (j + 1) * elen] = e
        blocks.append(bytes(b))
    data = b''.join(blocks)
    return data[:len(data) - cut]


class FLoad(unittest.TestCase):
    """The command, the movie and the backdrop (fload.s), both processors."""

    @classmethod
    def setUpClass(cls):
        if not (HEAD / 'bin/sim65').exists():
            raise unittest.SkipTest('cc65 master (CC65_HEAD) is needed')
        cls.tmp = tempfile.TemporaryDirectory(prefix='a2fc-fload-')
        cls.sims = {}
        for cpu in ('6502', '65c02'):
            d = Path(cls.tmp.name) / cpu
            d.mkdir()
            cls.sims[cpu] = FLoadSim(cpu, d)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def load(self, command, files, fault='-', msg=None, bdrop=None, cpus=('6502', '65c02'), nxt=None):
        for cpu in cpus:
            res = self.sims[cpu].run(command, files, fault)
            self.assertEqual(res['msg'], msg, (cpu, command, fault))
            self.assertEqual(res['page2'], b'\xEE' * 0x2000, 'page 2 untouched')
            self.assertEqual(res['low'][:0x600], b'\x5A' * 0x600, 'memory below $0800 untouched')
            path = command[2:] if len(command) >= 3 and command[0] in '*+' else command
            self.assertEqual(res['cmd'], path, (cpu, command))
            if nxt is not None:
                self.assertEqual(res['next'], nxt, (cpu, command, fault))
            if msg is None:
                movie = files[path.split(',')[0]]
                self.assertEqual(res['movie'], movie)
                if bdrop is None:
                    self.assertEqual(res['bdrop'], 0, command)
                else:
                    self.assertEqual(res['bdrop'], 1, command)
                    self.assertEqual(res['bg'], bdrop + bytes(8192 - len(bdrop)))
            else:
                self.assertEqual(res['bdrop'], 0)
        return res

    def test_fload(self):
        rng = __import__('random').Random(12)
        movie = ref.synthetic(5, frames=2)
        pic = bytes(rng.randrange(256) for _ in range(8192))
        pic2 = bytes(rng.randrange(256) for _ in range(8192))
        short = pic[:8184]
        M = '/HD/FV/M.PARADIES'
        B = '/HD/FV/PARADIES'
        S = '/HD/FV/STREAM'
        NOBD = 'THE BACKDROP CANNOT BE USED.'
        NOREAD = 'THE MOVIE CANNOT BE READ.'
        # the same-name backdrop
        self.load(M, {M: movie})
        self.load(M, {M: movie, B: pic}, bdrop=pic)
        self.load(M, {M: movie, B: short}, bdrop=short)
        for bad in (8191, 8185, 8193, 5000, 600):           # other sizes: not used
            self.load(M, {M: movie, B: pic2[:bad] if bad <= 8192 else pic2 + b'x'}, cpus=('6502',))
        for fault in 'OERSTC':                                 # unreadable: not used
            self.load(M, {M: movie, B: pic}, fault + B)
        self.load('/HD/FV/PARADIES2', {'/HD/FV/PARADIES2': movie, '/HD/FV/RADIES2': pic})   # no M.
        self.load('/HD/FV/M.', {'/HD/FV/M.': movie})
        # the explicit backdrop
        self.load(M + ',STREAM', {M: movie, S: pic}, bdrop=pic)
        self.load(M + ',STREAM', {M: movie, S: short}, bdrop=short)
        self.load(M + ',STREAM', {M: movie, S: pic2, B: pic}, bdrop=pic2)   # before the same name
        self.load(M + ',STREAM', {M: movie, B: pic}, msg=NOBD)               # missing
        self.load(M + ',STREAM', {M: movie, S: pic[:8000]}, msg=NOBD)        # wrong size
        for fault in 'OERSTC':
            self.load(M + ',STREAM', {M: movie, S: pic}, fault + S, msg=NOBD)
        name15 = 'ABCDEFGHIJKLMNO'
        self.load('/HD/M.X,' + name15, {'/HD/M.X': movie, '/HD/' + name15: pic}, bdrop=pic)
        self.load('/HD/M.X,' + name15 + 'P', {'/HD/M.X': movie, '/HD/' + name15 + 'P': pic},
                  msg=NOBD)                                           # 16 characters
        self.load('/HD/M.X,', {'/HD/M.X': movie, '/HD/X': pic}, msg=NOBD)    # an empty name
        self.load('M.X', {'M.X': movie, 'X': pic}, bdrop=pic)               # no directory
        # the movie first
        self.load('', {}, msg='NO MOVIE WAS GIVEN.')
        self.load(',STREAM', {S: pic}, msg='NO MOVIE WAS GIVEN.')
        self.load(M, {}, msg=NOREAD)
        self.load(M + ',STREAM', {S: pic}, msg=NOREAD)
        for fault in 'OERSTC':
            self.load(M, {M: movie, B: pic}, fault + M, msg=NOREAD)
        self.load(M, {M: movie[:512], B: pic}, msg='NOT A FANTAVISION MOVIE (CHECK 1).')
        bad = bytearray(movie)
        bad[3] = 7
        self.load(M + ',STREAM', {M: bytes(bad), S: pic}, msg='NOT A FANTAVISION MOVIE (CHECK 2).')
        print('PASS fantavision: the command, the movie and its backdrop (fload), both processors')

    def test_scan_next_movie(self):
        movie = ref.synthetic(5, frames=2)
        D = '/HD/FV'
        mv = lambda n: (n, 0x06, 0x8400, len(movie))
        listing = [mv('M.A'), ('PIC', 0x06, 0x2000, 8192), None, mv('M.B'),
                   ('NOTE', 0x04, 0, 600), ('M.D', 0x0F, 0, 512, 13), mv('M.C'),
                   ('M.SMALL', 0x06, 0x8400, 512), ('M.BIG', 0x06, 0x8400, 9217),
                   ('M.AUX', 0x06, 0x8401, 2000), ('M.TXT', 0x04, 0x8400, 2000)]
        files = {D: prodos_dir(listing)}
        for cur, nxt in (('M.A', 'M.B'), ('M.B', 'M.C'), ('M.C', 'M.A'), ('M.GONE', 'M.A')):
            f = dict(files, **{D + '/' + cur: movie})
            res = self.load(D + '/' + cur, f, nxt=nxt)
            self.assertEqual((res['cdl'], res['slide'], res['mode'], res['delay']), (7, 0, 1, 0))
        # The only movie: none other, the slideshow plays it again.
        only = {D: prodos_dir([('PIC', 6, 0x2000, 8192), mv('M.A')]), D + '/M.A': movie}
        self.load(D + '/M.A', only, nxt='')
        # Over several blocks: 40 entries, the next one in the fourth block.
        many = [('F%02d' % i, 4, 0, 100) for i in range(40)]
        many[3], many[38] = mv('M.A'), mv('M.Z')
        big = {D: prodos_dir(many), D + '/M.A': movie}
        self.assertEqual(len(big[D]), 4 * 512)
        self.load(D + '/M.A', big, nxt='M.Z')
        # Any failure but the clean end: no next movie.
        for fault in 'ORC2':
            self.load(D + '/M.A', big, fault + D, nxt='')
        self.load(D + '/M.A', dict(big, **{D: prodos_dir(many, cut=1)}), nxt='')
        self.load(D + '/M.A', dict(big, **{D: prodos_dir(many, elen=0x28, epb=12)}), nxt='')
        # The volume directory, and no directory at all.
        self.load('/HD/M.A', {'/HD': prodos_dir([mv('M.A'), mv('M.B')]), '/HD/M.A': movie}, nxt='M.B')
        self.load('M.A', {'M.A': movie}, nxt='')
        print('PASS fantavision: the next movie from one pass over the directory, both processors')

    def test_scan_backdrop_by_prefix(self):
        rng = __import__('random').Random(13)
        movie = ref.synthetic(5, frames=2)
        pic = bytes(rng.randrange(256) for _ in range(8192))
        pic2 = bytes(rng.randrange(256) for _ in range(8192))
        short = pic2[:8184]
        D = '/HD/FV'
        M = D + '/M.CHECKER'
        mv = ('M.CHECKER', 0x06, 0x8400, len(movie))
        board = ('CHECKERBOARD', 0x06, 0x4000, 8192)
        base = {M: movie, D + '/CHECKERBOARD': pic}
        # M.CHECKER and CHECKERBOARD, as on Fantavision's own disks.
        self.load(M, dict(base, **{D: prodos_dir([mv, board])}), bdrop=pic)
        # NAME itself first, wherever it is; then the first longer name.
        f = dict(base, **{D + '/CHECKER': short,
                          D: prodos_dir([board, mv, ('CHECKER', 6, 0x2000, 8184)])})
        self.load(M, f, bdrop=short)
        f = dict(base, **{D + '/CHECKERED': pic2,
                          D: prodos_dir([('CHECKERED', 6, 0x2000, 8192), board, mv])})
        self.load(M, f, bdrop=pic2)
        # NAME of another size is no picture: the longer one.
        f = dict(base, **{D + '/CHECKER': b'x' * 500,
                          D: prodos_dir([('CHECKER', 4, 0, 500), mv, board])})
        self.load(M, f, bdrop=pic)
        # Neither a movie nor a short NAME (under 4 characters) by prefix.
        self.load(M, dict(base, **{D: prodos_dir([mv, ('CHECKERBOARD', 6, 0x8400, 8192)])}))
        short_name = {D + '/M.ABC': movie, D + '/ABCDEF': pic,
                      D: prodos_dir([('M.ABC', 6, 0x8400, len(movie)), ('ABCDEF', 6, 0x2000, 8192)])}
        self.load(D + '/M.ABC', short_name)
        short_name[D + '/ABC'] = pic2
        short_name[D] = prodos_dir([('M.ABC', 6, 0x8400, len(movie)), ('ABCDEF', 6, 0x2000, 8192),
                                    ('ABC', 6, 0x2000, 8192)])
        self.load(D + '/M.ABC', short_name, bdrop=pic2)
        # A named backdrop wins; an unreadable directory finds nothing by
        # prefix; an unreadable picture found is simply not used.
        f = dict(base, **{D + '/STREAM': pic2, D: prodos_dir([mv, board])})
        self.load(M + ',STREAM', f, bdrop=pic2)
        for fault in 'OR':
            self.load(M, dict(base, **{D: prodos_dir([mv, board])}), fault + D)
            self.load(M, dict(base, **{D: prodos_dir([mv, board])}), fault + D + '/CHECKERBOARD')
        print('PASS fantavision: a backdrop by its name\'s beginning (M.CHECKER), both processors')

    def test_relaunch_command(self):
        movie = ref.synthetic(5, frames=2)
        rng = __import__('random').Random(14)
        pic = bytes(rng.randrange(256) for _ in range(8192))
        M = '/HD/FV/M.B'
        f = {M: movie, '/HD/FV/STREAM': pic}
        for cmd, want in (('*O' + M, (1, 1, 0)), ('+C' + M, (0, 0, 2)), ('*J' + M, (1, 0, 9)),
                          ('+A' + M, (0, 0, 0)), ('*Z' + M, (1, 1, 0)), ('*K' + M, (1, 1, 0)),
                          (M, (0, 1, 0))):
            res = self.load(cmd, f)
            self.assertEqual((res['slide'], res['mode'], res['delay']), want, cmd)
            self.assertEqual(res['ocl'], len(M))
        res = self.load('+C' + M + ',STREAM', f, bdrop=pic)
        self.assertEqual(res['cmd'], M + ',STREAM')
        # Too short for a prefix: a path like any other.
        self.load('*O', {}, msg='THE MOVIE CANNOT BE READ.')
        print('PASS fantavision: the relaunch command (slideshow, speed), both processors')


# -- measurements -----------------------------------------------------------------

def measure_set():
    """(label, movie) of the synthetic set used for the timings."""
    out = [('synthetic %d' % s, ref.synthetic(s)) for s in range(40)]
    out += [('shaped %d' % s, ref.shaped_movie(s)) for s in range(12)]
    names = {0: 'dots', 1: 'lines', 2: 'solids', 3: 'solids'}
    for kind in (0, 1, 2):
        for big in (False, True):
            for seed in range(3):
                out.append(('%s%s' % (names[kind], ' big' if big else ''),
                            ref.demo_movie(kind, seed=seed, big=big, n=32 if big else 8, frames=4)))
    return out


def collect(sim, limit=24, count=True):
    """(label, frame, counters, cycles, fv_timing cycles) per frame; with
    count=False the cycles are the accelerated speed's (no counting), the
    counters those of the counted run of the same movie."""
    rows = []
    for label, movie in measure_set():
        res = sim.run(movie, limit)
        fast = sim.run(movie, limit, count=False)['frames'] if not count else res['frames']
        for i, ((shown, c, cyc, tcyc, _), f) in enumerate(zip(res['frames'], fast)):
            rows.append((label, i, c, f[2] if not count else cyc, tcyc))
    return rows


def measure():
    with tempfile.TemporaryDirectory(prefix='a2fc-fanta-') as d:
        sim = Sim('6502', Path(d))
        rows = collect(sim, count=False)
        counted = collect(sim)
    def stats(xs):
        xs = sorted(xs)
        return '%7d %7d %7d' % (xs[0], statistics.median(xs), xs[-1])
    print('cycles per frame (6502, sim65), accelerated: min median max | original model: min median max | speed-up (median)')
    groups = {}
    for label, i, c, cyc, tcyc in rows:
        key = label.split(' ')[0]
        if label.endswith('big'):
            key += ' big'
        groups.setdefault(key, []).append((cyc, c['orig'], c['own'], tcyc))
    allr = [r for g in groups.values() for r in g]
    for key, g in sorted(groups.items()) + [('ALL', allr)]:
        print('%-12s %s | %s  x%.1f' % (key, stats([r[0] for r in g]), stats([r[1] for r in g]),
                                        statistics.median([r[1] / r[0] for r in g])))
    err = [abs(c['own'] - cyc - tcyc) / (cyc + tcyc) for _, _, c, cyc, tcyc in counted]
    print('own estimate vs measured (build + timing): median error %.1f%%, 90%% within %.1f%%' %
          (100 * statistics.median(err), 100 * sorted(err)[int(len(err) * 0.9)]))
    print('fv_timing: %d-%d cycles' % (min(r[4] for r in counted), max(r[4] for r in counted)))


def lstsq(rows, ys):
    """Least squares, relative (each row weighted by 1 / y), normal equations."""
    n = len(rows[0])
    m = [[0.0] * (n + 1) for _ in range(n)]
    for r, y in zip(rows, ys):
        w = 1.0 / (y * y)
        for i in range(n):
            for j in range(n):
                m[i][j] += w * r[i] * r[j]
            m[i][n] += w * r[i] * y
    for i in range(n):                       # Gauss-Jordan, partial pivoting
        p = max(range(i, n), key=lambda k: abs(m[k][i]))
        m[i], m[p] = m[p], m[i]
        if abs(m[i][i]) < 1e-12:
            continue
        for k in range(n):
            if k != i:
                f = m[k][i] / m[i][i]
                for j in range(i, n + 1):
                    m[k][j] -= f * m[i][j]
    return [m[i][n] / m[i][i] if abs(m[i][i]) > 1e-12 else 0.0 for i in range(n)]


def calibrate():
    with tempfile.TemporaryDirectory(prefix='a2fc-fanta-') as d:
        sim = Sim('6502', Path(d))
        rows = collect(sim)
    names = OWN_COUNTERS
    A = [[1.0] + [c['own_' + k] for k in names] for _, _, c, _, _ in rows]
    y = [cyc + tcyc for _, _, _, cyc, tcyc in rows]
    keep = list(range(len(names) + 1))
    while True:                              # no negative cost: drop and refit
        sub = lstsq([[r[i] for i in keep] for r in A], y)
        worst = min(range(len(keep)), key=lambda i: sub[i])
        if sub[worst] >= 0:
            break
        del keep[worst]
    coef = [0.0] * (len(names) + 1)
    for i, v in zip(keep, sub):
        coef[i] = v
    print('OWN_BASE (incl. fv_timing) = %d' % round(coef[0]))
    for k, v in zip(names, coef[1:]):
        print('  %-8s %d' % (k, round(v)))
    err = sorted(abs(sum(a * c for a, c in zip(r, coef)) - v) / v for r, v in zip(A, y))
    print('median error %.1f%%, 90%% within %.1f%%, max %.1f%%' %
          (100 * err[len(err) // 2], 100 * err[int(len(err) * 0.9)], 100 * err[-1]))


if __name__ == '__main__':
    if '--measure' in sys.argv:
        measure()
    elif '--calibrate' in sys.argv:
        calibrate()
    else:
        unittest.main(verbosity=1)
