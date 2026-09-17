#!/usr/bin/env python3
"""Banc de la surcouche AWDATA (src/plugins/awdata.c) : les bases de donnees
($19) et les tableurs ($1B) d'AppleWorks, lus a l'ecran.

    make all disk && A2FC_IMG=A2FILECMD-full python3 bench/awdata.py

tools/test_awdata.py compare chaque ecran du C a la reference sur l'hote,
avec un remplacant pour l'impression des nombres ; ce banc fait tourner la
surcouche livree, et donc le vrai FOUT de la ROM Applesoft : un tableur
synthetique aligne les cas de format (point sans zero, notation E, neuf
chiffres), relus contre tools/awdata_ref.py. Les fichiers PRESIDENTS et
MATH.QUIZ des essais de CiderPress II s'y ajoutent quand ils sont la
(tools/cp2_samples.py). Retour ouvre AWDATA, Espace/B/R naviguent, Echap
rend les panneaux avec le curseur sur le fichier, resident et pile C
intacts."""
import struct
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from xplug import boot_hd, menu_run, ok_all, RET, ESC
import awdata_ref as ref
import cp2_samples

PORT = 6855

NUMBERS = [0.5, 1.0, -2.25, 100.0, 0.01, 0.001, 123456789.0, 1e9, 1234567891.0,
           1 / 3, 0.1, -1e-10, 2.0 ** 100, 0.0, 1e300, 3.14159265358979, 65535.0,
           -0.75, 1e-38, 99999999.5, 12.5e6, 7e-3, 2.5e-2]


def numbers_sheet():
    """Un tableur : une constante par ligne, puis une formule qui en cite une."""
    body = bytearray(b'\x00\x00')
    for i, v in enumerate(NUMBERS, 1):
        cellb = bytes([0xA0, 0x00]) + struct.pack('<d', v)
        r = i.to_bytes(2, 'little') + bytes([len(cellb)]) + cellb + b'\xff'
        body += len(r).to_bytes(2, 'little') + r
    f = bytes([0x80, 0x00]) + struct.pack('<d', 42.0) + b'\xdc\xf9\xfe\x00\xf0\xff\xfc\xfe\x00\xff\xff\xf4'
    r = (30).to_bytes(2, 'little') + bytes([0x81, len(f)]) + f + b'\xff'
    body += len(r).to_bytes(2, 'little') + r + b'\xff\xff'
    head = bytearray(300)
    head[242] = 30
    return bytes(head) + bytes(body)


def screen(s):
    rows = s.rows()
    return [r.rstrip() for r in rows[:22]], rows[23]


def main():
    sheet = numbers_sheet()
    files = {'WORK/NUMBERS#1B0000': sheet}
    v = cp2_samples.volume()
    real = {}
    for name, key in (('PRESIDENTS', '/DOCS/PRESIDENTS'), ('MATH.QUIZ', '/DOCS/MATH.QUIZ')):
        if key in v:
            t, aux, data = v[key]
            files['WORK/%s#%02X%04X' % (name, t, aux)] = data
            real[name] = data
    with tempfile.TemporaryDirectory(prefix='a2fc-awdata-') as tmp:
        with boot_hd(tmp, files, port=PORT, plugins=['awdata']) as (p, s):
            stack = p.peek(0x80, 2)
            p.poke(s.sym['_a2fc_ops'], b'\x2a\x00')
            s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'volumes')
            s.select('/WORKHD'); s.key(RET)
            s.wait(lambda: s.rows()[0].startswith('/WORKHD '), 'la racine'); p.stable()
            s.select('WORK'); s.key(RET)
            s.wait(lambda: s.has('/WORKHD/WORK'), 'WORK'); p.stable()

            # 1. Les nombres par la ROM : Retour sur un $1B.
            lines, end = ref.ss_lines(sheet)
            s.select('NUMBERS', 0); p.stable()
            s.key(RET)
            s.wait(lambda: 'NUMBERS  page 1' in s.rows()[23], 'la page 1', 60); p.stable()
            rows, bar = screen(s)
            for want, got in zip(lines[:22], rows):
                s.ok('FOUT : %s' % want, ref.same_line(got, want.rstrip()), got)
            s.ok('NUMBERS : page 1 sans fin', '(end)' not in bar, bar)
            s.key(b' '); p.stable()
            rows, bar = screen(s)
            s.ok('NUMBERS : page 2, la formule',
                 all(ref.same_line(g, w.rstrip()) for g, w in zip(rows, lines[22:])), rows[:3])
            s.ok('NUMBERS : page 2 (end)', 'page 2 (end)' in bar, bar)
            s.key(b' '); p.stable()
            s.ok('NUMBERS : Espace a la fin reste', 'page 2 (end)' in s.rows()[23])
            s.key(b'B'); p.stable()
            s.ok('NUMBERS : B revient a la page 1', 'NUMBERS  page 1' in s.rows()[23])
            s.key(ESC)
            s.wait(lambda: s.has('! More'), 'retour aux panneaux', 60); p.stable()
            s.ok('NUMBERS : curseur sur le fichier', s.line(0).startswith('NUMBERS '), s.line(0))
            s.ok('NUMBERS : resident et pile C preserves',
                 s.value('ops') == 42 and p.peek(0x80, 2) == stack)

            # 2. La base de donnees reelle, par le menu.
            if 'PRESIDENTS' in real:
                names, recs, end = ref.db_records(real['PRESIDENTS'])
                s.select('PRESIDENTS', 0); p.stable()
                menu_run(s, p, 'AWDATA')
                s.wait(lambda: 'record 1 of %d' % len(recs) in s.rows()[23], 'la fiche 1', 60)
                p.stable()
                for k in (0, 1, 2, 3):
                    rows, bar = screen(s)
                    want = [r.rstrip() for r in ref.db_screen(names, recs[k])]
                    s.ok('PRESIDENTS : fiche %d' % (k + 1), rows[:len(want)] == want,
                         [r for r, w in zip(rows, want) if r != w][:2])
                    s.ok('PRESIDENTS : barre %d' % (k + 1),
                         bar.startswith('PRESIDENTS  record %d of %d ' % (k + 1, len(recs))), bar)
                    s.key(b' '); p.stable()
                s.key(b'R'); p.stable()
                s.ok('PRESIDENTS : R revient a la fiche 1',
                     'record 1 of' in s.rows()[23] and screen(s)[0][0] == ref.db_screen(names, recs[0])[0].rstrip())
                s.key(ESC)
                s.wait(lambda: s.has('! More'), 'retour aux panneaux', 60); p.stable()

            # 3. Le tableur reel : toutes les pages.
            if 'MATH.QUIZ' in real:
                lines, end = ref.ss_lines(real['MATH.QUIZ'])
                pages = [lines[i:i + 22] for i in range(0, len(lines), 22)]
                s.select('MATH.QUIZ', 0); p.stable()
                s.key(RET)
                bad = []
                for k, want in enumerate(pages):
                    s.wait(lambda: 'MATH.QUIZ  page %d' % (k + 1) in s.rows()[23], 'la page', 60)
                    p.stable()
                    rows, bar = screen(s)
                    if not all(ref.same_line(g, w.rstrip()) for g, w in zip(rows, want)):
                        bad.append(k + 1)
                    s.key(b' ')
                s.ok('MATH.QUIZ : les %d pages' % len(pages), not bad, bad)
                p.stable()
                s.ok('MATH.QUIZ : la derniere page dit (end)', '(end)' in s.rows()[23], s.rows()[23])
                s.key(ESC)
                s.wait(lambda: s.has('! More'), 'retour aux panneaux', 60); p.stable()
    return ok_all(s, 'awdata')


if __name__ == '__main__':
    sys.exit(main())
