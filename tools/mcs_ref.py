#!/usr/bin/env python3
"""Reference sequencer for Music Construction Set's 2304-byte exports.

The format and sequencing follow published MUSIC SOURCE (Will Harvey,
1983), available in cybernesto/mcs-player, MIT. See NOTICE. Editor .OBJ
files are notation objects, not these two 1152-byte note buffers.
"""
from pathlib import Path
import argparse

STAFF = 1152
PERIODS = [int(s, 16) for s in '''
1d 1e 20 22 24 26 29 2b 2e 30 33 36 3a 3d 41 44
48 4d 51 56 5b 61 67 6d 73 7a 81 89 91 9a a3 ac
b7 c1 cd d9 e6 f4 102 112 122 133 145 159 16d 183 19a 1b2
1cc 1e8 205 223 244 266 28b 2b2 2db 306 334 365 398 3cf 1 1
'''.split()]


def validate(data):
    if len(data) != 2 * STAFF:
        raise ValueError('expected two 1152-byte staff buffers')
    ends = []
    for base in (0, STAFF):
        seen = False
        chord = False
        for p in range(base, base + STAFF, 2):
            pitch, flags = data[p:p + 2]
            if pitch >> 1 == 0 and flags == 0:
                if chord or not seen:
                    raise ValueError('empty staff or unterminated chord')
                ends.append(p)
                break
            if pitch >= 128 or not flags & 63:
                raise ValueError('pitch or duration out of range')
            seen = True
            chord = bool(flags & 128)
        else:
            raise ValueError('unterminated staff')
    return ends


def fixture(staff0=None, staff1=None):
    """Synthetic, freely redistributable song: rests, chords and ties."""
    if staff0 is None:
        staff0 = [(60, 0x84), (64, 0x44), (124, 2), (76, 3)]
    if staff1 is None:
        staff1 = [(84, 0x84), (88, 4), (92, 2), (96, 3)]
    out = bytearray()
    for staff in (staff0, staff1):
        buf = bytes(v for pair in staff for v in pair) + b'\0\0'
        if len(buf) > STAFF:
            raise ValueError('staff too long')
        out.extend(buf.ljust(STAFF, b'\0'))
    return bytes(out)


def frames(data, tempo=4):
    """28 AY register bytes, initial frame then each hardware tick.

    One play-through stops when either staff reaches its terminator, where
    the published player would restart both staffs. Tick period: VIA latch
    $40FF plus the 6522's two-cycle reload interval.
    """
    ends = validate(data)
    pos, count, tied = [0, STAFF], [1, 1], [False, False]
    owner = [None] * 6
    regs = bytearray(28)
    regs[0] = regs[2] = regs[4] = regs[14] = regs[16] = regs[18] = 1
    regs[7] = regs[21] = 0xf8
    tc = dc = 0
    frequency = 1

    def plug(v, amp):
        chip, tone = divmod(v, 3)
        r = chip * 14 + tone * 2
        regs[r:r + 2] = frequency.to_bytes(2, 'little')
        regs[chip * 14 + 8 + tone] = amp

    yield bytes(regs)
    while True:
        dc += 1
        if dc == 3:
            dc = 0
            for v, staff in enumerate(owner):
                if staff is not None and not tied[staff]:
                    chip, tone = divmod(v, 3)
                    r = chip * 14 + 8 + tone
                    if regs[r] != 8:
                        regs[r] -= 1
        tc += 1
        if tc == tempo:
            tc = 0
            for staff in range(2):
                count[staff] -= 1
                if count[staff]:
                    continue
                for v in range(6):
                    if owner[v] == staff:
                        owner[v] = None
                        plug(v, 0)
                while True:
                    if pos[staff] == ends[staff]:
                        return
                    scan = range(6) if staff == 0 else range(5, -1, -1)
                    v = next((v for v in scan if owner[v] is None), 5 if staff == 0 else 0)
                    owner[v] = staff
                    pitch, flags = data[pos[staff]:pos[staff] + 2]
                    pos[staff] += 2
                    frequency = PERIODS[pitch >> 1]
                    plug(v, 10)
                    tied[staff] = bool(flags & 64)
                    count[staff] = flags & 63
                    if not flags & 128:
                        break
        yield bytes(regs)


def disk_exports(path):
    """Read only known exports from the reference toolkit's DOS disk.

    Reject failed directory reads and cyclic chains; DosImage validates
    sector bounds and the DOS binary length. No writes to the source.
    """
    from take1_ref import DosImage
    disk = DosImage(Path(path).read_bytes())
    v = disk.sector(17, 0)
    t, s = v[1:3]
    seen = set()
    while t or s:
        if (t, s) in seen:
            raise ValueError('cyclic catalog')
        seen.add((t, s))
        cat = disk.sector(t, s)
        for i in range(7):
            e = cat[11 + 35 * i:46 + 35 * i]
            if e[0] in (0, 255) or e[2] & 127 != 4:
                continue
            name = bytes(c & 127 for c in e[3:33]).decode('ascii').rstrip()
            data = disk.read_file(e[0], e[1])
            if len(data) != 2 * STAFF:
                continue
            try:
                validate(data)
            except ValueError:
                continue
            yield name, data
        t, s = cat[1:3]


def original_frames(data, player):
    """Execute the ORIGINAL 6502 player, not a second copy of our algorithm.

    `player` is MCS-MB from the public reference toolkit disk (load $8500).
    Emulate its interrupt calls and compare BUFFER $8400/$8410 each tick.
    The tiny CPU records RAM accesses; VIA writes are disposable RAM here.
    """
    from mos6502 import CPU
    validate(data)
    cpu = CPU()
    cpu.m[0x8500:0x8500 + len(player)] = player
    cpu.m[0x8900:0x8900 + len(data)] = data
    cpu.call(0x8503)  # INIT jump-table entry
    regs = lambda: bytes(cpu.m[0x8400:0x840e] + cpu.m[0x8410:0x841e])
    yield regs()
    for tick in range(200000):
        cpu.writes.clear()
        sentinel = 0xfff0
        cpu.push(sentinel >> 8)
        cpu.push(sentinel & 255)
        cpu.push(cpu.p(0x20))
        cpu.pc = 0x8500  # INTRUPT jump-table entry, returns with RTI
        for step in range(10000):
            if cpu.pc == sentinel:
                break
            op = cpu.fetch()
            cpu.ops[op]()
        else:
            raise ValueError('original interrupt did not return')
        if 0x3fe in cpu.writes:  # SONGADDS restarted the whole song
            return
        yield regs()
    raise ValueError('original song did not terminate')


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('song', type=Path)
    args = ap.parse_args()
    data = args.song.read_bytes()
    print('MCS export:', len(list(frames(data))), 'ticks')
