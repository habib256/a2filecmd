#!/usr/bin/env python3
"""Banc BINARY2 : extraire une archive Binary II (.BNY) vers un dossier ProDOS.

    make disk && POM2=/chemin/vers/pom2_playtest python3 bench/bny.py

tools/mkbny.py fabrique l'archive (format verifie octet a octet contre
nulib2), le banc la pose sur /SCRATCH, l'ouvre par le menu ! (surcouche
A2FILE/BINARY2.PLG) vers un dossier, puis verifie que chaque fichier en sort
avec son nom, son type et sa taille."""

import shutil, sys, tempfile, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from pom2 import Pom2, Session, ROOT, DISK
from run import scratch_volume, RET, TAB, ESC, volume
import mkbny

ONE = b'the first file inside\r' * 3      # 63 octets
TWO = b'and the second file here\r' * 5   # 125 octets, non multiple de 128 -> bourrage


def main():
    checks = []
    def ok(label, cond, detail=''):
        checks.append(bool(cond))
        print(('PASS ' if cond else 'FAIL ') + label + (' ' + str(detail) if detail else ''), flush=True)

    with tempfile.TemporaryDirectory(prefix='a2fc-bny-') as tmp:
        tmp = Path(tmp)
        floppy = tmp / 'A2FILECMD.po'
        shutil.copyfile(DISK, floppy)
        hdv = scratch_volume(tmp)
        stage = tmp / 'scratch'
        (stage / 'OUT').exists() or (stage / 'OUT').mkdir()
        mkbny.write_bny(stage / 'ARC.BNY', [
            {'name': 'ONE', 'data': ONE, 'filetype': 0x04, 'auxtype': 0},
            {'name': 'TWO', 'data': TWO, 'filetype': 0x06, 'auxtype': 0x1234}])
        hdv = volume(stage, tmp / 'SCRATCH.hdv', 'SCRATCH', 1600)

        with Pom2(hdv, floppy=floppy, port=6714, mouse=True) as p:
            s = Session(p)
            s.boot()

            def open_panel(x, *names):
                if s.cursor_row(x) is None:
                    s.key(TAB)
                s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'volumes')
                if s.cursor_row(x) is None:
                    s.key(TAB)
                s.select('/SCRATCH', x); s.key(RET)
                s.wait(lambda: s.rows()[0][x:x + 8] == '/SCRATCH', 'scratch'); p.stable()
                for n in names:
                    s.select(n, x); s.key(RET)
                    s.wait(lambda: ('/SCRATCH/' + n) in s.rows()[0][x:], 'dossier ' + n); p.stable()

            open_panel(40, 'OUT')            # cible : /SCRATCH/OUT (panneau droit)
            open_panel(0)                    # l'archive : /SCRATCH (panneau gauche)
            s.select('ARC.BNY', 0); p.stable()
            s.key(b'!'); s.wait(lambda: s.has('the overlays'), 'menu', 30); p.stable()
            s.key(b'B'); p.stable(); s.key(b'B'); p.stable()   # BASLIST puis BINARY2
            s.key(RET)
            s.wait(lambda: s.has('extracted') or s.has('failed') or s.has('Binary'), 'extraction', 30)
            p.stable()
            ok('BINARY2 : deux fichiers extraits', s.has('2 file(s) extracted'), s.rows()[22].strip()[:40])
            ok('BINARY2 : l autre panneau les montre tout de suite, sans y entrer',
               any(r[40:].startswith('ONE ') for r in s.rows()) and any(r[40:].startswith('TWO ') for r in s.rows()),
               [r[40:56].strip() for r in s.rows()[2:8]])

            open_panel(0, 'OUT')             # regarder la cible
            s.select('ONE', 0); p.stable()
            ok('BINARY2 : ONE a la bonne taille et le type TXT',
               str(len(ONE)) in s.line(0) and 'TXT' in s.line(0), s.line(0).rstrip()[:40])
            s.select('TWO', 0); p.stable()
            ok('BINARY2 : TWO a la bonne taille, le type BIN et l auxtype $1234',
               str(len(TWO)) in s.line(0) and 'BIN' in s.line(0) and '1234' in s.line(0),
               s.line(0).rstrip()[:40])
            s.key(ESC) if s.value('view', 1) else None
            # contenu : ONE est un TXT, il s'ouvre dans la visionneuse de texte
            s.select('ONE', 0); p.stable()
            s.key(RET); s.wait(lambda: s.value('view', 1) == 2, 'vue ONE', 20); p.stable()
            ok('BINARY2 : le contenu de ONE est correct', s.has('the first file inside'),
               ''.join(s.rows()[2:3]).strip()[:30])

    passed = sum(1 for c in checks if c)
    print(f'\n{passed}/{len(checks)} controles', flush=True)
    return 0 if passed == len(checks) else 1


if __name__ == '__main__':
    sys.exit(main())
