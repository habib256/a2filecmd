#!/usr/bin/env python3
"""Reference ProDOS volume checker: the host oracle for the FIXIT overlay.

FIXIT will walk a volume on the Apple II -- a read pass first, repairs later.
This module is the ground truth that walker is compared against: it reads a
ProDOS-order image and names every inconsistency it can find, as findings
carrying a stable identifier, the block and the entry slot concerned, the
expected and the found value, and the ProDOS path of the entry. It never
writes anything: `check` takes bytes and returns findings.

    python3 tools/prodos_check.py IMAGE.po [--json]

and exits 1 when the image has at least one finding, 0 when it is healthy.

Library:

    result = check(data)            # Result(findings, complete)
    to_json(result.findings)        # list of dicts, deterministically sorted
    envelope(result)                # {"complete": bool, "findings": [...]}

`complete` is False when the walk could not see the whole volume: a directory
loop, the depth limit, a chain pointer that leads nowhere, or a bitmap the
header does not locate. BM_LOST is then not reported at all, because a block
nobody claims may belong to the part of the tree the walk could not reach.
BM_USED_FREE is still reported: a claim we did make is a fact.

Conventions that keep the report readable, and that the C walker mirrors:

  * `expected` is the truth the checker computed, `found` is what the image
    stores. Either may be None when the check has no such value.
  * a structural defect that hides part of a file (bad key, unknown storage
    type, out-of-range index pointer, bad fork) marks the entry partial, and
    the derived count check (FILE_BLOCKS) is then skipped: FIXIT wants the
    cause, not the arithmetic that follows from it. The pass stays complete,
    so BM_LOST is still reported for the blocks that entry no longer reaches.
  * DIR_CHAIN is about one back-pointer, VOLDIR_SIZE about the shape of the
    volume directory: a volume directory that grew a fifth, well-formed block
    yields VOLDIR_SIZE alone, and a chain cut short by a bad `next` yields
    DIR_CHAIN alone -- the blocks the walk never saw are not a shape.
  * blocks 0, 1, 2 to 5 and the bitmap blocks are reserved: marked free they
    are BM_RESERVED, never BM_USED_FREE, and never BM_LOST.
  * a directory key or a chain pointer that names a block the walk has
    already reached -- another directory, a boot block, a block a file
    claims -- is DIR_LOOP, not a longer chain: read on as a directory, file
    data would only spell findings out of what it is not.

`CHECKS` is the identifier list, in the order of section 3 of docs/FIXIT.md,
and is meant to be read as the C enum. `DEVICE_ONLY` names the two checks that
need a device rather than an image -- a failed READ_BLOCK, and the block 2 name
against what ON_LINE reports -- and this module never emits them.
"""
import argparse
import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

BLOCK = 512
ENTRY_LEN = 39
ENTRIES_PER_BLOCK = 13
VOLUME_DIR = 2
VOLUME_DIR_BLOCKS = (2, 3, 4, 5)  # fixed by ProDOS: it cannot grow
MIN_BLOCKS = 6                    # blocks 0-1 boot, 2-5 the volume directory
MAX_DEPTH = 16                    # ProDOS nesting limit, as in volinfo.c
ACCESS_RESERVED = 0x1C            # bits 4..2 of the access byte, always zero

SEEDLING, SAPLING, TREE, EXTENDED, SUBDIR = 1, 2, 3, 5, 0xD
FILE_STORAGE = (SEEDLING, SAPLING, TREE, EXTENDED, SUBDIR)
FORK_STORAGE_TYPES = (SEEDLING, SAPLING, TREE)
CAPACITY = {SEEDLING: BLOCK, SAPLING: 256 * BLOCK, TREE: 256 * 256 * BLOCK}

CHECKS = (
    'HDR_STORAGE', 'HDR_ENTRY_LEN', 'HDR_PER_BLOCK', 'HDR_BITMAP', 'HDR_TOTAL',
    'DIR_CHAIN', 'DIR_LOOP', 'DIR_HEADER', 'DIR_PARENT', 'DIR_DEPTH',
    'ENT_STORAGE', 'ENT_NAME', 'ENT_HEADER_PTR', 'ENT_KEY',
    'FILE_COUNT', 'DIR_BLOCKS', 'DIR_EOF', 'FILE_BLOCKS', 'FILE_EOF',
    'IDX_RANGE', 'FORK_STORAGE',
    'XLINK', 'BM_USED_FREE', 'BM_LOST',
    # Rows 25 to 30 of docs/FIXIT.md: FIXIT checks this module also names, so
    # that the C enum and the oracle stay one single list.
    'IO_ERROR', 'HDR_NAME', 'VOLDIR_SIZE', 'ENT_ACCESS', 'BM_RESERVED', 'BM_TAIL',
)

DEVICE_ONLY = ('IO_ERROR', 'HDR_NAME')   # need a device: never emitted here


@dataclass(frozen=True)
class Finding:
    """One inconsistency. `slot` is the entry index in `block`, or None."""
    id: str
    block: int
    slot: int = None
    expected: int = None
    found: int = None
    path: str = ''


@dataclass(frozen=True)
class Result:
    findings: list
    complete: bool

    def __iter__(self):                     # allows: findings, complete = check(d)
        return iter((self.findings, self.complete))


def sort_key(f):
    """Total order on findings: id, block, slot, then the remaining fields."""
    none_last = -1
    return (f.id, f.block,
            none_last if f.slot is None else f.slot, f.path,
            none_last if f.expected is None else f.expected,
            none_last if f.found is None else f.found)


def to_json(findings):
    return [asdict(f) for f in sorted(findings, key=sort_key)]


def envelope(result):
    return {'complete': result.complete, 'findings': to_json(result.findings)}


def valid_name(raw):
    """A ProDOS name: 1-15 chars, a letter first, then letters, digits, '.'."""
    if not 1 <= len(raw) <= 15:
        return False
    if not 0x41 <= raw[0] <= 0x5A:
        return False
    return all(0x41 <= c <= 0x5A or 0x30 <= c <= 0x39 or c == 0x2E for c in raw)


def load(path):
    """Image bytes, with the 64-byte 2IMG header removed when there is one."""
    data = Path(path).read_bytes()
    if data[:4] == b'2IMG':
        offset = int.from_bytes(data[24:28], 'little')
        length = int.from_bytes(data[28:32], 'little')
        data = data[offset:offset + length] if length else data[offset:]
    return data


class Checker:
    def __init__(self, data):
        self.d = bytes(data)
        self.image_blocks = len(self.d) // BLOCK
        self.findings = []
        self.complete = True
        self.owner = {}                     # block -> path of its first claimant
        self.total = self.image_blocks
        self.bitmap = 0
        self.bitmap_blocks = 0
        self.bitmap_ok = False
        self.volume = ''
        self.volume_files = 0
        self.root_chain = []
        self.root_cut = False

    # -- primitives ---------------------------------------------------------
    def readable(self, n):
        return 0 <= n < self.image_blocks

    def block(self, n):
        return self.d[n * BLOCK:(n + 1) * BLOCK]

    def add(self, id, block, slot=None, expected=None, found=None, path=''):
        self.findings.append(Finding(id, block, slot, expected, found, path))

    def claim(self, b, path):
        """Record that `path` uses block `b`; a second claim is a cross-link."""
        if b in self.owner:
            self.add('XLINK', b, None, None, None, path)
            return False
        self.owner[b] = path
        return True

    # -- the volume header --------------------------------------------------
    def header(self):
        e = self.block(VOLUME_DIR)[4:4 + ENTRY_LEN]
        if len(e) < ENTRY_LEN:
            self.add('HDR_TOTAL', VOLUME_DIR, 0, self.image_blocks, 0, '')
            self.complete = False
            return False
        name = e[1:1 + (e[0] & 15)]
        self.volume = '/' + name.decode('ascii', 'replace')
        if e[0] >> 4 != 0xF:
            self.add('HDR_STORAGE', VOLUME_DIR, 0, 0xF, e[0] >> 4, self.volume)
        if not valid_name(name):
            self.add('ENT_NAME', VOLUME_DIR, 0, None, e[0] & 15, self.volume)
        if e[0x1F] != ENTRY_LEN:
            self.add('HDR_ENTRY_LEN', VOLUME_DIR, 0, ENTRY_LEN, e[0x1F], self.volume)
        if e[0x20] != ENTRIES_PER_BLOCK:
            self.add('HDR_PER_BLOCK', VOLUME_DIR, 0, ENTRIES_PER_BLOCK, e[0x20], self.volume)
        self.volume_files = int.from_bytes(e[0x21:0x23], 'little')

        total = int.from_bytes(e[0x25:0x27], 'little')
        # Under six blocks a volume cannot even hold its own root: blocks 0
        # and 1 boot, 2 to 5 the volume directory. fixit.c refuses the same.
        if total != self.image_blocks or total < MIN_BLOCKS:
            self.add('HDR_TOTAL', VOLUME_DIR, 0, self.image_blocks, total, self.volume)
        self.total = total if MIN_BLOCKS <= total <= self.image_blocks else self.image_blocks

        self.bitmap = int.from_bytes(e[0x23:0x25], 'little')
        self.bitmap_blocks = (self.total + 4095) // 4096
        if (self.bitmap < 3 or self.bitmap >= self.total
                or self.bitmap + self.bitmap_blocks > self.total):
            self.add('HDR_BITMAP', VOLUME_DIR, 0, None, self.bitmap, self.volume)
            self.complete = False
        else:
            self.bitmap_ok = True
        return True

    # -- directories --------------------------------------------------------
    def directory(self, key, path, depth, parent, declared):
        """Walk one directory chain. Returns (its blocks, cut)."""
        if depth > MAX_DEPTH:
            self.add('DIR_DEPTH', key, None, MAX_DEPTH, depth, path)
            self.complete = False
            return [], True
        if key in self.owner:
            # A block the walk has already reached -- another directory, or a
            # block a file claims -- is not a longer chain, it is a loop. Read
            # on as a directory it would only spell findings out of file data.
            self.add('DIR_LOOP', key, None, None, key, path)
            self.complete = False
            return [], True

        chain, count, cut = [], 0, False
        block, prev = key, 0
        while True:
            self.claim(block, path)
            chain.append(block)
            b = self.block(block)
            if len(b) < BLOCK:              # a truncated image, not a ProDOS fault
                self.add('DIR_CHAIN', block, None, None, None, path)
                self.complete, cut = False, True
                break
            if int.from_bytes(b[0:2], 'little') != prev:
                self.add('DIR_CHAIN', block, None, prev,
                         int.from_bytes(b[0:2], 'little'), path)
            first = 1 if block == key else 0
            if block == key and depth > 1:
                declared = self.subdir_header(b, key, path, parent)
            for slot in range(first, ENTRIES_PER_BLOCK):
                e = b[4 + slot * ENTRY_LEN:4 + (slot + 1) * ENTRY_LEN]
                if not e[0] >> 4:
                    continue
                count += 1
                self.entry(e, block, slot, path, key, depth)
            nxt = int.from_bytes(b[2:4], 'little')
            if not nxt:
                break
            if nxt in self.owner:
                self.add('DIR_LOOP', block, None, None, nxt, path)
                self.complete, cut = False, True
                break
            # Blocks 0 and 1 are the boot blocks: a chain never leads there.
            # The walk claims both before it starts, so a `next` of 1 is
            # already a loop above; the bound mirrors fixit.c all the same.
            if nxt < VOLUME_DIR or nxt >= self.total or not self.readable(nxt):
                self.add('DIR_CHAIN', block, None, None, nxt, path)
                self.complete, cut = False, True
                break
            prev, block = block, nxt

        if declared is not None and not cut and count != declared:
            self.add('FILE_COUNT', key, 0, count, declared, path)
        if depth == 1:
            self.root_chain, self.root_cut = chain, cut
        return chain, cut

    def subdir_header(self, b, key, path, parent):
        """Check a subdirectory header; returns its declared file count."""
        e = b[4:4 + ENTRY_LEN]
        if e[0] >> 4 != 0xE:
            self.add('DIR_HEADER', key, 0, 0xE, e[0] >> 4, path)
        if not valid_name(e[1:1 + (e[0] & 15)]):
            self.add('ENT_NAME', key, 0, None, e[0] & 15, path)
        if e[0x1F] != ENTRY_LEN:
            self.add('DIR_HEADER', key, 0, ENTRY_LEN, e[0x1F], path)
        if e[0x20] != ENTRIES_PER_BLOCK:
            self.add('DIR_HEADER', key, 0, ENTRIES_PER_BLOCK, e[0x20], path)
        pointer = int.from_bytes(e[0x23:0x25], 'little')
        # One DIR_PARENT at most: the first of the three fields that is wrong.
        if pointer != parent[0]:
            self.add('DIR_PARENT', key, 0, parent[0], pointer, path)
        elif e[0x25] != parent[1] + 1:
            self.add('DIR_PARENT', key, 0, parent[1] + 1, e[0x25], path)
        elif e[0x26] != ENTRY_LEN:
            self.add('DIR_PARENT', key, 0, ENTRY_LEN, e[0x26], path)
        return int.from_bytes(e[0x21:0x23], 'little')

    # -- entries ------------------------------------------------------------
    def entry(self, e, block, slot, dirpath, dirkey, depth):
        storage = e[0] >> 4
        raw = e[1:1 + (e[0] & 15)]
        path = dirpath + '/' + raw.decode('ascii', 'replace')
        if not valid_name(raw):
            self.add('ENT_NAME', block, slot, None, e[0] & 15, path)
        pointer = int.from_bytes(e[0x25:0x27], 'little')
        if pointer != dirkey:
            self.add('ENT_HEADER_PTR', block, slot, dirkey, pointer, path)
        if e[0x1E] & ACCESS_RESERVED:
            self.add('ENT_ACCESS', block, slot, None, e[0x1E], path)
        key = int.from_bytes(e[0x11:0x13], 'little')
        used = int.from_bytes(e[0x13:0x15], 'little')
        eof = int.from_bytes(e[0x15:0x18], 'little')

        if storage not in FILE_STORAGE:
            self.add('ENT_STORAGE', block, slot, None, storage, path)
            return
        bad_key = key < 2 or key >= self.total
        if bad_key:
            self.add('ENT_KEY', block, slot, None, key, path)

        if storage == SUBDIR:
            if bad_key:
                return
            chain, cut = self.directory(key, path, depth + 1, (block, slot), None)
            if cut:
                return
            if used != len(chain):
                self.add('DIR_BLOCKS', block, slot, len(chain), used, path)
            if eof != len(chain) * BLOCK:
                self.add('DIR_EOF', block, slot, len(chain) * BLOCK, eof, path)
            return

        if storage == EXTENDED:
            reached, partial = self.extended(key, bad_key, path)
        else:
            if eof > CAPACITY[storage]:
                self.add('FILE_EOF', block, slot, CAPACITY[storage], eof, path)
            if bad_key:
                reached, partial = 0, True
            else:
                reached, partial = self.fork(storage, key, path)
        if not partial and reached != used:
            self.add('FILE_BLOCKS', block, slot, reached, used, path)

    def extended(self, key, bad_key, path):
        """The key block of an extended file: two mini-entries, at 0 and 256."""
        if bad_key:
            return 0, True
        self.claim(key, path)
        reached, partial = 1, False
        b = self.block(key)
        for i, offset in enumerate((0, 256)):
            m = b[offset:offset + 8]
            storage = m[0]
            fkey = int.from_bytes(m[1:3], 'little')
            feof = int.from_bytes(m[5:8], 'little')
            if storage not in FORK_STORAGE_TYPES:
                self.add('FORK_STORAGE', key, i, None, storage, path)
                partial = True
                continue
            if feof > CAPACITY[storage]:
                self.add('FILE_EOF', key, i, CAPACITY[storage], feof, path)
            if fkey < 2 or fkey >= self.total:
                self.add('ENT_KEY', key, i, None, fkey, path)
                partial = True
                continue
            n, p = self.fork(storage, fkey, path)
            reached += n
            partial = partial or p
        return reached, partial

    def fork(self, storage, key, path):
        """Blocks a seedling/sapling/tree reaches, and whether it is partial."""
        self.claim(key, path)
        if storage == SEEDLING:
            return 1, False
        reached, partial = 1, False
        b = self.block(key)
        for i in range(256):
            p = b[i] | (b[256 + i] << 8)
            if not p:
                continue                    # a sparse hole, at any level
            if p < 2 or p >= self.total:
                self.add('IDX_RANGE', key, i, None, p, path)
                partial = True
                continue
            if storage == SAPLING:
                self.claim(p, path)
                reached += 1
            else:
                n, sub = self.fork(SAPLING, p, path)
                reached += n
                partial = partial or sub
        return reached, partial

    def volume_dir_shape(self):
        """The volume directory is blocks 2, 3, 4 and 5, in that order.

        The finding names the first block that does not belong to that shape:
        the block found where another was expected, or the fifth block of a
        chain that is too long, with `expected` then the length ProDOS fixes
        and `found` the length this volume has. A chain the walk could not
        follow to its end says nothing about the shape, so it says nothing.
        """
        chain = self.root_chain
        if self.root_cut or not chain:
            return
        for i, expected in enumerate(VOLUME_DIR_BLOCKS):
            if i >= len(chain):
                self.add('VOLDIR_SIZE', chain[-1], None, len(VOLUME_DIR_BLOCKS),
                         len(chain), self.volume)
                return
            if chain[i] != expected:
                self.add('VOLDIR_SIZE', chain[i], None, expected, chain[i], self.volume)
                return
        if len(chain) > len(VOLUME_DIR_BLOCKS):
            self.add('VOLDIR_SIZE', chain[len(VOLUME_DIR_BLOCKS)], None,
                     len(VOLUME_DIR_BLOCKS), len(chain), self.volume)

    # -- the allocation bitmap ---------------------------------------------
    def bitmap_check(self):
        if not self.bitmap_ok:
            return
        reserved = set(VOLUME_DIR_BLOCKS) | {0, 1}
        reserved |= set(range(self.bitmap, self.bitmap + self.bitmap_blocks))
        bits = self.d[self.bitmap * BLOCK:(self.bitmap + self.bitmap_blocks) * BLOCK]
        for b in range(self.total):
            if (b >> 3) >= len(bits):
                break
            free = bool(bits[b >> 3] & (0x80 >> (b & 7)))
            if b in reserved:
                # ProDOS owns these whatever the directory tree says.
                if free:
                    self.add('BM_RESERVED', b, None, None, None, '')
            elif b in self.owner:
                if free:
                    self.add('BM_USED_FREE', b, None, None, None, self.owner[b])
            elif not free and self.complete:
                self.add('BM_LOST', b, None, None, None, '')
        # The padding of the last bitmap page must be zero.
        for b in range(self.total, self.bitmap_blocks * 4096):
            if (b >> 3) >= len(bits):
                break
            if bits[b >> 3] & (0x80 >> (b & 7)):
                self.add('BM_TAIL', b, None, None, None, '')

    def run(self):
        if self.image_blocks >= 3 and self.header():
            self.claim(0, '')
            self.claim(1, '')
            if self.bitmap_ok:
                for i in range(self.bitmap_blocks):
                    self.claim(self.bitmap + i, '')
            self.directory(VOLUME_DIR, self.volume, 1, None, self.volume_files)
            self.volume_dir_shape()
            self.bitmap_check()
        elif self.image_blocks < 3:
            self.add('HDR_TOTAL', VOLUME_DIR, 0, self.image_blocks, 0, '')
            self.complete = False
        return Result(self.findings, self.complete)


def check(data):
    """Every inconsistency of a ProDOS-order image. Never writes."""
    return Checker(data).run()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('image', type=Path, help='the ProDOS image to check (.po, .hdv, .2mg)')
    ap.add_argument('--json', action='store_true', help='print the findings envelope')
    args = ap.parse_args()

    result = check(load(args.image))
    if args.json:
        print(json.dumps(envelope(result), indent=1))
        return 1 if result.findings else 0
    for f in sorted(result.findings, key=sort_key):
        slot = '' if f.slot is None else f'slot {f.slot}'
        want = '' if f.expected is None else f'expected {f.expected}'
        got = '' if f.found is None else f'found {f.found}'
        print(f'{f.id:<13} block {f.block:<6}{slot:<8}{want:<16}{got:<12}{f.path}')
    print(f'{len(result.findings)} finding(s), '
          f'{"complete" if result.complete else "INCOMPLETE walk"}')
    return 1 if result.findings else 0


if __name__ == '__main__':
    sys.exit(main())
