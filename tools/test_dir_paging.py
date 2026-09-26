#!/usr/bin/env python3
"""Paging a large directory: the counted blocks give exactly the full walk.

dir_next (src/a2fc.c) skips the blocks wholly before a window by counting
their active entries with dir_count_block (src/a2fc_mli.s) instead of
validating each name. This runs the real C of dir_open/dir_next and the
real assembly under sim65, on both processors with the compiler of each
edition (cc65 2.19 for the 65C02, cc65 master for the 6502), on directory
files built here, and checks every window against two models: the list of
active entries (the specification) and a step-by-step model of the walk
(for malformed directories). The directory files are compared byte for
byte after each run: paging only reads.
"""
import os
import random
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'src/a2fc.c').read_text()
ASM_SOURCE = (ROOT / 'src/a2fc_mli.s').read_text()
HEAD = Path(os.environ.get('CC65_HEAD', str(Path.home() / 'opt/cc65-head')))
WINDOW = 139


def section(text, start, end):
    i = text.index(start)
    return text[i:text.index(end, i)]


# The host twin of dir_count_block, for the harnesses built with the host
# compiler (tools/test_core_dirscan.py). test_twin_matches_assembly holds it
# to the assembly.
DIR_COUNT_BLOCK_C = r'''
static unsigned char dir_count_block(const unsigned char* e) {
    unsigned char i, n = 0;
    for (i = 0; i < 13; ++i, e += 0x27)
        if (e[0] >= 0x10) { if (!(e[0] & 0x0F)) return 0xFF; ++n; }
    return n;
}
'''

ASM = '''        .importzp ptr1, tmp1
        .segment "CODE"
''' + section(ASM_SOURCE, '; unsigned char __fastcall__ dir_count_block', '; void __fastcall__ aux_copy')

HARNESS = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#ifndef __CC65__
#define __fastcall__
#endif
static void activity_tick(void) {}
static unsigned char copy_buf[512];
static int dir_fd = -1;
static FILE* img_f;
static unsigned char dir_img, dir_error, dir_index, dir_per_block, dir_entry_len;
static unsigned int dir_block_key, dir_skip_count;
struct DirEntry { char name[17]; unsigned char type, access; unsigned int aux, blocks, mdate; unsigned long size; unsigned int key; };
static struct DirEntry dir_entry;
static unsigned char img_read_block(unsigned int b, unsigned char* buf) { (void)b; (void)buf; return 0; }
#ifdef HOST_TWIN
''' + DIR_COUNT_BLOCK_C + r'''
#else
unsigned char __fastcall__ dir_count_block(const unsigned char* entries);
#endif
''' + section(SOURCE, 'static unsigned char dir_open(const char* path)\n{', '/* ---------------------------------------------------------------------- */\n/* Display') + r'''
/* argv: directory file, window length, then skips. One line a skip:
 * "E<dir_error> <names...>", or "O" when the directory does not open. */
int main(int argc, char** argv) {
    int a, n, limit = atoi(argv[2]);
    for (a = 3; a < argc; ++a) {
        if (!dir_open(argv[1])) { printf("O\n"); continue; }
        dir_skip_count = (unsigned int)atol(argv[a]);
        n = 0;
        while (n < limit && dir_next()) {
            if (!n) printf("N");
            printf(" %s", dir_entry.name);
            ++n;
        }
        dir_close();
        printf("%sE%u\n", n ? " " : "", dir_error);
    }
    return 0;
}
'''

COUNT_HARNESS = r'''
#include <stdio.h>
#include <fcntl.h>
#include <unistd.h>
#ifndef __CC65__
#define __fastcall__
#endif
#ifdef HOST_TWIN
''' + DIR_COUNT_BLOCK_C + r'''
#else
unsigned char __fastcall__ dir_count_block(const unsigned char* entries);
#endif
static unsigned char block[512];
int main(int argc, char** argv) {
    int fd = open(argv[1], O_RDONLY);
    if (fd < 0) return 9;
    while (read(fd, block, 512) == 512) printf("%u\n", dir_count_block(block + 4));
    return close(fd) ? 8 : 0;
}
'''


def entry(name, storage=1):
    e = bytearray(39)
    e[0] = (storage << 4) | len(name)
    e[1:1 + len(name)] = name
    e[0x10] = 0x04
    return e


def directory(slots, truncate=None, chain_end=None):
    """slots: per entry after the header, bytes of 39 (active or deleted).

    Block 0 holds the header and 12 entries, the others 13; each block's
    next pointer is nonzero except on the last (or on chain_end)."""
    blocks = []
    rest = list(slots)
    first = True
    while first or rest:
        b = bytearray(512)
        n = 12 if first else 13
        chunk, rest = rest[:n], rest[n:]
        if first:
            h = bytearray(39)
            h[0] = 0xE0 | 3
            h[1:4] = b'DIR'
            h[0x1F], h[0x20] = 0x27, 0x0D
            active = sum(1 for e in slots if e[0] >= 0x10)
            h[0x21:0x23] = active.to_bytes(2, 'little')   # file_count (block +0x25)
            b[4:4 + 39] = h
            base = 1
        else:
            base = 0
        for i, e in enumerate(chunk):
            off = 4 + (base + i) * 39
            b[off:off + 39] = e
        blocks.append(b)
        first = False
    for i, b in enumerate(blocks):
        if i:
            b[0:2] = (100 + i - 1).to_bytes(2, 'little')
        if i + 1 < len(blocks) and i != chain_end:
            b[2:4] = (100 + i + 1).to_bytes(2, 'little')
    data = b''.join(blocks)
    if truncate is not None:
        data = data[:truncate]
    return data


def valid_name(e):
    n = e[0] & 0x0F
    if not n:
        return False
    for i in range(n):
        c = e[1 + i] | 0x20
        if (c < ord('a') or c > ord('z')) and (not i or not (ord('0') <= c <= ord('9') or c == ord('.'))):
            return False
    return True


def walk_model(data, skip, limit):
    """What dir_next does, step by step: (names, error)."""
    blocks = [data[i:i + 512] for i in range(0, len(data), 512)]
    cur, b, idx, out = blocks[0], 0, 1, []

    def next_block():
        nonlocal cur, b
        if not (cur[2] | cur[3] << 8):
            return 0
        if b + 1 >= len(blocks) or len(blocks[b + 1]) < 512:
            return None                      # read error
        b += 1
        cur = blocks[b]
        return 1

    while len(out) < limit:
        if idx >= 13:
            r = next_block()
            if r is None:
                return out, 1
            if not r:
                return out, 0
            idx = 0
            while skip >= 13:
                es = [cur[4 + i * 39:4 + (i + 1) * 39] for i in range(13)]
                if any(e[0] >= 0x10 and not e[0] & 0x0F for e in es):
                    return out, 1
                skip -= sum(1 for e in es if e[0] >= 0x10)
                r = next_block()
                if r is None:
                    return out, 1
                if not r:
                    return out, 0
        e = cur[4 + idx * 39:4 + (idx + 1) * 39]
        idx += 1
        if e[0] < 0x10:
            continue
        if not valid_name(e):
            return out, 1
        if skip:
            skip -= 1
            continue
        out.append(bytes(e[1:1 + (e[0] & 0x0F)]).decode())
    return out, 0


def random_slots(rng, active, deleted_ratio):
    slots, names = [], []
    while len(names) < active:
        if rng.random() < deleted_ratio:
            e = entry(b'GONE%d' % rng.randrange(1000))
            e[0] &= 0x0F                     # storage 0, name kept: as ProDOS leaves it
            slots.append(e)
        else:
            name = b'F%04d' % len(names)
            slots.append(entry(name, rng.choice((1, 2, 3, 0xD))))
            names.append(name.decode())
    for _ in range(rng.randrange(14)):       # trailing holes
        slots.append(bytearray(39))
    return slots, names


def toolchains():
    """(cpu, cl65, sim65, env): the compiler of each edition."""
    found = []
    if shutil.which('cl65') and shutil.which('sim65'):
        found.append(('sim65c02', shutil.which('cl65'), shutil.which('sim65'), {}))
    if (HEAD / 'bin/cl65').exists():
        found.append(('sim6502', str(HEAD / 'bin/cl65'), str(HEAD / 'bin/sim65'),
                      {'CC65_HOME': str(HEAD / 'share/cc65')}))
    return found


class DirPaging(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='dir-paging-')
        cls.p = Path(cls.tmp.name)
        (cls.p / 'walk.c').write_text(HARNESS)
        (cls.p / 'count.c').write_text(COUNT_HARNESS)
        (cls.p / 'dir_count_block.s').write_text(ASM)
        cls.runners = []
        for cpu, cl65, sim65, env in toolchains():
            env = {**os.environ, **env}
            for prog in ('walk', 'count'):
                subprocess.run([cl65, '-t', cpu, '-O', '-Oirs', '-Cl', '-I', str(ROOT),
                                '-o', str(cls.p / f'{prog}-{cpu}'), str(cls.p / f'{prog}.c'),
                                str(cls.p / 'dir_count_block.s')], check=True, env=env, capture_output=True)
            cls.runners.append((cpu, sim65, env))
        for prog in ('walk', 'count'):
            subprocess.run(['cc', '-std=c99', '-DHOST_TWIN', '-Wno-unused-function',
                            str(cls.p / f'{prog}.c'), '-o', str(cls.p / f'{prog}-host')],
                           check=True, capture_output=True)
        if not cls.runners:
            raise unittest.SkipTest('no cc65 toolchain')

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def walk(self, data, skips, limit=WINDOW):
        """{runner: [(names, error)]} for each skip, the file checked unchanged."""
        f = self.p / 'dir.bin'
        f.write_bytes(data)
        results = {}
        for cpu, sim65, env in self.runners + [('host', None, None)]:
            exe = str(self.p / f'walk-{cpu}')
            cmd = ([sim65, exe] if sim65 else [exe]) + [str(f), str(limit)] + [str(s) for s in skips]
            out = subprocess.check_output(cmd, text=True, env=env, timeout=120)
            rows = []
            for line in out.splitlines():
                words = line.split()
                if words[0] == 'O':
                    rows.append(None)
                elif words[0] == 'N':
                    rows.append((words[1:-1], int(words[-1][1:])))
                else:
                    rows.append(([], int(words[0][1:])))
            results[cpu] = rows
            self.assertEqual(f.read_bytes(), data, cpu)
        return results

    def check(self, data, skips, limit=WINDOW, names=None):
        results = self.walk(data, skips, limit)
        for i, skip in enumerate(skips):
            expected = walk_model(data, skip, limit)
            if names is not None:           # well formed: the specification
                self.assertEqual(expected, (names[skip:skip + limit], 0), skip)
            for cpu, rows in results.items():
                self.assertEqual(rows[i], (expected[0], expected[1]), (cpu, skip))

    def test_windows_equal_the_full_walk(self):
        rng = random.Random(1)
        for active in (0, 1, 12, 13, 138, 139, 140, 278, 300, 700):
            for ratio in (0.0, 0.3, 0.8):
                slots, names = random_slots(rng, active, ratio)
                data = directory(slots)
                skips = sorted({k * WINDOW for k in range(active // WINDOW + 2)}
                               | {rng.randrange(active + 20) for _ in range(6)} | {12, 13, 25, 26})
                with self.subTest(active=active, ratio=ratio):
                    self.check(data, skips, names=names)

    def test_every_skip_of_a_small_directory(self):
        rng = random.Random(2)
        slots, names = random_slots(rng, 90, 0.4)
        self.check(directory(slots), list(range(0, 95)), limit=5, names=names)

    def test_fifteen_hundred_entries(self):
        rng = random.Random(3)
        slots, names = random_slots(rng, 1500, 0.1)
        self.check(directory(slots), [k * WINDOW for k in range(12)], names=names)

    def test_nameless_active_entry_in_a_counted_block_is_an_error(self):
        rng = random.Random(4)
        slots, names = random_slots(rng, 300, 0.0)
        slots[40][0] = 0x10                  # active, length 0, block 3
        data = directory(slots)
        results = self.walk(data, [WINDOW, 2 * WINDOW])
        for cpu, rows in results.items():
            self.assertEqual(rows, [([], 1), ([], 1)], cpu)
        self.check(data, [0, 5, WINDOW, 2 * WINDOW])

    def test_bad_character_in_a_counted_block_still_counts_one(self):
        # The only difference from validating every skipped name: the window
        # beyond shows (aligned, the entry counted), its own window refuses.
        rng = random.Random(5)
        slots, names = random_slots(rng, 400, 0.0)
        slots[40][2] = ord('/')              # F0040 -> F/040, block 3
        data = directory(slots)
        results = self.walk(data, [0, 2 * WINDOW])
        for cpu, rows in results.items():
            self.assertEqual(rows[0], (names[:40], 1), cpu)
            self.assertEqual(rows[1], (names[2 * WINDOW:3 * WINDOW], 0), cpu)
        self.check(data, [0, WINDOW, 2 * WINDOW])

    def test_read_error_while_counting_is_an_error_not_the_end(self):
        rng = random.Random(6)
        slots, names = random_slots(rng, 700, 0.2)
        full = directory(slots)
        for cut in (512 * 3, 512 * 5 + 100, 512 * 9, 512 * 20):
            data = full[:cut]
            with self.subTest(cut=cut):
                results = self.walk(data, [2 * WINDOW, 4 * WINDOW])
                for cpu, rows in results.items():
                    for names_got, error in rows:
                        if names_got == []:
                            self.assertEqual(error, 1, cpu)
                self.check(data, [0, WINDOW, 2 * WINDOW, 4 * WINDOW])

    def test_chain_ending_early_is_the_end(self):
        rng = random.Random(7)
        slots, names = random_slots(rng, 500, 0.0)
        data = directory(slots, chain_end=4)     # blocks 0-4 only: 12 + 4 x 13 = 64
        self.check(data, [0, WINDOW, 2 * WINDOW, 60], limit=WINDOW)
        results = self.walk(data, [WINDOW])
        for cpu, rows in results.items():
            self.assertEqual(rows[0], ([], 0), cpu)

    def test_directory_changed_between_two_pages(self):
        # Nothing is remembered from one page to the next: an entry added or
        # removed before the window moves the window, as a full walk does.
        rng = random.Random(8)
        slots, names = random_slots(rng, 600, 0.2)
        before = directory(slots)
        self.check(before, [2 * WINDOW], names=names)
        live = [i for i, e in enumerate(slots) if e[0] >= 0x10]
        slots[live[10]][0] &= 0x0F                                   # deleted early
        hole = next(i for i, e in enumerate(slots) if e[0] < 0x10 and i > live[30])
        slots[hole] = entry(b'NEWONE')                               # created in a hole
        after = directory(slots)
        order = [bytes(e[1:1 + (e[0] & 15)]).decode() for e in slots if e[0] >= 0x10]
        self.check(after, [WINDOW, 2 * WINDOW, 3 * WINDOW], names=order)

    def test_fuzz(self):
        rng = random.Random(9)
        for round_ in range(25):
            slots, _ = random_slots(rng, rng.randrange(900), rng.random())
            for _ in range(rng.randrange(6)):
                e = rng.choice(slots)
                k = rng.randrange(4)
                if k == 0:
                    e[0] = rng.randrange(256)
                elif k == 1:
                    e[1 + rng.randrange(15)] = rng.randrange(256)
                elif k == 2:
                    e[0] = 0x10
                else:
                    e[0] &= 0x0F
            data = directory(slots, truncate=rng.choice((None, None, rng.randrange(512, 512 * 60))))
            if len(data) < 512:
                continue
            skips = [rng.randrange(1000) for _ in range(4)] + [WINDOW, 3 * WINDOW]
            with self.subTest(round=round_):
                self.check(data, skips)

    def test_twin_matches_assembly(self):
        rng = random.Random(10)
        blocks = bytearray()
        for _ in range(300):
            b = bytearray(rng.randrange(256) for _ in range(512))
            for i in range(13):
                if rng.random() < 0.5:
                    b[4 + i * 39] = rng.choice((0, 0x10, 0x05, 0x13, 0xF0, 0xE7, 0x2F))
            blocks += b
        f = self.p / 'blocks.bin'
        f.write_bytes(bytes(blocks))
        expected = []
        for k in range(300):
            es = [blocks[k * 512 + 4 + i * 39] for i in range(13)]
            expected.append(255 if any(e >= 0x10 and not e & 15 for e in es)
                            else sum(1 for e in es if e >= 0x10))
        for cpu, sim65, env in self.runners + [('host', None, None)]:
            exe = str(self.p / f'count-{cpu}')
            out = subprocess.check_output(([sim65, exe] if sim65 else [exe]) + [str(f)],
                                          text=True, env=env, timeout=60)
            self.assertEqual(list(map(int, out.split())), expected, cpu)


if __name__ == '__main__':
    unittest.main()
