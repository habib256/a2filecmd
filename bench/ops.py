#!/usr/bin/env python3
"""Banc des operations longues : la barre de progression sur toute la ligne,
ESC qui interrompt une copie, une suppression qui se voit fichier par fichier.

    make disk && POM2=/chemin/vers/pom2_playtest python3 bench/ops.py

/SCRATCH porte BIG (300 Ko, un fichier "tree") et trois petits fichiers ; la
copie de BIG vers /SCRATCH/OUT est assez longue pour lire la barre en ligne 22
et pour l'interrompre par ESC : le fichier partiel doit avoir disparu de la
cible et le message dire ou l'on en etait. Puis trois fichiers marques se
copient, et se suppriment avec la barre."""

import re, shutil, sys, tempfile, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pom2 import Pom2, Session, ROOT
from run import scratch_volume, RET, TAB, ESC, volume

BAR = re.compile(r'^ *1/1 {2,}BIG +\[[#.]{40}\] +\d+/\d+ *$')


def main():
    checks = []
    def ok(label, cond, detail=''):
        checks.append(bool(cond))
        print(('PASS ' if cond else 'FAIL ') + label + (' ' + str(detail) if detail else ''), flush=True)

    with tempfile.TemporaryDirectory(prefix='a2fc-ops-') as tmp:
        tmp = Path(tmp)
        floppy = tmp / 'A2FILECMD.po'
        shutil.copyfile(ROOT / 'dist/A2FILECMD.po', floppy)
        scratch_volume(tmp)
        stage = tmp / 'scratch'
        (stage / 'BIG.BIN').write_bytes(bytes(range(256)) * 1200)        # 300 Ko
        for n in ('AA', 'BB', 'CC'):
            (stage / (n + '.TXT')).write_bytes((n + ' small file\r').encode() * 3)
        hdv = volume(stage, tmp / 'SCRATCH.hdv', 'SCRATCH', 1600)

        with Pom2(hdv, floppy=floppy, port=6742, speed=20000) as p:
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

            open_panel(40, 'OUT')            # cible : /SCRATCH/OUT (droite)
            open_panel(0)                    # source : /SCRATCH (gauche)
            # 1. la barre, lue pendant la copie, puis ESC
            s.select('BIG', 0); p.stable()
            s.key(b'C')
            seen, t0 = None, time.time()
            while time.time() - t0 < 30:
                row = s.rows()[22].rstrip()
                if BAR.match(row) and '#' in row:
                    seen = row; break
                time.sleep(0.05)
            ok('la barre de progression prend toute la ligne 22 (40 cases, compteur, octets)', seen is not None, seen)
            s.key(ESC)
            s.wait(lambda: s.has('Interrupted'), 'interruption', 60); p.stable()
            ok('ESC interrompt la copie et le dit', s.has('Interrupted: 0 of 1 done.'), s.rows()[22].strip()[:50])
            ok('le fichier partiel a ete retire de la cible', not any(r[40:].startswith('BIG ') for r in s.rows()))
            # 2. trois fichiers marques se copient, et la cible les montre
            for n in ('AA', 'BB', 'CC'):
                s.select(n, 0); s.key(b' ')
            p.stable()
            s.key(b'C'); s.wait(lambda: s.has('copied') or s.has('failed'), 'copie', 60); p.stable()
            ok('trois fichiers marques copies', s.has('3 files copied'), s.rows()[22].strip()[:40])
            ok('la cible les montre', all(any(r[40:].startswith(n + ' ') for r in s.rows()) for n in ('AA', 'BB', 'CC')))
            # 3. la suppression, avec la barre, et les entrees disparaissent
            s.key(TAB)                       # la cible, /SCRATCH/OUT
            for n in ('AA', 'BB', 'CC'):
                s.select(n, 40); s.key(b' ')
            p.stable()
            s.key(b'D'); s.wait(lambda: s.has('Delete 3 tagged files?'), 'confirmation'); s.key(b'Y')
            s.wait(lambda: s.has('deleted') or s.has('failed'), 'suppression', 60); p.stable()
            ok('D supprime les trois avec le compte', s.has('3 items deleted.'), s.rows()[22].strip()[:40])
            ok('et ils ont disparu du panneau', not any(r[40:].startswith(('AA ', 'BB ', 'CC ')) for r in s.rows()))

    passed = sum(1 for c in checks if c)
    print(f'\n{passed}/{len(checks)} controles', flush=True)
    return 0 if passed == len(checks) else 1


if __name__ == '__main__':
    sys.exit(main())
