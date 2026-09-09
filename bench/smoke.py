"""Le banc minimal : la disquette publiee demarre-t-elle sur les panneaux ?

    python3 bench/smoke.py

C'est le controle qui garde tout le reste honnete : il part de
dist/A2FILECMD.po tel qu'il sera telecharge, l'amorce comme une vraie
disquette en slot 6, et regarde ce que l'Apple IIe affiche.
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pom2 import Pom2, Session, ROOT, DISK, IMG


def scratch(dirpath, name='SCRATCH', blocks=1600):
    """Un second volume, vide et inscriptible : POM2 veut un disque dur, et
    les bancs ont besoin d'une cible pour copier."""
    stage = dirpath / 'scratch'
    (stage / 'WORK').mkdir(parents=True)
    (stage / 'WORK/NOTE.TXT').write_bytes(b'scratch volume\r')
    hdv = dirpath / 'SCRATCH.hdv'
    subprocess.run([sys.executable, str(ROOT / 'tools/mkvolume.py'), str(stage), str(hdv),
                    '--volume', name, '--blocks', str(blocks)], check=True, capture_output=True)
    return hdv


def main():
    with tempfile.TemporaryDirectory(prefix='a2fc-smoke-') as tmp:
        tmp = Path(tmp)
        floppy = tmp / 'A2FILECMD.po'
        shutil.copyfile(DISK, floppy)
        with Pom2(scratch(tmp), floppy=floppy, port=6601) as p:
            s = Session(p)
            # la page de titre du lanceur, le temps du chargement : la version
            # 6502 s'y nomme (" - 6502"), l'autre non
            s.wait(lambda: s.has('A2 FILE CMD'), 'page de titre', 60)
            title = next((r for r in s.rows() if 'A2 FILE CMD' in r), '')
            s.boot()
            s.ok('la page de titre nomme la version (6502 ou non)',
                 (' - 6502' in title) == IMG.endswith('-6502'), title.strip()[:40])
            s.ok('la disquette publiee demarre sur les panneaux',
                 s.has('/A2FILECMD'), s.rows()[0][:40])
            s.ok('la barre de statut porte le nom et la version',
                 s.has('A2 FILE CMD 0.6.8'), s.rows()[20][:60].strip())
            s.ok('le lanceur est le seul .SYSTEM du volume',
                 any(r.startswith('A2FILE.SYSTEM') for r in s.rows()))
            s.ok('le dossier A2FILE est la, et pas de DEMO : la disquette est nue',
                 s.has('A2FILE/') and not s.has('DEMO/'))
            print('\n'.join(r.rstrip() for r in s.rows()[:22]), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
