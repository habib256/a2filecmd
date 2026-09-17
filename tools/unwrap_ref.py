#!/usr/bin/env python3
"""AppleSingle and MacBinary: the reference for the UNWRAP overlay.

    unwrap_ref.py FILE          # prints what UNWRAP extracts
    unwrap_ref.py --selftest

unwrap(data, wrapper_name) -> (name, type, aux, data fork, resource length)
or None, as src/plugins/unwrap.c decides; the makers build test files.
The formats are summed up in unwrap.c's header comment (after CiderPress
II's AppleSingle and MacBinary notes and File Type Note $E0/0001).
"""
import struct
import sys
from pathlib import Path


def prodos_name(raw):
    out = ''
    for c in raw:
        if 97 <= c <= 122:
            c -= 32
        ch = chr(c)
        if not ('A' <= ch <= 'Z' or '0' <= ch <= '9' or ch == '.'):
            ch = '.'
        if not out and not 'A' <= ch <= 'Z':
            continue
        out += ch
        if len(out) == 15:
            break
    return out


def hfs_type(t):
    """ProDOS (type, aux) of a Mac type and creator, 8 bytes."""
    mt, cr = t[:4], t[4:8]
    if mt == b'TEXT':
        return 0x04, 0
    if mt == b'MIDI':
        return 0xD7, 0
    if mt == b'AIFF':
        return 0xD8, 0
    if mt == b'AIFC':
        return 0xD8, 1
    if mt == b'dImg' and cr == b'dCpy':
        return 0xE0, 0x8005
    if cr == b'pdos':
        if mt == b'PSYS':
            return 0xFF, 0
        if mt == b'PS16':
            return 0xB3, 0
        if mt[0] == ord('p'):
            return mt[1], mt[2] << 8 | mt[3]
        if mt[2:] == b'  ' and all(chr(c) in '0123456789ABCDEF' for c in mt[:2]):
            return int(mt[:2], 16), 0
    return 0, 0


def crc16(data):
    c = 0
    for b in data:
        c ^= b << 8
        for _ in range(8):
            c = ((c << 1) ^ 0x1021) & 0xFFFF if c & 0x8000 else (c << 1) & 0xFFFF
    return c


def apple_single(data):
    if len(data) < 26 or data[:4] != b'\x00\x05\x16\x00' or data[4:8] not in (
            b'\x00\x01\x00\x00', b'\x00\x02\x00\x00'):
        return None
    v1 = data[5] == 1
    n = struct.unpack('>H', data[24:26])[0]
    name, typed, fork, rsrc = '', 0, None, 0
    ptype = paux = 0
    for i in range(n):
        o = 26 + 12 * i
        if o + 12 > len(data):
            return 'broken'
        eid, at, ln = struct.unpack('>III', data[o:o + 12])
        if at > len(data) or ln > len(data) - at:
            return 'broken'
        if eid == 1:
            fork = data[at:at + ln]
        elif eid == 2:
            rsrc = ln
        elif eid == 3 and ln:
            name = prodos_name(data[at:at + min(ln, 63)])
        elif eid == 11 and ln >= 8:
            ptype, paux, typed = data[at + 3], data[at + 6] << 8 | data[at + 7], 2
        elif eid == 7 and v1 and ln >= 16 and data[8:14] == b'ProDOS':
            ptype, paux, typed = data[at + 11], data[at + 14] << 8 | data[at + 15], 2
        elif eid == 9 and ln >= 8 and typed != 2:
            ptype, paux = hfs_type(data[at:at + 8])
            typed = 1
    if fork is None:
        return 'broken'
    return name, ptype, paux, fork, rsrc


def mac_binary(data):
    h = data[:128]
    if len(h) < 128 or h[0] or not 1 <= h[1] <= 63 or h[74] or h[82]:
        return None
    if crc16(h[:124]) != struct.unpack('>H', h[124:126])[0] and any(h[99:128]):
        return None
    ln, rsrc = struct.unpack('>II', h[83:91])
    if ln > len(data) - 128:
        return None
    t, a = hfs_type(h[65:73])
    return prodos_name(h[2:2 + h[1]]), t, a, data[128:128 + ln], rsrc


def unwrap(data, wrapper):
    r = apple_single(data)
    if r is None:
        r = mac_binary(data)
    if r is None or r == 'broken':
        return None
    name, t, a, fork, rsrc = r
    if t == 0x0F or len(fork) > 0xFFFFFF:
        return None
    if not name:
        name = prodos_name(wrapper.encode())
        if '.' in name[1:]:
            name = name[:name.rindex('.')]
    return name, t, a, fork, rsrc


# -- makers --------------------------------------------------------------------

def make_as(entries, version=2, home=b''):
    """AppleSingle from [(id, bytes)], in that order."""
    head = b'\x00\x05\x16\x00' + bytes([0, version, 0, 0]) + home.ljust(16, b'\0' if version == 2 else b' ')[:16]
    head += struct.pack('>H', len(entries))
    at = len(head) + 12 * len(entries)
    table, body = b'', b''
    for eid, blob in entries:
        table += struct.pack('>III', eid, at + len(body), len(blob))
        body += blob
    return head + table + body


def make_mb(name, mtype, fork, rsrc=b'', version=2):
    h = bytearray(128)
    h[1] = len(name)
    h[2:2 + len(name)] = name
    h[65:73] = mtype
    h[83:87] = len(fork).to_bytes(4, 'big')
    h[87:91] = len(rsrc).to_bytes(4, 'big')
    if version >= 2:
        h[122], h[123] = 0x81, 0x81
        h[124:126] = crc16(bytes(h[:124])).to_bytes(2, 'big')
    pad = lambda b: b + bytes(-len(b) % 128)
    return bytes(h) + pad(fork) + pad(rsrc)


def selftest():
    assert prodos_name(b'hello world!') == 'HELLO.WORLD.'
    assert prodos_name(b'1st file') == 'ST.FILE'
    assert prodos_name(b'x' * 40) == 'X' * 15
    assert hfs_type(b'p\x06\x20\x00pdos') == (6, 0x2000)
    assert hfs_type(b'FC  pdos') == (0xFC, 0)
    assert hfs_type(b'TEXTttxt') == (4, 0)
    assert hfs_type(b'APPLMSWD') == (0, 0)
    a = make_as([(3, b'Read Me'), (11, b'\x00\xc3\x00\x04\x00\x00\x00\x00'), (1, b'hi\r')])
    assert unwrap(a, 'X.AS') == ('READ.ME', 4, 0, b'hi\r', 0)
    a = make_as([(1, b'data'), (2, b'rsrc')], version=1, home=b'ProDOS')
    assert unwrap(a, 'FOO.AS') == ('FOO', 0, 0, b'data', 4)
    m = make_mb(b'Game', b'p\x06\x08\x00pdos', b'\x01' * 300, b'r')
    assert unwrap(m, 'GAME.BIN') == ('GAME', 6, 0x800, b'\x01' * 300, 1)
    m1 = make_mb(b'Old', b'TEXTttxt', b'abc', version=1)
    assert unwrap(m1, 'OLD.BIN') == ('OLD', 4, 0, b'abc', 0)
    assert unwrap(b'\0' * 200, 'Z') is None
    print('selftest: names, types, AppleSingle, MacBinary')


def main():
    if sys.argv[1:] == ['--selftest']:
        selftest()
        return 0
    p = Path(sys.argv[1])
    r = unwrap(p.read_bytes(), p.name)
    if r is None:
        print('not an AppleSingle or MacBinary file')
        return 1
    name, t, a, fork, rsrc = r
    print('%s: %d bytes, $%02X/$%04X, resource fork %d' % (name, len(fork), t, a, rsrc))
    return 0


if __name__ == '__main__':
    sys.exit(main())
