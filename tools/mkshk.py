#!/usr/bin/env python3
"""Ecrit et lit des archives ShrinkIt (NuFX, .SHK) en Python pur.

    mkshk.py SORTIE.SHK [--fmt 0|2|3] FICHIER...
    mkshk.py --list ARCHIVE.SHK
    mkshk.py --extract ARCHIVE.SHK DOSSIER
    mkshk.py --selftest

Pourquoi : c'est le generateur de fixtures et l'oracle de reference du
decodeur 6502 d'A2 File Cmd. L'exactitude des octets compte plus que la
vitesse ; la disposition suit nufxlib (Lzw.c, Record.c, Thread.c), qui
imite GSHK a l'octet pres. Le type ProDOS vient d'un suffixe NOM#TTAAAA
comme pour mkvolume ($04/0 par defaut) ; un .po ou .dsk devient une image
de disquette (genre 1, auxtype = nombre de blocs, storage_type 512).

Le format, petit-boutiste : un en-tete maitre de 48 octets ("NuFile", CRC-16
des 40 octets qui suivent, nombre d'enregistrements, dates, version 2,
longueur totale), puis les enregistrements : "NuFX", CRC-16 de la suite
jusqu'aux en-tetes de threads, attrib_count $3C, version 3, nombre de
threads, systeme 1 (ProDOS), acces, type, auxtype, storage_type, trois
dates, 16 octets par thread (classe, format, genre, CRC, longueur, longueur
compressee) et les donnees des threads dans le meme ordre. Le nom est un
thread de classe 3 (32 octets au moins, CRC 0 comme nufxlib), les donnees
un thread de classe 2 (CRC-16 seed $FFFF des octets d'origine). Un fichier
vide est toujours stocke tel quel.

La compression (2 = LZW/1, 3 = LZW/2) travaille par morceaux de 4096 octets,
le dernier complete de zeros : d'abord un RLE d'echappement $DB ([$DB valeur
compte-1] pour 4 octets identiques ou plus, et pour tout $DB ; s'il ne
raccourcit pas, le morceau reste brut), puis LZW sur cette sortie : codes de
9 a 12 bits, poids faible d'abord, table 256-4095, largeur du prochain code
9 tant que entry <= $1FE, 10 jusqu'a $3FE, 11 jusqu'a $7FE, 12 ensuite.
LZW/1 repart d'une table vide a chaque morceau ; LZW/2 la garde et emet $100
des que l'entree $FFD est prise. Si LZW ne raccourcit pas, la sortie du RLE
est ecrite telle quelle et LZW/2 vide sa table. En-tete de morceau : LZW/1 =
longueur RLE (u16) + octet 0/1 (LZW utilise) ; LZW/2 = longueur RLE | $8000
si LZW, suivi alors de la longueur du morceau en-tete compris (u16). Le flux
commence par CRC-16 (seed 0, donnees completees a 4096) + volume $FE + $DB
en LZW/1, volume $FE + $DB en LZW/2, et finit par un octet nul, comme
ShrinkIt. Verifie a l'octet pres contre nulib2 (LZW/2 et stockage).
"""
import datetime
import os
import random
import struct
import sys
from pathlib import Path

MASTER_SIG, RECORD_SIG, BXY_SIG = b'\x4e\xf5\x46\xe9\x6c\xe5', b'\x4e\xf5\x46\xd8', b'\x0a\x47\x4c'
CHUNK, ESC, VOL = 4096, 0xDB, 0xFE       # nufxlib : kNuRLEDefaultEscape, kNuLZWDefaultVol
CLEAR, FIRST, STOP = 0x100, 0x101, 0xFFD  # table vide, premiere entree, derniere
RLE_MIN_RUN = 4                           # nufxlib : matchCount > 3
WIDTH = (8, 9, 10, 10, 11, 11, 11, 11) + (12,) * 9
ACCESS_UNLOCKED, ACCESS_LOCKED = 0xE3, 0x21
_CRC = []
for _c in [i << 8 for i in range(256)]:
    for _ in range(8):
        _c = ((_c << 1) ^ 0x1021) if _c & 0x8000 else _c << 1
    _CRC.append(_c & 0xFFFF)


def crc16(data, crc=0):
    """CRC-16/XMODEM : polynome $1021, bit fort d'abord, sans reflexion."""
    for b in data:
        crc = ((crc << 8) & 0xFFFF) ^ _CRC[(crc >> 8) ^ b]
    return crc


def nufx_when(dt):
    """sec, min, heure, annee-1900, jour-1, mois-1, 0, jour de semaine (1 = dimanche)."""
    return bytes([dt.second, dt.minute, dt.hour, dt.year - 1900, dt.day - 1,
                  dt.month - 1, 0, (dt.weekday() + 1) % 7 + 1])


WHEN = nufx_when(datetime.datetime(2026, 9, 8, 12, 0, 0))


def code_width(entry):
    """Largeur du prochain code LZW, entry etant la prochaine entree du decodeur."""
    return WIDTH[(entry + 1) >> 8]


def rle_pack(block):
    out, i, n = bytearray(), 0, len(block)
    while i < n:
        v, j = block[i], i + 1
        while j < n and block[j] == v:
            j += 1
        cnt, i = j - i, j
        while cnt > 256:
            out += bytes((ESC, v, 255))
            cnt -= 256
        out += bytes((ESC, v, cnt - 1)) if cnt >= RLE_MIN_RUN or v == ESC else bytes([v]) * cnt
    return bytes(out)


def rle_unpack(data, esc=ESC):
    out, i = bytearray(), 0
    while i < len(data):
        if data[i] == esc:
            out += bytes([data[i + 1]]) * (data[i + 2] + 1)
            i += 3
        else:
            out.append(data[i])
            i += 1
    if len(out) != CHUNK:
        raise ValueError(f'RLE : {len(out)} octets au lieu de {CHUNK}')
    return bytes(out)


class Lzw:
    """Encodeur ; l'etat survit d'un morceau a l'autre pour LZW/2."""

    def __init__(self):
        self.clears = 0
        self.clear()

    def clear(self):
        self.table, self.next, self.pending_clear = {}, FIRST, False

    def block(self, data):
        out, acc, nbits = bytearray(), 0, 0

        def put(code):
            nonlocal acc, nbits
            acc |= code << nbits
            nbits += code_width(self.next - 1)   # le decodeur a une entree de retard
            while nbits >= 8:
                out.append(acc & 0xFF)
                acc, nbits = acc >> 8, nbits - 8

        def clear():
            put(CLEAR)
            self.clear()
            self.clears += 1

        if self.pending_clear:           # la table s'est remplie a la fin du morceau precedent
            clear()
        prefix, i, n = data[0], 1, len(data)
        while i < n:
            ch, i = data[i], i + 1
            code = self.table.get((prefix, ch))
            if code is not None:
                prefix = code
                continue
            put(prefix)
            self.table[(prefix, ch)] = self.next
            self.next, prefix = self.next + 1, ch
            if self.next > STOP:         # l'entree $FFD vient d'etre prise : GSHK vide la table
                put(prefix)
                if i >= n:
                    self.pending_clear = True
                    return bytes(out + bytes([acc & 0xFF] if nbits else b''))
                clear()
                prefix, i = data[i], i + 1
        put(prefix)
        self.next += 1                   # l'entree fantome que le decodeur ajoute au morceau suivant
        self.pending_clear = self.next > STOP
        return bytes(out + bytes([acc & 0xFF] if nbits else b''))


class Unlzw:
    """Decodeur, ecrit comme le fera le 6502 : prefixe + suffixe, pile de caracteres."""

    def __init__(self):
        self.prefix, self.suffix, self.old, self.final = [0] * 4097, [0] * 4097, 0, 0
        self.reset()

    def reset(self):
        self.entry, self.fresh = FIRST, True

    def block(self, buf, start, out_len):
        """Decode out_len octets depuis buf[start:] ; rend (octets, nombre d'octets lus)."""
        out, pos, bit = bytearray(), start, 0
        while len(out) < out_len:
            w = code_width(self.entry)
            code = (int.from_bytes(buf[pos:pos + 3], 'little') >> bit) & ((1 << w) - 1)
            pos, bit = pos + (bit + w) // 8, (bit + w) % 8
            if code == CLEAR:
                self.reset()
            elif self.fresh:
                if code > 0xFF:
                    raise ValueError('premier code LZW invalide')
                out.append(code)
                self.old, self.final, self.fresh = code, code, False
            else:
                p, stack = code, []
                if p >= self.entry:      # KwKwK
                    if p != self.entry:
                        raise ValueError(f'code LZW {p:#x} hors table ({self.entry:#x})')
                    stack.append(self.final)
                    p = self.old
                while p > 0xFF:
                    stack.append(self.suffix[p])
                    p = self.prefix[p]
                self.final = p
                out.append(p)
                out += bytes(reversed(stack))
                self.suffix[self.entry], self.prefix[self.entry] = p, self.old
                self.entry, self.old = self.entry + 1, code
        if len(out) != out_len:
            raise ValueError('LZW : le morceau deborde')
        return bytes(out), pos + (bit > 0) - start


def shrink(data, fmt):
    """Le flux compresse d'un thread et le nombre de vidages de table LZW/2."""
    lz, out, crc1 = Lzw(), bytearray(), 0
    for off in range(0, len(data), CHUNK):
        block = data[off:off + CHUNK].ljust(CHUNK, b'\0')
        if fmt == 2:
            crc1 = crc16(block, crc1)
            lz.clear()
        rle = rle_pack(block)
        if len(rle) >= CHUNK:
            rle = block
        lzw = lz.block(rle)
        if len(lzw) < len(rle):
            out += struct.pack('<HB', len(rle), 1) if fmt == 2 else \
                struct.pack('<HH', len(rle) | 0x8000, len(lzw) + 4)
            out += lzw
        else:
            out += (struct.pack('<HB', len(rle), 0) if fmt == 2 else struct.pack('<H', len(rle))) + rle
            lz.clear()
    head = (struct.pack('<H', crc1) if fmt == 2 else b'') + bytes((VOL, ESC))
    return head + bytes(out) + b'\0', lz.clears


def unshrink(comp, fmt, size):
    if fmt == 0:
        if len(comp) < size:
            raise ValueError('thread tronque')
        return comp[:size]
    if fmt not in (2, 3):
        raise NotImplementedError(f'format de thread {fmt}')
    pos = 4 if fmt == 2 else 2
    esc, lz, out, crc1 = comp[pos - 1], Unlzw(), bytearray(), 0
    while len(out) < size:
        if fmt == 2:
            rle_len, used = struct.unpack_from('<HB', comp, pos)
            pos += 3
            lz.reset()
        else:
            word, = struct.unpack_from('<H', comp, pos)
            rle_len, used, pos = word & 0x1FFF, word >> 15, pos + 2
        if used and fmt == 2:
            chunk, n = lz.block(comp, pos, rle_len)
        elif used:
            lzw_len = struct.unpack_from('<H', comp, pos)[0] - 4
            pos += 2
            chunk, n = lz.block(comp[:pos + lzw_len], pos, rle_len)
            if n != lzw_len:
                raise ValueError(f'LZW/2 : {n} octets lus au lieu de {lzw_len}')
        else:
            chunk, n = comp[pos:pos + rle_len], rle_len
            lz.reset()
        pos += n
        if pos > len(comp):
            raise ValueError('flux LZW tronque')
        chunk = rle_unpack(chunk, esc) if rle_len != CHUNK else chunk
        if fmt == 2:
            crc1 = crc16(chunk, crc1)
        out += chunk
    if fmt == 2 and crc1 != struct.unpack_from('<H', comp)[0]:
        raise ValueError('CRC du flux LZW/1 faux')
    return bytes(out[:size])


def make_record(e):
    name, data, fmt = e['name'].encode('latin-1'), bytes(e['data']), e.get('fmt', 3)
    blocks = e.get('disk_blocks')
    if blocks:
        if len(data) != blocks * 512:
            raise ValueError(f'{e["name"]} : {len(data)} octets pour {blocks} blocs')
        kind, ftype, aux, storage = 1, 0, blocks, 512
    else:
        kind, ftype, aux = 0, e.get('filetype', 0x04), e.get('auxtype', 0)
        storage = 1 if len(data) <= 512 else 2 if len(data) <= 131072 else 3
    comp, tfmt = (data, 0) if fmt == 0 or not data else (shrink(data, fmt)[0], fmt)
    padded = name.ljust(32, b'\0')
    body = struct.pack('<HHIHBBIIIH', 0x3C, 3, 2, 1, ord('/'), 0,
                       ACCESS_LOCKED if e.get('locked') else ACCESS_UNLOCKED,
                       ftype, aux, storage) + WHEN * 3 + struct.pack('<HH', 0, 0)
    body += struct.pack('<HHHHII', 3, 0, 0, 0, len(name), len(padded))
    body += struct.pack('<HHHHII', 2, tfmt, kind, crc16(data, 0xFFFF), len(data), len(comp))
    return RECORD_SIG + struct.pack('<H', crc16(body)) + body + padded + comp


def write_shk(path_out, entries):
    recs = b''.join(make_record(e) for e in entries)
    body = struct.pack('<I', len(entries)) + WHEN * 2 + struct.pack('<H', 2) + bytes(8)
    body += struct.pack('<I', 48 + len(recs)) + bytes(6)
    Path(path_out).write_bytes(MASTER_SIG + struct.pack('<H', crc16(body)) + body + recs)


def read_shk(path):
    buf = Path(path).read_bytes()
    if buf[:3] == BXY_SIG:
        buf = buf[128:]
    if buf[:6] != MASTER_SIG:
        raise ValueError(f'{path} : pas une archive NuFX')
    if crc16(buf[8:48]) != struct.unpack_from('<H', buf, 6)[0]:
        raise ValueError('CRC de l\'en-tete maitre faux')
    if struct.unpack_from('<I', buf, 0x26)[0] > len(buf):
        raise ValueError('archive tronquee')
    pos, out = 48, []
    for _ in range(struct.unpack_from('<I', buf, 8)[0]):
        if buf[pos:pos + 4] != RECORD_SIG:
            raise ValueError(f'enregistrement attendu a {pos:#x}')
        attr, ver, nthreads = struct.unpack_from('<HHI', buf, pos + 6)
        access, ftype, aux, storage = struct.unpack_from('<IIIH', buf, pos + 0x12)
        theads = pos + attr + struct.unpack_from('<H', buf, pos + attr - 2)[0]
        p = theads + 16 * nthreads
        if crc16(buf[pos + 6:p]) != struct.unpack_from('<H', buf, pos + 4)[0]:
            raise ValueError(f'CRC de l\'enregistrement a {pos:#x} faux')
        rec = dict(name=buf[pos + attr:theads].decode('latin-1'), data=b'', filetype=ftype,
                   auxtype=aux, kind=0, fmt=0, locked=access & 0xFF == ACCESS_LOCKED)
        for t in range(nthreads):
            cls, tfmt, kind, tcrc, teof, ceof = struct.unpack_from('<HHHHII', buf, theads + 16 * t)
            raw, p = buf[p:p + ceof], p + ceof
            if cls == 3 and kind == 0:
                rec['name'] = raw[:teof].decode('latin-1')
            elif cls == 2 and kind in (0, 1):
                data = unshrink(raw, tfmt, teof or (aux * storage if kind else 0))
                if ver >= 3 and crc16(data, 0xFFFF) != tcrc:
                    raise ValueError(f'{rec["name"]} : CRC du thread faux')
                rec.update(data=data, kind=kind, fmt=tfmt)
        out.append(rec)
        pos = p
    return out


def host_entry(path, fmt):
    name, ftype, aux = Path(path).name, 0x04, 0
    stem, sharp, suffix = name.rpartition('#')
    if sharp and len(suffix) == 6 and all(c in '0123456789abcdefABCDEF' for c in suffix):
        name, ftype, aux = stem, int(suffix[:2], 16), int(suffix[2:], 16)
    data = Path(path).read_bytes()
    e = dict(name=name.upper(), data=data, filetype=ftype, auxtype=aux, fmt=fmt)
    if name.lower().endswith(('.po', '.dsk')) and len(data) % 512 == 0:
        e.update(name=Path(name).stem.upper(), disk_blocks=len(data) // 512)
    return e


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ['--selftest']:
        return selftest()
    if argv[:1] == ['--list'] and len(argv) == 2:
        for r in read_shk(argv[1]):
            what = f'disquette {r["auxtype"]} blocs' if r['kind'] else f'${r["filetype"]:02X} ${r["auxtype"]:04X}'
            print(f'{r["name"]:20} {len(r["data"]):8}  {what}  format {r["fmt"]}')
        return 0
    if argv[:1] == ['--extract'] and len(argv) == 3:
        for r in read_shk(argv[1]):
            name = r['name'].replace('/', os.sep)
            name += '.po' if r['kind'] else f'#{r["filetype"]:02X}{r["auxtype"]:04X}'
            Path(argv[2], name).parent.mkdir(parents=True, exist_ok=True)
            Path(argv[2], name).write_bytes(r['data'])
        return 0
    fmt = 3
    if '--fmt' in argv:
        i = argv.index('--fmt')
        fmt = int(argv[i + 1])
        del argv[i:i + 2]
    if len(argv) < 2 or argv[0].startswith('--') or fmt not in (0, 2, 3):
        raise SystemExit(__doc__)
    write_shk(argv[0], [host_entry(f, fmt) for f in argv[1:]])
    return 0


def selftest():
    import tempfile
    rng = random.Random(2026)
    words = [''.join(rng.choice('abcdefghijklmnopqrstuvwxyz') for _ in range(rng.randint(2, 9)))
             for _ in range(300)]
    soup = ' '.join(rng.choice(words) for _ in range(40000)).encode()
    disk = bytearray(280 * 512)
    disk[1024:1024 + 120000] = soup[:120000]     # des blocs pleins, d'autres vides
    cases = [('VIDE', b''), ('UN', b'A'), ('BLOC', bytes(range(256)) * 16),
             ('BLOCPLUS1', bytes(range(256)) * 16 + b'!'), ('ZEROS', bytes(8192)),
             ('ALEA', rng.randbytes(10000)), ('TEXTE', (b'Apple II forever ' * 2000)[:20000]),
             ('ESCAPES', bytes(rng.choice((0xDB, 0xDB, 0x41)) for _ in range(6000)) + b'\xdb' * 300),
             ('SOUPE', soup), ('DISK', bytes(disk))]
    sizes = {}
    with tempfile.TemporaryDirectory() as tmp:
        for fmt in (0, 2, 3):
            entries = [dict(name=n, data=d, filetype=0x06, auxtype=0x2000 + i, fmt=fmt,
                            locked=i % 2 == 0) for i, (n, d) in enumerate(cases[:-1])]
            entries.append(dict(name='DISK', data=bytes(disk), fmt=fmt, disk_blocks=280))
            write_shk(Path(tmp, f'test{fmt}.shk'), entries)
            back = read_shk(Path(tmp, f'test{fmt}.shk'))
            assert len(back) == len(entries)
            for e, r in zip(entries, back):
                assert r['name'] == e['name'] and r['data'] == e['data'], e['name']
                assert r['kind'] == (1 if 'disk_blocks' in e else 0)
                assert r['fmt'] == (fmt if e['data'] else 0)
                if r['kind']:
                    assert r['auxtype'] == 280
                else:
                    assert (r['filetype'], r['auxtype'], r['locked']) == \
                        (e['filetype'], e['auxtype'], bool(e.get('locked')))
                comp, clears = shrink(e['data'], fmt) if fmt and e['data'] else (e['data'], 0)
                sizes[e['name'], fmt] = len(comp)
                assert clears or fmt != 3 or e['name'] != 'DISK', 'la table LZW/2 ne s\'est jamais remplie'
    assert sizes['TEXTE', 3] < 20000 // 8, sizes['TEXTE', 3]
    print(f'{"":12}{"brut":>8}{"LZW/1":>8}{"LZW/2":>8}')
    for n, d in cases:
        print(f'{n:12}{len(d):8}{sizes[n, 2]:8}{sizes[n, 3]:8}')
    print('selftest : OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
