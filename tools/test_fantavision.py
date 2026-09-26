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
        .import fv_movie, fv_len, fv_shown, fv_done, fv_frames
        .import fv_counts, fv_orig, fv_own, fv_wait, fv_count
        .export _fv_check, _fv_begin, _fv_first, _fv_next, _fv_timing
        .export _fv_movie := fv_movie, _fv_len := fv_len, _fv_shown := fv_shown
        .export _fv_done := fv_done, _fv_frames := fv_frames, _fv_counts := fv_counts
        .export _fv_orig := fv_orig, _fv_own := fv_own, _fv_wait := fv_wait
        .export _fv_count := fv_count
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
    if (r == 0) {
        c0 = cyc(); fv_begin(); c1 = cyc(); cb = c1 - c0;
        out(&cb, 4);
        for (f = 0; f < limit; ++f) {
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
        (workdir / f'{cpu}.cfg').write_text(cfg)
        (workdir / 'harness.c').write_text(HARNESS)
        (workdir / 'glue.s').write_text(GLUE)
        self.exe = workdir / f'harness-{cpu}'
        subprocess.run([str(HEAD / 'bin/cl65'), '-t', target, '-C', str(workdir / f'{cpu}.cfg'),
                        '-O', '-o', str(self.exe), str(workdir / 'harness.c'),
                        str(workdir / 'glue.s'), str(ROOT / 'src/fanta/engine.s')],
                       check=True, cwd=workdir, env=env)
        self.sim = str(HEAD / 'bin/sim65')

    def run(self, movie, limit=20, count=True):
        (self.dir / 'movie.bin').write_bytes(movie)
        # -x: a hang shows as a failure, not as a stuck test
        p = subprocess.run([self.sim, '-x', '1000000000', str(self.exe), str(limit),
                            '1' if count else '0'],
                           cwd=self.dir, capture_output=True, timeout=900)
        if p.returncode != 0:
            raise AssertionError('sim65 exit %d: %s' % (p.returncode, p.stderr[-300:]))
        o = p.stdout
        res = {'overhead': struct.unpack_from('<I', o, 0)[0], 'code': o[4], 'frames': []}
        pos = 5
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


def ref_frames(movie, limit):
    player = ref.Player(movie)
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

    def compare(self, cpu, movie, limit=16, label='', count=True):
        res = self.sims[cpu].run(movie, limit, count)
        self.assertEqual(res['code'], 0, label)
        player, frames = ref_frames(movie, limit)
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
        cases.append((h + b'\x01' * 8 + b'\x00' * 200, None))
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
        cases.append((h + b'\x00' * 200, 'frames'))                      # 0 frames
        cases.append((h + b'\x01' * 8 * 127 + b'\x00' * 10, None))      # 127 frames
        cases.append((h + b'\x01' * 8 * 128 + b'\x00' * 10, 'frames'))  # 128 frames
        cases.append((h + b'\x01' * 7 + b'\x00' + b'\x01' * 200, 'record'))  # 0 inside a frame
        for bad in (2, 3, 5, 69, 70, 71, 72, 254, 255):
            # otherwise well formed: the length alone is wrong
            rec = bytes([bad, 2, 0x33, 0]) + bytes(max(0, bad - 4))
            cases.append((h + rec + b'\x01' * 7 + b'\x00' * 100, 'record'))
        # n = 33
        cases.append((h + ref.record(2, 1, 3, 0, [1] * 33, [1] * 33)[:1] + bytes(70) + b'\x01' * 60,
                      'record'))
        # a record running past the end, a frame cut short
        big = h + b'\x01' * 7 + ref.record(2, 1, 3, 0, list(range(32)), list(range(32)))
        cases.append((big + b'\x01' * 7 + bytes([68]) + bytes(40), 'truncated'))
        cases.append((h + b'\x01' * 8 * 12 + b'\x01' * 7, 'truncated'))
        # ends exactly at the end of the file
        cases.append((h + b'\x01' * 8 * 13, None))
        for movie, why in cases:
            if why is None:
                self.assertIsNone(ref.check(movie))
                for cpu in ('6502', '65c02'):
                    self.compare(cpu, movie, 3, 'accepted edge case')
            else:
                self.refused(movie, why)
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
        print('PASS fantavision: every check refuses before anything is drawn, both processors')


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
