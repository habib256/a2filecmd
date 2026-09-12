#!/usr/bin/env python3
"""Banc AWP : un document AppleWorks se lit page par page.

    make disk && POM2=/chemin/vers/pom2_playtest python3 bench/awp.py

tools/mkawp.py ecrit deux documents sur /SCRATCH : LETTER (format 3.0, avec
le mot a sauter apres l'en-tete, des enrichissements et des tabulations) et
OLD (format 2.x). Entree ouvre le premier dans la surcouche AWP, Espace
tourne la page, T ouvre le second ; ce que montre l'ecran est compare a ce
que mkawp.read_awp relit du fichier."""

import shutil, sys, tempfile, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from pom2 import Pom2, Session, ROOT, DISK
from archive_support import archive_floppy
from run import scratch_volume, RET, TAB, ESC, volume
import mkawp, mkdemo

OLD = "An older AppleWorks file, version two.\n\nIt has no word to skip after the header.\n"


def main():
    checks = []
    def ok(label, cond, detail=''):
        checks.append(bool(cond))
        print(('PASS ' if cond else 'FAIL ') + label + (' ' + str(detail) if detail else ''), flush=True)

    with tempfile.TemporaryDirectory(prefix='a2fc-awp-') as tmp:
        tmp = Path(tmp)
        floppy = archive_floppy(tmp, 'AWP')
        scratch_volume(tmp)
        stage = tmp / 'scratch'
        mkawp.write_awp(stage / 'LETTER#1A0000', mkdemo.LETTER)
        mkawp.write_awp(stage / 'OLD#1A0000', OLD, version=0)
        hdv = volume(stage, tmp / 'SCRATCH.hdv', 'SCRATCH', 1600)
        letter = mkawp.read_awp(stage / 'LETTER#1A0000')
        old = mkawp.read_awp(stage / 'OLD#1A0000')

        with Pom2(hdv, floppy=floppy, port=6720, mouse=True) as p:
            s = Session(p)
            s.boot()
            s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'volumes')
            s.select('/SCRATCH'); s.key(RET)
            s.wait(lambda: s.rows()[0][:9] == '/SCRATCH ', 'scratch'); p.stable()
            s.select('LETTER'); p.stable()
            ok('le type $1A se lit AWP dans la colonne Type', 'AWP' in s.line(), s.line()[:40])
            s.key(RET); s.wait(lambda: s.value('view', 1) == 2, 'vue AWP', 20); p.stable()
            shown = [r.rstrip() for r in s.rows()[:22]]
            ok('Entree ouvre le document, la premiere page est celle du fichier',
               shown == [l.rstrip() for l in letter[:22]],
               next((f'{i}: {a!r} != {b!r}' for i, (a, b) in enumerate(zip(shown, letter)) if a.rstrip() != b.rstrip()), ''))
            ok('le gras est saute, la tabulation rendue',
               s.has('A2 FILE CMD -- A LETTER') and not s.has('*A2') and any(r.startswith('        Name    Type') for r in s.rows()),
               next((r[:40] for r in s.rows() if 'Name' in r), ''))
            s.key(b' '); time.sleep(1); p.stable()
            ok('Espace tourne la page', s.has('page 2') and s.has(letter[22].strip()[:30]), s.rows()[22][40:60])
            s.key(b'B'); time.sleep(1); p.stable()
            ok('B revient a la premiere', s.has('page 1'), s.rows()[22][40:60])
            s.key(ESC); s.wait(lambda: s.value('view', 1) == 0, 'retour'); p.stable()
            s.select('OLD'); p.stable(); s.key(b'T')
            s.wait(lambda: s.value('view', 1) == 2, 'vue OLD', 20); p.stable()
            ok('T lit un fichier AppleWorks 2.x (sans mot a sauter)',
               s.rows()[0].rstrip() == old[0] and s.rows()[2].rstrip() == old[2] and s.has('(end)'),
               s.rows()[0][:40])
            s.key(ESC); s.wait(lambda: s.value('view', 1) == 0, 'retour'); p.stable()

    passed = sum(1 for c in checks if c)
    print(f'\n{passed}/{len(checks)} controles', flush=True)
    return 0 if passed == len(checks) else 1


if __name__ == '__main__':
    sys.exit(main())
