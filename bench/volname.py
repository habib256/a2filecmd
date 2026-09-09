#!/usr/bin/env python3
"""Banc de la surcouche VOLNAME (src/plugins/volname.c) : renommer un volume
ProDOS depuis le menu `!`, par RENAME sur "/ANCIEN" et "/NOUVEAU".

    make build-6502/volname.PLG ARCH=6502 && python3 bench/volname.py

Le cas interessant est le volume d'amorcage, /WORKHD, d'ou le programme
tourne : il est renomme /RENAMED depuis la liste des volumes, on verifie
que les panneaux suivent, que le menu `!` se charge encore (le programme
lit ses surcouches par un chemin absolu qui portait l'ancien nom), puis il
est renomme WORKHD depuis un panneau ouvert dedans (l'autre branche : le
volume est le premier composant du chemin). /RAM devient /RAMDISK et
revient. Une image ouverte comme un dossier est refusee.

pom2_playtest ne recopie pas le disque dur dans son fichier (seul le Disk II
a l'ecriture en retour) : la preuve sur l'hote se fait sur une disquette en
lecteur 2, /WORKPO, renommee /FLOPPY et relue apres l'arret -- bloc 2,
l'en-tete du repertoire de volume, longueur du nom dans le quartet bas de
l'octet 4, puis le nom. Pour le disque dur, la liste des volumes est relue
par ON_LINE, que ProDOS sert en lisant ce meme bloc 2 sur le disque."""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from xplug import boot_hd, menu_run, ok_all, RET, ESC, TAB
from pom2 import ROOT
from prodos_read import Image

PORT = 6808
DEL = b'\x7f'


def make_po(tmp, name, files):
    stage = tmp / ('stage_' + name)
    stage.mkdir()
    for rel, data in files.items():
        (stage / rel).write_bytes(data)
    po = tmp / (name + '.po')
    subprocess.run([sys.executable, str(ROOT / 'tools/mkvolume.py'), str(stage), str(po),
                    '--volume', name, '--blocks', '280'], check=True, capture_output=True)
    return po


def rename_to(s, p, old, new):
    """Lance VOLNAME sur la selection, verifie l'invite, remplace le nom."""
    menu_run(s, p, 'VOLNAME')
    s.wait(lambda: s.has('Rename volume /%s to: %s' % (old, old)), "l'invite de VOLNAME", 20)
    for _ in old:
        s.key(DEL, 0.1)
    s.type(new)
    s.key(RET)
    s.wait(lambda: s.has('Volume renamed to /' + new) or s.has('failed'), 'la fin de VOLNAME', 30)
    p.stable()


def volumes(s):
    return [r[:16].split(' ')[0].rstrip('/') for r in s.rows()[2:20] if r.startswith('/')]


def main():
    with tempfile.TemporaryDirectory(prefix='a2fc-volname-') as tmp:
        tmp = Path(tmp)
        tiny = make_po(tmp, 'TINY', {'INSIDE.TXT': b'inside\r'})
        po = make_po(tmp, 'WORKPO', {'NOTE.TXT': b'note\r'})
        files = {'WORK/NOTE.TXT': b'hello\r', 'WORK/TINY.PO': tiny.read_bytes()}
        with boot_hd(tmp, files, port=PORT, plugins=['volname'], floppy2=po) as (p, s):
            # Au demarrage : /WORKHD a gauche (actif), la liste des volumes a
            # droite. Le panneau droit va dans /WORKHD/WORK, pour voir s'il suit.
            s.key(TAB); s.select('/WORKHD', 40); s.key(RET)
            s.wait(lambda: s.rows()[0][40:48] == '/WORKHD ', 'WORKHD a droite'); p.stable()
            s.select('WORK', 40); s.key(RET); s.wait(lambda: s.rows()[0][40:].startswith('/WORKHD/WORK'), 'WORK a droite'); p.stable()
            s.key(TAB); p.stable()

            # 1. La liste des volumes : le disque dur, /RAM, la disquette.
            s.key(b'/'); s.wait(lambda: s.rows()[0].startswith('[Volumes]'), 'volumes'); p.stable()
            vols = volumes(s)
            s.ok('la liste des volumes montre /WORKHD, /RAM et /WORKPO',
                 all(v in vols for v in ('/WORKHD', '/RAM', '/WORKPO')), vols)

            # 2. Une image ouverte comme un dossier est refusee.
            s.select('/WORKHD'); s.key(RET)
            s.wait(lambda: s.rows()[0][:8] == '/WORKHD ', 'WORKHD'); p.stable()
            s.select('WORK'); s.key(RET); s.wait(lambda: s.rows()[0].startswith('/WORKHD/WORK'), 'WORK'); p.stable()
            s.select('TINY.PO'); s.key(RET)
            s.wait(lambda: s.has('INSIDE '), "l'image ouverte comme un dossier", 30); p.stable()
            menu_run(s, p, 'VOLNAME')
            s.ok("refuse une image ouverte comme un dossier", s.has('Not a ProDOS volume.'), s.rows()[22].strip())
            s.key(ESC); s.wait(lambda: s.rows()[0].startswith('/WORKHD/WORK') and s.has('TINY.PO'), 'retour dans WORK'); p.stable()

            # 3. Le volume d'amorcage, renomme depuis la liste des volumes.
            s.key(b'/'); s.wait(lambda: s.rows()[0].startswith('[Volumes]'), 'volumes'); p.stable()
            s.select('/WORKHD')
            rename_to(s, p, 'WORKHD', 'RENAMED')
            s.ok('/WORKHD renomme /RENAMED : le message', s.has('Volume renamed to /RENAMED'), s.rows()[22].strip())
            vols = volumes(s)
            s.ok('la liste des volumes, relue par ON_LINE, montre /RENAMED et plus /WORKHD',
                 '/RENAMED' in vols and '/WORKHD' not in vols, vols)
            s.ok("l'autre panneau, ouvert dans /WORKHD/WORK, suit en /RENAMED/WORK",
                 s.rows()[0][40:].startswith('/RENAMED/WORK') and s.has('NOTE '), s.rows()[0][40:].strip())

            # 4. Escape a l'invite : rien ne bouge.
            s.select('/RENAMED')
            menu_run(s, p, 'VOLNAME')
            s.wait(lambda: s.has('Rename volume /RENAMED to: RENAMED'), "l'invite", 20)
            s.key(ESC); p.stable()
            s.ok("Escape a l'invite ne renomme rien", '/RENAMED' in volumes(s) and not s.has('Rename volume'), volumes(s))

            # 5. Depuis un panneau ouvert dans le volume : le menu `!` se charge
            #    encore (cfg_path suit), et le volume est celui du chemin.
            s.key(RET); s.wait(lambda: s.rows()[0][:9] == '/RENAMED ', 'la racine de /RENAMED'); p.stable()
            s.ok('le volume renomme s ouvre, A2FILE/ dedans', s.has('A2FILE/'), s.rows()[0][:20])
            rename_to(s, p, 'RENAMED', 'WORKHD')
            s.ok("depuis le panneau ouvert dedans, le menu ! se charge et /RENAMED redevient /WORKHD",
                 s.has('Volume renamed to /WORKHD') and s.rows()[0][:8] == '/WORKHD ', s.rows()[0][:20])
            s.ok("l'autre panneau suit aussi, en /WORKHD/WORK", s.rows()[0][40:].startswith('/WORKHD/WORK'), s.rows()[0][40:].strip())

            # 6. /RAM -> /RAMDISK, et retour.
            s.key(b'/'); s.wait(lambda: s.rows()[0].startswith('[Volumes]'), 'volumes'); p.stable()
            s.select('/RAM')
            rename_to(s, p, 'RAM', 'RAMDISK')
            s.ok('/RAM renomme /RAMDISK', '/RAMDISK' in volumes(s) and '/RAM' not in volumes(s), volumes(s))
            s.select('/RAMDISK')
            rename_to(s, p, 'RAMDISK', 'RAM')
            s.ok('/RAMDISK renomme /RAM', '/RAM' in volumes(s) and '/RAMDISK' not in volumes(s), volumes(s))

            # 7. La disquette du lecteur 2, relue sur l'hote apres l'arret.
            s.select('/WORKPO')
            rename_to(s, p, 'WORKPO', 'FLOPPY')
            s.ok('/WORKPO renomme /FLOPPY a l ecran', '/FLOPPY' in volumes(s) and '/WORKPO' not in volumes(s), volumes(s))
            s.ok('A2FC a repris la main sur ses panneaux', s.has('Type  Aux'))

        block2 = po.read_bytes()[2 * 512:3 * 512]
        length = block2[4] & 15
        name = block2[5:5 + length].decode('ascii', 'replace')
        s.ok('sur l hote, le bloc 2 de la disquette porte le nom FLOPPY (longueur 6)',
             length == 6 and name == 'FLOPPY', (length, name))
        img = Image(po.read_bytes())
        names = [e[1:1 + (e[0] & 15)].decode() for e in img.entries(2)]
        s.ok('le repertoire de la disquette est intact : NOTE toujours la',
             img.header()['name'] == 'FLOPPY' and names == ['NOTE'], (img.header(), names))
    return ok_all(s, 'volname')


if __name__ == '__main__':
    sys.exit(main())
