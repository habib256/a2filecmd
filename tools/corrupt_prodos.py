#!/usr/bin/env python3
"""Controlled ProDOS corruptions, each with the findings it must produce.

The other half of the FIXIT oracle: `prodos_check.py` says what is wrong with
an image, this module makes images that are wrong on purpose and declares,
entry by entry, exactly which findings the checker -- and later the C walker
of FIXIT -- has to report. A corruption whose declared list is empty would be
a corruption nobody detects, so the test suite refuses one.

    python3 tools/corrupt_prodos.py IN.po OUT.po NAME [NAME...] [--expect E.json]
    python3 tools/corrupt_prodos.py --list

Library:

    path = make_fixture(tmpdir)             # a clean 1600-block volume
    CORRUPTIONS['crosslink'](data, inv)     # mutates `data`, returns an Expect

A corruption is a function (bytearray, Inventory) -> Expect(findings, complete)
where `findings` are prodos_check.Finding objects. Targets are always chosen by
walking the image -- the first seedling, the first sapling, the first free
block -- never by a hard-coded block number, so the fixture can change without
rewriting the expectations.
"""
import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prodos_check as pc
from prodos_check import BLOCK, ENTRY_LEN, ENTRIES_PER_BLOCK, Finding

TOOLS = Path(__file__).resolve().parent


@dataclass
class Expect:
    findings: list = field(default_factory=list)
    complete: bool = True
    # (old, new) for a corruption that changes the name of an entry: every
    # finding another corruption declared about that entry -- or about
    # anything under it -- carries the path the checker will now print.
    renames: list = field(default_factory=list)

    def merge(self, other):
        return Expect(self.findings + other.findings,
                      self.complete and other.complete,
                      self.renames + other.renames)

    def renamed(self):
        """The same findings, with every declared path put through `renames`."""
        if not self.renames:
            return self
        out = []
        for f in self.findings:
            path = f.path
            for old, new in self.renames:
                if path == old or path.startswith(old + '/'):
                    path = new + path[len(old):]
            out.append(f if path == f.path else replace(f, path=path))
        return Expect(out, self.complete, self.renames)


@dataclass
class Ref:
    """One directory entry and where it lives."""
    path: str
    block: int                  # the directory block holding the entry
    slot: int                   # its index in that block
    dirkey: int                 # key block of the directory holding it
    storage: int
    key: int
    used: int
    eof: int
    blocks: list = field(default_factory=list)   # every block the entry reaches
    chain: list = field(default_factory=list)    # a subdirectory's own blocks
    forks: list = field(default_factory=list)    # extended: (offset, storage, key)

    @property
    def offset(self):
        return self.block * BLOCK + 4 + self.slot * ENTRY_LEN


class Inventory:
    """Where everything lives in a healthy image, in the checker's walk order."""

    def __init__(self, data):
        self.d = bytes(data)
        e = self.d[2 * BLOCK + 4:2 * BLOCK + 4 + ENTRY_LEN]
        self.volume = '/' + e[1:1 + (e[0] & 15)].decode('ascii')
        self.file_count = word(e, 0x21)
        self.bitmap = word(e, 0x23)
        self.total = word(e, 0x25)
        self.bitmap_blocks = (self.total + 4095) // 4096
        self.entries = []
        self.root_chain = []
        self.root_count = 0
        self.taken = set()          # free blocks already handed to a corruption
        self.walk(2, self.volume, self.root_chain, root=True)

    def block(self, n):
        return self.d[n * BLOCK:(n + 1) * BLOCK]

    def walk(self, key, path, chain, root=False):
        """Fill self.entries for one directory; `chain` gets its blocks."""
        block, count = key, 0
        while block:
            b = self.block(block)
            chain.append(block)
            for slot in range(1 if block == key else 0, ENTRIES_PER_BLOCK):
                e = b[4 + slot * ENTRY_LEN:4 + (slot + 1) * ENTRY_LEN]
                if not e[0] >> 4:
                    continue
                count += 1
                self.describe(e, block, slot, path, key)
            block = word(b, 2)
        if root:
            self.root_count = count
        return count

    def describe(self, e, block, slot, path, dirkey):
        ref = Ref(path=path + '/' + e[1:1 + (e[0] & 15)].decode('ascii'),
                  block=block, slot=slot, dirkey=dirkey, storage=e[0] >> 4,
                  key=word(e, 0x11), used=word(e, 0x13),
                  eof=int.from_bytes(e[0x15:0x18], 'little'))
        self.entries.append(ref)            # the checker's order: parent, then children
        if ref.storage == pc.SUBDIR:
            self.walk(ref.key, ref.path, ref.chain)
            ref.blocks = list(ref.chain)
        elif ref.storage == pc.EXTENDED:
            ref.blocks = [ref.key]
            mini = self.block(ref.key)
            for i, off in enumerate((0, 256)):
                m = mini[off:off + 8]
                ref.forks.append((i, m[0], word(m, 1)))
                ref.blocks += self.fork_blocks(m[0], word(m, 1))
        else:
            ref.blocks = self.fork_blocks(ref.storage, ref.key)
        return ref

    def fork_blocks(self, storage, key):
        if storage == pc.SEEDLING:
            return [key]
        out, index = [key], self.block(key)
        for i in range(256):
            p = index[i] | (index[256 + i] << 8)
            if not p:
                continue
            out += [p] if storage == pc.SAPLING else self.fork_blocks(pc.SAPLING, p)
        return out

    # -- picking targets ----------------------------------------------------
    def first(self, storage):
        for ref in self.entries:
            if ref.storage == storage:
                return ref
        raise SystemExit(f'the fixture has no file of storage type {storage}')

    def seedlings(self):
        return [r for r in self.entries if r.storage == pc.SEEDLING]

    def free_block(self):
        """The lowest free block this inventory has not handed out yet.

        Two corruptions of one run must never be given the same block: each
        would then declare findings about what the other did to it. The
        inventory is taken once per run, so the cursor is what keeps them
        apart -- and the first call still answers the lowest free block, so a
        corruption applied alone always lands on the same one.
        """
        bits = self.d[self.bitmap * BLOCK:]
        for b in range(self.total):
            if b not in self.taken and bits[b >> 3] & (0x80 >> (b & 7)):
                self.taken.add(b)
                return b
        raise SystemExit('the fixture has no free block')


# -- byte helpers -----------------------------------------------------------
def word(buf, offset):
    return int.from_bytes(buf[offset:offset + 2], 'little')


def put_word(data, offset, value):
    data[offset:offset + 2] = value.to_bytes(2, 'little')


def put24(data, offset, value):
    data[offset:offset + 3] = value.to_bytes(3, 'little')


def set_free(data, inv, block, free):
    """Mark `block` free (bit set) or used (bit clear) in the bitmap."""
    offset = inv.bitmap * BLOCK + (block >> 3)
    mask = 0x80 >> (block & 7)
    if free:
        data[offset] |= mask
    else:
        data[offset] &= 0xFF ^ mask


def index_pointer(data, index, slot, target):
    data[index * BLOCK + slot] = target & 255
    data[index * BLOCK + 256 + slot] = target >> 8


BAD = 0xFFFF                       # the classic garbage pointer


# -- the corruptions --------------------------------------------------------
def bitmap_free_used(data, inv):
    """A block a file uses is marked free in the bitmap."""
    ref = inv.first(pc.SEEDLING)
    set_free(data, inv, ref.key, True)
    return Expect([Finding('BM_USED_FREE', ref.key, None, None, None, ref.path)])


def bitmap_lost(data, inv):
    """A free block is marked used: nobody claims it."""
    b = inv.free_block()
    set_free(data, inv, b, False)
    return Expect([Finding('BM_LOST', b, None, None, None, '')])


def crosslink(data, inv):
    """A second file's key points at the first file's data block."""
    first, second = inv.seedlings()[0], inv.seedlings()[1]
    put_word(data, second.offset + 0x11, first.key)
    return Expect([Finding('XLINK', first.key, None, None, None, second.path),
                   Finding('BM_LOST', second.key, None, None, None, '')])


def lost(blocks):
    """BM_LOST for every block an abandoned entry no longer reaches."""
    return [Finding('BM_LOST', b, None, None, None, '') for b in sorted(set(blocks))]


def key_out_of_range(data, inv):
    """A file's key block points past the end of the volume."""
    ref = inv.first(pc.SEEDLING)
    put_word(data, ref.offset + 0x11, BAD)
    # The entry is partial: FILE_BLOCKS is not emitted, and every block it
    # used to reach -- one, for a seedling -- is now claimed by nobody.
    return Expect([Finding('ENT_KEY', ref.block, ref.slot, None, BAD, ref.path)]
                  + lost(ref.blocks))


def index_out_of_range(data, inv):
    """A sapling's index block holds a pointer past the end of the volume."""
    ref = inv.first(pc.SAPLING)
    slot = 255
    if len(ref.blocks) - 1 > slot:
        raise SystemExit('the fixture sapling fills its index block')
    index_pointer(data, ref.key, slot, BAD)
    return Expect([Finding('IDX_RANGE', ref.key, slot, None, BAD, ref.path)])


def file_count_high(data, inv):
    """The volume header counts one file too many."""
    return _file_count(data, inv, +1)


def file_count_low(data, inv):
    """The volume header counts one file too few."""
    return _file_count(data, inv, -1)


def _file_count(data, inv, delta):
    put_word(data, 2 * BLOCK + 4 + 0x21, inv.file_count + delta)
    return Expect([Finding('FILE_COUNT', 2, 0, inv.root_count,
                           inv.file_count + delta, inv.volume)])


def blocks_used_wrong(data, inv):
    """A file entry claims one block more than its index reaches."""
    ref = inv.first(pc.SAPLING)
    put_word(data, ref.offset + 0x13, ref.used + 1)
    return Expect([Finding('FILE_BLOCKS', ref.block, ref.slot, len(ref.blocks),
                           ref.used + 1, ref.path)])


def dir_blocks_wrong(data, inv):
    """A subdirectory entry claims more blocks than its chain has."""
    ref = inv.first(pc.SUBDIR)
    put_word(data, ref.offset + 0x13, ref.used + 1)
    return Expect([Finding('DIR_BLOCKS', ref.block, ref.slot, len(ref.chain),
                           ref.used + 1, ref.path)])


def dir_eof_wrong(data, inv):
    """A subdirectory entry's EOF is not its chain length times 512."""
    ref = inv.first(pc.SUBDIR)
    put24(data, ref.offset + 0x15, ref.eof + BLOCK)
    return Expect([Finding('DIR_EOF', ref.block, ref.slot, len(ref.chain) * BLOCK,
                           ref.eof + BLOCK, ref.path)])


def chain_broken(data, inv):
    """The second volume directory block no longer points back at the first."""
    if len(inv.root_chain) < 2:
        raise SystemExit('the fixture volume directory has a single block')
    block = inv.root_chain[1]
    put_word(data, block * BLOCK, BAD)
    return Expect([Finding('DIR_CHAIN', block, None, inv.root_chain[0], BAD,
                           inv.volume)])


def chain_loop(data, inv):
    """The last volume directory block points back at the first."""
    last = inv.root_chain[-1]
    put_word(data, last * BLOCK + 2, inv.root_chain[0])
    return Expect([Finding('DIR_LOOP', last, None, None, inv.root_chain[0],
                           inv.volume)], complete=False)


def parent_wrong(data, inv):
    """A subdirectory header points at the wrong entry of its parent."""
    ref = inv.first(pc.SUBDIR)
    offset = ref.key * BLOCK + 4 + 0x25
    data[offset] = ref.slot + 2
    return Expect([Finding('DIR_PARENT', ref.key, 0, ref.slot + 1, ref.slot + 2,
                           ref.path)])


def header_ptr_wrong(data, inv):
    """A file entry no longer points back at the directory holding it."""
    ref = inv.first(pc.SEEDLING)
    put_word(data, ref.offset + 0x25, BAD)
    return Expect([Finding('ENT_HEADER_PTR', ref.block, ref.slot, ref.dirkey,
                           BAD, ref.path)])


def bad_storage(data, inv):
    """A file entry carries a storage type ProDOS never writes."""
    ref = inv.first(pc.SEEDLING)
    data[ref.offset] = (7 << 4) | (data[ref.offset] & 15)
    # The entry is abandoned whole: its index block and its data blocks alike
    # are reached by nobody. A seedling has one block, a sapling has more.
    return Expect([Finding('ENT_STORAGE', ref.block, ref.slot, None, 7, ref.path)]
                  + lost(ref.blocks))


def bad_name(data, inv):
    """A file name starts with a digit."""
    ref = inv.first(pc.SEEDLING)
    data[ref.offset + 1] = ord('1')
    length = data[ref.offset] & 15
    head, tail = ref.path.rsplit('/', 1)
    path = head + '/1' + tail[1:]
    # The entry answers to another name now: any other corruption of the same
    # run that names it declared the old one.
    return Expect([Finding('ENT_NAME', ref.block, ref.slot, None, length, path)],
                  renames=[(ref.path, path)])


def eof_too_big(data, inv):
    """A seedling claims an EOF a single block cannot hold."""
    ref = inv.first(pc.SEEDLING)
    put24(data, ref.offset + 0x15, 1000)
    return Expect([Finding('FILE_EOF', ref.block, ref.slot, BLOCK, 1000, ref.path)])


def hdr_bitmap_bad(data, inv):
    """The volume header points its bitmap at block 0."""
    put_word(data, 2 * BLOCK + 4 + 0x23, 0)
    return Expect([Finding('HDR_BITMAP', 2, 0, None, 0, inv.volume)],
                  complete=False)


def hdr_entry_len(data, inv):
    """The volume header announces 40-byte entries."""
    data[2 * BLOCK + 4 + 0x1F] = 40
    return Expect([Finding('HDR_ENTRY_LEN', 2, 0, ENTRY_LEN, 40, inv.volume)])


def hdr_storage(data, inv):
    """The volume header is not marked as a volume directory."""
    offset = 2 * BLOCK + 4
    data[offset] = (0xD << 4) | (data[offset] & 15)
    return Expect([Finding('HDR_STORAGE', 2, 0, 0xF, 0xD, inv.volume)])


def fork_bad(data, inv):
    """The data fork of an extended file has an impossible storage type."""
    ref = inv.first(pc.EXTENDED)
    _, storage, key = ref.forks[0]
    data[ref.key * BLOCK] = 4
    # Only that fork is abandoned: the key block and the resource fork are
    # still reached, every block of the data fork is not.
    return Expect([Finding('FORK_STORAGE', ref.key, 0, None, 4, ref.path)]
                  + lost(inv.fork_blocks(storage, key)))


def voldir_size(data, inv):
    """The volume directory grew a fifth block, well formed but impossible.

    ProDOS fixes the volume directory at blocks 2 to 5 and never extends it.
    The new block is chained both ways and marked used, so the volume is
    coherent in every other respect: VOLDIR_SIZE is the only thing wrong, and
    DIR_CHAIN -- which is about one back-pointer -- has nothing to say.
    """
    extra = inv.free_block()
    last = inv.root_chain[-1]
    put_word(data, last * BLOCK + 2, extra)
    put_word(data, extra * BLOCK, last)
    set_free(data, inv, extra, False)
    return Expect([Finding('VOLDIR_SIZE', extra, None, 4,
                           len(inv.root_chain) + 1, inv.volume)])


def bad_access(data, inv):
    """A file entry has a reserved bit set in its access byte."""
    ref = inv.first(pc.SEEDLING)
    data[ref.offset + 0x1E] |= 0x04
    return Expect([Finding('ENT_ACCESS', ref.block, ref.slot, None,
                           data[ref.offset + 0x1E], ref.path)])


def bitmap_reserved_free(data, inv):
    """The second boot block is marked free: ProDOS owns it whatever we say."""
    set_free(data, inv, 1, True)
    return Expect([Finding('BM_RESERVED', 1, None, None, None, '')])


def bitmap_tail_set(data, inv):
    """A bit is set past the end of the volume, in the bitmap's padding."""
    if not inv.total % 4096:
        raise SystemExit('the fixture fills its bitmap page: no padding to break')
    set_free(data, inv, inv.total, True)
    return Expect([Finding('BM_TAIL', inv.total, None, None, None, '')])


def two_faults(data, inv):
    """Two independent faults at once: a lost block and a wrong file count."""
    return bitmap_lost(data, inv).merge(file_count_high(data, inv))


CORRUPTIONS = {
    'bitmap_free_used': bitmap_free_used,
    'bitmap_lost': bitmap_lost,
    'crosslink': crosslink,
    'key_out_of_range': key_out_of_range,
    'index_out_of_range': index_out_of_range,
    'file_count_high': file_count_high,
    'file_count_low': file_count_low,
    'blocks_used_wrong': blocks_used_wrong,
    'dir_blocks_wrong': dir_blocks_wrong,
    'dir_eof_wrong': dir_eof_wrong,
    'chain_broken': chain_broken,
    'chain_loop': chain_loop,
    'parent_wrong': parent_wrong,
    'header_ptr_wrong': header_ptr_wrong,
    'bad_storage': bad_storage,
    'bad_name': bad_name,
    'eof_too_big': eof_too_big,
    'hdr_bitmap_bad': hdr_bitmap_bad,
    'hdr_entry_len': hdr_entry_len,
    'hdr_storage': hdr_storage,
    'fork_bad': fork_bad,
    'voldir_size': voldir_size,
    'bad_access': bad_access,
    'bitmap_reserved_free': bitmap_reserved_free,
    'bitmap_tail_set': bitmap_tail_set,
    'two_faults': two_faults,
}

# Seventeen faults on one volume, one per identifier a walk can still reach,
# none of them clobbering another's entry or cutting the pass short: with the
# overflow line that is eighteen lines, one page of the FIXIT screen exactly.
# Left out: ENT_KEY, ENT_STORAGE, FILE_BLOCKS and DIR_LOOP, which aim at an
# entry another corruption already owns, and the HDR_* ones, which refuse the
# volume before the walk.
MANY = ('bitmap_free_used', 'bitmap_lost', 'crosslink', 'index_out_of_range',
        'file_count_high', 'dir_blocks_wrong', 'dir_eof_wrong', 'chain_broken',
        'parent_wrong', 'header_ptr_wrong', 'bad_name', 'eof_too_big',
        'fork_bad', 'voldir_size', 'bad_access', 'bitmap_reserved_free',
        'bitmap_tail_set')


def apply(data, names):
    """Apply the named corruptions in order; returns the union of the Expects.

    The inventory is taken once, from the pristine image: a corruption never
    chooses its target in an image another corruption has already broken, and
    two of them are never handed the same free block.

    Two corruptions can still speak of the same entry, and then the union is
    not the whole truth: a cause that makes the checker abandon an entry
    (`bad_storage`, `key_out_of_range`) silences what a second corruption of
    the same entry would have shown, and a pass a corruption cuts short
    (`chain_loop`, `hdr_bitmap_bad`) silences the bitmap. `MANY` is the set
    this repository combines, and `tools/test_prodos_check.py` holds it to
    what the checker really reports.
    """
    inv = Inventory(bytes(data))
    out = Expect()
    for name in names:
        if name not in CORRUPTIONS:
            raise SystemExit(f'unknown corruption: {name}')
        out = out.merge(CORRUPTIONS[name](data, inv))
    return out.renamed()


def expect_json(expect):
    return {'complete': expect.complete, 'findings': pc.to_json(expect.findings)}


# -- the fixture ------------------------------------------------------------
def make_fixture(tmpdir, volume='CHECKVOL', blocks=1600):
    """A clean 1600-block volume with one of every ProDOS shape.

    A seedling (several, so cross-links have two of them), a sapling, a tree
    big enough to need a master index, a subdirectory with nested files, and
    more than thirteen root entries so the volume directory spans two blocks.
    mkvolume.py writes all of that; the extended file is added here by hand,
    because mkvolume has no reason to know about forks.
    """
    tmpdir = Path(tmpdir)
    stage = tmpdir / 'stage'
    stage.mkdir(parents=True, exist_ok=True)
    for i in range(11):                      # A.TXT .. K.TXT, plain seedlings
        letter = chr(ord('A') + i)
        (stage / f'{letter}.TXT').write_bytes((letter * 39 + '\r').encode() * (i + 1))
    (stage / 'SAP.BIN').write_bytes(bytes(range(256)) * 16)          # 8 blocks
    (stage / 'TREE.BIN').write_bytes(bytes(range(256)) * 568)        # 284 blocks
    sub = stage / 'SUB'
    sub.mkdir(exist_ok=True)
    (sub / 'NEST.TXT').write_bytes(b'nested\r' * 10)
    (sub / 'NEST2.TXT').write_bytes(b'deeper\r' * 100)

    image = tmpdir / 'fixture.po'
    subprocess.run([sys.executable, str(TOOLS / 'mkvolume.py'), str(stage), str(image),
                    '--volume', volume, '--blocks', str(blocks)],
                   check=True, capture_output=True)
    data = bytearray(image.read_bytes())
    add_extended_file(data, 'EXT')
    image.write_bytes(bytes(data))
    return image


def add_extended_file(data, name, data_eof=300, rsrc_eof=64):
    """Add an extended file with two seedling forks; keeps the volume clean.

    Layout of a key block of storage type $5: a mini-entry at offset 0 for the
    data fork and another at 256 for the resource fork -- storage type, key
    block, blocks used, then a three-byte EOF.
    """
    inv = Inventory(bytes(data))
    free = [b for b in range(inv.total)
            if data[inv.bitmap * BLOCK + (b >> 3)] & (0x80 >> (b & 7))][:3]
    key, data_block, rsrc_block = free
    for offset, fork_key, eof in ((0, data_block, data_eof), (256, rsrc_block, rsrc_eof)):
        mini = bytearray(8)
        mini[0] = pc.SEEDLING
        put_word(mini, 1, fork_key)
        put_word(mini, 3, 1)
        put24(mini, 5, eof)
        data[key * BLOCK + offset:key * BLOCK + offset + 8] = mini
    data[data_block * BLOCK:data_block * BLOCK + data_eof] = b'X' * data_eof
    data[rsrc_block * BLOCK:rsrc_block * BLOCK + rsrc_eof] = b'R' * rsrc_eof
    for b in free:
        set_free(data, inv, b, False)

    block, slot = free_entry_slot(data, inv)
    entry = bytearray(ENTRY_LEN)
    entry[0] = (pc.EXTENDED << 4) | len(name)
    entry[1:1 + len(name)] = name.encode('ascii')
    entry[0x10] = 0x06                        # BIN, as good a type as any
    put_word(entry, 0x11, key)
    put_word(entry, 0x13, 3)                  # the key block and both forks
    put24(entry, 0x15, data_eof)
    entry[0x1E] = 0xE3                        # destroy, rename, write, read
    put_word(entry, 0x25, 2)                  # header pointer: the volume dir
    offset = block * BLOCK + 4 + slot * ENTRY_LEN
    data[offset:offset + ENTRY_LEN] = entry
    put_word(data, 2 * BLOCK + 4 + 0x21, inv.file_count + 1)


def free_entry_slot(data, inv):
    for block in inv.root_chain:
        for slot in range(1 if block == 2 else 0, ENTRIES_PER_BLOCK):
            if not data[block * BLOCK + 4 + slot * ENTRY_LEN] >> 4:
                return block, slot
    raise SystemExit('the volume directory is full')


def main():
    if '--list' in sys.argv[1:]:
        for name, fn in CORRUPTIONS.items():
            print(f'{name:<18} {fn.__doc__.splitlines()[0]}')
        return 0
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('source', type=Path, help='the healthy image to read')
    ap.add_argument('out', type=Path, help='the corrupt image to write')
    ap.add_argument('names', nargs='+', help='the corruptions to apply, in order')
    ap.add_argument('--expect', type=Path, help='where to write the expected findings')
    ap.add_argument('--list', action='store_true', help='list the corruptions')
    args = ap.parse_args()

    data = bytearray(pc.load(args.source))
    expect = apply(data, args.names)
    args.out.write_bytes(bytes(data))
    if args.expect:
        args.expect.write_text(json.dumps(expect_json(expect), indent=1) + '\n')
    print(f'{args.out}: {", ".join(args.names)} -> {len(expect.findings)} expected '
          f'finding(s), {"complete" if expect.complete else "INCOMPLETE walk"}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
