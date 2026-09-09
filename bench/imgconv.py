#!/usr/bin/env python3
"""Banc de la surcouche IMGCONV (src/plugins/imgconv.c) : conversion d'une
image disque entre .PO/.HDV (ordre ProDOS), .DSK/.DO (ordre DOS 3.3) et
.2MG (en-tete 2IMG de 64 octets sur de l'ordre ProDOS).

    make build/imgconv.PLG && A2FC_IMG=A2FILECMD-full python3 bench/imgconv.py

Les sources sont sur le disque dur du banc (/WORKHD/IMG : une image .PO de
64 blocs faite par tools/mkvolume.py, une de 16 blocs au nom trop long, un
morceau de 12 blocs qui ne fait pas des pistes entieres, et un fichier
texte). Les RESULTATS vont sur une disquette en lecteur 2 (/WORKPO/OUT et
/WORKPO/BACK) : POM2 ne reecrit jamais le .hdv d'amorcage sur l'hote, la
disquette si, a l'arret. C'est elle que l'on relit ensuite octet a octet.

Trois conversions verifiees sur l'hote : le .2MG doit etre exactement ce
que produit tools/po22mg.py, le .DSK exactement l'entrelacement de
tools/po2dsk.py (dont la table SECTORS est importee ici -- po2dsk.py lui
meme ne sait faire que 280 blocs, d'ou la reimplementation), et le .PO
obtenu en reconvertissant ce .DSK doit rendre les octets de depart."""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from xplug import boot_hd, menu_run, ok_all, RET, TAB, ESC
from pom2 import ROOT
from prodos_read import Image
from po2dsk import SECTORS          # la table d'entrelacement livree
from po22mg import to_2mg           # l'oracle du .2MG

PORT = 6815

# Ce qui met fin a une execution de la surcouche, sur la ligne 22 (note).
DONE = (' -> ', 'failed', 'already in that format', 'Other panel',
        'whole tracks', 'Aborted', 'Select a .PO')


def to_dsk(po):
    """po2dsk.py pour un nombre quelconque de pistes (il suppose 280 blocs)."""
    assert len(po) % 4096 == 0, 'pas des pistes entieres'
    out = bytearray(len(po))
    for block in range(len(po) // 512):
        track, pair = divmod(block, 8)
        for half, sector in enumerate(SECTORS[pair]):
            dst = (track * 16 + sector) * 256
            out[dst:dst + 256] = po[block * 512 + half * 256:block * 512 + (half + 1) * 256]
    return bytes(out)


def make_image(tmp, tag, volume, blocks):
    """Une image ProDOS de `blocks` blocs, faite par l'outil du depot."""
    stage = tmp / ('src-' + tag)
    stage.mkdir()
    (stage / 'HELLO.TXT').write_bytes(('image %s de %d blocs\r' % (volume, blocks)).encode())
    (stage / 'DATA.BIN').write_bytes(bytes(range(256)) * 4)
    out = tmp / (tag + '.po')
    subprocess.run([sys.executable, str(ROOT / 'tools/mkvolume.py'), str(stage), str(out),
                    '--volume', volume, '--blocks', str(blocks)], check=True, capture_output=True)
    return out.read_bytes()


def stage_floppy(tmp):
    """La disquette du lecteur 2 : deux dossiers vides, les cibles."""
    stage = tmp / 'flop'
    (stage / 'OUT').mkdir(parents=True)
    (stage / 'BACK').mkdir(parents=True)
    po = tmp / 'WORKPO.po'
    subprocess.run([sys.executable, str(ROOT / 'tools/mkvolume.py'), str(stage), str(po),
                    '--volume', 'WORKPO', '--blocks', '280'], check=True, capture_output=True)
    return po


def catalog(po, path):
    """{nom: (type, auxtype, donnees)} du repertoire `path` de l'image."""
    img = Image(po.read_bytes())
    key = 2
    for part in path.split('/'):
        entries = {e[1:1 + (e[0] & 15)].decode(): e for e in img.entries(key)}
        key = int.from_bytes(entries[part][0x11:0x13], 'little')
    return {e[1:1 + (e[0] & 15)].decode(): (e[0x10], int.from_bytes(e[0x1F:0x21], 'little'), img.read(e))
            for e in img.entries(key) if e[0] >> 4 != 0xD}


def main():
    with tempfile.TemporaryDirectory(prefix='a2fc-imgconv-') as tmp:
        tmp = Path(tmp)
        src64 = make_image(tmp, 'tiny', 'TINY', 64)
        src16 = make_image(tmp, 'small', 'SMALL', 16)
        hd_files = {
            'IMG/TINY.PO': src64,
            'IMG/VERYLONGNAME.PO': src16,
            'IMG/ODD.PO': src64[:12 * 512],          # 12 blocs : pas des pistes entieres
            'IMG/NOTE.TXT': b'not a disk image at all\r',
        }
        po = stage_floppy(tmp)
        with boot_hd(tmp, hd_files, port=PORT, plugins=['imgconv'], floppy2=po) as (p, s):
            def open_panel(x, vol, *names):
                """Amene le panneau qui commence en colonne x sur /vol/names..."""
                if s.cursor_row(x) is None:
                    s.key(TAB)
                s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'volumes')
                s.select(vol, x); s.key(RET)
                s.wait(lambda: s.rows()[0][x:].startswith(vol), vol); p.stable()
                path = vol
                for n in names:
                    s.select(n, x); s.key(RET)
                    path += '/' + n
                    s.wait(lambda: s.rows()[0][x:].startswith(path), path); p.stable()

            def launch(name, x):
                if s.cursor_row(x) is None:         # le panneau vise doit etre l'actif
                    s.key(TAB)
                s.select(name, x); p.stable()
                menu_run(s, p, 'IMGCONV')

            def finished(before, seconds=180):
                """La note de fin, ligne 22 : differente de ce qui y etait avant
                (la barre de progression y passe aussi) et porteuse d'un verdict."""
                s.wait(lambda: s.rows()[22] != before and any(m in s.rows()[22] for m in DONE),
                       'la fin de la conversion', seconds)
                p.stable()
                return s.rows()[22].strip()

            def convert(name, x, key, seconds=180):
                before = s.rows()[22]
                launch(name, x)
                s.wait(lambda: s.has('Convert to P)'), 'la question du format', 20)
                s.key(key)
                return finished(before, seconds)

            # Panneau droit sur la disquette (/WORKPO/OUT), gauche sur /WORKHD/IMG.
            open_panel(40, '/WORKPO', 'OUT')
            open_panel(0, '/WORKHD', 'IMG')
            s.ok('les panneaux sont sur /WORKHD/IMG et /WORKPO/OUT',
                 s.rows()[0].startswith('/WORKHD/IMG') and s.rows()[0][40:].startswith('/WORKPO/OUT'),
                 s.rows()[0])

            # 1. Un fichier qui n'est pas une image : refus, sans question.
            before = s.rows()[22]
            launch('NOTE', 0)
            line = finished(before, 30)
            s.ok('refuse un fichier qui n\'est pas une image', 'Select a .PO' in line, line)

            # 2. ESC a la question annule.
            launch('TINY.PO', 0)
            s.wait(lambda: s.has('Convert to P)'), 'la question du format', 20)
            s.key(ESC)
            s.wait(lambda: 'Convert to P)' not in s.rows()[22], 'le retour de la surcouche', 20)
            p.stable()
            s.ok('ESC annule sans rien ecrire',
                 not s.has(' -> ') and s.has('Type  Aux'), s.rows()[22].strip())

            # 3. Meme format : refus.
            line = convert('TINY.PO', 0, b'P', 30)
            s.ok('refuse la conversion vers le meme format',
                 'already in that format' in line, line)

            # 4. Une image qui ne fait pas des pistes entieres : refus pour un .DSK.
            line = convert('ODD.PO', 0, b'D', 30)
            s.ok('refuse un .DSK qui ne ferait pas des pistes entieres',
                 'whole tracks' in line, line)

            # 5. .PO -> .2MG, puis .PO -> .DSK, dans /WORKPO/OUT.
            line = convert('TINY.PO', 0, b'2')
            s.ok('TINY.PO -> TINY.2MG, 64 blocks', line == 'TINY.PO -> TINY.2MG, 64 blocks', line)
            line = convert('TINY.PO', 0, b'D')
            s.ok('TINY.PO -> TINY.DSK, 64 blocks', line == 'TINY.PO -> TINY.DSK, 64 blocks', line)

            # 6. Le nom coupe a 15 caracteres : VERYLONGNAME.PO -> VERYLONGNAM.DSK.
            line = convert('VERYLONGNAME.PO', 0, b'D')
            s.ok('le nom est coupe pour tenir en 15 caracteres',
                 line == 'VERYLONGNAME.PO -> VERYLONGNAM.DSK, 16 blocks', line)

            # 7. Retour : le .DSK produit, reconverti en .PO dans /WORKPO/BACK.
            open_panel(40, '/WORKPO', 'BACK')
            open_panel(0, '/WORKPO', 'OUT')
            line = convert('TINY.DSK', 0, b'P')
            s.ok('TINY.DSK -> TINY.PO, 64 blocks', line == 'TINY.DSK -> TINY.PO, 64 blocks', line)

            # 8. L'autre panneau sur le meme dossier : refus.
            open_panel(40, '/WORKPO', 'OUT')
            line = convert('TINY.DSK', 0, b'P', 30)
            s.ok("refuse l'autre panneau quand c'est le meme dossier",
                 'Other panel' in line, line)

        # La disquette, ecrite dans son fichier a l'arret de POM2.
        out = catalog(po, 'OUT')
        back = catalog(po, 'BACK')
        s.ok('OUT/TINY.2MG : exactement la sortie de tools/po22mg.py',
             out.get('TINY.2MG', (0, 0, b''))[2] == to_2mg(src64),
             (len(out.get('TINY.2MG', (0, 0, b''))[2]), out.get('TINY.2MG', (0, 0, b''))[2][:32]))
        s.ok('OUT/TINY.2MG : type $06, auxtype $0000',
             out.get('TINY.2MG', (0, 0, b''))[:2] == (0x06, 0), out.get('TINY.2MG', (None, None))[:2])
        s.ok('OUT/TINY.DSK : exactement l\'entrelacement DOS 3.3 de po2dsk.py',
             out.get('TINY.DSK', (0, 0, b''))[2] == to_dsk(src64),
             (len(out.get('TINY.DSK', (0, 0, b''))[2]), out.get('TINY.DSK', (0, 0, b''))[2][:16]))
        s.ok('OUT/VERYLONGNAM.DSK : les 2 pistes de l\'image de 16 blocs',
             out.get('VERYLONGNAM.DSK', (0, 0, b''))[2] == to_dsk(src16),
             (len(out.get('VERYLONGNAM.DSK', (0, 0, b''))[2]),))
        s.ok('BACK/TINY.PO : l\'aller-retour .PO -> .DSK -> .PO rend les octets de depart',
             back.get('TINY.PO', (0, 0, b''))[2] == src64,
             (len(back.get('TINY.PO', (0, 0, b''))[2]), back.get('TINY.PO', (0, 0, b''))[:2]))
        s.ok('BACK/TINY.PO : type $06, auxtype $0000',
             back.get('TINY.PO', (0, 0, b''))[:2] == (0x06, 0), back.get('TINY.PO', (None, None))[:2])
        s.ok('rien d\'autre laisse sur la disquette',
             sorted(out) == ['TINY.2MG', 'TINY.DSK', 'VERYLONGNAM.DSK'] and sorted(back) == ['TINY.PO'],
             (sorted(out), sorted(back)))
    return ok_all(s, 'imgconv')


if __name__ == '__main__':
    sys.exit(main())
