#!/usr/bin/env python3
"""Mutation campaign over the four readers that write files onto a volume.

One question: **can a malformed archive or disk image make one of the four
extractors lose a file, keep a half-written one, or call a wreck a success?**
The campaign breaks healthy inputs in every way the format allows, runs the
real C -- the drivers of `src/a2fc.c` (BINARY2, IMGFS, DOSGET, UNSHRINK) and
the real assembly LZW core of `src/unshrink.s` under sim65 -- compiled from
the harnesses of `tools/test_binary2_safety.py`,
`tools/test_imgfs_safety.py`, `tools/test_dos_extract.py`,
`tools/test_unshrink_safety.py` and `tools/test_unshrink_core.py` with
`-fsanitize=address,undefined`, and judges every run against a host
reference decoder written here from the format.

    python3 tools/fuzz_archives.py --count 2000 --seed 1 --out build/fuzz-archives

Why a sibling of `tools/fuzz_images.py` and not the same file: that campaign
fuzzes the *viewers* (DGR, EXTASIE, PACKFOT, 816PAINT, FONTVIEW, PRINTSHOP,
LZ4FH). They take one buffer and paint a screen; the only question is whether
they stay inside their buffers, so one CLI, one mutator set and one invariant
(no bounds violation) fit them all. The four readers here take an archive or a
disk image and *create files on a ProDOS volume*: the questions are what is
left on the volume, whether it is right, and whether the verdict is honest.
Nothing of the shape carries over, so this is its own file with its own
invariants, and `fuzz_images.py` is untouched.

Five invariants, each of which saves the input, the seed and a one-line
reason into `--out` when it fails:

1. **no crash, no hang** -- the driver terminates cleanly under ASan and
   UBSan, and the sim65 core answers within its timeout with a decoded
   block or a refusal;
2. **no pre-existing file is touched** -- the volume starts with files of
   known bytes; after the run every one of them has the same bytes, the same
   size and the same mtime, and every output was created through the
   exclusive `reserve_output` (the harness aborts on any other open flag);
3. **what is kept is right** -- every file left on the volume that the run
   created equals, byte for byte, what the host reference decodes for that
   member; a reference that refuses a member forbids a file for it. None of
   these four documents keeping a partial (docs/DATA-SAFETY.md rows
   "Binary II, ShrinkIt, extraction ProDOS/DOS 3.3", "IMGFS" and "UNSHRINK":
   the readback "retire le fichier possede"), so a kept partial is a failure;
4. **verdict honesty** -- a success message is said only of an input the
   reference reads whole, and its count is the reference's count; a failure
   or "reads back different" message leaves behind only the members that
   were completed before it;
5. **the input is never modified** -- the archive or image file comes back
   byte-identical.

What the reference is. For each format it is a host decoder written from the
format (Binary II records, NuFX records and threads, the ProDOS directory
and index blocks, the DOS 3.3 VTOC, catalog and track/sector lists), which
returns the ordered list of members it can read whole and the point at which
the input stops being readable. On healthy inputs it is held to the project's
own independent readers -- `tools/mkbny.py`, `tools/mkshk.py` and
`tools/prodos_read.py` -- by `tools/test_fuzz_archives.py`. A few rules it
also has to know are policies of the tool rather than of the format, each
named where it is used: the ProDOS name a member is given, the storage type
IMGFS looks up in the directory, and the sparse/hole and five-list rules of
DOSGET. Those are transliterated with a comment pointing at the code.

Only throwaway inputs and throwaway volumes are touched: every seed is built
here, in a temporary directory, and every case gets its own copy.
"""
import argparse
import hashlib
import json
import os
import random
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

import corrupt_prodos            # noqa: E402
import mkbny                     # noqa: E402
import mkdos33                   # noqa: E402
import mkshk                     # noqa: E402
import test_binary2_safety       # noqa: E402
import test_dos_extract          # noqa: E402
import test_imgfs_safety         # noqa: E402
import test_unshrink_core        # noqa: E402
import test_unshrink_safety      # noqa: E402

CFLAGS = ['-std=c99', '-g', '-O1', '-Wno-unknown-pragmas',
          '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
          '-fno-omit-frame-pointer']
SAN_ENV = {'ASAN_OPTIONS': 'detect_leaks=0:abort_on_error=1',
           'UBSAN_OPTIONS': 'halt_on_error=1:print_stacktrace=0'}

# PATH_LEN is 64 in src/a2fc_plugin.h and BINARY2 and UNSHRINK both refuse a
# destination whose path plus a 16-character name would not fit. The working
# directories therefore live directly under /tmp with short names; a campaign
# run from a deep scratchpad would measure the refusal, not the reader.
TMPBASE = '/tmp'

# The files the volume already holds when a run starts. COLLIDE names, per
# decoder, a file one of its seeds really produces, so the exclusive
# reservation is exercised on a real collision and not only in theory.
PREEXISTING = {
    'KEEP.TXT': b'keep me whole\r' * 7,
    'OTHER.BIN': bytes(range(256)) * 2,
}
# COLLIDE is filled at build time from the names the healthy seeds really
# produce (see `seed_names`), so the planted collision is always a name the
# input under test wants.


# -- the ProDOS name a member is given --------------------------------------
def prodos_name(src, seps=(0x2F, 0x3A)):
    """The tool's name policy: `b2_name` and `us_prodos_name` in src/a2fc.c.

    The last component after a separator, upper case, letters digits and
    periods, a letter first, fifteen characters at most, never empty. A byte
    above $7F is a negative `char` for the C, so it passes none of the class
    tests and becomes a period here too.
    """
    start = 0
    for i, c in enumerate(src):
        if c in seps:
            start = i + 1
    out = bytearray()
    for c in src[start:]:
        if len(out) >= 15:
            break
        if 0x61 <= c <= 0x7A:
            c -= 32
        if not (0x41 <= c <= 0x5A or 0x30 <= c <= 0x39 or c == 0x2E):
            c = 0x2E
        if not out and not 0x41 <= c <= 0x5A:
            out.append(0x58)
            if len(out) == 15:
                break
        out.append(c)
    if not out:
        out.append(0x58)
    return out.decode('ascii')


# -- what a reference says --------------------------------------------------
class Expect:
    """What the host reference reads out of one input.

    `files` is the ordered list of (name, bytes) the reader should be able to
    produce, in the order it produces them, `whole` says the input was read to
    its end without a fault, and `note` is the reason it stopped. Everything
    before that point may be on the volume after a failure; nothing else may.
    `extra` counts what the reader skips rather than extracts (Binary II
    folders, ShrinkIt threads it cannot decompress, IMGFS files it refuses),
    and `fired` lists the documented divergences this input met.
    """

    def __init__(self, files=(), whole=True, note='', extra=0, fired=()):
        self.files = list(files)
        self.whole = whole
        self.note = note
        self.extra = extra          # folders skipped / files refused as too big
        self.fired = list(fired)    # the documented divergences this input met

    @property
    def names(self):
        return {n for n, _ in self.files}

    def by_name(self):
        out = {}
        for n, d in self.files:
            out.setdefault(n, d)    # the first wins; a later one cannot be created
        return out


def collide(names, existing):
    """Stop a reference at the first member whose name is already taken.

    Every one of the four reserves its output exclusively, so a name already
    on the volume -- planted there, or produced by an earlier member of the
    same input -- is a create failure that ends the run. The members before
    it stay.
    """
    out, taken = [], set(existing)
    for name, data in names:
        if name in taken:
            return out, False
        taken.add(name)
        out.append((name, data))
    return out, True


# -- a cursor over the input ------------------------------------------------
class Cut(Exception):
    """The input ends, or is malformed, where the reference is reading."""


class Reader:
    def __init__(self, data):
        self.data = data
        self.pos = 0

    def take(self, n):
        if n < 0 or self.pos + n > len(self.data):
            raise Cut('short read of %d at %d' % (n, self.pos))
        out = self.data[self.pos:self.pos + n]
        self.pos += n
        return out

    def skip(self, n):
        self.take(n)


def u16(b, o=0):
    return b[o] | (b[o + 1] << 8)


def u24(b, o=0):
    return b[o] | (b[o + 1] << 8) | (b[o + 2] << 16)


def u32(b, o=0):
    return int.from_bytes(b[o:o + 4], 'little')


# ===========================================================================
# BINARY II
# ===========================================================================
HDR = 128


def b2_harness():
    """The harness of tools/test_binary2_safety.py, its main replaced.

    Everything that mocks the MLI/fopen/fwrite layer is kept unchanged; only
    `main` differs, because a campaign drives no injected fault and has to
    print the verdict on a line of its own.
    """
    head = test_binary2_safety.C.split('int main(')[0]
    return head + r'''
int main(int argc,char**argv) {
    strcpy(full,argv[1]);strcpy(panels[1].path,argv[2]);strcpy(selected.name,"TEST.BNY");
    fault=0;cleanup_bad=0;
    binary2_entry(NULL);
    printf("NOTE %s\nREMOVES %d\n",note,removes);
    return 0;
}
'''


def b2_record(name, data, more=True, filetype=6, storage=1, auxtype=0x1234):
    h = bytearray(HDR)
    h[0:3] = b'\x0aGL'
    h[3] = 0xE3
    h[4] = filetype & 0xFF
    h[5:7] = struct.pack('<H', auxtype & 0xFFFF)
    h[7] = storage
    h[8:10] = struct.pack('<H', (len(data) + 511) // 512)
    h[0x12] = 0x02
    h[0x14:0x17] = len(data).to_bytes(3, 'little')
    n = name.encode('ascii')
    h[0x17] = len(n)
    h[0x18:0x18 + len(n)] = n
    h[0x7F] = 1 if more else 0
    return bytes(h) + data + bytes((-len(data)) % HDR)


def b2_seeds():
    """Healthy Binary II archives: sizes around the 128-byte padding, a
    folder record and the files under it, a long path, an empty member."""
    payload = b'data\r' * 103
    out = {}
    out['one'] = b2_record('DATA', payload, more=False)
    out['sizes'] = (b2_record('EMPTY', b'') + b2_record('ONE', b'A')
                    + b2_record('EXACT', b'B' * 128) + b2_record('OVER', b'C' * 129)
                    + b2_record('BIG', bytes(range(256)) * 6, more=False))
    out['folders'] = (b2_record('SUB', b'', filetype=0x0F)
                      + b2_record('SUB/DATA', payload)
                      + b2_record('SUB/DEEP', bytes(39), storage=0x0D)
                      + b2_record('SUB/DEEP/END', b'end', more=False))
    # An archive the project's own writer produced, header for header: the
    # reference is then checked against tools/mkbny.py's reader as well.
    with tempfile.TemporaryDirectory(prefix='a2fzb', dir=TMPBASE) as t:
        path = Path(t) / 'real.bny'
        mkbny.write_bny(path, [dict(name='ALPHA', data=payload, filetype=6),
                               dict(name='BETA', data=b'', filetype=4),
                               dict(name='GAMMA.TXT', data=bytes(range(256)) * 3)])
        out['mkbny'] = path.read_bytes()
    return out


def b2_offsets(data):
    """The start of every record of an archive."""
    out, pos = [], 0
    while pos + HDR <= len(data):
        out.append(pos)
        eof = u24(data, pos + 0x14)
        more = data[pos + 0x7F]
        pos += HDR + eof + ((-eof) % HDR)
        if not more or pos > len(data):
            break
    return out


def b2_mutate(data, rng):
    heads = b2_offsets(data)
    kind = rng.randrange(10)
    d = bytearray(data)
    if kind == 0:                                   # every boundary of the format
        cuts = sorted({0, 1, 3, HDR - 1, HDR, HDR + 1, len(d) - 1, len(d) // 2}
                      | {h for h in heads} | {h + HDR for h in heads})
        return bytes(d[:rng.choice([c for c in cuts if 0 <= c <= len(d)])]), 'truncate'
    if kind == 1:                                   # a header field
        h = rng.choice(heads)
        field = rng.choice(['eof', 'namelen', 'name', 'type', 'storage',
                            'follow', 'magic', 'id'])
        if field == 'eof':
            d[h + 0x14:h + 0x17] = rng.choice(
                [0, 1, 127, 128, 129, len(d), 0xFFFFFF, rng.randrange(1 << 24)]
            ).to_bytes(3, 'little')
        elif field == 'namelen':
            d[h + 0x17] = rng.choice([0, 1, 15, 16, 64, 65, 255, rng.randrange(256)])
        elif field == 'name':
            d[h + 0x18 + rng.randrange(64)] = rng.randrange(256)
        elif field == 'type':
            d[h + 4] = rng.choice([0x0F, 0x06, 0x04, rng.randrange(256)])
        elif field == 'storage':
            d[h + 7] = rng.choice([0x0D, 1, 2, 3, rng.randrange(256)])
        elif field == 'follow':
            d[h + 0x7F] = rng.choice([0, 1, 255])
        elif field == 'magic':
            d[h + rng.randrange(3)] = rng.randrange(256)
        else:
            d[h + 0x12] = rng.randrange(256)
        return bytes(d), 'header.' + field
    if kind == 2:                                   # an illegal or overlong name
        h = rng.choice(heads)
        name = rng.choice([b'..', b'/', b'A' * 16, b'A' * 64, b'9START',
                           bytes(rng.randrange(1, 64)),
                           bytes(rng.randrange(0x80, 0x100) for _ in range(20)),
                           b'A/B/C/' + b'Z' * 30, b'NAME WITH SPACE'])
        d[h + 0x17] = len(name)
        d[h + 0x18:h + 0x18 + 64] = name.ljust(64, b'\0')
        return bytes(d), 'name'
    if kind == 3:                                   # bytes of the payload
        for _ in range(rng.randrange(1, 9)):
            d[rng.randrange(len(d))] = rng.randrange(256)
        return bytes(d), 'bytes'
    if kind == 4:                                   # a record repeated
        h = rng.choice(heads)
        eof = u24(d, h + 0x14)
        n = HDR + eof + ((-eof) % HDR)
        return bytes(d[:h] + d[h:h + n] + d[h:]), 'duplicate'
    if kind == 5:                                   # a partial record appended
        return bytes(d + b2_record('TAIL', b'x' * 300, more=False)[:rng.randrange(1, 300)]), 'tail'
    if kind == 6:                                   # the last record says more follow
        if heads:
            d[heads[-1] + 0x7F] = 1
        return bytes(d), 'more'
    if kind == 7:                                   # bytes inserted, everything shifts
        at = rng.randrange(len(d) + 1)
        return bytes(d[:at] + rng.randbytes(rng.randrange(1, 130)) + d[at:]), 'insert'
    if kind == 8:                                   # a stored size beyond the data
        h = rng.choice(heads)
        d[h + 0x14:h + 0x17] = (len(d) + rng.randrange(1, 4096)).to_bytes(3, 'little')
        return bytes(d), 'oversize'
    return bytes(rng.randbytes(rng.randrange(0, 600))), 'random'


def b2_reference(data, existing):
    """The Binary II reader of the format: 128-byte headers, `eof` bytes of
    data, zero padding to the next multiple of 128, "files to follow" in the
    last byte. A record whose type is $0F or whose storage type is $0D is a
    folder: it is skipped, and its data and padding must still be there.
    """
    r = Reader(data)
    files, folders, more = [], 0, True
    whole, why = True, ''
    while more:
        try:
            h = r.take(HDR)
            if h[0:3] != b'\x0aGL' or h[0x17] > 64:
                raise Cut('not a Binary II header')
            eof = u24(h, 0x14)
            pad = (-eof) % HDR
            more = h[0x7F] != 0
            if h[4] == 0x0F or h[7] == 0x0D:
                r.skip(eof + pad)
                folders += 1
                continue
            body = r.take(eof)
            r.skip(pad)
            files.append((prodos_name(h[0x18:0x18 + h[0x17]]), body))
        except Cut as e:
            whole, why = False, str(e)
            break
    files, ok = collide(files, existing)
    if not ok:
        whole, why = False, 'name already on the volume'
    return Expect(files, whole, why, folders)


def b2_verdict(note, expect):
    """The message BINARY2 must print for this input."""
    if expect.whole:
        return '%u file(s) extracted, %u folder(s) skipped.' % (len(expect.files),
                                                                expect.extra)
    return None                   # any of the failure messages; never a success


# ===========================================================================
# UNSHRINK: the NuFX driver (the assembly core is fuzzed separately, below)
# ===========================================================================
US_ARCHIVE = test_unshrink_safety.archive
US_RECORD = test_unshrink_safety.record
US_THREAD = test_unshrink_safety.thread
US_RAW = test_unshrink_safety.UnshrinkSafety.raw_lzw


def us_harness():
    """The harness of tools/test_unshrink_safety.py, its main replaced.

    Its `us_chunk` is the host stand-in that copies raw 4096-byte chunks out
    of an LZW container: what is under test here is the C driver -- the NuFX
    parser, the AUX window refill, the two CRCs, the file lifecycle -- not
    the 6502 decoder, which gets its own campaign (`unshrink-core`).
    """
    head = test_unshrink_safety.C.split('int main(')[0]
    return head + r'''
int main(int argc,char** argv){
    strcpy(full,argv[1]);strcpy(panels[0].path,"/SOURCE");
    fault=0;cleanup_bad=0;read_at=0;cancel_at=0;
    strcpy(dstroot,argv[2]);
    strcpy(panels[1].path,argv[2]);panels[0].count=1;
    strcpy(selected.name,"ARCHIVE.SHK");
    memset(&state,0xA5,sizeof state);   /* scratch is not zeroed on entry */
    unshrink_entry(NULL);
    if(output_open)abort();
    printf("NOTE %s\nREMOVES %d OPENS %d\n",note,removes,opens);
    return 0;
}
'''


def us_seeds():
    payload = b'data\r' * 103
    big = bytes(range(256)) * 49
    out = {}
    out['stored'] = US_ARCHIVE(US_RECORD('DATA', payload))
    out['lzw1'] = US_ARCHIVE(US_RECORD('DATA', US_RAW(big, 2), fmt=2, eof=len(big)))
    out['lzw2'] = US_ARCHIVE(US_RECORD('DATA', US_RAW(big, 3), fmt=3, eof=len(big)))
    out['v3'] = US_ARCHIVE(US_RECORD('DATA', payload, version=3,
                                     crc=mkshk.crc16(payload, 0xFFFF)))
    disk = bytes(range(256)) * 4
    out['disk'] = US_ARCHIVE(US_RECORD('LONGDISKIMAGENAME', disk, kind=1,
                                       auxtype=2, eof=0))
    out['many'] = US_ARCHIVE(
        US_RECORD('FIRST', payload, extra=[US_THREAD(b'a comment', klass=0)]),
        US_RECORD('SECOND', US_RAW(payload, 2), fmt=2, eof=len(payload)),
        US_RECORD('THIRD', b''))
    out['bxy'] = b'\x0aGL' + bytes(125) + out['stored']
    # An archive tools/mkshk.py really wrote (stored threads, record version
    # 3, so the thread CRCs are live): the reference is then checked against
    # that tool's reader as well.
    with tempfile.TemporaryDirectory(prefix='a2fzs', dir=TMPBASE) as t:
        path = Path(t) / 'real.shk'
        mkshk.write_shk(path, [dict(name='ALPHA', data=payload, fmt=0),
                               dict(name='BETA', data=b'', fmt=0),
                               dict(name='GAMMA.TXT', data=bytes(range(256)) * 3, fmt=0)])
        out['mkshk'] = path.read_bytes()
    return out


def us_offsets(data):
    """The boundaries of a NuFX archive: master header, every record start,
    the thread headers and the start of every thread's data."""
    out = [0, 48]
    pos = 128 if data[:3] == b'\x0aGL' else 0
    out.append(pos)
    pos += 48
    for _ in range(64):
        if pos + 8 > len(data) or data[pos:pos + 4] != b'\x4e\xf5\x46\xd8':
            break
        attrib = u16(data, pos + 6)
        if not 34 <= attrib <= 256 or pos + attrib > len(data):
            break
        nthreads = u16(data, pos + 0x0A)
        namelen = u16(data, pos + attrib - 2)
        head = pos + attrib + namelen
        out += [pos, pos + 8, pos + attrib, head]
        p = head + 16 * nthreads
        for t in range(nthreads):
            th = head + 16 * t
            if th + 16 > len(data):
                return sorted({o for o in out if 0 <= o <= len(data)})
            out += [th, p]
            p += u32(data, th + 12)
        out.append(p)
        pos = p
        if pos > len(data):
            break
    return sorted({o for o in out if 0 <= o <= len(data)})


def us_record_heads(data):
    return [o for o in us_offsets(data)
            if o + 4 <= len(data) and data[o:o + 4] == b'\x4e\xf5\x46\xd8']


def us_threads(data):
    """Every thread of the archive: (header offset, data offset, ceof)."""
    out = []
    for pos in us_record_heads(data):
        attrib = u16(data, pos + 6)
        if not 34 <= attrib <= 256 or pos + attrib > len(data):
            continue
        nthreads = u16(data, pos + 0x0A)
        head = pos + attrib + u16(data, pos + attrib - 2)
        p = head + 16 * nthreads
        for t in range(nthreads):
            th = head + 16 * t
            if th + 16 > len(data):
                break
            out.append((th, p, u32(data, th + 12)))
            p += u32(data, th + 12)
    return out


def us_thread_heads(data):
    return [th for th, _, _ in us_threads(data)]


def us_mutate(data, rng):
    d = bytearray(data)
    kind = rng.randrange(11)
    if kind == 0:
        cuts = us_offsets(data) + [0, 1, len(d) - 1, len(d) // 2]
        return bytes(d[:rng.choice([c for c in cuts if 0 <= c <= len(d)])]), 'truncate'
    if kind == 1:                                   # the master header
        field = rng.choice(['magic', 'records', 'crc', 'total'])
        if field == 'magic':
            d[rng.randrange(6)] = rng.randrange(256)
        elif field == 'records':
            d[8:10] = rng.choice([0, 1, 2, 255, 65535]).to_bytes(2, 'little')
        elif field == 'crc':
            d[6] ^= 1
        else:
            d[0x26:0x2A] = rng.randrange(1 << 32).to_bytes(4, 'little')
        return bytes(d), 'master.' + field
    heads = us_record_heads(data)
    threads = us_thread_heads(data)
    if kind == 2 and heads:                         # a record attribute
        h = rng.choice(heads)
        field = rng.choice(['magic', 'attrib', 'version', 'threads', 'sep',
                            'filetype', 'auxtype', 'storage', 'namelen'])
        if field == 'magic':
            d[h + rng.randrange(4)] = rng.randrange(256)
        elif field == 'attrib':
            d[h + 6:h + 8] = rng.choice([0, 1, 33, 34, 35, 59, 60, 61, 255,
                                         256, 257, 65535]).to_bytes(2, 'little')
        elif field == 'version':
            d[h + 8:h + 10] = rng.choice([0, 1, 2, 3, 4, 256, 65535]).to_bytes(2, 'little')
        elif field == 'threads':
            d[h + 0x0A:h + 0x0C] = rng.choice([0, 1, 2, 3, 8, 9, 255, 65535]
                                              ).to_bytes(2, 'little')
        elif field == 'sep':
            d[h + 0x10] = rng.choice([0, ord('/'), ord(':'), 0xFF, rng.randrange(256)])
        elif field == 'filetype':
            d[h + 0x16:h + 0x18] = rng.randrange(65536).to_bytes(2, 'little')
        elif field == 'auxtype':
            d[h + 0x1A:h + 0x1C] = rng.choice([0, 1, 2, 3, 280, 1600, 65535,
                                               rng.randrange(65536)]).to_bytes(2, 'little')
        elif field == 'storage':
            d[h + 0x1E:h + 0x20] = rng.randrange(65536).to_bytes(2, 'little')
        else:
            attrib = u16(d, h + 6)
            if 34 <= attrib <= 256 and h + attrib <= len(d):
                d[h + attrib - 2:h + attrib] = rng.choice(
                    [0, 1, 16, 32, 255, 256, 511, 65535]).to_bytes(2, 'little')
        return bytes(d), 'record.' + field
    if kind == 3 and threads:                       # a thread header
        th = rng.choice(threads)
        field = rng.choice(['klass', 'fmt', 'kind', 'crc', 'teof', 'ceof'])
        if field == 'klass':
            d[th:th + 2] = rng.choice([0, 1, 2, 3, 4, 65535]).to_bytes(2, 'little')
        elif field == 'fmt':
            d[th + 2:th + 4] = rng.choice([0, 1, 2, 3, 4, 5, 65535]).to_bytes(2, 'little')
        elif field == 'kind':
            d[th + 4:th + 6] = rng.choice([0, 1, 2, 3, 65535]).to_bytes(2, 'little')
        elif field == 'crc':
            d[th + 6:th + 8] = rng.randrange(65536).to_bytes(2, 'little')
        elif field == 'teof':
            d[th + 8:th + 12] = rng.choice([0, 1, 511, 512, 4095, 4096, 4097,
                                            len(d), 1 << 24, 0xFFFFFFFF]).to_bytes(4, 'little')
        else:
            d[th + 12:th + 16] = rng.choice([0, 1, 15, 16, 4095, 4096, 4099, 4100,
                                             len(d), 0xFFFFFFFF]).to_bytes(4, 'little')
        return bytes(d), 'thread.' + field
    if kind == 4:                                   # bytes of the compressed data
        for _ in range(rng.randrange(1, 9)):
            d[rng.randrange(len(d))] = rng.randrange(256)
        return bytes(d), 'bytes'
    if kind == 5 and heads:                         # an illegal or overlong name
        h = rng.choice(heads)
        attrib = u16(d, h + 6)
        namelen = u16(d, h + attrib - 2) if h + attrib <= len(d) else 0
        name = rng.choice([b'..', b'/', b'A' * 16, b'A' * 40, b'9NAME',
                           bytes(rng.randrange(0x80, 0x100) for _ in range(20)),
                           b'DIR/SUB/' + b'Z' * 30, b'', b'   '])
        if namelen:                      # the name held in the record header
            d[h + attrib:h + attrib + namelen] = name.ljust(namelen, b'\0')[:namelen]
        else:                            # the class-3 name thread
            for th, at, ceof in us_threads(bytes(d)):
                if th > h and d[th] == 3 and d[th + 4] == 0:
                    d[th + 8:th + 12] = len(name).to_bytes(4, 'little')
                    d[at:at + min(ceof, len(name))] = name[:ceof]
                    break
        return bytes(d), 'name'
    if kind == 6:                                   # inside an LZW stream
        streams = [(at, ceof) for th, at, ceof in us_threads(data)
                   if d[th] == 2 and d[th + 2] in (2, 3) and at + ceof <= len(d)]
        if streams:
            at, ceof = rng.choice(streams)
            # the stream header (CRC, volume, escape), a chunk header, or a
            # byte of the compressed body
            off = rng.choice([rng.randrange(min(4, max(1, ceof))),
                              rng.randrange(min(8, max(1, ceof))),
                              rng.randrange(max(1, ceof))])
            d[at + off] = rng.randrange(256)
            return bytes(d), 'lzw.stream'
        d[rng.randrange(len(d))] = rng.randrange(256)
        return bytes(d), 'lzw.stream'
    if kind == 7:                                   # bytes inserted, everything shifts
        at = rng.randrange(len(d) + 1)
        return bytes(d[:at] + rng.randbytes(rng.randrange(1, 130)) + d[at:]), 'insert'
    if kind == 8 and threads:                       # a stored size beyond the data
        th = rng.choice(threads)
        d[th + 8:th + 12] = (len(d) + rng.randrange(1, 4096)).to_bytes(4, 'little')
        return bytes(d), 'oversize'
    if kind == 9 and heads:                         # a record repeated
        h = heads[-1]
        return bytes(d + d[h:]), 'duplicate'
    return bytes(rng.randbytes(rng.randrange(0, 700))), 'random'


US_NEED = 4100
US_WINDOW = 8192


def us_stream(r, fmt, ceof, total, thcrc, want1):
    """One data thread decoded the way the driver decodes it.

    `us_chunk` here is the harness stand-in: an LZW container of raw
    4096-byte chunks, each preceded by the format's chunk header (3 bytes for
    LZW/1, 2 for LZW/2). The AUX window refill of `us_fill` is reproduced
    because its arithmetic is what decides whether a truncated thread is
    caught. Returns (ok, bytes, crcbad, rem_in).
    """
    rem_in, rem_out, out = ceof, total, bytearray()
    crc0, crc1, want0 = 0, 0xFFFF, 0
    if fmt == 0:
        if rem_in < rem_out:
            return False, b'', False, rem_in
        while rem_out:
            n = min(512, rem_out)
            try:
                b = r.take(n)
            except Cut:
                return False, bytes(out), False, rem_in
            if thcrc:
                crc1 = mkshk.crc16(b, crc1)
            out += b
            rem_out -= n
            rem_in -= n
    else:
        hn = 4 if fmt == 2 else 2
        if rem_in < hn:
            return False, b'', False, rem_in
        try:
            b = r.take(hn)
        except Cut:
            return False, b'', False, rem_in
        rem_in -= hn
        want0 = u16(b, 0)
        h = 3 if fmt == 2 else 2
        win, win_len, win_pos = bytearray(US_WINDOW), 0, 0
        while rem_out:
            left = win_len - win_pos
            if left >= US_NEED or not rem_in:
                if not left:
                    return False, bytes(out), False, rem_in
            else:
                win[0:left] = win[win_pos:win_pos + left]
                win_len, win_pos = left, 0
                while win_len <= US_WINDOW - 512 and rem_in:
                    n = min(512, rem_in)
                    try:
                        b = r.take(n)
                    except Cut:
                        return False, bytes(out), False, rem_in
                    win[win_len:win_len + n] = b
                    win[win_len + n:win_len + 512] = bytes(512 - n)
                    win_len += n
                    rem_in -= n
            used = h + 4096
            if used > win_len - win_pos:
                return False, bytes(out), False, rem_in
            block = bytes(win[win_pos + h:win_pos + h + 4096])
            win_pos += used
            n = min(4096, rem_out)
            for off in range(0, 4096, 512):
                if off >= n and fmt != 2:
                    break
                seg = block[off:off + 512]
                if fmt == 2:
                    crc0 = mkshk.crc16(seg, crc0)
                if off < n:
                    k = min(512, n - off)
                    if thcrc:
                        crc1 = mkshk.crc16(seg[:k], crc1)
                    out += seg[:k]
            rem_out -= n
    crcbad = (fmt == 2 and crc0 != want0) or (thcrc and crc1 != want1)
    return not crcbad, bytes(out), crcbad, rem_in


def us_reference(data, existing):
    """The NuFX reader of the format, and the driver's own name and disk rules.

    Master header (48 bytes, optionally behind a 128-byte Binary II header),
    then `records` records: magic, attribute count 34..256, the attributes,
    an optional name in the header, up to eight 16-byte thread headers, then
    the threads in order. A class-3 kind-0 thread names the file; a class-2
    kind-0/1 thread is the data or a disk image; anything else is skipped.
    A verified file stays even when the compressed padding after it cannot be
    read -- that error belongs to the archive, and the message says so
    (`us_kept` in src/a2fc.c); it is the only member of these four documented
    to survive a later fault, and it is complete, not partial.
    """
    r = Reader(data)
    files, whole, why, unsupported, fired = [], True, '', 0, []

    def narrow():
        if 'NUFX_16BIT_LOW' not in fired:
            fired.append('NUFX_16BIT_LOW')

    try:
        hdr = r.take(48)
        if hdr[0:3] == b'\x0aGL':
            r.take(80)
            hdr = r.take(48)
        if hdr[0:6] != b'\x4e\xf5\x46\xe9\x6c\xe5':
            return Expect([], False, 'not a NuFX archive')
        records = u16(hdr, 8)
        for _ in range(records):
            head = r.take(8)
            if head[0:4] != b'\x4e\xf5\x46\xd8':
                raise Cut('record magic')
            attrib = u16(head, 6)
            if attrib < 34 or attrib > 256:
                raise Cut('attribute count %d' % attrib)
            hdr = head + r.take(attrib - 8)
            nthreads = u16(hdr, 0x0A)
            sep = hdr[0x10]
            auxtype = u16(hdr, 0x1A)
            v3 = hdr[8] >= 3 or hdr[9]
            if u16(hdr, 0x0C) or u16(hdr, 0x18) or u16(hdr, 0x1C):
                narrow()                # total_threads, file_type, extra_type
            namelen = u16(hdr, attrib - 2)
            name, have_name = '', False
            if namelen:
                if namelen > 255:
                    raise Cut('name in header too long')
                name = prodos_name(r.take(namelen), (sep,))
                have_name = True
            if nthreads > 8:
                raise Cut('%d threads' % nthreads)
            th = r.take(nthreads * 16)
            for t in range(nthreads):
                e = th[t * 16:t * 16 + 16]
                klass, fmt, kind = e[0], e[2], e[4]      # the driver's low byte
                if e[1] or e[3] or e[5]:
                    narrow()
                want1, teof, ceof = u16(e, 6), u32(e, 8), u32(e, 12)
                if klass == 3 and kind == 0:
                    n = min(ceof, 512)
                    raw = r.take(n)
                    name = prodos_name(raw[:min(teof, n)], (sep,))
                    have_name = True
                    r.skip(ceof - n)
                elif klass == 2 and kind in (0, 1):
                    if fmt not in (0, 2, 3):
                        unsupported += 1        # "Unsupported compression"
                        r.skip(ceof)
                        continue
                    if not have_name:
                        name = prodos_name(b'Create', (sep,))
                    out_name, total = name, teof
                    if kind == 1:               # a disk image: NAME.PO, blocks x 512
                        out_name = name[:12] + '.PO'
                        total = (auxtype * 512) & 0xFFFFFFFF
                    if out_name in {n for n, _ in files} or out_name in existing:
                        raise Cut('name already on the volume')
                    ok, body, crcbad, rem = us_stream(r, fmt, ceof, total, v3, want1)
                    if not ok:
                        raise Cut('CRC error' if crcbad else 'thread unreadable')
                    files.append((out_name, body))
                    r.skip(rem)                 # the rest of the thread
                else:
                    r.skip(ceof)
    except Cut as e:
        whole, why = False, str(e)
    return Expect(files, whole, why, unsupported, fired)


def us_verdict(note, expect):
    """A thread the driver cannot decompress leaves "Unsupported compression."
    in `note`, and the final count is only printed when `note` is still empty
    (src/a2fc.c, `unshrink_entry`): such an archive has no success message."""
    if expect.whole and not expect.extra:
        return '%u file(s) extracted.' % len(expect.files)
    return None


# ===========================================================================
# IMGFS: a ProDOS image opened as a folder, its files extracted
# ===========================================================================
BLOCK = 512
MAX_ENTRIES = 140
ENTRY_LEN = 0x27
PER_BLOCK = 0x0D


def _patch(text, old, new, what):
    if old not in text:
        raise SystemExit('fuzz_archives: the harness no longer has ' + what)
    return text.replace(old, new, 1)


def im_harness():
    """The harness of tools/test_imgfs_safety.py, reading a real image file.

    Its block reader served a 300-block array built in `main`; a campaign
    needs a whole mutated volume on disk, so only `img_open` and
    `img_read_block` change -- everything that mocks the output side is the
    harness's, unchanged -- and `main` takes the entries the panel would hold.
    """
    c = test_imgfs_safety.C
    c = _patch(c, 'static struct Entry entries[4];',
               'static struct Entry entries[160];', 'its entry snapshot')
    c = _patch(c, 'unsigned char fs,count,cursor,img_len,tags[4];',
               'unsigned char fs,cursor,img_len,tags[4];unsigned int count;',
               'its panel')
    c = _patch(c, 'static int tag_count(const struct Panel* p){'
                  'return p->tags[0]+p->tags[1]+p->tags[2]+p->tags[3];}',
               'static int alltags;\n'
               'static int tag_count(const struct Panel* p){return alltags;}',
               'its tag counter')
    c = _patch(c, 'static int tagged(const struct Panel* p,unsigned i){return p->tags[i];}',
               'static int tagged(const struct Panel* p,unsigned i){(void)i;return 1;}',
               'its tag test')
    c = _patch(c, 'static int img_open(const char* p){img_f=tmpfile();return img_f!=NULL;}',
               'static int img_open(const char* p){img_f=fopen(p,"rb");return img_f!=NULL;}',
               'its image opener')
    start = c.index('static int img_read_block(')
    end = c.index('\n}\n', start) + 3
    c = c[:start] + '''static int img_read_block(unsigned block,unsigned char* buf){
 ++reads;
 if(fseek(img_f,(long)block*512,SEEK_SET))return 0;
 return fread(buf,1,512,img_f)==512;
}
''' + c[end:]
    c = _patch(c, 'static int reserve(const char* p,int flags){++opens;',
               'static int reserve(const char* p,int flags){++opens;'
               'if(flags!=(O_WRONLY|O_CREAT|O_EXCL))abort();', 'its reservation')
    head = c.split('int main(')[0]
    return head + r'''
int main(int argc,char** argv){
 /* argv: image, destination, dir_key, then one "NAME:type:aux:size:key" per entry */
 int i,n=argc-4;
 unsigned type,aux,key;unsigned long size;char nm[64];
 fault=0;
 strcpy(panels[1].path,argv[2]);
 strcpy(panels[0].path,argv[1]);panels[0].img_len=(unsigned char)strlen(argv[1]);
 panels[0].dir_key=(unsigned)atoi(argv[3]);
 panels[0].count=(unsigned)n;panels[0].cursor=0;
 alltags=n>0;
 for(i=0;i<n;++i){
  if(sscanf(argv[4+i],"%63[^:]:%u:%u:%lu:%u",nm,&type,&aux,&size,&key)!=5)abort();
  strncpy(entries[i].name,nm,16);entries[i].name[16]=0;
  entries[i].type=(unsigned char)type;entries[i].aux=aux;
  entries[i].size=size;entries[i].mdate=key;
 }
 note[0]=0;
 extract_targets();
 printf("NOTE %s\nOPS %u REMOVES %d OPENS %d\n",note,a2fc_ops,removes,opens);
 return 0;
}
'''


class ImEntry:
    __slots__ = ('name', 'type', 'aux', 'size', 'key')

    def __init__(self, name, type, aux, size, key):
        self.name, self.type, self.aux, self.size, self.key = name, type, aux, size, key

    def arg(self):
        return '%s:%u:%u:%u:%u' % (self.name, self.type, self.aux, self.size, self.key)


def im_block(data, n):
    off = n * BLOCK
    return data[off:off + BLOCK] if 0 <= n and off + BLOCK <= len(data) else None


def im_panel(data, dir_key=2):
    """The entries the panel would hold: `dir_open_image` and `dir_next` of
    src/a2fc.c, which is what feeds the extraction's snapshot."""
    buf = im_block(data, dir_key)
    if buf is None or (buf[4] >> 4) < 0x0E:
        return None
    if buf[4 + 0x1F] != ENTRY_LEN or buf[4 + 0x20] != PER_BLOCK:
        return None
    index, key, out = 1, dir_key, []
    while len(out) < MAX_ENTRIES:
        if index >= PER_BLOCK:
            nxt = buf[2] | (buf[3] << 8)
            if not nxt:
                break
            nb = im_block(data, nxt)
            if nb is None or (nb[0] | (nb[1] << 8)) != key:
                break                       # dir_error: the walk stops here
            buf, key, index = nb, nxt, 0
        e = buf[4 + index * ENTRY_LEN:4 + (index + 1) * ENTRY_LEN]
        index += 1
        if not e[0] & 0xF0:
            continue
        n = e[0] & 0x0F
        bad = not n
        for i in range(n):
            c = e[i + 1] | 0x20
            if (c < 0x61 or c > 0x7A) and (not i or not (0x30 <= c <= 0x39 or c == 0x2E)):
                bad = True
                break
        if bad:
            break                           # dir_error: the walk stops here
        out.append(ImEntry(e[1:1 + n].decode('latin-1'), e[0x10],
                           e[0x1F] | (e[0x20] << 8), u24(e, 0x15),
                           e[0x11] | (e[0x12] << 8)))
    return out


def im_storage(data, e, dir_key):
    """`img_storage` in src/a2fc.c: the storage type is read from the entry of
    the open image whose key block and size are the snapshot's, never guessed
    from the size. 255 directory blocks at most, so a cycle ends."""
    block, guard = dir_key, 0
    wkey = e.key.to_bytes(2, 'little')
    wsize = e.size.to_bytes(3, 'little')
    while block and guard < 255:
        buf = im_block(data, block)
        if buf is None:
            return 0
        for k in range(13):
            p = buf[4 + k * ENTRY_LEN:]
            t = p[0] >> 4
            if t and t < 0x0D and p[0x11:0x13] == wkey and p[0x15:0x18] == wsize:
                return t
        block = buf[2] | (buf[3] << 8)
        guard += 1
    return 0


def im_read(data, e, storage):
    """One file out of the image: seedling (the key is the data, beyond it a
    sparse seedling reads zeros) or sapling (the key is an index block of 256
    pointers, low bytes then high); a null pointer is a hole. Returns None on
    a read error and 2 for what the overlay refuses before reserving."""
    if e.size > 128 * 1024 or not 1 <= storage <= 2:
        return 2
    need = (e.size + 511) >> 9
    idx = None
    if storage == 2:
        idx = im_block(data, e.key)
        if idx is None:
            return None
    out, left = bytearray(), e.size
    for i in range(need):
        blk = (e.key if not i else 0) if storage == 1 else (idx[i] | (idx[256 + i] << 8))
        n = min(512, left)
        if blk:
            b = im_block(data, blk)
            if b is None:
                return None
        else:
            b = bytes(512)
        out += b[:n]
        left -= n
    return bytes(out)


def im_reference(data, entries, dir_key, existing):
    files, big, whole, why = [], 0, True, ''
    taken = set(existing)
    for e in entries:
        if e.name.startswith('.') or e.type == 0x0F:
            continue
        st = im_storage(data, e, dir_key)
        if not st:
            whole, why = False, 'no entry carries this key and size'
            break
        r = im_read(data, e, st)
        if r == 2:
            big += 1
            continue
        if r is None:
            whole, why = False, 'the image cannot be read'
            break
        if e.name in taken:
            whole, why = False, 'name already on the volume'
            break
        taken.add(e.name)
        files.append((e.name, r))
    return Expect(files, whole, why, big)


def im_verdict(note, expect):
    n = len(expect.files)
    if not expect.whole:
        return None
    if expect.extra:
        return '%u file%s extracted, %u not supported (tree/fork).' % (
            n, '' if n == 1 else 's', expect.extra)
    return '%u file%s extracted.' % (n, '' if n == 1 else 's')


# ===========================================================================
# DOS 3.3 / DOSGET
# ===========================================================================
SECT = 256
TPD, SPT = 35, 16


def d3_harness():
    """The harness of tools/test_dos_extract.py, reading a real .dsk file."""
    c = test_dos_extract.C
    c = _patch(c, 'static struct Entry entries[2];',
               'static struct Entry entries[160];', 'its entry snapshot')
    c = _patch(c, 'unsigned char fs,count,cursor,img_len;',
               'unsigned char fs,cursor,img_len;unsigned int count;', 'its panel')
    c = _patch(c, 'static int img_open(const char* p){img_f=tmpfile();return img_f!=NULL;}',
               'static int img_open(const char* p){img_f=fopen(p,"rb");return img_f!=NULL;}',
               'its image opener')
    start = c.index('static int dos_read_sector(')
    end = c.index('\n}\n', start) + 3
    c = c[:start] + '''static int dos_read_sector(unsigned t,unsigned s){
 ++reads;
 if(t>=35||s>=16)return 0;
 if(fseek(img_f,((long)t*16+s)*256,SEEK_SET))return 0;
 return fread(copy_buf,1,256,img_f)==256;
}
''' + c[end:]
    c = _patch(c, 'static int reserve(const char* p,int flags){',
               'static int reserve(const char* p,int flags){'
               'if(flags!=(O_WRONLY|O_CREAT|O_EXCL))abort();', 'its reservation')
    head = c.split('int main(')[0]
    return head + r'''
int main(int argc,char** argv){
 /* argv: image, destination, then one "NAME:type:mdate" per entry */
 int i,n=argc-3;
 unsigned type,mdate;char nm[64];
 fault=0;alltags=1;
 strcpy(panels[1].path,argv[2]);
 strcpy(panels[0].path,argv[1]);panels[0].img_len=(unsigned char)strlen(argv[1]);
 panels[0].count=(unsigned)n;panels[0].cursor=0;
 for(i=0;i<n;++i){
  if(sscanf(argv[3+i],"%63[^:]:%u:%u",nm,&type,&mdate)!=3)abort();
  strncpy(entries[i].name,nm,16);entries[i].name[16]=0;
  entries[i].type=(unsigned char)type;entries[i].mdate=mdate;
 }
 note[0]=0;
 dos_extract();
 printf("NOTE %s\nOPS %u REMOVES %d\n",note,a2fc_ops,removes);
 return 0;
}
'''


def d3_type(t):
    """`dos33_type` in src/a2fc.c: the closest ProDOS type to a DOS 3.3 one."""
    return {0x00: 0x04, 0x01: 0xFA, 0x02: 0xFC, 0x04: 0x06}.get(t & 0x7F, 0x00)


class D3Entry:
    __slots__ = ('name', 'type', 'mdate')

    def __init__(self, name, type, mdate):
        self.name, self.type, self.mdate = name, type, mdate

    def arg(self):
        return '%s:%u:%u' % (self.name, self.type, self.mdate)


def d3_sector(data, t, s):
    if t >= TPD or s >= SPT:
        return None
    off = (t * SPT + s) * SECT
    return data[off:off + SECT] if off + SECT <= len(data) else None


def d3_panel(data):
    """`read_dos33_panel` in src/a2fc.c: the VTOC, then the catalog chain."""
    v = d3_sector(data, 17, 0)
    if v is None or not 1 <= v[3] <= 3 or not v[1] or v[1] >= 35 or v[2] >= 16:
        return None
    if v[0x34] != 35 or v[0x27] != 0x7A:
        return None
    ct, cs, remaining, out = v[1], v[2], 560, []
    while ct and len(out) < MAX_ENTRIES:
        if not remaining:
            return None
        buf = d3_sector(data, ct, cs)
        if buf is None:
            return None
        remaining -= 1
        ct, cs = buf[1], buf[2]
        for i in range(7):
            if len(out) >= MAX_ENTRIES:
                break
            d = buf[0x0B + i * 0x23:0x0B + (i + 1) * 0x23]
            if not d[0]:
                ct = 0
                break
            if d[0] == 0xFF:
                continue
            n = 30
            while n > 1 and (d[2 + n] & 0x7F) == 0x20:
                n -= 1
            name = bytearray()
            for k in range(min(n, 15)):
                c = d[3 + k] & 0x7F
                if 0x61 <= c <= 0x7A:
                    c -= 32
                if not (0x41 <= c <= 0x5A or 0x30 <= c <= 0x39):
                    c = 0x2E
                name.append(c)
            if not name or not 0x41 <= name[0] <= 0x5A:
                if not name:
                    name.append(0x58)
                else:
                    name[0] = 0x58
            out.append(D3Entry(name.decode('ascii'), d3_type(d[2]),
                               (d[0] << 8) | d[1]))
    return out


def d3_read_file(data, e):
    """`d3_pass` in src/a2fc.c, which is the DOS 3.3 format plus three rules
    of the tool, all three in the comment above that function: no sector is
    read twice (a chain that loops is refused), five T/S lists at most, and a
    00/00 pair is a hole that becomes a sector of zeros once a later pair
    holds data -- the holes after the last data sector are not the file's.
    Only BIN, INT and BAS carry a header and an exact length, and a header
    cannot be a hole. Returns the bytes, or None for a refusal."""
    tslt, tsls = e.mdate >> 8, e.mdate & 0xFF
    seen, out = set(), bytearray()
    sized = e.type == 6 or e.type >= 0xFA
    skip, first, lists, left, holes = 0, True, 0, 0, 0

    def rd(t, s):
        if not t or t >= 35 or s >= 16 or (t, s) in seen:
            return None
        seen.add((t, s))
        return d3_sector(data, t, s)

    while tslt:
        lists += 1
        if lists > 5:
            return None
        buf = rd(tslt, tsls)
        if buf is None:
            return None
        tslt, tsls = buf[1], buf[2]
        if (not tslt and tsls) or tslt >= 35 or tsls >= 16:
            return None
        ts = buf[0x0C:0x0C + 244]
        for j in range(122):
            t, s = ts[2 * j], ts[2 * j + 1]
            if not t:
                if s:
                    return None
                holes += 1
                continue
            while True:
                if holes:
                    cb = bytes(SECT)
                else:
                    cb = rd(t, s)
                    if cb is None:
                        return None
                if first:
                    first = False
                    if sized and holes:
                        return None
                    skip = 2 if e.type >= 0xFA else 4 if e.type == 6 else 0
                    if skip:
                        left = cb[skip - 2] | (cb[skip - 1] << 8)
                count = SECT - skip
                if sized and count > left:
                    count = left
                out += cb[skip:skip + count]
                skip = 0
                if sized:
                    left -= count
                    if not left:
                        return None if first else bytes(out)
                if not holes:
                    break
                holes -= 1
    if first or left:
        return None
    return bytes(out)


def d3_reference(data, entries, existing):
    files, whole, why = [], True, ''
    taken = set(existing)
    for e in entries:
        if e.name.startswith('.'):
            continue
        body = d3_read_file(data, e)
        if body is None:
            whole, why = False, 'the track/sector chain is not readable'
            break
        if e.name in taken:
            whole, why = False, 'name already on the volume'
            break
        taken.add(e.name)
        files.append((e.name, body))
    return Expect(files, whole, why)


def d3_verdict(note, expect):
    n = len(expect.files)
    if expect.whole:
        return '%u file%s extracted.' % (n, '' if n == 1 else 's')
    return None


def d3_build(files):
    """A DOS 3.3 disk whose files may span several T/S lists.

    tools/mkdos33.py writes one list per file, which stops at 122 sectors; a
    campaign that never sees a chained list would never break one, so the
    chaining is done here. Everything else -- the VTOC fields, the catalog
    layout, the free map -- is that tool's, so the seeds stay the disks the
    rest of the suite reads.
    """
    dk = mkdos33.Disk()
    v = bytearray(SECT)
    v[0x01], v[0x02], v[0x03], v[0x06] = 17, 15, 3, 254
    v[0x27], v[0x34], v[0x35] = 122, TPD, SPT
    v[0x36], v[0x37] = 0, 1
    dk.put(17, 0, v)
    entries = []
    for name, dtype, data in files:
        nsect = (len(data) + SECT - 1) // SECT
        data_ts = [dk.alloc() for _ in range(nsect)]
        for i, (t, s) in enumerate(data_ts):
            dk.put(t, s, data[i * SECT:(i + 1) * SECT])
        chunks = [data_ts[i:i + 122] for i in range(0, max(1, len(data_ts)), 122)]
        lists = [dk.alloc() for _ in chunks]
        for n, (part, (lt, ls)) in enumerate(zip(chunks, lists)):
            tsl = bytearray(SECT)
            nxt = lists[n + 1] if n + 1 < len(lists) else (0, 0)
            tsl[0x01], tsl[0x02] = nxt
            tsl[0x05], tsl[0x06] = (n * 122) & 255, (n * 122) >> 8
            for i, (t, s) in enumerate(part):
                tsl[0x0C + i * 2], tsl[0x0D + i * 2] = t, s
            dk.put(lt, ls, tsl)
        e = bytearray(0x23)
        e[0], e[1], e[2] = lists[0][0], lists[0][1], dtype
        for i, ch in enumerate(name.upper().ljust(30)[:30]):
            e[3 + i] = ord(ch) | 0x80
        total = nsect + len(lists)
        e[0x21], e[0x22] = total & 0xFF, (total >> 8) & 0xFF
        entries.append(bytes(e))
    cat = list(range(15, 0, -1))
    i = 0
    for n, cs in enumerate(cat):
        c = bytearray(SECT)
        nxt = cat[n + 1] if n + 1 < len(cat) else 0
        c[0x01], c[0x02] = (17 if nxt else 0), nxt
        for slot in range(7):
            if i < len(entries):
                c[0x0B + slot * 0x23:0x0B + slot * 0x23 + 0x23] = entries[i]
                i += 1
        dk.put(17, cs, c)
        if i >= len(entries):
            break
    for t, s in dk.free:
        dk.d[mkdos33.off(17, 0) + 0x38 + t * 4 + (1 if s < 8 else 0)] |= 1 << (s & 7)
    return bytes(dk.d)


def d3_seeds():
    """Healthy DOS 3.3 disks: every type that carries a header, a text file
    over two T/S lists, a locked entry, and a truncated image file."""
    text = b'HELLO FROM DOS 3.3\r' * 30 + b'\x00'
    binary = bytes([0x00, 0x20, 0x2C, 0x01]) + bytes((i * 17 + 3) & 255 for i in range(300))
    applesoft = bytes([0x64, 0x00]) + bytes((i * 7 + 1) & 255 for i in range(100))
    integer = bytes([0x20, 0x00]) + bytes((i * 3 + 9) & 255 for i in range(32))
    long_text = bytes((i * 13 + 5) & 255 for i in range(130 * SECT))
    out = {}
    out['plain'] = d3_build([('GREETINGS', 0x00, text),
                             ('BINFILE', 0x04, binary),
                             ('MYPROG', 0x02, applesoft),
                             ('INTPROG', 0x01, integer),
                             ('LOCKED', 0x84, binary)])
    out['long'] = d3_build([('LONGTEXT', 0x00, long_text),
                            ('BINFILE', 0x04, binary)])
    out['short'] = out['plain'][:18 * SPT * SECT]       # a truncated image file
    return out


def d3_catalog_sectors(data):
    v = d3_sector(data, 17, 0)
    if v is None:
        return []
    ct, cs, out, guard = v[1], v[2], [], 0
    while ct and guard < 20:
        buf = d3_sector(data, ct, cs)
        if buf is None:
            break
        out.append((ct, cs))
        ct, cs, guard = buf[1], buf[2], guard + 1
    return out


def d3_ts_lists(data):
    """Every T/S list sector the catalog points at."""
    out = []
    for ct, cs in d3_catalog_sectors(data):
        buf = d3_sector(data, ct, cs)
        for i in range(7):
            d = buf[0x0B + i * 0x23:0x0B + (i + 1) * 0x23]
            if d[0] and d[0] != 0xFF:
                out.append((d[0], d[1]))
    return out


def d3_mutate(data, rng):
    d = bytearray(data)

    def put(t, s, off, value):
        at = (t * SPT + s) * SECT + off
        if at < len(d):
            d[at] = value & 0xFF

    kind = rng.randrange(10)
    if kind == 0:                                   # the VTOC
        field = rng.choice(['cattrack', 'catsector', 'version', 'tracks',
                            'pairs', 'bitmap'])
        off = {'cattrack': 1, 'catsector': 2, 'version': 3, 'pairs': 0x27,
               'tracks': 0x34}.get(field)
        if field == 'bitmap':
            for _ in range(rng.randrange(1, 12)):
                put(17, 0, 0x38 + rng.randrange(140), rng.randrange(256))
        else:
            put(17, 0, off, rng.choice([0, 1, 16, 17, 34, 35, 122, 0x7A, 255,
                                        rng.randrange(256)]))
        return bytes(d), 'vtoc.' + field
    cat = d3_catalog_sectors(data)
    lists = d3_ts_lists(data)
    if kind == 1 and cat:                           # the catalog chain
        t, s = rng.choice(cat)
        pick = rng.choice(['loop', 'range', 'end'])
        if pick == 'loop':
            back = rng.choice(cat)
            put(t, s, 1, back[0])
            put(t, s, 2, back[1])
        elif pick == 'range':
            put(t, s, 1, rng.choice([35, 40, 255]))
            put(t, s, 2, rng.choice([16, 200, 255]))
        else:
            put(t, s, 1, 0)
            put(t, s, 2, rng.randrange(256))
        return bytes(d), 'catalog.' + pick
    if kind == 2 and cat:                           # a catalog entry
        t, s = rng.choice(cat)
        i = rng.randrange(7)
        base = 0x0B + i * 0x23
        field = rng.choice(['tslist', 'type', 'name', 'sectors', 'deleted'])
        if field == 'tslist':
            put(t, s, base, rng.choice([0, 1, 17, 34, 35, 255, rng.randrange(256)]))
            put(t, s, base + 1, rng.choice([0, 1, 15, 16, 255, rng.randrange(256)]))
        elif field == 'type':
            put(t, s, base + 2, rng.choice([0, 1, 2, 4, 8, 0x10, 0x20, 0x40,
                                            0x80, 0x84, rng.randrange(256)]))
        elif field == 'name':
            for _ in range(rng.randrange(1, 6)):
                put(t, s, base + 3 + rng.randrange(30), rng.randrange(256))
        elif field == 'sectors':
            put(t, s, base + 0x21, rng.randrange(256))
            put(t, s, base + 0x22, rng.randrange(256))
        else:
            put(t, s, base, rng.choice([0, 0xFF]))
        return bytes(d), 'entry.' + field
    if kind == 3 and lists:                         # a track/sector list
        t, s = rng.choice(lists)
        pick = rng.choice(['loop', 'next', 'pair', 'hole', 'range', 'dup'])
        if pick == 'loop':
            put(t, s, 1, t)
            put(t, s, 2, s)
        elif pick == 'next':
            nt, ns = rng.choice(lists)
            put(t, s, 1, nt)
            put(t, s, 2, ns)
        elif pick == 'pair':
            j = rng.randrange(122)
            put(t, s, 0x0C + 2 * j, rng.randrange(256))
            put(t, s, 0x0D + 2 * j, rng.randrange(256))
        elif pick == 'hole':
            j = rng.randrange(122)
            put(t, s, 0x0C + 2 * j, 0)
            put(t, s, 0x0D + 2 * j, rng.choice([0, 0, 1]))
        elif pick == 'range':
            j = rng.randrange(8)
            put(t, s, 0x0C + 2 * j, rng.choice([35, 40, 255]))
            put(t, s, 0x0D + 2 * j, rng.randrange(256))
        else:
            j = rng.randrange(1, 8)
            at = (t * SPT + s) * SECT
            d[at + 0x0C + 2 * j] = d[at + 0x0C]
            d[at + 0x0D + 2 * j] = d[at + 0x0D]
        return bytes(d), 'tslist.' + pick
    if kind == 4 and lists:                         # the header of a sized file
        t, s = rng.choice(lists)
        buf = d3_sector(data, t, s)
        dt, ds = buf[0x0C], buf[0x0D]
        if dt:
            put(dt, ds, rng.randrange(4), rng.randrange(256))
            put(dt, ds, 2, rng.choice([0, 1, 255]))
            put(dt, ds, 3, rng.choice([0, 1, 255]))
        return bytes(d), 'header'
    if kind == 5:                                   # the image file cut short
        cuts = [0, SECT, 17 * SPT * SECT, 18 * SPT * SECT, len(d) // 2, len(d) - 1]
        return bytes(d[:rng.choice([c for c in cuts if 0 <= c <= len(d)])]), 'truncate'
    if kind == 6:                                   # blind flips
        for _ in range(rng.randrange(1, 20)):
            d[rng.randrange(len(d))] = rng.randrange(256)
        return bytes(d), 'bytes'
    if kind == 7 and cat:                           # a name of illegal bytes
        t, s = rng.choice(cat)
        i = rng.randrange(7)
        name = rng.choice([bytes(30), b' ' * 30, bytes(range(0xA0, 0xBE)),
                           b'\xc1' * 30, bytes(rng.randrange(256) for _ in range(30))])
        for k in range(30):
            put(t, s, 0x0B + i * 0x23 + 3 + k, name[k % len(name)])
        return bytes(d), 'entry.badname'
    if kind == 8 and cat:                           # two entries with one name
        if len(cat) and lists:
            t, s = cat[0]
            a = 0x0B
            b = 0x0B + 0x23
            at = (t * SPT + s) * SECT
            d[at + b:at + b + 0x23] = d[at + a:at + a + 0x23]
        return bytes(d), 'entry.twin'
    return bytes(d[:rng.randrange(0, len(d))]), 'truncate'


# ===========================================================================
# UNSHRINK's assembly core, under sim65
# ===========================================================================
CORE_CPUS = ('6502', '65c02')
# What the sim65 harness returns when the input is shorter than the stream
# header it has to read before calling the core at all.
CORE_SHORT = (11, 12, 13)


def core_build(work, bug=False):
    """src/unshrink.s and the harness of tools/test_unshrink_core.py, linked
    for both CPUs. The AUX-mirror assert is about the real $1B00 load
    address, so it is relaxed for the sim65 layout, exactly as that test
    relaxes it."""
    import shutil as _sh
    target = Path(subprocess.check_output([_sh.which('cl65'), '--print-target-path'],
                                          text=True).strip())
    src = (ROOT / 'src/unshrink.s').read_text().replace(
        '.assert us_end <= $2000', '.assert us_end <= $FFFF')
    (work / 'unshrink.s').write_text(src)
    harness = test_unshrink_core.HARNESS
    (work / 'harness.c').write_text(plant(harness, 'unshrink-core') if bug else harness)
    out = {}
    for cpu in CORE_CPUS:
        base = 'sim65c02' if cpu == '65c02' else 'sim6502'
        cfg = (target.parent / ('cfg/%s.cfg' % base)).read_text()
        cfg = cfg.replace('start = $0200, size = $FDF0 - __STACKSIZE__',
                          'start = %s, size = $FDF0 - %s - __STACKSIZE__'
                          % (test_unshrink_core.CFG_START, test_unshrink_core.CFG_START))
        cfg = cfg.replace('    CODE:     load = MAIN,   type = ro;',
                          '    CODE:     load = MAIN,   type = ro;\n'
                          '    UNSHRINK: load = MAIN,   type = ro;')
        (work / ('%s.cfg' % cpu)).write_text(cfg)
        exe = work / ('core-%s' % cpu)
        subprocess.run([_sh.which('cl65'), '-t', base, '--cpu', cpu,
                        '-C', str(work / ('%s.cfg' % cpu)), '-O', '-o', str(exe),
                        str(work / 'harness.c'), str(work / 'unshrink.s')],
                       check=True, cwd=work, capture_output=True)
        out[cpu] = str(exe)
    return out


def core_seeds():
    """Streams mkshk really produces, for both LZW formats."""
    samples = {
        'runs': test_unshrink_core.runs(1, 12000),
        'text': b'SHRINKIT ON THE APPLE II. ' * 300,
        'zeros': bytes(6000) + b'tail' * 40,
        'random': random.Random(7).randbytes(9000),
        'small': b'A' * 40,
    }
    out = {}
    for label, payload in samples.items():
        for fmt in (2, 3):
            stream, _ = mkshk.shrink(payload, fmt)
            out['%s-%d' % (label, fmt)] = (fmt, stream, len(payload))
    return out


def core_mutate(seed, rng):
    fmt, stream, size = seed
    d = bytearray(stream)
    kind = rng.randrange(6)
    if kind == 0:
        return (fmt, bytes(d[:rng.randrange(0, len(d) + 1)]), size), 'truncate'
    if kind == 1:
        for _ in range(rng.randrange(1, 8)):
            d[rng.randrange(len(d))] = rng.randrange(256)
        return (fmt, bytes(d), size), 'bytes'
    if kind == 2:                       # the stream header: CRC, volume, escape
        d[rng.randrange(min(4, len(d)))] = rng.randrange(256)
        return (fmt, bytes(d), size), 'stream.header'
    if kind == 3:                       # a chunk header: the RLE length
        at = rng.randrange(max(1, len(d) - 3))
        d[at:at + 2] = rng.choice([0, 1, 0x1000, 0x1001, 0x1FFF, 0x8000,
                                   0x9000, 0xFFFF]).to_bytes(2, 'little')
        return (fmt, bytes(d), size), 'chunk.length'
    if kind == 4:                       # the declared output size
        return (fmt, bytes(d), rng.choice([0, 1, 4095, 4096, 4097, 8192,
                                           0xFFFF, size + 4096])), 'size'
    at = rng.randrange(len(d) + 1)
    return (fmt, bytes(d[:at] + rng.randbytes(rng.randrange(1, 64)) + d[at:]),
            size), 'insert'


def core_reference(fmt, stream, size):
    """mkshk's LZW decoder, without the stream CRC the C driver checks.

    The 6502 core refuses more than this does -- an RLE length above 4096, a
    code beyond the next table entry -- so a refusal is never judged against
    it. What is judged is silence: the core must never hand back bytes that
    differ from these.
    """
    if fmt not in (2, 3):
        return None
    try:
        pos = 4 if fmt == 2 else 2
        esc, lz, out = stream[pos - 1], mkshk.Unlzw(), bytearray()
        while len(out) < size:
            if fmt == 2:
                rle_len, used = struct.unpack_from('<HB', stream, pos)
                pos += 3
                lz.reset()
            else:
                word, = struct.unpack_from('<H', stream, pos)
                rle_len, used, pos = word & 0x1FFF, word >> 15, pos + 2
            if used and fmt == 2:
                chunk, n = lz.block(stream, pos, rle_len)
            elif used:
                lzw_len = struct.unpack_from('<H', stream, pos)[0] - 4
                pos += 2
                chunk, n = lz.block(stream[:pos + lzw_len], pos, rle_len)
                if n != lzw_len:
                    return None
            else:
                chunk, n = stream[pos:pos + rle_len], rle_len
                lz.reset()
            pos += n
            if pos > len(stream):
                return None
            chunk = mkshk.rle_unpack(chunk, esc) if rle_len != mkshk.CHUNK else chunk
            out += chunk
        return bytes(out[:size])
    except Exception:
        return None


def core_run(exe, work, fmt, stream, size, timeout):
    (work / 'in.bin').write_bytes(struct.pack('<BH', fmt, size & 0xFFFF) + stream)
    try:
        p = subprocess.run([shutil.which('sim65'), exe], cwd=work,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, b'no answer in %gs' % timeout
    return p.returncode, p.stdout if p.returncode == 0 else p.stderr[-2000:]


# ===========================================================================
# the campaign
# ===========================================================================
SUCCESS = {
    'binary2': r'^\d+ file\(s\) extracted, \d+ folder\(s\) skipped\.$',
    'unshrink': r'^\d+ file\(s\) extracted\.$',
    'imgfs': r'^\d+ files? extracted(\.|, \d+ not supported \(tree/fork\)\.)$',
    'dos33': r'^\d+ files? extracted\.$',
}

# Divergences between the C and the host reference that are a property of the
# two designs, not a fault. Each names the document that carries it; the
# summary counts how often each fired. A divergence that is not one of these
# is a failure of invariant 4.
ALLOWED = {
    # NuFX stores thread_class, thread_format and thread_kind in 16 bits and
    # total_threads, file_type and extra_type in 32; `struct UsState` in
    # src/a2fc.c keeps them in a byte or a word, so the driver reads the low
    # part and ignores the high one. On any archive a writer really produces
    # the high part is zero, and a fuzzed one only ever makes the driver
    # MORE permissive: it may take for a data thread what a strict reader
    # would skip. What it writes is still the archive's own bytes, verified
    # by a second decode and by the thread CRC, so no file is lost or
    # corrupted by it. The reference therefore reads the same low part, and
    # this counter says how often an input leaned on the difference.
    'NUFX_16BIT_LOW': 'a NuFX 16- or 32-bit field whose high part is not zero',
}


class Case:
    def __init__(self, index, decoder, seed_name, mutator):
        self.index = index
        self.decoder = decoder
        self.seed = seed_name
        self.mutator = mutator
        self.failures = []
        self.fired = []
        self.note = ''
        self.kept = 0

    def fail(self, invariant, reason):
        self.failures.append((invariant, reason))


def prepare_volume(vdir, rng, names):
    """A throwaway volume with files already on it, one of which may carry the
    name a member of the input wants."""
    shutil.rmtree(vdir, ignore_errors=True)
    vdir.mkdir(parents=True)
    existing = dict(PREEXISTING)
    if names and rng.random() < 0.3:
        existing[rng.choice(names)] = b'a file that was already here\r' * 3
    for name, body in existing.items():
        (vdir / name).write_bytes(body)
    return {name: (body, (vdir / name).stat().st_mtime_ns)
            for name, body in existing.items()}


def judge(case, before, vdir, note, expect, verdict, success_re):
    """Invariants 2, 3 and 4 over one finished run."""
    for name, (body, mtime) in before.items():
        p = vdir / name
        if not p.exists():
            case.fail('2-preserve', 'the pre-existing %s was removed' % name)
        elif p.read_bytes() != body:
            case.fail('2-preserve', 'the pre-existing %s was rewritten' % name)
        elif p.stat().st_mtime_ns != mtime:
            case.fail('2-preserve', 'the pre-existing %s was reopened for writing' % name)
    left = {p.name: p.read_bytes() for p in vdir.iterdir() if p.name not in before}
    case.kept = len(left)
    ref = expect.by_name()
    for name, body in sorted(left.items()):
        if name not in ref:
            case.fail('3-reference',
                      'kept %s (%u bytes); the reference produces no such file'
                      % (name, len(body)))
        elif body != ref[name]:
            n = next((i for i in range(min(len(body), len(ref[name])))
                      if body[i] != ref[name][i]), min(len(body), len(ref[name])))
            case.fail('3-reference',
                      'kept %s: %u bytes, first difference at %u; the reference '
                      'decodes %u bytes' % (name, len(body), n, len(ref[name])))
    want = verdict(note, expect)
    if re.match(success_re, note):
        if want is None:
            case.fail('4-verdict', 'said %r of an input the reference cannot '
                                   'read whole (%s)' % (note, expect.note))
        elif note != want:
            case.fail('4-verdict', 'said %r, the reference says %r' % (note, want))
        elif set(left) != expect.names:
            case.fail('4-verdict', 'said %r but left %s; the reference produces %s'
                      % (note, sorted(left), sorted(expect.names)))
    elif want is not None:
        case.fail('4-verdict', 'refused with %r an input the reference reads '
                               'whole into %s' % (note, sorted(expect.names)))


def run_driver(exe, args, timeout):
    """The C driver, under the sanitizers. Returns (note, diagnostics)."""
    try:
        p = subprocess.run([exe] + args, env=dict(os.environ, **SAN_ENV),
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, 'no answer in %gs' % timeout
    if p.returncode:
        return None, ('exit %d\n%s' % (p.returncode,
                                       p.stderr.decode('utf-8', 'replace')[-4000:]))
    out = p.stdout.decode('utf-8', 'replace')
    if not out.startswith('NOTE '):
        return None, 'unreadable output: %r' % out[:400]
    return out.splitlines()[0][5:], ''


def case_binary2(index, state, rng, work):
    seeds = state['seeds']['binary2']
    name = rng.choice(sorted(seeds))
    data, tag = b2_mutate(seeds[name], rng)
    case = Case(index, 'binary2', name, tag)
    vdir = work / 'V'
    before = prepare_volume(vdir, rng, state['collide']['binary2'])
    src = work / 'A'
    src.write_bytes(data)
    note, diag = run_driver(state['exes']['binary2'], [str(src), str(vdir)],
                            state['timeout'])
    if note is None:
        case.fail('1-crash', diag.splitlines()[0])
        return case, data, diag
    if src.read_bytes() != data:
        case.fail('5-input', 'the archive was modified')
    case.note = note
    expect = b2_reference(data, set(before))
    case.fired += expect.fired
    judge(case, before, vdir, note, expect,
          b2_verdict, SUCCESS['binary2'])
    return case, data, diag


def case_unshrink(index, state, rng, work):
    seeds = state['seeds']['unshrink']
    name = rng.choice(sorted(seeds))
    data, tag = us_mutate(seeds[name], rng)
    case = Case(index, 'unshrink', name, tag)
    vdir = work / 'V'
    before = prepare_volume(vdir, rng, state['collide']['unshrink'])
    src = work / 'A'
    src.write_bytes(data)
    note, diag = run_driver(state['exes']['unshrink'], [str(src), str(vdir)],
                            state['timeout'])
    if note is None:
        case.fail('1-crash', diag.splitlines()[0])
        return case, data, diag
    if src.read_bytes() != data:
        case.fail('5-input', 'the archive was modified')
    case.note = note
    expect = us_reference(data, set(before))
    case.fired += expect.fired
    judge(case, before, vdir, note, expect,
          us_verdict, SUCCESS['unshrink'])
    return case, data, diag


def case_imgfs(index, state, rng, work):
    seeds = state['seeds']['imgfs']
    name = rng.choice(sorted(seeds))
    data, tag = im_mutate(seeds[name], rng)
    case = Case(index, 'imgfs', name, tag)
    entries = im_panel(data, 2)
    if entries is None:
        case.mutator = tag + '|no-panel'
        return case, data, ''
    vdir = work / 'V'
    before = prepare_volume(vdir, rng, state['collide']['imgfs'])
    src = work / 'I.PO'
    src.write_bytes(data)
    note, diag = run_driver(state['exes']['imgfs'],
                            [str(src), str(vdir), '2'] + [e.arg() for e in entries],
                            state['timeout'])
    if note is None:
        case.fail('1-crash', diag.splitlines()[0])
        return case, data, diag
    if src.read_bytes() != data:
        case.fail('5-input', 'the image was modified')
    case.note = note
    if not entries:
        return case, data, diag             # nothing tagged: the overlay returns
    expect = im_reference(data, entries, 2, set(before))
    case.fired += expect.fired
    judge(case, before, vdir, note, expect,
          im_verdict, SUCCESS['imgfs'])
    return case, data, diag


def case_dos33(index, state, rng, work):
    seeds = state['seeds']['dos33']
    name = rng.choice(sorted(seeds))
    data, tag = d3_mutate(seeds[name], rng)
    case = Case(index, 'dos33', name, tag)
    entries = d3_panel(data)
    if entries is None:
        case.mutator = tag + '|no-panel'
        return case, data, ''
    vdir = work / 'V'
    before = prepare_volume(vdir, rng, state['collide']['dos33'])
    src = work / 'I.DSK'
    src.write_bytes(data)
    note, diag = run_driver(state['exes']['dos33'],
                            [str(src), str(vdir)] + [e.arg() for e in entries],
                            state['timeout'])
    if note is None:
        case.fail('1-crash', diag.splitlines()[0])
        return case, data, diag
    if src.read_bytes() != data:
        case.fail('5-input', 'the image was modified')
    case.note = note
    if not entries:
        return case, data, diag
    expect = d3_reference(data, entries, set(before))
    case.fired += expect.fired
    judge(case, before, vdir, note, expect,
          d3_verdict, SUCCESS['dos33'])
    return case, data, diag


def case_core(index, state, rng, work):
    """The real LZW core of src/unshrink.s, on both CPUs, under sim65."""
    seeds = state['seeds']['unshrink-core']
    name = rng.choice(sorted(seeds))
    (fmt, stream, size), tag = core_mutate(seeds[name], rng)
    case = Case(index, 'unshrink-core', name, tag)
    want = core_reference(fmt, stream, size)
    diag, answers = '', {}
    for cpu, exe in sorted(state['exes']['unshrink-core'].items()):
        rc, out = core_run(exe, work, fmt, stream, size, state['timeout'])
        if rc is None:
            case.fail('1-crash', '%s: %s' % (cpu, out.decode('utf-8', 'replace')))
            diag = '%s hung' % cpu
        elif rc == 2:
            answers[cpu] = ('refused', b'')
        elif rc in CORE_SHORT:
            # The sim65 harness of tools/test_unshrink_core.py could not even
            # read the stream header: the mutation cut the input below it, so
            # there is nothing for the core to decode.
            answers[cpu] = ('short', b'')
        elif rc:
            case.fail('1-crash', '%s: exit %d' % (cpu, rc))
            diag = out.decode('utf-8', 'replace')
        else:
            answers[cpu] = ('decoded' if want is not None
                            else 'decoded, no reference', out)
            case.kept = 1
            if want is not None and out != want:
                n = next((i for i in range(min(len(out), len(want)))
                          if out[i] != want[i]), min(len(out), len(want)))
                case.fail('3-reference',
                          '%s decoded %u bytes, the reference decodes %u, first '
                          'difference at %u' % (cpu, len(out), len(want), n))
    # The same assembly, assembled twice: the two CPUs must answer the same.
    if len(answers) == len(CORE_CPUS) and len(set(answers.values())) > 1:
        case.fail('3-reference', 'the two CPUs disagree: %s'
                  % {cpu: (v, len(b)) for cpu, (v, b) in sorted(answers.items())})
    if answers:
        case.note = sorted(answers.values())[0][0]
        if case.note == 'short':
            case.mutator += '|short'
    return case, struct.pack('<BH', fmt, size & 0xFFFF) + stream, diag


CASES = {'binary2': case_binary2, 'unshrink': case_unshrink, 'imgfs': case_imgfs,
         'dos33': case_dos33, 'unshrink-core': case_core}
SUFFIX = {'binary2': '.bny', 'unshrink': '.shk', 'imgfs': '.po',
          'dos33': '.dsk', 'unshrink-core': '.lzw'}


# -- IMGFS seeds and mutators ----------------------------------------------
def im_seeds(work):
    """Healthy ProDOS images: one of every shape (the fixture of
    tools/corrupt_prodos.py, tree and extended file included, which IMGFS
    must refuse rather than truncate), and a small volume of seedlings and
    one sapling."""
    out = {}
    fixture = work / 'imfix'
    fixture.mkdir(parents=True, exist_ok=True)
    out['fixture1600'] = corrupt_prodos.make_fixture(fixture).read_bytes()
    stage = work / 'imstage'
    stage.mkdir(parents=True, exist_ok=True)
    (stage / 'HELLO.TXT').write_bytes(b'HELLO IMAGE\r' * 20)
    (stage / 'ONE.BIN').write_bytes(bytes(range(256)))
    (stage / 'SAP.BIN').write_bytes(bytes(range(256)) * 20)      # 10 blocks
    (stage / 'EMPTY.TXT').write_bytes(b'')
    sub = stage / 'SUB'
    sub.mkdir(exist_ok=True)
    (sub / 'NEST.TXT').write_bytes(b'nested\r' * 30)
    image = work / 'small.po'
    subprocess.run([sys.executable, str(ROOT / 'tools/mkvolume.py'), str(stage),
                    str(image), '--volume', 'SMALL', '--blocks', '300'],
                   check=True, capture_output=True)
    out['small300'] = image.read_bytes()
    return out


IM_NAMED = tuple(corrupt_prodos.CORRUPTIONS)


def im_mutate(data, rng):
    d = bytearray(data)
    kind = rng.randrange(8)
    if kind in (0, 1):
        # The named corruptions of tools/corrupt_prodos.py: cross-links,
        # out-of-range keys and index pointers, broken and looping chains,
        # bad storage types and names, an eof beyond the blocks, a bitmap that
        # disagrees. One to three of them, whichever this seed can host.
        names = rng.sample(IM_NAMED, rng.randrange(1, 4))
        inv = corrupt_prodos.Inventory(bytes(d))
        done = []
        for name in names:
            try:
                corrupt_prodos.CORRUPTIONS[name](d, inv)
                done.append(name)
            except (SystemExit, IndexError, ValueError):
                pass
        return bytes(d), 'named:' + (','.join(sorted(done)) or 'none')
    entries = list(corrupt_prodos.Inventory(bytes(d)).entries)
    if kind == 2 and entries:                       # a directory entry field
        ref = rng.choice(entries)
        off = ref.offset
        field = rng.choice(['storage', 'key', 'eof', 'namelen', 'name', 'type', 'aux'])
        if field == 'storage':
            d[off] = (rng.randrange(16) << 4) | (d[off] & 15)
        elif field == 'key':
            d[off + 0x11:off + 0x13] = rng.choice(
                [0, 1, 2, 3, len(d) // 512, len(d) // 512 + 1, 65535,
                 rng.randrange(65536)]).to_bytes(2, 'little')
        elif field == 'eof':
            d[off + 0x15:off + 0x18] = rng.choice(
                [0, 1, 511, 512, 513, 131071, 131072, 131073, 1 << 23,
                 rng.randrange(1 << 24)]).to_bytes(3, 'little')
        elif field == 'namelen':
            d[off] = (d[off] & 0xF0) | rng.randrange(16)
        elif field == 'name':
            d[off + 1 + rng.randrange(15)] = rng.randrange(256)
        elif field == 'type':
            d[off + 0x10] = rng.choice([0, 4, 6, 0x0F, rng.randrange(256)])
        else:
            d[off + 0x1F:off + 0x21] = rng.randrange(65536).to_bytes(2, 'little')
        return bytes(d), 'entry.' + field
    if kind == 3:                                   # a directory header or chain
        block = rng.choice([2, 3, 4, 5])
        field = rng.choice(['prev', 'next', 'entry_len', 'per_block', 'storage'])
        if field in ('prev', 'next'):
            d[block * BLOCK + (0 if field == 'prev' else 2):
              block * BLOCK + (0 if field == 'prev' else 2) + 2] = rng.choice(
                  [0, 2, block, block + 1, len(d) // 512, 65535]).to_bytes(2, 'little')
        elif field == 'entry_len':
            d[block * BLOCK + 4 + 0x1F] = rng.choice([0, 1, 0x27, 0x28, 255])
        elif field == 'per_block':
            d[block * BLOCK + 4 + 0x20] = rng.choice([0, 1, 0x0D, 0x0E, 255])
        else:
            off = block * BLOCK + 4
            d[off] = (rng.randrange(16) << 4) | (d[off] & 15)
        return bytes(d), 'dir.' + field
    if kind == 4:                                   # an index block pointer
        index = [e.key for e in entries if e.storage in (2, 3)]
        block = (rng.choice(index) if index
                 else rng.randrange(2, max(3, len(d) // BLOCK)))
        slot = rng.randrange(256)
        value = rng.choice([0, 1, block, 2, len(d) // 512, 65535,
                            rng.randrange(65536)])
        if (block + 1) * BLOCK <= len(d):
            d[block * BLOCK + slot] = value & 255
            d[block * BLOCK + 256 + slot] = value >> 8
        return bytes(d), 'index.pointer'
    if kind == 5:                                   # blind flips in the metadata
        for _ in range(rng.randrange(1, 10)):
            block = rng.choice([2, 3, 4, 5, 6, 7])
            if (block + 1) * BLOCK <= len(d):
                d[block * BLOCK + rng.randrange(BLOCK)] = rng.randrange(256)
        return bytes(d), 'bytes.meta'
    if kind == 6:                                   # the image file cut short
        cuts = [0, BLOCK, 2 * BLOCK, 3 * BLOCK, len(d) // 4, len(d) // 2, len(d) - 1]
        return bytes(d[:rng.choice([c for c in cuts if 0 <= c <= len(d)])]), 'truncate'
    for _ in range(rng.randrange(1, 40)):           # blind flips anywhere
        d[rng.randrange(len(d))] = rng.randrange(256)
    return bytes(d), 'bytes.any'


# -- the planted bugs -------------------------------------------------------
# One per decoder family, each aimed at a different invariant, so
# tools/test_fuzz_images.py can prove that the campaign really catches what it
# claims to catch. Nothing of this reaches a normal run: --bug applies them to
# the harness sources only.
BUGS = {
    # invariant 3: the cleanup of a failed record silently does not happen, so
    # the half-written file stays on the volume and is reported as removed.
    'binary2': [('static int remove_file(const char* p) {++removes;'
                 'return cleanup_bad?-1:remove(p);}',
                 'static int remove_file(const char* p) {(void)p;++removes;return 0;}')],
    # invariant 5: the archive itself is written to.
    'unshrink': [('    unshrink_entry(NULL);',
                  '    unshrink_entry(NULL);\n'
                  '    {FILE* f=fopen(full,"r+b");if(f){fputc(0,f);fclose(f);}}')],
    # invariant 2: the reservation is no longer exclusive, so a file that was
    # already on the volume is opened for writing and truncated.
    'imgfs': [('if(flags!=(O_WRONLY|O_CREAT|O_EXCL))abort();', ''),
              ('return open(p,flags,0600);',
               'return open(p,flags&~O_EXCL,0600);')],
    # invariant 3: one byte of every output lands wrong, and the cleanup that
    # the readback asks for does not happen.
    'dos33': [('static size_t write_file(const void* p,size_t s,size_t n,FILE* f)'
               '{++writes;if(fault==5)n/=2;if(fault==6)io_error=1;',
               'static size_t write_file(const void* p,size_t s,size_t n,FILE* f)'
               '{++writes;if(n>3){unsigned char c[256];memcpy(c,p,n);c[3]^=1;'
               'return fwrite(c,s,n,f);}'),
              ('static int remove_file(const char* p){++removes;return fault==8?-1:remove(p);}',
               'static int remove_file(const char* p){(void)p;++removes;return 0;}')],
    # invariant 3: the 6502 core hands back one byte that is not what it
    # decoded, which only the host reference can see.
    'unshrink-core': [('        if (write(1, (void*)0x8000, n) != n) return 14;',
                       '        *(unsigned char*)0x8000 ^= 1;\n'
                       '        if (write(1, (void*)0x8000, n) != n) return 14;')],
}


def plant(source, name):
    for old, new in BUGS[name]:
        source = _patch(source, old, new, 'the line bug %r plants into' % name)
    return source


# -- building everything once ----------------------------------------------
def build_all(work, wanted, bug=False):
    exes, seeds = {}, {}
    sources = {'binary2': b2_harness, 'unshrink': us_harness,
               'imgfs': im_harness, 'dos33': d3_harness}
    for name in wanted:
        if name == 'unshrink-core':
            exes[name] = core_build(work, bug)
            seeds[name] = core_seeds()
            continue
        c = work / (name + '_fuzz.c')
        text = sources[name]()
        c.write_text(plant(text, name) if bug else text)
        exe = work / (name + '_fuzz')
        r = subprocess.run([os.environ.get('CC', 'cc')] + CFLAGS + ['-I', str(ROOT),
                           str(c), '-o', str(exe)], capture_output=True, text=True)
        if r.returncode:
            raise SystemExit('fuzz_archives: %s harness does not compile\n%s'
                             % (name, r.stderr[-3000:]))
        exes[name] = str(exe)
        seeds[name] = {'binary2': b2_seeds, 'unshrink': us_seeds,
                       'dos33': d3_seeds}[name]() if name != 'imgfs' else im_seeds(work)
    return exes, seeds


def seed_names(seeds):
    """The names the healthy seeds of each decoder really produce.

    The pre-existing file planted on the volume is drawn from these, so the
    exclusive reservation is tested against a name the input wants, not
    against a guess that no seed happens to use.
    """
    out = {}
    for name, seed in seeds.items():
        got = set()
        for data in seed.values():
            if name == 'binary2':
                got |= b2_reference(data, set()).names
            elif name == 'unshrink':
                got |= us_reference(data, set()).names
            elif name == 'imgfs':
                entries = im_panel(data, 2) or []
                got |= im_reference(data, entries, 2, set()).names
            elif name == 'dos33':
                entries = d3_panel(data) or []
                got |= d3_reference(data, entries, set()).names
        out[name] = sorted(got)
    return out


def save(case, data, diag, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    stem = out / ('%s-%06d' % (case.decoder, case.index))
    stem.with_suffix(SUFFIX[case.decoder]).write_bytes(data)
    stem.with_suffix('.json').write_text(json.dumps({
        'case': case.index, 'decoder': case.decoder, 'seed': case.seed,
        'mutator': case.mutator, 'note': case.note,
        'failures': case.failures, 'diagnostics': diag}, indent=1) + '\n')


_STATE = {}


def _init(exes, seeds, collide, timeout, out, tmp):
    _STATE.update(exes=exes, seeds=seeds, collide=collide, timeout=timeout,
                  out=out, tmp=tmp)


def _work(job):
    decoder, index = job
    rng = random.Random('%s-%d' % (decoder, index))
    work = Path(_STATE['tmp']) / ('w%d' % (os.getpid() % 100000))
    work.mkdir(parents=True, exist_ok=True)
    try:
        case, data, diag = CASES[decoder](index, _STATE, rng, work)
    except Exception as e:                       # the campaign itself must not hide
        case = Case(index, decoder, '?', 'harness')
        case.fail('0-campaign', '%s: %s' % (type(e).__name__, e))
        data, diag = b'', ''
    if case.failures and _STATE['out'] is not None:
        save(case, data, diag, _STATE['out'])
    return {'index': case.index, 'decoder': case.decoder, 'seed': case.seed,
            'mutator': case.mutator, 'note': case.note, 'kept': case.kept,
            'failures': case.failures, 'fired': case.fired}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--count', type=int, default=200,
                    help='how many cases per decoder')
    ap.add_argument('--seed', type=int, default=1, help='the campaign seed')
    ap.add_argument('--out', type=Path, default=ROOT / 'build/fuzz-archives',
                    help='where a failing case keeps its input and its JSON')
    ap.add_argument('--decoder', choices=sorted(CASES), action='append')
    ap.add_argument('--workers', type=int, default=0, help='parallel cases')
    ap.add_argument('--timeout', type=float, default=20.0,
                    help='seconds a single run may take')
    ap.add_argument('--bug', action='store_true',
                    help='plant one bug per decoder: every invariant must bite')
    ap.add_argument('--quiet', action='store_true')
    ap.add_argument('--verbose', action='store_true',
                    help='print the mutator tally of every decoder')
    a = ap.parse_args(argv)
    wanted = a.decoder or sorted(CASES)

    with tempfile.TemporaryDirectory(prefix='a2fz', dir=TMPBASE) as tmp:
        work = Path(tmp)
        exes, seeds = build_all(work, wanted, a.bug)
        collide = seed_names(seeds)
        # The case numbers: a campaign seed picks a disjoint band, so case 7 of
        # seed 1 is always the same input and reproduces on its own.
        base = int(hashlib.sha256(str(a.seed).encode()).hexdigest()[:8], 16) & 0x3FFFFFF
        jobs = [(d, base * 1000 + i) for d in wanted for i in range(a.count)]
        results = []
        workers = a.workers or min(os.cpu_count() or 1, 8)
        if workers > 1:
            with ProcessPoolExecutor(max_workers=workers, initializer=_init,
                                     initargs=(exes, seeds, collide, a.timeout,
                                               a.out, tmp)) as pool:
                for r in pool.map(_work, jobs, chunksize=4):
                    results.append(r)
        else:
            _init(exes, seeds, collide, a.timeout, a.out, tmp)
            for job in jobs:
                results.append(_work(job))
    return report(results, a, wanted)


def shape(note):
    """One message with its counts and its file name removed: what the
    decoder *said*, so the summary can show which verdicts were reached."""
    note = re.sub(r'\d+', '#', note)
    note = re.sub(r'(Cleanup failed: |CRC error: )[A-Z0-9.]+', r'\1NAME', note)
    note = re.sub(r'Extract failed: [A-Z0-9.]+ reads back',
                  'Extract failed: NAME reads back', note)
    return re.sub(r'^[A-Z0-9.]+ extracted;', 'NAME extracted;', note)


def report(results, a, wanted):
    failures = Counter()
    fired = Counter()
    bad = [r for r in results if r['failures']]
    kept = sum(r['kept'] for r in results)
    for r in results:
        for name in r['fired']:
            fired[name] += 1
        for invariant, _ in r['failures']:
            failures[invariant] += 1
    if not a.quiet:
        print('cases           %d (%d per decoder, seed %d)'
              % (len(results), a.count, a.seed))
        print('failing cases   %d' % len(bad))
        print('invariants      %s' % (dict(sorted(failures.items())) or 'all held'))
        print('divergences     %s' % (dict(sorted(fired.items())) or 'none fired'))
        print('kept outputs    %d verified against the reference' % kept)
        for name in wanted:
            rows = [r for r in results if r['decoder'] == name]
            muts = Counter(r['mutator'].split(':')[0].split('|')[0] for r in rows)
            nopanel = sum(1 for r in rows if '|no-panel' in r['mutator'])
            extra = ', %d without a readable panel' % nopanel if nopanel else ''
            says = Counter(shape(r['note']) for r in rows)
            print('%-15s %d cases, %d mutators, %d verdicts, %d with an output%s'
                  % (name, len(rows), len(muts), len(says),
                     sum(1 for r in rows if r['kept']), extra))
            if a.verbose:
                print('  mutators  %s' % dict(sorted(muts.items())))
                for text, n in says.most_common():
                    print('  %5d  %s' % (n, text or '(no message)'))
        for r in bad[:20]:
            print('FAIL %s case %d (%s, %s, note %r)'
                  % (r['decoder'], r['index'], r['seed'], r['mutator'], r['note']))
            for invariant, why in r['failures']:
                print('     %-14s %s' % (invariant, why))
        if bad:
            print('%d failing input(s) kept in %s' % (len(bad), a.out))
    return 1 if bad else 0


if __name__ == '__main__':
    raise SystemExit(main())
