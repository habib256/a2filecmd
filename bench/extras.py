#!/usr/bin/env python3
"""La disquette publiee charge les outils de son complement en lecteur 2."""
import subprocess
import shutil
import sys
import tempfile
import zlib
from pathlib import Path

from pom2 import Pom2, Session, ROOT, BUILD, FULL
from smoke import scratch
from xplug import menu_run, ok_all, RET, ESC
from volname import rename_to
sys.path.insert(0, str(ROOT / 'tools'))
from prodos_read import Image
import mkdemo


def catalog(image):
    img = Image(image.read_bytes())
    def name(e):
        return e[1:1 + (e[0] & 15)].decode('ascii')
    root = {name(e): e for e in img.entries(2)}
    key = int.from_bytes(root['A2FILE'][17:19], 'little')
    return img, root, {name(e): e for e in img.entries(key)}


def main():
    cpu = '65C02' if FULL else '6502'
    bootvol, extravol = 'A2FC' + cpu, 'A2EXTRA' + cpu
    boot = ROOT / ('dist/A2FILECMD-%s-BOOT.po' % cpu)
    extra = ROOT / ('dist/A2FILECMD-%s-EXTRA.po' % cpu)
    bi, br, bc = catalog(boot)
    xi, xr, xc = catalog(extra)
    assert len(extra.read_bytes()) == 143360
    assert 'PRODOS' not in xr and 'BASIC.SYSTEM' in xr
    assert set(bc).intersection(xc) == {'MENU.PLG', 'EXTRAS.CAT'}, 'seuls le menu et le catalogue accompagnent les deux disques'
    assert len([n for n in set(bc) | set(xc) if n.endswith('.PLG')]) == 34
    for name, entry in xc.items():
        if not name.endswith('.PLG'): continue
        assert entry[16] == 6 and int.from_bytes(entry[31:33], 'little') == 0x1B00
        stem = name[:-4]
        path = BUILD / (stem.lower() + '.PLG')
        if not path.exists():
            path = BUILD / ('A2FILE.CODE.BIN.' + stem)
        assert xi.read(entry) == path.read_bytes(), name
    print('PASS les images publiees reunissent 34 surcouches, avec menu commun, aux bons octets et attributs', flush=True)

    with tempfile.TemporaryDirectory(prefix='a2fc-extras-') as tmp:
        tmp = Path(tmp)
        floppy = tmp / 'BOOT.po'; shutil.copyfile(boot, floppy)
        companion = tmp / 'EXTRAS.po'; shutil.copyfile(extra, companion)
        hd = scratch(tmp)
        # Use the published boot and companion floppies, a scratch HD for the file.
        with Pom2(hd, floppy=floppy, floppy2=companion, port=6830) as p:
            s = Session(p); s.boot()
            s.key(b'/'); s.select('/SCRATCH'); s.key(RET)
            s.select('WORK'); s.key(RET); s.select('NOTE'); p.stable()
            note = b'scratch volume\r'
            s.key(b'E')
            s.wait(lambda: s.value('view', 1) == 5, 'EDIT depuis le lecteur 2', 30)
            s.ok('E charge EDIT absent de la disquette principale', 'cratch volume' in s.rows()[0])
            s.key(ESC); p.stable()
            # Editor's menu: Q leaves without saving unchanged text.
            if not s.has('Type  Aux'):
                s.key(b'Q')
            s.wait(lambda: s.has('Type  Aux'), 'retour editeur', 30)
            menu_run(s, p, 'CRC')
            expected = 'NOTE: CRC-32 $%08X, %d bytes' % (zlib.crc32(note), len(note))
            s.wait(lambda: expected in s.rows()[22], 'CRC du complement', 30)
            s.ok('le menu charge une surcouche a table de services du lecteur 2', s.rows()[22].strip() == expected)
            s.key(b'!'); s.wait(lambda: s.has('the overlays'), 'menu fusionne', 30); p.stable()
            s.ok('le menu contient les 33 commandes des deux disquettes', '/33' in s.rows()[0], s.rows()[0])
            s.key(ESC)
            s.key(b'/'); s.select('/' + extravol); p.stable()
            rename_to(s, p, extravol, 'TOOLS')
            s.ok('le complement peut etre renomme', s.has('Volume renamed to /TOOLS'))
            s.select('/SCRATCH'); s.key(RET); s.select('WORK'); s.key(RET); s.select('NOTE')
            menu_run(s, p, 'CRC')
            s.wait(lambda: expected in s.rows()[22], 'CRC apres renommage', 30)
            s.ok('le chargeur retrouve le nom actuel du lecteur 2', expected in s.rows()[22])
            p.eject(1)
            s.key(b'E')
            s.wait(lambda: s.has('Insert ' + extravol + ' S6,D2'), 'complement absent', 30)
            s.ok('la demande nomme le disque et le lecteur', s.has('Insert ' + extravol + ' S6,D2'))
            s.key(ESC)
            s.ok('sans complement E signale la surcouche absente', s.has('EDIT.PLG is missing or stale'))
            s.key(b'T'); s.wait(lambda: s.has('scratch volume'), 'texte principal', 30)
            s.ok('les outils de la disquette principale restent utilisables', s.has('scratch volume'))
            s.key(ESC)
            s.key(b'!'); s.wait(lambda: s.has('the overlays'), 'menu sans complement', 30); p.stable()
            s.ok('sans complement le catalogue garde les 33 commandes', '/33' in s.rows()[0], s.rows()[0])
            s.key(ESC)
    first = ok_all(s, 'extras, deux lecteurs')
    with tempfile.TemporaryDirectory(prefix='a2fc-extras-one-') as tmp:
        tmp = Path(tmp)
        floppy = tmp / 'BOOT.po'; shutil.copyfile(boot, floppy)
        companion = tmp / 'EXTRAS.po'; shutil.copyfile(extra, companion)
        with Pom2(scratch(tmp), floppy=floppy, port=6831) as p:
            s = Session(p); s.boot()
            s.key(b'/'); s.select('/SCRATCH'); s.key(RET)
            s.select('WORK'); s.key(RET); s.select('NOTE'); p.stable()
            menu_run(s, p, 'CRC')
            s.wait(lambda: s.has('Insert ' + extravol + ' S6,D2'), 'demande de complement', 30)
            s.key(b'1')
            s.wait(lambda: s.has('Insert ' + extravol + ' S6,D1'), 'lecteur choisi', 30)
            s.ok('un seul lecteur : nom du complement et lecteur 1 explicites', s.has('Insert ' + extravol + ' S6,D1'))
            p.insert(0, str(companion)); s.key(RET)
            s.wait(lambda: expected in s.rows()[22], 'CRC apres echange', 30)
            s.ok('CRC charge apres remplacement de la disquette dans le lecteur 1', expected in s.rows()[22])
            # MENU accompanies both disks, so another command remains selectable.
            menu_run(s, p, 'IDENT')
            s.wait(lambda: s.has('Text, CR ends'), 'IDENT sur le meme disque', 30)
            s.ok('le menu reste accessible pendant l echange', s.has('Text, CR ends'))
            s.key(b'T')
            s.wait(lambda: s.has('Insert ' + bootvol + ' S6,D1'), 'demande du disque principal', 30)
            s.ok('le retour nomme la disquette principale et le meme lecteur', s.has('Insert ' + bootvol + ' S6,D1'))
            p.insert(0, str(floppy)); s.key(RET)
            s.wait(lambda: s.value('view', 1) == 2, 'TEXT apres retour du disque principal', 30)
            s.ok('TEXT fonctionne apres restitution de la disquette principale', s.has('scratch volume'))
            s.key(ESC)
            # The file itself can be on the boot floppy, without a hard disk.
            s.key(b'/'); s.select('/' + bootvol); s.key(RET)
            s.select('A2FILE'); s.key(RET); s.select('A2FILE.HELP')
            s.key(b'E')
            s.wait(lambda: s.has('Insert ' + extravol + ' S6,D1'), 'disque de l editeur', 30)
            p.insert(0, str(companion)); s.key(RET)
            s.wait(lambda: s.has('Insert ' + bootvol + ' S6,D1'), 'disque du fichier', 30)
            s.ok('apres le code, le disque contenant le fichier est demande', s.has('Insert ' + bootvol + ' S6,D1'))
            p.insert(0, str(floppy)); s.key(RET)
            s.wait(lambda: s.value('view', 1) == 5 and s.has('A2 FILE CMD'), 'edition depuis une seule disquette', 30)
            s.ok('le fichier de la disquette principale est lu apres l echange', s.has('A2 FILE CMD'))
            s.key(ESC); p.stable()
            if not s.has('Type  Aux'): s.key(b'Q')
            s.wait(lambda: s.has('Type  Aux'), 'retour des panneaux', 30)
            s.key(b'E')
            s.wait(lambda: s.has('Insert ' + extravol + ' S6,D1'), 'editeur encore', 30)
            p.insert(0, str(companion)); s.key(RET)
            s.wait(lambda: s.has('Insert ' + bootvol + ' S6,D1'), 'annuler la lecture du fichier', 30)
            s.key(ESC); p.stable()
            s.ok('ESC apres une grande surcouche restaure les panneaux', s.has('Type  Aux') or s.has('Volume          Slot'))
    second = ok_all(s, 'extras, un lecteur')
    with tempfile.TemporaryDirectory(prefix='a2fc-extras-basic-') as tmp:
        tmp = Path(tmp)
        floppy = tmp / 'BOOT.po'; shutil.copyfile(boot, floppy)
        companion = tmp / 'EXTRAS.po'; shutil.copyfile(extra, companion)
        hd = scratch(tmp)
        program = mkdemo.applesoft([(10, bytes([mkdemo.HOME])),
            (20, bytes([mkdemo.PRINT]) + b'"EXTRAS BASIC OK"'), (30, bytes([mkdemo.END]))])
        (tmp / 'scratch/WORK/HELLO.BAS').write_bytes(program)
        subprocess.run([sys.executable, str(ROOT / 'tools/mkvolume.py'), str(tmp / 'scratch'), str(hd),
                        '--volume', 'SCRATCH', '--blocks', '1600'], check=True, capture_output=True)
        with Pom2(hd, floppy=floppy, floppy2=companion, port=6832) as p:
            s = Session(p); s.boot()
            s.key(b'/'); s.select('/SCRATCH'); s.key(RET)
            s.select('WORK'); s.key(RET); s.select('HELLO'); s.key(RET)
            s.wait(lambda: s.has('Run HELLO?'), 'confirmation BASIC', 30)
            s.key(b'Y')
            s.wait(lambda: any('EXTRAS BASIC OK' in r for r in s.rows40()), 'BASIC du complement', 60)
            s.ok('BASIC.SYSTEM du lecteur 2 execute le programme du disque de travail', True)
            s.type('-/' + bootvol + '/A2FILE.SYSTEM'); s.key(RET)
            s.wait(lambda: s.has('Type  Aux'), 'retour de BASIC', 90)
            s.ok('le chemin absolu relance A2FC sur sa disquette', s.has('Type  Aux'))
    return first or second or ok_all(s, 'extras, BASIC')


if __name__ == '__main__':
    sys.exit(main())
