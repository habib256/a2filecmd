#!/usr/bin/env python3
"""Banc COMPARE et SEARCH : deux surcouches lancees par le menu !.

    make disk && POM2=/chemin/vers/pom2_playtest python3 bench/find.py

COMPARE (A2FILE/COMPARE.PLG) confronte le fichier selectionne a celui de meme
nom dans l'autre panneau, octet par octet : identique, ou premier octet qui
differe. SEARCH (A2FILE/SEARCH.PLG) demande un texte et marque, dans le
panneau actif, les fichiers qui le contiennent (insensible a la casse). Les
fichiers d'essai sont dans des sous-dossiers a eux, petits, pour que la
lecture reste rapide (SEARCH lit chaque fichier en entier)."""

import shutil, sys, tempfile, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from pom2 import Pom2, Session, ROOT, DISK
from run import scratch_volume, RET, TAB, volume


def main():
    checks = []
    def ok(label, cond, detail=''):
        checks.append(bool(cond))
        print(('PASS ' if cond else 'FAIL ') + label + (' ' + str(detail) if detail else ''), flush=True)

    with tempfile.TemporaryDirectory(prefix='a2fc-find-') as tmp:
        tmp = Path(tmp)
        floppy = tmp / 'A2FILECMD.po'
        shutil.copyfile(DISK, floppy)
        hdv = scratch_volume(tmp)
        stage = tmp / 'scratch'
        # deux dossiers pour COMPARE, un troisieme pour SEARCH -- petits fichiers.
        (stage / 'DIRA').mkdir(); (stage / 'DIRB').mkdir(); (stage / 'FIND').mkdir()
        (stage / 'DIRA/SAME.TXT').write_bytes(b'hello world here\r' * 3)
        (stage / 'DIRB/SAME.TXT').write_bytes(b'hello world here\r' * 3)      # identique
        (stage / 'DIRA/DIFF.TXT').write_bytes(b'the planet mars\r' * 3)
        (stage / 'DIRB/DIFF.TXT').write_bytes(b'the planet moon\r' * 3)       # differe a l'octet 12
        (stage / 'FIND/HASIT.TXT').write_bytes(b'a line with WIDGET inside\r')
        (stage / 'FIND/NOPE.TXT').write_bytes(b'nothing to see here\r')
        hdv = volume(stage, tmp / 'SCRATCH.hdv', 'SCRATCH', 1600)

        with Pom2(hdv, floppy=floppy, port=6708, mouse=True) as p:
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

            def menu(letter):
                s.key(b'!'); s.wait(lambda: s.has('the overlays'), 'menu', 30); p.stable()
                s.key(letter); p.stable(); s.key(RET)

            # ── COMPARE ──────────────────────────────────────────────────
            open_panel(40, 'DIRB'); open_panel(0, 'DIRA')
            s.select('SAME', 0); p.stable()
            menu(b'C'); s.wait(lambda: s.has('Identical') or s.has('Differ'), 'compare 1', 15); p.stable()
            ok('COMPARE : deux fichiers identiques', s.has('Identical'), s.rows()[22].strip()[:40])
            s.select('DIFF', 0); p.stable()
            menu(b'C'); s.wait(lambda: s.has('Identical') or s.has('Differ'), 'compare 2', 15); p.stable()
            ok('COMPARE : deux fichiers qui different, a l octet 12',
               s.has('Differ at byte 12'), s.rows()[22].strip()[:40])

            # ── SEARCH ───────────────────────────────────────────────────
            open_panel(0, 'FIND')
            menu(b'S'); s.wait(lambda: s.has('Search for'), 'invite', 15); p.stable()
            s.type('WIDGET'); s.key(RET)
            s.wait(lambda: s.has('contain') or s.has('No file'), 'recherche', 30); p.stable()
            ok('SEARCH : un seul fichier contient le texte', s.has('1 file(s) contain'),
               s.rows()[22].strip()[:40])
            s.select('HASIT', 0); p.stable()
            ok('SEARCH : le fichier trouve est marque', s.line(0).lstrip().startswith('HASIT') and '*' in s.line(0)[:24],
               s.line(0).rstrip()[:24])

    passed = sum(1 for c in checks if c)
    print(f'\n{passed}/{len(checks)} controles', flush=True)
    return 0 if passed == len(checks) else 1


if __name__ == '__main__':
    sys.exit(main())
