#!/usr/bin/env python3
"""Ecrit et lit des archives Binary II (.BNY) en Python pur.

    mkbny.py SORTIE.BNY FICHIER...
    mkbny.py --list ARCHIVE.BNY
    mkbny.py --extract ARCHIVE.BNY DOSSIER
    mkbny.py --selftest

Pourquoi : c'est le generateur de fixtures et l'oracle de reference du
decodeur 6502 d'A2 File Cmd. L'exactitude des octets prime ; la disposition
suit la specification d'origine de Gary B. Little (Binary ][, novembre 1986,
telle que reprise par la File Type Note Apple II et nulib2/nufxlib). Le type
ProDOS vient d'un suffixe NOM#TTAAAA comme pour mkvolume et mkshk (type $06,
auxtype 0 par defaut).

Une archive Binary II est une simple concatenation d'entrees. Chaque entree
est un en-tete d'information de 128 octets suivi des `eof` octets de donnees,
completes de zeros jusqu'au multiple de 128 suivant : l'en-tete suivant
commence donc a 128 + arrondi(eof, 128) de l'en-tete courant. Le compteur
"fichiers a suivre" a +$7F vaut n-1 dans la premiere entree, puis decroit
jusqu'a 0 dans la derniere.

En-tete de 128 octets, petit-boutiste (offsets verifies contre la spec
nulib.com et ciderpress2.com) :

  +$00  3  signature $0A $47 $4C
  +$03  1  acces ProDOS ($E3 : lecture/ecriture/renom/destruction)
  +$04  1  type de fichier ProDOS
  +$05  2  auxtype ProDOS
  +$07  1  storage_type ProDOS
  +$08  2  taille en blocs de 512 octets
  +$0A  2  date de modification ProDOS
  +$0C  2  heure de modification ProDOS
  +$0E  2  date de creation ProDOS
  +$10  2  heure de creation ProDOS
  +$12  1  octet d'identification $02
  +$13  1  reserve
  +$14  3  longueur du fichier en octets (EOF)
  +$17  1  longueur du nom (1..64)
  +$18 64  nom / chemin ProDOS en majuscules
  +$75  4  espace disque total (premiere entree seulement)
  +$79  1  type de systeme d'exploitation
  +$7A  2  type de fichier natif
  +$7C  1  drapeau de fichier fantome
  +$7D  1  drapeaux de donnees
  +$7E  1  numero de version Binary II
  +$7F  1  nombre de fichiers a suivre

Note d'offsets : la spec range bien la version a +$7E et le compteur
"fichiers a suivre" a +$7F (et non l'inverse) ; l'EOF est a +$14 et la
longueur du nom a +$17. Verifie a l'octet pres : nulib2 -btv liste et
-bx extrait les fichiers produits ici a l'identique.
"""
import datetime
import os
import struct
import sys
from pathlib import Path

MAGIC = b'\x0a\x47\x4c'
HDR = 128
ACCESS = 0xE3                # detruire, renommer, ecrire, lire
BNY_VERSION = 0              # $00 = spec d'origine (novembre 1986)


def prodos_when(dt):
    """(mot date, mot heure) ProDOS pour un datetime."""
    return (((dt.year % 100) << 9) | (dt.month << 5) | dt.day,
            (dt.hour << 8) | dt.minute)


WHEN = prodos_when(datetime.datetime(2026, 9, 8, 12, 0, 0))


def roundup(n, m=HDR):
    """Le plus petit multiple de m superieur ou egal a n."""
    return (n + m - 1) // m * m


def prodos_layout(eof):
    """(storage_type, taille en blocs de 512) pour un fichier de `eof` octets."""
    data = (eof + 511) // 512
    if data <= 1:
        return 1, data                       # seedling
    if data <= 256:
        return 2, data + 1                    # sapling : + un bloc d'index
    idx = (data + 255) // 256
    return 3, data + idx + 1                  # tree : + index maitre et index


def make_header(e, follow, disk_space):
    """L'en-tete de 128 octets d'une entree ; `follow` fichiers la suivent."""
    name = e['name'].encode('ascii')
    if not 1 <= len(name) <= 64:
        raise ValueError(f'nom de 1 a 64 octets attendu : {e["name"]!r}')
    eof = len(e['data'])
    storage, blocks = prodos_layout(eof)
    h = bytearray(HDR)
    h[0x00:0x03] = MAGIC
    h[0x03] = ACCESS
    h[0x04] = e.get('filetype', 0x06) & 0xFF
    h[0x05:0x07] = struct.pack('<H', e.get('auxtype', 0) & 0xFFFF)
    h[0x07] = storage
    h[0x08:0x0A] = struct.pack('<H', blocks & 0xFFFF)
    h[0x0A:0x0C] = struct.pack('<H', WHEN[0])
    h[0x0C:0x0E] = struct.pack('<H', WHEN[1])
    h[0x0E:0x10] = struct.pack('<H', WHEN[0])
    h[0x10:0x12] = struct.pack('<H', WHEN[1])
    h[0x12] = 0x02
    h[0x14:0x17] = struct.pack('<I', eof)[:3]
    h[0x17] = len(name)
    h[0x18:0x18 + len(name)] = name
    h[0x75:0x79] = struct.pack('<I', disk_space)   # nul sauf premiere entree
    h[0x7E] = BNY_VERSION
    h[0x7F] = follow & 0xFF
    return bytes(h)


def write_bny(path_out, entries):
    """Ecrit une archive .BNY a partir d'une liste de dicts {name, data,
    filetype, auxtype}. Complete chaque fichier de zeros au multiple de 128."""
    n = len(entries)
    disk_space = sum(prodos_layout(len(e['data']))[1] for e in entries)
    out = bytearray()
    for i, e in enumerate(entries):
        data = bytes(e['data'])
        out += make_header(e, n - 1 - i, disk_space if i == 0 else 0)
        out += data + bytes(roundup(len(data)) - len(data))
    Path(path_out).write_bytes(bytes(out))


def read_bny(path):
    """Lit une archive .BNY -> liste de dicts {name, data, filetype, auxtype}.
    Verifie la signature, lit exactement `eof` octets, saute le bourrage, et
    s'arrete quand "fichiers a suivre" tombe a 0 ou que le fichier finit."""
    buf = Path(path).read_bytes()
    pos, out = 0, []
    while pos + HDR <= len(buf):
        h = buf[pos:pos + HDR]
        if h[0x00:0x03] != MAGIC or h[0x12] != 0x02:
            raise ValueError(f'signature Binary II absente a {pos:#x}')
        eof = int.from_bytes(h[0x14:0x17], 'little')
        nlen = h[0x17]
        if not 1 <= nlen <= 64:
            raise ValueError(f'longueur de nom {nlen} invalide a {pos:#x}')
        name = h[0x18:0x18 + nlen].decode('latin-1')
        start = pos + HDR
        if start + eof > len(buf):
            raise ValueError(f'{name} : donnees tronquees a {pos:#x}')
        out.append(dict(name=name, data=buf[start:start + eof],
                        filetype=h[0x04], auxtype=struct.unpack('<H', h[0x05:0x07])[0]))
        pos = start + roundup(eof)
        if h[0x7F] == 0:
            break
    if not out:
        raise ValueError(f'{path} : archive Binary II vide ou invalide')
    return out


def host_entry(path):
    """Un dict d'entree depuis un fichier hote, type via suffixe NOM#TTAAAA."""
    name, ftype, aux = Path(path).name, 0x06, 0
    stem, sharp, suffix = name.rpartition('#')
    if sharp and len(suffix) == 6 and all(c in '0123456789abcdefABCDEF' for c in suffix):
        name, ftype, aux = stem, int(suffix[:2], 16), int(suffix[2:], 16)
    return dict(name=name.upper(), data=Path(path).read_bytes(),
                filetype=ftype, auxtype=aux)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ['--selftest']:
        return selftest()
    if argv[:1] == ['--list'] and len(argv) == 2:
        for r in read_bny(argv[1]):
            print(f'{r["name"]:20} {len(r["data"]):8}  ${r["filetype"]:02X} ${r["auxtype"]:04X}')
        return 0
    if argv[:1] == ['--extract'] and len(argv) == 3:
        Path(argv[2]).mkdir(parents=True, exist_ok=True)
        for r in read_bny(argv[1]):
            fn = f'{r["name"]}#{r["filetype"]:02X}{r["auxtype"]:04X}'.replace('/', os.sep)
            Path(argv[2], fn).write_bytes(r['data'])
        return 0
    if len(argv) < 2 or argv[0].startswith('--'):
        raise SystemExit(__doc__)
    write_bny(argv[0], [host_entry(f) for f in argv[1:]])
    return 0


def selftest():
    import tempfile
    sets = {
        'un fichier': [
            dict(name='HELLO', data=b'Apple II forever\r', filetype=0x04, auxtype=0)],
        'trois types/tailles': [
            dict(name='SHORT', data=b'\x01\x02\x03', filetype=0x06, auxtype=0x0300),
            dict(name='DEUXCENTS', data=bytes(range(200)), filetype=0x04, auxtype=0),
            dict(name='TROISCENTS', data=(b'x' * 300), filetype=0xFF, auxtype=0x2000)],
        'multiple exact de 128': [
            dict(name='BLOC', data=bytes(range(128)) * 2, filetype=0x06, auxtype=0),
            dict(name='UNBLOC', data=bytes(128), filetype=0x06, auxtype=0)],
        'fichier vide': [
            dict(name='VIDE', data=b'', filetype=0x04, auxtype=0),
            dict(name='APRES', data=b'ok', filetype=0x06, auxtype=0)],
    }
    with tempfile.TemporaryDirectory() as tmp:
        for label, entries in sets.items():
            p = Path(tmp, 'test.bny')
            write_bny(p, entries)
            raw = p.read_bytes()
            assert len(raw) % HDR == 0, f'{label} : longueur {len(raw)} non multiple de 128'
            back = read_bny(p)
            assert len(back) == len(entries), f'{label} : {len(back)} lus sur {len(entries)}'
            # La chaine "fichiers a suivre" : n-1, n-2, ... 0.
            for i in range(len(entries)):
                off = sum(HDR + roundup(len(e['data'])) for e in entries[:i])
                assert raw[off:off + 3] == MAGIC, f'{label} : signature perdue a {off}'
                assert raw[off + 0x7F] == len(entries) - 1 - i, \
                    f'{label} : compteur faux, entree {i}'
            for e, r in zip(entries, back):
                assert r['name'] == e['name'], f'{label} : nom {r["name"]} != {e["name"]}'
                assert r['data'] == e['data'], f'{label} : donnees de {e["name"]}'
                assert r['filetype'] == e['filetype'], f'{label} : type de {e["name"]}'
                assert r['auxtype'] == e['auxtype'], f'{label} : aux de {e["name"]}'
            n = sum(len(d['data']) for d in entries)
            print(f'{label:24} {len(entries)} entrees, {len(raw):6} octets '
                  f'({n} de donnees)  OK')
    print('selftest : OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
