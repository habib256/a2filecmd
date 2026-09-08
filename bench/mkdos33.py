#!/usr/bin/env python3
"""Fabrique une disquette DOS 3.3 minimale (.dsk, ordre DOS) pour tester la
lecture DOS 3.3 d'A2 File Cmd : une VTOC, un catalogue, et quelques fichiers."""
import sys
from pathlib import Path

SECT = 256
TPD, SPT = 35, 16
SIZE = TPD * SPT * SECT

def off(track, sector):
    return (track * SPT + sector) * SECT

class Disk:
    def __init__(self):
        self.d = bytearray(SIZE)
        # sectors allocated by the writer; start free-map tracking after DOS area
        self.free = []  # list of (track, sector) available for files
        for t in range(3, 17):            # tracks 3..16 for files (image kept small for tests)
            for s in range(SPT):
                self.free.append((t, s))
    def put(self, track, sector, data):
        o = off(track, sector)
        self.d[o:o+len(data)] = data
    def alloc(self):
        return self.free.pop(0)

def build(files):
    """files: list of (name, dos_type, data_bytes)"""
    dk = Disk()
    # VTOC
    v = bytearray(SECT)
    v[0x01] = 17          # catalog track
    v[0x02] = 15          # catalog sector
    v[0x03] = 3           # DOS 3.3
    v[0x06] = 254         # volume
    v[0x27] = 122         # max T/S pairs
    v[0x34] = TPD
    v[0x35] = SPT
    v[0x36] = 0; v[0x37] = 1   # 256 bytes/sector
    dk.put(17, 0, v)
    # write files, build catalog entries
    entries = []
    for name, dtype, data in files:
        nsect = (len(data) + SECT - 1) // SECT
        data_ts = [dk.alloc() for _ in range(nsect)]
        # write data sectors
        for i, (t, s) in enumerate(data_ts):
            dk.put(t, s, data[i*SECT:(i+1)*SECT])
        # T/S list sector
        tsl_t, tsl_s = dk.alloc()
        tsl = bytearray(SECT)
        tsl[0x00] = 0
        tsl[0x01] = 0; tsl[0x02] = 0   # no next T/S list
        for i, (t, s) in enumerate(data_ts):
            tsl[0x0C + i*2] = t
            tsl[0x0C + i*2 + 1] = s
        dk.put(tsl_t, tsl_s, tsl)
        # catalog entry
        e = bytearray(0x23)
        e[0] = tsl_t; e[1] = tsl_s; e[2] = dtype
        nm = name.upper().ljust(30)[:30]
        for i, ch in enumerate(nm):
            e[3+i] = ord(ch) | 0x80
        total = nsect + 1
        e[0x21] = total & 0xFF; e[0x22] = (total >> 8) & 0xFF
        entries.append(bytes(e))
    # catalog sectors: track 17, sectors 15 down to 1, 7 entries each
    cat_sectors = list(range(15, 0, -1))
    ei = 0
    for idx, cs in enumerate(cat_sectors):
        c = bytearray(SECT)
        nxt = cat_sectors[idx+1] if idx+1 < len(cat_sectors) else 0
        c[0x01] = 17 if nxt else 0
        c[0x02] = nxt
        for slot in range(7):
            if ei < len(entries):
                c[0x0B + slot*0x23 : 0x0B + slot*0x23 + 0x23] = entries[ei]
                ei += 1
        dk.put(17, cs, c)
        if ei >= len(entries):
            break
    return bytes(dk.d)

def main():
    out = Path(sys.argv[1])
    # Applesoft file: 2-byte length header + tokenized (we fake a tiny program)
    applesoft = bytes([0x05,0x00]) + b'\x00\x00'  # minimal
    text = b'HELLO FROM DOS 3.3\r' * 5 + b'\x00'
    binary = bytes([0x00,0x20, 0x04,0x00]) + b'\x01\x02\x03\x04'  # addr $2000, len 4
    data = build([
        ('GREETINGS', 0x00, text),      # T
        ('MYPROG', 0x02, applesoft),    # A
        ('BINFILE', 0x04, binary),      # B
    ])
    data = data[:18 * SPT * SECT]      # 18 tracks : VTOC (17) + catalogue + fichiers, sous 128 Ko
    out.write_bytes(data)
    print(f'{out}: DOS 3.3, {len(data)} bytes')

if __name__ == '__main__':
    main()
