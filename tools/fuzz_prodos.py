#!/usr/bin/env python3
"""Mutation campaign over the real C walker of FIXIT and REPAIR.

One question: **can REPAIR make a ProDOS volume worse?** The campaign breaks
healthy volumes in every way a bad block, a bad pointer or a half-written
directory can break one, runs the real C -- the walker of
`src/plugins/fixit_walk.h`, compiled from the harnesses of
`tools/test_fixit.py` and `tools/test_repair.py` with
`-fsanitize=address,undefined` -- and judges every run against the host
oracle `tools/prodos_check.py`.

    python3 tools/fuzz_prodos.py --count 2000 --seed 1 --out build/fuzz-prodos

Seven invariants, each of which saves the image, the seed, the JSON of every
run and a one-line reason into `--out` when it fails:

1. **no crash, no hang** -- FIXIT, REPAIR's plan, REPAIR's `FIX` and the
   oracle all terminate cleanly, under ASan and UBSan;
2. **differential** -- FIXIT's counters and `complete` are the oracle's, and
   REPAIR's plan pass agrees with FIXIT on the identifiers REPAIR carries.
   The divergences that are a property of the two designs, not a fault, are
   in `ALLOWED` below with the line of docs/FIXIT.md that documents each, and
   the summary counts how often each fired;
3. **a refusal writes nothing** -- not one WRITE_BLOCK, and the image is
   byte-identical;
4. **writes stay on the plan** -- every written block is a bitmap page or a
   directory block the oracle also walked; never an index block, a file data
   block, block 0 or block 1;
5. **files survive** -- every file the tolerant reader below could read
   before the repair reads exactly the same bytes after it, and no file
   entry's storage, key or eof moved;
6. **monotone** -- the oracle finds no identifier after the repair that it
   did not find before, `repaired` is said only of a volume that is clean of
   everything REPAIR carries, `still reports N findings` counts what the
   oracle counts, and a second REPAIR over the repaired volume writes
   nothing;
7. **idempotence under failure** -- with a write error, a readback mismatch
   or a failed restore injected at a random write, every BYTE of the image
   is either what the volume had or what a complete repair writes there (a
   correction whose restore succeeded does not stop the walk, so the image
   ends as the original with a subset of the corrections in it), no block
   the uninjected run never wrote has moved, and `not restored` leaves the
   volume as it was.

Only throwaway images are touched: every seed is built here, in a temporary
directory, and every run works on its own copy.
"""
import argparse
import hashlib
import json
import os
import random
import subprocess
import sys
import tempfile
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

import corrupt_prodos
import prodos_check
from prodos_check import BLOCK, ENTRY_LEN
import test_fixit
import test_prodos_check
import test_repair

# The identifiers an image can carry: the two DEVICE_ONLY ones need a device
# and the oracle never emits them, so a campaign over images cannot cover
# them and never compares them.
IMAGE_IDS = tuple(c for c in prodos_check.CHECKS if c not in prodos_check.DEVICE_ONLY)
# What REPAIR's walker does not even count (docs/FIXIT.md section 5, "Ce que
# REPAIR ne contrôle pas"): the comparison of FIXIT against REPAIR skips them.
DROPPED = set(test_repair.DROPPED)

# The notes that mean FIXIT or REPAIR never walked the volume at all: the
# selection was refused, or the header was. Nothing is comparable then.
NO_WALK = {test_repair.M_NOTVOL, test_repair.M_NOVOL, test_repair.M_BADHDR,
           test_repair.M_NOREAD, 'ON_LINE failed.'}


# -- the two harnesses ------------------------------------------------------
# The C sources come from the two test suites unchanged; the campaign only
# adds to its own copy of the REPAIR one what a campaign needs and a unit
# test does not: the bytes of every write (so a failure injection can be
# judged against what an uninjected run wrote), a write table big enough for
# a fuzzed plan, and one planted bug that tools/test_fuzz_prodos.py uses to
# prove invariant 6 really catches a lost write.
FIXIT_HARNESS = test_fixit.HARNESS


def _patch(text, old, new, what):
    if old not in text:
        raise SystemExit('fuzz_prodos: the REPAIR harness no longer has ' + what)
    return text.replace(old, new, 1)


def _repair_harness():
    h = test_repair.HARNESS
    h = _patch(h, '#define MAXW 64', '#define MAXW 4096',
               'its write table (MAXW)')
    h = _patch(h, 'static int errwrite, failall, badread, changed;',
               'static int errwrite, failall, badread, changed;\n'
               '/* The campaign: every write recorded whole, and one planted bug. */\n'
               'static FILE* wdump;\n'
               'static int bug, skipped;\n'
               'static unsigned int skipblock;\n'
               'static unsigned char shadow[512];',
               'its injection variables')
    h = _patch(h, '        if (failall || rank == errwrite) return 0x27;',
               '        if (bug && !skipped) {     /* planted: this write is lost,\n'
               '                                    * and the readback lies about it */\n'
               '            skipped = 1; skipblock = b->block;\n'
               '            memcpy(shadow, b->buf, 512);\n'
               '            if (rank <= MAXW) wok[rank - 1] = 1;\n'
               '            return 0;\n'
               '        }\n'
               '        if (failall || rank == errwrite) return 0x27;',
               'its write branch')
    h = _patch(h, '        if (rank <= MAXW) wok[rank - 1] = 1;\n        return 0;',
               '        if (rank <= MAXW) wok[rank - 1] = 1;\n'
               '        if (wdump) {\n'
               '            unsigned char head[2];\n'
               '            head[0] = (unsigned char)(b->block & 255);\n'
               '            head[1] = (unsigned char)(b->block >> 8);\n'
               '            fwrite(head, 1, 2, wdump);\n'
               '            fwrite(b->buf, 1, 512, wdump);\n'
               '            fflush(wdump);\n'
               '        }\n'
               '        return 0;',
               'its write acknowledgement')
    h = _patch(h, '        if (b->block == reject) return 0x27;\n'
                  '        if (seek_block(b->block)) return 0x27;\n'
                  '        if (fread(b->buf, 1, 512, disk) != 512) return 0x27;',
               '        if (b->block == reject) return 0x27;\n'
               '        if (seek_block(b->block)) return 0x27;\n'
               '        if (fread(b->buf, 1, 512, disk) != 512) return 0x27;\n'
               '        if (skipped && b->block == skipblock) memcpy(b->buf, shadow, 512);',
               'its read branch')
    h = _patch(h, "        else if (opt(argv[i], \"poison\", &v)) poison = atoi(v);",
               "        else if (opt(argv[i], \"poison\", &v)) poison = atoi(v);\n"
               "        else if (opt(argv[i], \"wdump\", &v)) wdump = fopen(v, \"wb\");\n"
               "        else if (opt(argv[i], \"bug\", &v)) bug = atoi(v);",
               'its option table')
    return h


REPAIR_HARNESS = _repair_harness()

CFLAGS = ['-std=c99', '-g', '-O1', '-Wno-unknown-pragmas',
          '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
          '-fno-omit-frame-pointer']
SAN_ENV = {'ASAN_OPTIONS': 'detect_leaks=0:abort_on_error=1',
           'UBSAN_OPTIONS': 'halt_on_error=1:print_stacktrace=0'}


def build_harnesses(work):
    """Compile both harnesses once, sanitizers in."""
    out = {}
    for name, source in (('fixit', FIXIT_HARNESS), ('repair', REPAIR_HARNESS)):
        c = work / (name + '_fuzz.c')
        c.write_text(source)
        exe = work / (name + '_fuzz')
        subprocess.run([os.environ.get('CC', 'cc')] + CFLAGS + ['-I', str(ROOT),
                       str(c), '-o', str(exe)], check=True, capture_output=True)
        out[name] = str(exe)
    return out


# -- the oracle, instrumented ----------------------------------------------
class Walk(prodos_check.Checker):
    """The oracle's own walk, told to keep the map it already computes.

    Nothing of the checking changes: the subclass only records which blocks
    the walk treated as directory blocks, as index blocks and as the key
    block of an extended file, which blocks were claimed and by how many
    claimants, and where every file entry lives. Invariants 4 and 5 are
    judged on that map, so what a write is allowed to touch and what a file
    is are the oracle's answers, never the campaign's guess.
    """

    def __init__(self, data):
        super().__init__(data)
        self.dirblocks = set()
        self.dirkeys = set()
        self.index_blocks = set()
        self.ext_keys = set()
        self.claims = {}
        self.files = {}                 # (block, slot) -> (path, storage, key, eof)
        self.depth_of = {}              # (block, slot) -> the nesting level

    def claim(self, b, path):
        self.claims[b] = self.claims.get(b, 0) + 1
        return super().claim(b, path)

    def directory(self, key, path, depth, parent, declared):
        chain, cut = super().directory(key, path, depth, parent, declared)
        if chain:
            self.dirkeys.add(key)
            self.dirblocks.update(chain)
        return chain, cut

    def entry(self, e, block, slot, dirpath, dirkey, depth):
        storage = e[0] >> 4
        self.depth_of[(block, slot)] = depth
        if storage in (prodos_check.SEEDLING, prodos_check.SAPLING,
                       prodos_check.TREE, prodos_check.EXTENDED):
            raw = e[1:1 + (e[0] & 15)]
            self.files[(block, slot)] = (
                dirpath + '/' + raw.decode('ascii', 'replace'), storage,
                int.from_bytes(e[0x11:0x13], 'little'),
                int.from_bytes(e[0x15:0x18], 'little'))
        return super().entry(e, block, slot, dirpath, dirkey, depth)

    def extended(self, key, bad_key, path):
        if not bad_key:
            self.ext_keys.add(key)
        return super().extended(key, bad_key, path)

    def fork(self, storage, key, path):
        if storage in (prodos_check.SAPLING, prodos_check.TREE):
            self.index_blocks.add(key)
        return super().fork(storage, key, path)

    @property
    def bitmap_pages(self):
        if not self.bitmap_ok:
            return set()
        return set(range(self.bitmap, self.bitmap + self.bitmap_blocks))


def walked(data):
    w = Walk(data)
    result = w.run()
    return w, result


# -- a tolerant reader ------------------------------------------------------
MAX_READ_BLOCKS = 2048          # 1 MB per file: a fuzzed eof reaches 16 MB


def _block(data, n):
    if n < 0 or (n + 1) * BLOCK > len(data):
        return bytes(BLOCK)
    return data[n * BLOCK:(n + 1) * BLOCK]


def read_file(data, storage, key, eof):
    """The bytes of one file, whatever the volume looks like.

    Out-of-range and zero pointers read as holes rather than raising, and a
    fuzzed eof is capped at MAX_READ_BLOCKS: what matters is that the same
    entry read before and after a repair gives the same answer, and the cap
    is the same on both sides.
    """
    if storage == prodos_check.EXTENDED:
        mini = _block(data, key)[0:8]
        return read_file(data, mini[0], int.from_bytes(mini[1:3], 'little'),
                         int.from_bytes(mini[5:8], 'little'))
    if storage == prodos_check.SEEDLING:
        return _block(data, key)[:eof]
    if storage not in (prodos_check.SAPLING, prodos_check.TREE):
        return b''
    need = min((eof + BLOCK - 1) // BLOCK, MAX_READ_BLOCKS)
    out = bytearray()
    index = _block(data, key)
    for n in range(need):
        page = index
        if storage == prodos_check.TREE:
            sap = page[n >> 8] | (page[256 + (n >> 8)] << 8)
            page = _block(data, sap) if sap else bytes(BLOCK)
        p = page[n & 255] | (page[256 + (n & 255)] << 8)
        out += _block(data, p) if p else bytes(BLOCK)
    return bytes(out[:eof])


def file_bytes(data, files):
    return {k: read_file(data, v[1], v[2], v[3]) for k, v in files.items()}


def changed_blocks(a, b):
    """The blocks that differ, compared 512 bytes at a time.

    A byte-by-byte loop over an 8193-block image is four million Python
    iterations per case; slicing is the same answer in a thousandth of the
    time, and the byte-level questions are then asked of those blocks only.
    """
    n = min(len(a), len(b)) // BLOCK
    return {i for i in range(n)
            if a[i * BLOCK:(i + 1) * BLOCK] != b[i * BLOCK:(i + 1) * BLOCK]}


# -- the seeds --------------------------------------------------------------
def build_floppy(work):
    """A 280-block mkvolume floppy with a subdirectory and a sapling."""
    stage = work / 'floppy-stage'
    stage.mkdir(parents=True, exist_ok=True)
    (stage / 'HELLO.TXT').write_bytes(b'HELLO FLOPPY\r' * 20)
    (stage / 'OTHER.TXT').write_bytes(b'A SECOND SEEDLING\r' * 4)
    (stage / 'SAP.BIN').write_bytes(bytes(range(256)) * 16)      # 8 blocks
    sub = stage / 'SUB'
    sub.mkdir(exist_ok=True)
    (sub / 'NEST.TXT').write_bytes(b'nested on a floppy\r' * 40)
    image = work / 'floppy.po'
    subprocess.run([sys.executable, str(ROOT / 'tools/mkvolume.py'), str(stage),
                    str(image), '--volume', 'FLOPPY', '--blocks', '280'],
                   check=True, capture_output=True)
    return image.read_bytes()


DEEP_LEVELS = 15                # depths 2 to 16: one more is DIR_DEPTH


def build_big():
    """A hand-made 8193-block volume: three bitmap pages, files in two windows.

    The walker works one 4096-block window at a time and reports a fault of
    the directory tree in the first window only, so a volume whose files do
    not all live in window 0 is the one that exercises `base`, `span` and
    the per-window bitmap page. 8193 blocks give a last window of one block,
    which is also where BM_TAIL lives.

    It also carries a legal nest of fifteen subdirectories, which is depths
    2 to 16 -- the deepest ProDOS allows. DIR_DEPTH is a fault no mutation
    of a healthy shallow volume can reach (a pointer back up the tree is a
    loop, not a deeper level), so the seed is built one level away from it:
    any mutation that turns the file at the bottom into a directory, or
    grafts one more level on, is the seventeenth.
    """
    h = test_prodos_check
    total = 8193
    sub, nest, deep, leaf = 4200, 4201, 4300, 4320
    entries = [h.entry(1, b'A', key=20, blocks=1, eof=300),
               h.entry(2, b'S', key=4090, blocks=3, eof=1024),
               h.entry(1, b'B', key=8192, blocks=1, eof=512),
               h.entry(0xD, b'D', key=sub, blocks=1, eof=BLOCK),
               h.entry(0xD, b'DEEP', key=deep, blocks=1, eof=BLOCK)]
    d = h.fixture(total, entries)
    h.ptr(d, 4090, 0, 4100)
    h.ptr(d, 4090, 1, 5000)
    test_fixit.subdir_header(d, sub, 2, 4)
    d[sub * BLOCK + 4 + ENTRY_LEN:sub * BLOCK + 4 + 2 * ENTRY_LEN] = \
        h.entry(1, b'N', key=nest, blocks=1, eof=400, header=sub)

    parent, pslot = 2, 5
    for i in range(DEEP_LEVELS):
        block = deep + i
        h.allocated(d, block)
        test_fixit.subdir_header(d, block, parent, pslot)
        child = (h.entry(1, b'LEAF', key=leaf, blocks=1, eof=400, header=block)
                 if i == DEEP_LEVELS - 1 else
                 h.entry(0xD, b'L', key=block + 1, blocks=1, eof=BLOCK, header=block))
        d[block * BLOCK + 4 + ENTRY_LEN:block * BLOCK + 4 + 2 * ENTRY_LEN] = child
        parent, pslot = block, 1

    for b in (20, 4090, 4100, 5000, 8192, sub, nest, leaf):
        h.allocated(d, b)
    for b, fill in ((20, b'A'), (4100, b'S'), (5000, b'T'), (8192, b'B'),
                    (nest, b'N'), (leaf, b'L')):
        d[b * BLOCK:(b + 1) * BLOCK] = fill * BLOCK
    return bytes(d)


class SeedMap:
    """One healthy seed and everything a mutator needs to aim at it."""

    def __init__(self, name, data):
        self.name = name
        self.data = bytes(data)
        self.inv = corrupt_prodos.Inventory(self.data)
        w, result = walked(self.data)
        if result.findings:
            raise SystemExit('seed %s is not healthy: %s'
                             % (name, [f.id for f in result.findings]))
        self.total = self.inv.total
        self.bitmap = self.inv.bitmap
        self.pages = self.inv.bitmap_blocks
        self.bitmap_pages = sorted(w.bitmap_pages)
        self.dir_blocks = sorted(w.dirblocks)
        self.dir_keys = sorted(w.dirkeys)
        self.subdir_keys = sorted(k for k in w.dirkeys if k != 2)
        self.index_blocks = sorted(w.index_blocks)
        self.ext_keys = sorted(w.ext_keys)
        self.data_blocks = sorted(set(w.claims) - w.dirblocks - w.index_blocks
                                  - w.ext_keys - w.bitmap_pages - {0, 1})
        self.entries = list(self.inv.entries)
        # The file entry that sits at the deepest legal level, if the seed
        # has one: DIR_DEPTH is one storage nibble away from it.
        self.deepest = None
        for k, v in sorted(w.files.items()):
            if w.depth_of[k] == prodos_check.MAX_DEPTH:
                self.deepest = k
                break
        self.meta_blocks = sorted(set(self.dir_blocks) | set(self.index_blocks)
                                  | set(self.ext_keys) | set(self.bitmap_pages))


def build_seeds(work):
    seeds = {}
    fixture_dir = work / 'fixture'
    fixture_dir.mkdir(parents=True, exist_ok=True)
    seeds['fixture1600'] = SeedMap(
        'fixture1600', corrupt_prodos.make_fixture(fixture_dir).read_bytes())
    seeds['floppy280'] = SeedMap('floppy280', build_floppy(work))
    seeds['big8193'] = SeedMap('big8193', build_big())
    return seeds


# -- the mutators -----------------------------------------------------------
def put_word(d, off, v):
    d[off:off + 2] = (v & 0xFFFF).to_bytes(2, 'little')


def put24(d, off, v):
    d[off:off + 3] = (v & 0xFFFFFF).to_bytes(3, 'little')


def a_pointer(m, rng):
    """A pointer worth writing somewhere: in range, past the end, or a trap."""
    kind = rng.randrange(7)
    if kind == 0:
        return rng.randrange(0, m.total)
    if kind == 1:
        return rng.randrange(m.total, 65536)
    if kind == 2:
        return 0
    if kind == 3:
        return rng.choice(m.dir_blocks)
    if kind == 4:
        return rng.choice(m.bitmap_pages)
    if kind == 5 and m.data_blocks:
        return rng.choice(m.data_blocks)
    return 65535


def mut_entry(data, m, rng):
    """A random field of a random live directory entry."""
    ref = rng.choice(m.entries)
    off = ref.offset
    field = rng.choice(['storage', 'namelen', 'namebytes', 'key', 'used',
                        'eof', 'header', 'access', 'type'])
    if field == 'storage':
        data[off] = (rng.randrange(16) << 4) | (data[off] & 15)
    elif field == 'namelen':
        data[off] = (data[off] & 0xF0) | rng.randrange(16)
    elif field == 'namebytes':
        n = max(1, data[off] & 15)
        data[off + 1 + rng.randrange(n)] = rng.randrange(256)
    elif field == 'key':
        put_word(data, off + 0x11, a_pointer(m, rng))
    elif field == 'used':
        put_word(data, off + 0x13, rng.choice(
            [0, 1, ref.used + 1, max(0, ref.used - 1), rng.randrange(65536)]))
    elif field == 'eof':
        put24(data, off + 0x15, rng.choice(
            [0, 1, ref.eof + 1, max(0, ref.eof - 1), rng.randrange(1 << 24)]))
    elif field == 'header':
        put_word(data, off + 0x25, a_pointer(m, rng))
    elif field == 'access':
        data[off + 0x1E] = rng.randrange(256)
    else:
        data[off + 0x10] = rng.randrange(256)
    return 'entry.' + field


def mut_dirheader(data, m, rng):
    """A random field of a directory header, or of a chain pointer."""
    field = rng.choice(['file_count', 'entry_len', 'per_block', 'parent_block',
                        'parent_slot', 'parent_len', 'prev', 'next'])
    if field in ('prev', 'next'):
        block = rng.choice(m.dir_blocks)
        put_word(data, block * BLOCK + (0 if field == 'prev' else 2),
                 a_pointer(m, rng))
        return 'dir.' + field
    if field.startswith('parent'):
        if not m.subdir_keys:
            return mut_dirheader(data, m, rng)
        key = rng.choice(m.subdir_keys)
    else:
        key = rng.choice(m.dir_keys)
    off = key * BLOCK + 4
    if field == 'file_count':
        put_word(data, off + 0x21, rng.choice([0, 1, rng.randrange(65536)]))
    elif field == 'entry_len':
        data[off + 0x1F] = rng.randrange(256)
    elif field == 'per_block':
        data[off + 0x20] = rng.randrange(256)
    elif field == 'parent_block':
        put_word(data, off + 0x23, a_pointer(m, rng))
    elif field == 'parent_slot':
        data[off + 0x25] = rng.randrange(256)
    else:
        data[off + 0x26] = rng.randrange(256)
    return 'dir.' + field


def mut_index(data, m, rng):
    """A random pointer of a random index or master index block."""
    if not m.index_blocks:
        return mut_entry(data, m, rng)
    block = rng.choice(m.index_blocks)
    slot = rng.randrange(256)
    value = rng.choice([a_pointer(m, rng), block])      # ... or the block itself
    data[block * BLOCK + slot] = value & 255
    data[block * BLOCK + 256 + slot] = value >> 8
    return 'index.pointer'


def mut_bitmap(data, m, rng):
    """A bit of the allocation bitmap: set, cleared, or in the padding."""
    kind = rng.randrange(3)
    if kind == 2 and m.total % 4096:
        block = rng.randrange(m.total, m.pages * 4096)
        free = True
        tag = 'bitmap.padding'
    else:
        block = rng.randrange(m.total)
        free = kind == 0
        tag = 'bitmap.free' if free else 'bitmap.used'
    off = m.bitmap * BLOCK + (block >> 3)
    mask = 0x80 >> (block & 7)
    if free:
        data[off] |= mask
    else:
        data[off] &= 0xFF ^ mask
    return tag


def mut_volume(data, m, rng):
    """A field of the volume header that no other mutator owns."""
    off = 2 * BLOCK + 4
    field = rng.choice(['bitmap', 'total', 'storage'])
    if field == 'bitmap':
        put_word(data, off + 0x23, rng.choice(
            [0, 1, 2, m.total, m.total + 1, 65535, a_pointer(m, rng)]))
    elif field == 'total':
        put_word(data, off + 0x25, rng.choice(
            [0, 5, 6, rng.randrange(6, m.total), m.total + 1,
             m.total + rng.randrange(1, 4096), 65535]))
    else:
        data[off] = (rng.randrange(16) << 4) | (data[off] & 15)
    return 'volume.' + field


def mut_bytes(data, m, rng):
    """Two to five blind byte flips, in metadata blocks only."""
    for _ in range(rng.randrange(2, 6)):
        block = rng.choice(m.meta_blocks)
        data[block * BLOCK + rng.randrange(BLOCK)] = rng.randrange(256)
    return 'bytes.meta'


def mut_data(data, m, rng):
    """Blind byte flips in a file's data blocks: the deliberate small share."""
    if not m.data_blocks:
        return mut_bytes(data, m, rng)
    for _ in range(rng.randrange(1, 8)):
        block = rng.choice(m.data_blocks)
        data[block * BLOCK + rng.randrange(BLOCK)] = rng.randrange(256)
    return 'bytes.data'


def mut_fork(data, m, rng):
    """A mini-entry of an extended file's key block: +$000 and +$100."""
    if not m.ext_keys:
        return mut_entry(data, m, rng)
    off = rng.choice(m.ext_keys) * BLOCK + rng.choice((0, 256))
    field = rng.choice(['storage', 'key', 'used', 'eof'])
    if field == 'storage':
        data[off] = rng.randrange(256)
    elif field == 'key':
        put_word(data, off + 1, a_pointer(m, rng))
    elif field == 'used':
        put_word(data, off + 3, rng.randrange(65536))
    else:
        put24(data, off + 5, rng.randrange(1 << 24))
    return 'fork.' + field


def mut_deepen(data, m, rng):
    """One directory level too many: the seventeenth, which is DIR_DEPTH.

    No mutation of a shallow volume can reach that fault -- a pointer back
    up the tree is a loop, not a deeper level -- so the seed that carries
    the fifteen legal levels gets the one nibble that asks for a sixteenth.
    """
    if not m.deepest:
        return mut_dirheader(data, m, rng)
    block, slot = m.deepest
    off = block * BLOCK + 4 + slot * ENTRY_LEN
    data[off] = 0xD0 | (data[off] & 15)
    return 'deepen'


NAMED = tuple(corrupt_prodos.CORRUPTIONS)


def mut_named(data, m, rng):
    """One to three of the named corruptions of tools/corrupt_prodos.py.

    The inventory is taken once from the pristine seed, as
    `corrupt_prodos.apply` does; unlike it, a corruption this seed cannot
    host (no extended file on a floppy, no padding in a full bitmap page)
    is skipped rather than dropping the ones after it.
    """
    names = rng.sample(NAMED, rng.randrange(1, 4))
    inv = corrupt_prodos.Inventory(bytes(data))
    done = []
    for name in names:
        try:
            corrupt_prodos.CORRUPTIONS[name](data, inv)
            done.append(name)
        except (SystemExit, IndexError):    # a shape this seed does not have
            pass
    return 'named:' + (','.join(sorted(done)) or 'none')


STRUCTURED = (mut_entry, mut_dirheader, mut_index, mut_bitmap, mut_volume,
              mut_bytes, mut_fork)


def mut_combo(data, m, rng):
    """Two structured mutations at once."""
    a, b = rng.sample(STRUCTURED, 2)
    return 'combo:' + a(data, m, rng) + '+' + b(data, m, rng)


# (mutator, weight). The blind ones are cheap and the structured ones are
# what reaches a named check, so the weights lean on the structured side;
# data blocks are the payload whose integrity invariant 5 checks, so they
# are mutated on purpose in a small share of cases only.
MUTATORS = ((mut_entry, 22), (mut_dirheader, 14), (mut_index, 10),
            (mut_bitmap, 12), (mut_volume, 8), (mut_bytes, 10),
            (mut_fork, 6), (mut_named, 12), (mut_combo, 10), (mut_data, 2),
            (mut_deepen, 2))
_TOTAL_WEIGHT = sum(w for _, w in MUTATORS)


def mutate(seed, rng):
    """One mutated image, and the tag of the mutator that made it."""
    data = bytearray(seed.data)
    n = rng.randrange(_TOTAL_WEIGHT)
    for fn, weight in MUTATORS:
        if n < weight:
            return data, fn(data, seed, rng)
        n -= weight
    raise AssertionError


# -- running the harnesses --------------------------------------------------
class Crash(Exception):
    def __init__(self, what, detail):
        super().__init__(what)
        self.what = what
        self.detail = detail


def _run(args, timeout, what):
    try:
        p = subprocess.run(args, env=dict(os.environ, **SAN_ENV),
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=timeout)
    except subprocess.TimeoutExpired:
        raise Crash(what + ': hang', 'no answer in %gs' % timeout)
    if p.returncode:
        raise Crash(what + ': exit %d' % p.returncode,
                    p.stderr.decode('utf-8', 'replace')[-4000:])
    try:
        return json.loads(p.stdout)
    except ValueError as e:
        raise Crash(what + ': unreadable output', '%s\n%s' % (
            e, p.stdout.decode('utf-8', 'replace')[:2000]))


def run_fixit(exe, path, timeout):
    return _run([exe, str(path), 'run', '', '', '', '', ''], timeout, 'FIXIT')


def run_repair(exe, path, timeout, **kw):
    args = [exe, str(path)] + ['%s=%s' % (k, v) for k, v in sorted(kw.items())]
    r = _run(args, timeout, 'REPAIR')
    r['counts'] = {test_repair.IDS[int(k)]: v for k, v in r['counts'].items()}
    return r


def read_dump(path):
    """The writes an uninjected run made: block -> the contents it wrote."""
    out = {}
    if not path.exists():
        return out
    raw = path.read_bytes()
    for i in range(0, len(raw) - 513, 514):
        block = raw[i] | (raw[i + 1] << 8)
        out.setdefault(block, []).append(raw[i + 2:i + 514])
    return out


# -- the allow-list ---------------------------------------------------------
# Divergences between the C walker and the host oracle that are a property of
# the two designs and not a fault. Each carries the line of docs/FIXIT.md
# that documents it; the summary counts how often each fired. Nothing is ever
# hidden: a divergence that is not one of these is a failure of invariant 2.
ALLOWED = {
    # docs/FIXIT.md section 3, row 5: "l'oracle hote compare a la taille de
    # l'image". A header that declares FEWER blocks than the image holds is
    # HDR_TOTAL for the oracle and nothing at all for the walker, which can
    # read the last block it declares. Both then walk with the same total,
    # so this is the only counter that differs.
    'HDR_TOTAL_SHORT': 'header total below the image size: the oracle alone calls it HDR_TOTAL',
    # docs/FIXIT.md section 4, "Une bitmap complete des blocs references est
    # ecartee": the walker keeps `seen` for one 4096-block window at a time
    # and walks the whole tree once per window, so a block reached twice is
    # only ever seen as reached twice in the window that HOLDS it. A loop or
    # a cross-link whose two ends fall in different windows is therefore
    # named in one window and not in the other, and the walk of the window
    # that misses it goes on into whatever the pointer leads to -- where it
    # names faults the oracle, which stopped at the loop, never reaches.
    # It is a divergence of the report only: whichever window names it, the
    # pass is marked incomplete, and REPAIR refuses an incomplete pass
    # before the plan screen (`Scan incomplete: no repair.`), so nothing is
    # written. The allowance is therefore limited to that state.
    'WINDOW_LOOP': 'loop across bitmap windows on a volume of more than 4096 blocks, both passes incomplete',
}


def allowance(data, oracle, oracle_counts, fixit_counts, fixit_complete):
    """The documented divergences, applied to the oracle's counters.

    Returns (adjusted counters, the allowances that fired, whether the
    counters are comparable at all).
    """
    fired = []
    counts = dict(oracle_counts)
    total = int.from_bytes(data[2 * BLOCK + 4 + 0x25:2 * BLOCK + 4 + 0x27], 'little')
    image_blocks = len(data) // BLOCK
    if (prodos_check.MIN_BLOCKS <= total < image_blocks
            and counts.get('HDR_TOTAL') and not fixit_counts.get('HDR_TOTAL')):
        counts['HDR_TOTAL'] -= 1
        if not counts['HDR_TOTAL']:
            del counts['HDR_TOTAL']
        fired.append('HDR_TOTAL_SHORT')
    # Counted only when the two really part company: a multi-window volume
    # whose pass is incomplete usually still agrees, and an allowance that
    # fired on every such case would say nothing.
    if (counts != fixit_counts and total > 4096
            and not oracle.complete and not fixit_complete):
        fired.append('WINDOW_LOOP')
        return counts, fired, False
    return counts, fired, True


# -- one case ---------------------------------------------------------------
class Case:
    """Everything one mutated image produced, and what went wrong with it."""

    def __init__(self, index, seed_name, mutator, data):
        self.index = index
        self.seed = seed_name
        self.mutator = mutator
        self.data = bytes(data)
        self.failures = []              # (invariant, one-line reason)
        self.fired = []                 # allowances that fired
        self.ids = set()                # what the oracle found: coverage
        self.runs = {}                  # name -> the JSON of a harness run
        self.wrote = 0

    def fail(self, invariant, reason):
        self.failures.append((invariant, reason))


def differential(case, fx, rp, data, oracle):
    """Invariant 2: FIXIT is the oracle, and REPAIR's plan is FIXIT."""
    oracle_counts = {k: v for k, v in Counter(f.id for f in oracle.findings).items()
                     if k not in prodos_check.DEVICE_ONLY}
    fixit_counts = {k: v for k, v in fx['counts'].items()
                    if k not in prodos_check.DEVICE_ONLY}
    if fx['note'] in NO_WALK or fx['failed'] or fx['counts'].get('IO_ERROR'):
        return                          # the walker never saw the volume
    adjusted, fired, comparable = allowance(data, oracle, oracle_counts,
                                            fixit_counts, fx['complete'])
    case.fired += fired
    if not comparable:
        if bool(fx['complete']) != oracle.complete:
            case.fail('2-differential', 'complete: FIXIT %d, oracle %s'
                      % (fx['complete'], oracle.complete))
        return
    if fixit_counts != adjusted:
        only_c = {k: v for k, v in fixit_counts.items() if adjusted.get(k) != v}
        only_o = {k: v for k, v in adjusted.items() if fixit_counts.get(k) != v}
        case.fail('2-differential', 'FIXIT %s vs oracle %s' % (only_c, only_o))
    if bool(fx['complete']) != oracle.complete:
        case.fail('2-differential', 'complete: FIXIT %d, oracle %s'
                  % (fx['complete'], oracle.complete))
    if rp['note'] in NO_WALK or rp['failed']:
        return
    kept_fx = {k: v for k, v in fx['counts'].items() if k not in DROPPED}
    kept_rp = {k: v for k, v in rp['counts'].items() if k not in DROPPED}
    if kept_fx != kept_rp:
        case.fail('2-differential', 'REPAIR plan %s vs FIXIT %s' % (kept_rp, kept_fx))
    if fx['complete'] != rp['complete']:
        case.fail('2-differential', 'complete: FIXIT %d, REPAIR %d'
                  % (fx['complete'], rp['complete']))


def check_writes(case, writes, before, after, w):
    """Invariant 4: every written block is one the oracle calls a directory
    block, or a page of the bitmap. Never an index block, never a file's
    data block, never block 0 or 1."""
    allowed = set(w.dirblocks) | set(w.bitmap_pages)
    for b in {x['block'] for x in writes}:
        if b in allowed:
            continue
        kind = ('index block' if b in w.index_blocks else
                'extended key block' if b in w.ext_keys else
                'boot block' if b < 2 else 'unwalked block')
        case.fail('4-writes', 'block %u written: %s' % (b, kind))
    for b in changed_blocks(before, after) - allowed:
        case.fail('4-writes', 'block %u changed and is no directory or bitmap block' % b)


def check_files(case, before, after, w):
    """Invariant 5: no file lost or altered a byte, and no entry moved."""
    w2, _ = walked(after)
    got = file_bytes(after, w.files)
    want = file_bytes(before, w.files)
    for k, v in w.files.items():
        if k not in w2.files:
            case.fail('5-files', 'entry %s disappeared from block %u slot %u'
                      % (v[0], k[0], k[1]))
            continue
        if w2.files[k] != v:
            case.fail('5-files', 'entry %s moved: %s -> %s' % (v[0], v, w2.files[k]))
        if got[k] != want[k]:
            n = next((i for i in range(min(len(got[k]), len(want[k])))
                      if got[k][i] != want[k][i]), min(len(got[k]), len(want[k])))
            case.fail('5-files', 'file %s changed at byte %u (%u -> %u bytes)'
                      % (v[0], n, len(want[k]), len(got[k])))


def oracle_ids(result):
    return {f.id for f in result.findings if f.id not in prodos_check.DEVICE_ONLY}


def monotone(case, before_ids, after_result, note, allow):
    """Invariant 6: nothing new, and the verdict is the truth."""
    after_ids = oracle_ids(after_result)
    new = after_ids - before_ids - allow
    if new:
        case.fail('6-monotone', 'new after the repair: %s' % sorted(new))
    if note.startswith('Applied') and note.endswith('repaired.'):
        left = after_ids - DROPPED - allow
        if left:
            case.fail('6-monotone', '"repaired" but the oracle still finds %s'
                      % sorted(left))
    elif note.startswith('Applied') and 'still reports' in note:
        claimed = int(note.split('still reports')[1].split()[0])
        counted = sum(1 for f in after_result.findings
                      if f.id not in prodos_check.DEVICE_ONLY and f.id not in DROPPED)
        if claimed != counted and not allow:
            case.fail('6-monotone', 'note says %u findings, the oracle counts %u'
                      % (claimed, counted))


def injection(case, exe, work, before, repaired, written, timeout, rng, nwrite):
    """Invariant 7: a write error, a bad readback or a failed restore.

    A correction whose restore SUCCEEDED does not stop the walk: section 5
    says the corrections are independent, so the run goes on and the ones
    after it are applied to the block as it was put back. The image is then
    neither the one it started from nor the fully repaired one -- it is the
    original with a SUBSET of the corrections in it. What must hold is
    byte for byte: every byte is either the one the volume had or the one a
    complete repair writes there, and no block the uninjected run never
    wrote has moved at all. Nothing invented, nothing half written.
    """
    kind = rng.choice(['errwrite', 'badread', 'failall'])
    at = rng.randrange(1, nwrite + 1)
    kw = {'keys': 'F', 'answer': 'FIX'}
    kw[kind] = 1 if kind == 'failall' else at
    path = work / 'inject.po'
    path.write_bytes(before)
    r = run_repair(exe, path, timeout, **kw)
    after = path.read_bytes()
    case.runs['inject-' + kind] = r
    where = '%s at %u' % (kind, at)
    if kind == 'failall':
        if after != before:
            case.fail('7-injection', 'failall: the image moved although no write landed')
        if 'not restored' not in r['note']:
            case.fail('7-injection', 'failall: note is %r, not a refusal' % r['note'])
        return r
    moved = changed_blocks(before, after)
    for b in sorted(moved):
        for i in range(b * BLOCK, (b + 1) * BLOCK):
            if after[i] != before[i] and after[i] != repaired[i]:
                case.fail('7-injection',
                          '%s: byte %u of block %u is neither what it was nor '
                          'what a complete repair writes' % (where, i % BLOCK, b))
                break
    for b in sorted(moved - written):
        case.fail('7-injection', '%s: block %u moved and no write ever named it'
                  % (where, b))
    if 'not restored' in r['note'] and moved:
        named = int(r['note'].split()[1])
        if moved - {named}:
            case.fail('7-injection', '"not restored %u" but blocks %s also moved'
                      % (named, sorted(moved - {named})))
    return r


def one_case(index, seeds, exes, timeout, out, inject_share, bug):
    """Run one mutated image through everything, and judge it."""
    rng = random.Random(index)
    seed = seeds[rng.choice(sorted(seeds))]
    data, tag = mutate(seed, rng)
    data = bytes(data)
    case = Case(index, seed.name, tag, data)

    with tempfile.TemporaryDirectory(prefix='a2fc-fuzz-prodos-') as tmp:
        work = Path(tmp)
        try:
            w, oracle = walked(data)
            case.ids = oracle_ids(oracle)

            # (1) FIXIT: it reads, and the image must come back untouched.
            path = work / 'fixit.po'
            path.write_bytes(data)
            fx = run_fixit(exes['fixit'], path, timeout)
            case.runs['fixit'] = fx
            if path.read_bytes() != data:
                case.fail('1-readonly', 'FIXIT wrote to the volume')

            # (2) REPAIR, the plan alone: Escape at the plan screen.
            path = work / 'plan.po'
            path.write_bytes(data)
            plan = run_repair(exes['repair'], path, timeout)
            case.runs['plan'] = plan
            after_plan = path.read_bytes()
            if plan['nwrite'] or after_plan != data:
                case.fail('3-refusal', 'the plan screen wrote %u block(s)'
                          % plan['nwrite'])

            differential(case, fx, plan, data, oracle)

            # (3) REPAIR with the word FIX.
            path = work / 'fix.po'
            path.write_bytes(data)
            dump = work / 'writes.bin'
            kw = {'keys': 'F', 'answer': 'FIX', 'wdump': str(dump)}
            if bug:
                kw['bug'] = 1
            fix = run_repair(exes['repair'], path, timeout, **kw)
            case.runs['fix'] = fix
            after = path.read_bytes()
            case.wrote = fix['nwrite']

            refused = (fix['note'] in NO_WALK
                       or fix['note'] in (test_repair.M_CLEAN, test_repair.M_NOPLAN,
                                          test_repair.M_CANCEL, test_repair.M_IOERR,
                                          test_repair.M_XLINK, test_repair.M_PARTIAL,
                                          test_repair.M_BOOTVOL, test_repair.M_CHANGED,
                                          test_repair.M_NOTHING)
                       or not fix['corr'])
            if refused:
                if fix['nwrite'] or after != data:
                    case.fail('3-refusal', 'note %r wrote %u block(s)'
                              % (fix['note'], fix['nwrite']))
            check_writes(case, fix['writes'], data, after, w)
            check_files(case, data, after, w)

            allow = set()
            _, fired, _ok = allowance(data, oracle,
                                      Counter(f.id for f in oracle.findings),
                                      fx['counts'], fx['complete'])
            if 'HDR_TOTAL_SHORT' in fired:
                allow.add('HDR_TOTAL')
            after_result = prodos_check.check(after)
            monotone(case, case.ids, after_result, fix['note'], allow)

            # (4) a second REPAIR over the repaired volume writes nothing.
            if fix['nwrite'] and not bug:
                path = work / 'again.po'
                path.write_bytes(after)
                again = run_repair(exes['repair'], path, timeout,
                                   keys='F', answer='FIX')
                case.runs['again'] = again
                if again['nwrite']:
                    case.fail('6-monotone', 'a second run writes %u more block(s): %s'
                              % (again['nwrite'], again['note']))
                if path.read_bytes() != after:
                    case.fail('6-monotone', 'a second run changed the repaired image')

            # (5) the failure injections, on a share of the cases that write.
            if fix['nwrite'] and not bug and rng.random() < inject_share:
                injection(case, exes['repair'], work, data, after,
                          set(read_dump(dump)), timeout, rng, fix['nwrite'])
        except Crash as e:
            case.fail('1-crash', '%s: %s' % (e.what, e.detail.splitlines()[-1]
                                             if e.detail.strip() else ''))
            case.runs['crash'] = {'what': e.what, 'detail': e.detail}

    if case.failures and out is not None:
        save(case, out)
    return {'index': index, 'seed': case.seed, 'mutator': case.mutator,
            'failures': case.failures, 'fired': case.fired,
            'ids': sorted(case.ids), 'wrote': case.wrote}


def save(case, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    stem = out / ('case-%06d' % case.index)
    stem.with_suffix('.po').write_bytes(case.data)
    stem.with_suffix('.json').write_text(json.dumps({
        'case': case.index, 'seed': case.seed, 'mutator': case.mutator,
        'failures': case.failures, 'runs': case.runs}, indent=1) + '\n')
    stem.with_suffix('.txt').write_text(
        'case %d  seed %s  mutator %s\n%s\n'
        % (case.index, case.seed, case.mutator,
           '\n'.join('%-14s %s' % f for f in case.failures)))


# -- the campaign -----------------------------------------------------------
_STATE = {}


def _init(seeds, exes, timeout, out, inject_share, bug):
    _STATE.update(seeds=seeds, exes=exes, timeout=timeout, out=out,
                  inject_share=inject_share, bug=bug)


def _work(index):
    return one_case(index, _STATE['seeds'], _STATE['exes'], _STATE['timeout'],
                    _STATE['out'], _STATE['inject_share'], _STATE['bug'])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--count', type=int, default=200, help='how many cases')
    ap.add_argument('--seed', type=int, default=1, help='the campaign seed')
    ap.add_argument('--out', type=Path, default=ROOT / 'build/fuzz-prodos',
                    help='where a failing case keeps its image and its JSON')
    ap.add_argument('--workers', type=int, default=0, help='parallel cases')
    ap.add_argument('--timeout', type=float, default=30.0,
                    help='seconds a single harness run may take')
    ap.add_argument('--inject-share', type=float, default=0.25,
                    help='share of the writing cases that get a failure injected')
    ap.add_argument('--bug', action='store_true',
                    help='plant a lost write in the harness: invariant 6 must catch it')
    ap.add_argument('--verbose', action='store_true',
                    help='print how many cases produced each check id')
    ap.add_argument('--quiet', action='store_true')
    a = ap.parse_args(argv)

    with tempfile.TemporaryDirectory(prefix='a2fc-fuzz-prodos-seeds-') as tmp:
        work = Path(tmp)
        exes = build_harnesses(work)
        seeds = build_seeds(work)
        # The case numbers: a campaign seed picks a disjoint band, so case
        # 7 of seed 1 is always the same image and reproduces on its own.
        base = int(hashlib.sha256(str(a.seed).encode()).hexdigest()[:8], 16) & 0x3FFFFFF
        indexes = [base * 1000 + i for i in range(a.count)]
        results = []
        workers = a.workers or min(os.cpu_count() or 1, 8)
        if workers > 1:
            with ProcessPoolExecutor(max_workers=workers, initializer=_init,
                                     initargs=(seeds, exes, a.timeout, a.out,
                                               a.inject_share, a.bug)) as pool:
                for r in pool.map(_work, indexes, chunksize=1):
                    results.append(r)
        else:
            _init(seeds, exes, a.timeout, a.out, a.inject_share, a.bug)
            for i in indexes:
                results.append(_work(i))

    return report(results, a)


def report(results, a):
    failures = Counter()
    fired = Counter()
    mutators = Counter()
    seen = Counter()
    bad = [r for r in results if r['failures']]
    wrote = 0
    for r in results:
        mutators[r['mutator'].split(':')[0].split('.')[0]] += 1
        for id in r['ids']:
            seen[id] += 1
        for name in r['fired']:
            fired[name] += 1
        for invariant, _ in r['failures']:
            failures[invariant] += 1
        wrote += 1 if r['wrote'] else 0

    if not a.quiet:
        print('cases           %d (seed %d, %d with a write)'
              % (len(results), a.seed, wrote))
        print('failing cases   %d' % len(bad))
        print('invariants      %s' % (dict(sorted(failures.items())) or 'all held'))
        print('divergences     %s' % (dict(sorted(fired.items())) or 'none fired'))
        print('mutators        %s' % dict(sorted(mutators.items())))
        missing = [k for k in IMAGE_IDS if not seen[k]]
        print('check coverage  %d/%d ids' % (len(IMAGE_IDS) - len(missing), len(IMAGE_IDS)))
        if a.verbose:
            for id in IMAGE_IDS:
                print('  %-15s %d' % (id, seen[id]))
        if missing:
            print('never produced  %s' % ' '.join(missing))
        for r in bad[:20]:
            print('FAIL case %d (%s, %s)' % (r['index'], r['seed'], r['mutator']))
            for invariant, why in r['failures']:
                print('     %-14s %s' % (invariant, why))
        if bad:
            print('%d failing image(s) kept in %s' % (len(bad), a.out))
    return 1 if bad else 0


if __name__ == '__main__':
    raise SystemExit(main())
