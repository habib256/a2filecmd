#!/usr/bin/env python3
"""Banc de la surcouche FIXTYPES (src/plugins/fixtypes.c) : le type et
l'auxtype ProDOS des fichiers marques (ou du fichier sous le curseur)
d'apres le .SUFFIXE de leur nom, puis le suffixe retire du nom si on
repond Y.

    make build/fixtypes.PLG && A2FC_IMG=A2FILECMD-full python3 bench/fixtypes.py

Le disque dur du banc reste en memoire dans POM2 : les fichiers d'essai sont
poses sur une disquette en lecteur 2 (recopiee dans son fichier a l'arret),
et c'est ce .po que l'on relit sur l'hote pour verifier types, auxtypes et
noms -- l'ecran seul ne prouve rien.

Les fichiers sont crees en $06 avec leur suffixe dans le nom (NOM#060000,
sinon mkvolume retirerait .TXT et .BAS en les typant lui-meme). DUP.TXT a un
voisin DUP : il est type mais garde son nom. BOOT.SYSTEM et DISK.PO gardent
leur suffixe (ProDOS amorce les .SYSTEM, A2FC ouvre les images par leur
suffixe). UNKNOWN.XYZ n'est pas touche.

Deux passages : WORK depuis le panneau DROIT, huit fichiers marques, Y a la
question (la surcouche emprunte alors la table du panneau gauche pour relire
le repertoire actif) ; WORK2 depuis le panneau gauche, rien de marque, le
curseur sur ONE.BAS, N a la question."""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from xplug import boot_hd, menu_run, ok_all, RET, TAB
from pom2 import ROOT
from prodos_read import Image

PORT = 6802
SHK = b'NuFile' + bytes(range(60))
FILES = {
    'WORK/ARCHIVE.SHK#060000': SHK,
    'WORK/LETTER.AWP#060000': b'letter',
    'WORK/PROG.BAS#060000': b'\x0a\x00',
    'WORK/NOTE.TXT#060000': b'note\r',
    'WORK/UNKNOWN.XYZ#060000': b'xyz',
    'WORK/BOOT.SYSTEM#060000': b'boot',
    'WORK/DUP.TXT#060000': b'dup text\r',
    'WORK/DUP#040000': b'already there\r',
    'WORK/DISK.PO#060000': b'not really an image',
    'WORK2/ONE.BAS#060000': b'\x0a\x00',
    'WORK2/README#040000': b'readme\r',
}
TAGGED = ['ARCHIVE.SHK', 'LETTER.AWP', 'PROG.BAS', 'NOTE.TXT',
          'UNKNOWN.XYZ', 'BOOT.SYSTEM', 'DUP.TXT', 'DISK.PO']


def stage_floppy(tmp):
    stage = tmp / 'flop'
    for rel, data in FILES.items():
        path = stage / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    po = tmp / 'WORKPO.po'
    subprocess.run([sys.executable, str(ROOT / 'tools/mkvolume.py'), str(stage), str(po),
                    '--volume', 'WORKPO', '--blocks', '280'], check=True, capture_output=True)
    return po


def catalog(po, subdir):
    """{nom: (type, auxtype, donnees)} d'un sous-repertoire de la racine."""
    img = Image(po.read_bytes())
    root = {e[1:1 + (e[0] & 15)].decode(): e for e in img.entries(2)}
    key = int.from_bytes(root[subdir][0x11:0x13], 'little')
    return {e[1:1 + (e[0] & 15)].decode(): (e[0x10], int.from_bytes(e[0x1F:0x21], 'little'), img.read(e))
            for e in img.entries(key)}


def open_dir(s, p, x, volume, subdir):
    """Le panneau en colonne x (actif) sur /VOLUME/SUBDIR."""
    s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'volumes'); p.stable()
    s.select(volume, x); s.key(RET)
    s.wait(lambda: s.rows()[0][x:].startswith(volume + ' '), volume); p.stable()
    s.select(subdir, x); s.key(RET)
    s.wait(lambda: s.rows()[0][x:].startswith(volume + '/' + subdir + ' '), subdir); p.stable()


def run_fixtypes(s, p, answer):
    menu_run(s, p, 'FIXTYPES')
    s.wait(lambda: s.has('Drop suffix'), 'la question du suffixe', 20)
    s.key(answer)
    s.wait(lambda: s.has('files typed'), 'la fin de FIXTYPES', 60); p.stable()
    return s.rows()[22].strip()


def main():
    with tempfile.TemporaryDirectory(prefix='a2fc-fixtypes-') as tmp:
        tmp = Path(tmp)
        po = stage_floppy(tmp)
        before = catalog(po, 'WORK')
        with boot_hd(tmp, None, port=PORT, plugins=['fixtypes'], floppy2=po) as (p, s):
            # Refuse dans la liste des volumes (le message vient par api->note).
            s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'volumes'); p.stable()
            menu_run(s, p, 'FIXTYPES')
            s.wait(lambda: s.has('Open a directory'), 'le refus', 20)
            s.ok('refuse dans la liste des volumes', s.has('Open a directory'), s.rows()[22].strip())

            # Passage 1 : le panneau DROIT sur /WORKPO/WORK, huit fichiers marques, Y.
            s.key(TAB); p.stable()
            open_dir(s, p, 40, '/WORKPO', 'WORK')
            for name in TAGGED:
                s.select(name, 40); s.key(b' '); p.stable()
            s.ok('%d fichiers marques dans le panneau droit' % len(TAGGED),
                 s.has('%d tagged' % len(TAGGED)), s.rows()[21][60:].strip())
            line = run_fixtypes(s, p, b'Y')
            s.ok('7 types, 4 renommes, 1 passe', line.startswith('7 files typed, 4 renamed, 1 skipped'), line)
            s.ok('le panneau est relu : ARCHIVE sans suffixe, en $E0/$8002',
                 any(r[40:].startswith('ARCHIVE ') and '$8002' in r[40:] for r in s.rows()[2:20]),
                 [r[40:78] for r in s.rows()[2:20] if r[40:].startswith('ARCHIVE')])
            s.ok('le curseur est reste sur DISK.PO', s.line(40).startswith('DISK.PO '), s.line(40).rstrip())

            # Passage 2 : le panneau GAUCHE sur /WORKPO/WORK2, rien de marque, N.
            s.key(TAB); p.stable()
            open_dir(s, p, 0, '/WORKPO', 'WORK2')
            s.select('ONE.BAS', 0); p.stable()
            line = run_fixtypes(s, p, b'N')
            s.ok('sans marque, le fichier sous le curseur seul : 1 type, 0 renomme',
                 line.startswith('1 files typed, 0 renamed, 0 skipped'), line)
            s.ok('ONE.BAS garde son nom (N) et passe BAS a l\'ecran',
                 s.line(0).startswith('ONE.BAS ') and 'BAS' in s.line(0) and '$0801' in s.line(0), s.line(0).rstrip())
            try:
                p.eject(1)                   # la disquette recopiee dans WORKPO.po
            except Exception:
                pass                         # sinon l'arret de POM2 la recopie

        after = catalog(po, 'WORK')
        s.ok('ARCHIVE.SHK -> ARCHIVE $E0/$8002, contenu intact',
             after.get('ARCHIVE', (0, 0, b''))[:2] == (0xE0, 0x8002) and after['ARCHIVE'][2] == SHK
             and 'ARCHIVE.SHK' not in after, after.get('ARCHIVE', (None,))[:2])
        s.ok('LETTER.AWP -> LETTER $1A/$0000',
             after.get('LETTER', (0, 0))[:2] == (0x1A, 0) and 'LETTER.AWP' not in after, after.get('LETTER', (None,))[:2])
        s.ok('PROG.BAS -> PROG $FC/$0801',
             after.get('PROG', (0, 0))[:2] == (0xFC, 0x0801) and 'PROG.BAS' not in after, after.get('PROG', (None,))[:2])
        s.ok('NOTE.TXT -> NOTE $04/$0000',
             after.get('NOTE', (0, 0))[:2] == (0x04, 0) and 'NOTE.TXT' not in after, after.get('NOTE', (None,))[:2])
        s.ok('UNKNOWN.XYZ reste $06/$0000 sous son nom',
             after.get('UNKNOWN.XYZ', (0, 0))[:2] == (0x06, 0), after.get('UNKNOWN.XYZ', (None,))[:2])
        s.ok('BOOT.SYSTEM passe en $FF/$2000 et garde son suffixe',
             after.get('BOOT.SYSTEM', (0, 0))[:2] == (0xFF, 0x2000) and 'BOOT' not in after,
             after.get('BOOT.SYSTEM', (None,))[:2])
        s.ok('DUP.TXT est type $04 mais garde son nom : DUP existe deja, intact',
             after.get('DUP.TXT', (0, 0))[:2] == (0x04, 0) and after.get('DUP', (0, 0, b''))[2] == before['DUP'][2],
             (after.get('DUP.TXT', (None,))[:2], after.get('DUP', (None,))[:2]))
        s.ok('DISK.PO reste $06 et garde son suffixe (une image se reconnait par lui)',
             after.get('DISK.PO', (0, 0))[:2] == (0x06, 0) and 'DISK' not in after, after.get('DISK.PO', (None,))[:2])
        s.ok('rien d\'autre n\'a bouge dans WORK : %d fichiers avant, %d apres' % (len(before), len(after)),
             len(before) == len(after), sorted(after))
        work2 = catalog(po, 'WORK2')
        s.ok('WORK2 : ONE.BAS type $FC/$0801 sous son nom, README intact',
             work2.get('ONE.BAS', (0, 0))[:2] == (0xFC, 0x0801) and work2.get('README', (0, 0))[:2] == (0x04, 0)
             and len(work2) == 2, {k: v[:2] for k, v in work2.items()})
    return ok_all(s, 'fixtypes')


if __name__ == '__main__':
    sys.exit(main())
