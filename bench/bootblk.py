#!/usr/bin/env python3
"""Banc de la surcouche BOOTBLK (src/plugins/bootblk.c) : reecrire les blocs
d'amorcage ProDOS d'un volume, recopies de celui d'ou le programme tourne.

    make build/bootblk.PLG && A2FC_IMG=A2FILECMD-full python3 bench/bootblk.py

La cible est une disquette en lecteur 2, /WORKPO (280 blocs, tools/mkvolume.py),
dont les octets 0 a 1023 -- les blocs 0 et 1 -- sont barbouilles sur l'hote
AVANT l'amorcage : ProDOS n'y regarde pas (le repertoire de volume est le bloc
2), le volume se monte quand meme, et l'on sait exactement ce qu'il y avait la.
La source est le volume d'amorcage /WORKHD, que stage_hd construit avec
data/prodos_boot.tmpl : apres BOOTBLK, les 1024 premiers octets du .po doivent
etre ce fichier, octet pour octet, et le reste de l'image inchange.

pom2_playtest ne recopie pas le disque dur dans son fichier (seul le Disk II
a l'ecriture en retour) : d'ou la disquette, relue sur l'hote apres l'arret.

A l'ecran on verifie les deux branches du choix du volume -- la liste des
volumes (l'unite vient de Entry.mdate) et le chemin d'un panneau (l'unite
vient d'ON_LINE) -- le refus de reecrire le volume d'amorcage par lui-meme
dans les deux cas, la question qui nomme cible et source, et l'annulation."""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from xplug import boot_hd, menu_run, ok_all, RET
from pom2 import ROOT
from prodos_read import Image

PORT = 6814
TMPL = (ROOT / 'data/prodos_boot.tmpl').read_bytes()
GARBAGE = bytes((i * 7 + 13) & 0xFF for i in range(1024))
QUESTION = 'Rewrite the boot blocks of /WORKPO from /WORKHD?'
DONE = 'Boot blocks of /WORKPO rewritten from /WORKHD'
BOOTVOL = 'That is the volume booted from.'


def make_po(tmp):
    """/WORKPO, un fichier dedans, et des blocs 0-1 barbouilles."""
    stage = tmp / 'flop'
    stage.mkdir()
    (stage / 'NOTE.TXT').write_bytes(b'note\r')
    po = tmp / 'WORKPO.po'
    subprocess.run([sys.executable, str(ROOT / 'tools/mkvolume.py'), str(stage), str(po),
                    '--volume', 'WORKPO', '--blocks', '280'], check=True, capture_output=True)
    data = bytearray(po.read_bytes())
    data[0:1024] = GARBAGE
    po.write_bytes(bytes(data))
    return po


def volumes(s):
    return [r[:16].split(' ')[0].rstrip('/') for r in s.rows()[2:20] if r.startswith('/')]


def main():
    with tempfile.TemporaryDirectory(prefix='a2fc-bootblk-') as tmp:
        tmp = Path(tmp)
        po = make_po(tmp)
        before = po.read_bytes()
        with boot_hd(tmp, {'WORK/NOTE.TXT': b'hello\r'}, port=PORT,
                     plugins=['bootblk'], floppy2=po) as (p, s):
            def volume_list():
                s.key(b'/')
                s.wait(lambda: s.rows()[0].startswith('[Volumes]'), 'la liste des volumes')
                p.stable()

            # 1. Les trois volumes en ligne : le disque dur d'amorcage, /RAM,
            #    la disquette du lecteur 2.
            volume_list()
            vols = volumes(s)
            s.ok('la liste des volumes montre /WORKHD, /RAM et /WORKPO',
                 all(v in vols for v in ('/WORKHD', '/RAM', '/WORKPO')), vols)

            # 2. Le volume d'amorcage sur lui-meme, depuis la liste des volumes
            #    (l'unite vient de Entry.mdate) : refuse.
            s.select('/WORKHD')
            menu_run(s, p, 'BOOTBLK')
            p.stable()
            s.ok('refuse le volume d amorcage, choisi dans la liste des volumes',
                 s.has(BOOTVOL) and not s.has('(Y/N)'), s.rows()[22].strip())

            # 3. Depuis un panneau ouvert dans le volume d'amorcage : l'unite
            #    vient cette fois d'ON_LINE sur le nom du chemin. Refuse aussi.
            s.select('/WORKHD'); s.key(RET)
            s.wait(lambda: s.rows()[0][:8] == '/WORKHD ', 'la racine de /WORKHD'); p.stable()
            menu_run(s, p, 'BOOTBLK')
            p.stable()
            s.ok('refuse aussi depuis un panneau ouvert dans le volume d amorcage',
                 s.has(BOOTVOL) and not s.has('(Y/N)'), s.rows()[22].strip())

            # 4. La question nomme la cible et la source ; N n'ecrit rien.
            volume_list()
            s.select('/WORKPO')
            menu_run(s, p, 'BOOTBLK')
            s.wait(lambda: s.has(QUESTION), 'la question de BOOTBLK', 20)
            s.ok('la question nomme la cible et la source', s.has(QUESTION + ' (Y/N)'),
                 s.rows()[22].strip())
            s.key(b'N'); p.stable()
            s.ok('N a la question : rien n est reecrit',
                 not s.has('rewritten') and not s.has('failed'), s.rows()[22].strip())

            # 5. Y : les blocs 0 et 1 de /WORKHD passent sur /WORKPO.
            menu_run(s, p, 'BOOTBLK')
            s.wait(lambda: s.has(QUESTION), 'la question de BOOTBLK', 20)
            s.key(b'Y')
            s.wait(lambda: s.has(DONE) or s.has('failed'), 'la fin de BOOTBLK', 30)
            p.stable()
            s.ok('Y : "%s"' % DONE, s.has(DONE), s.rows()[22].strip())
            s.ok('A2FC a repris la main sur ses panneaux',
                 s.rows()[0].startswith('[Volumes]') and '/WORKPO' in volumes(s), volumes(s))

        # La disquette, recopiee dans son .po a l'arret de POM2.
        after = po.read_bytes()
        s.ok('sur l hote, les octets 0 a 1023 de la disquette sont data/prodos_boot.tmpl',
             after[:1024] == TMPL,
             (after[:16].hex(), TMPL[:16].hex(), 'bloc 1 nul : %s' % (set(after[512:1024]) == {0},)))
        s.ok('les blocs 0-1 barbouilles ont bien ete remplaces', after[:1024] != GARBAGE,
             after[:8].hex())
        s.ok('le reste de l image est inchange', after[1024:] == before[1024:],
             next((i + 1024 for i in range(len(before) - 1024)
                   if after[1024 + i] != before[1024 + i]), 'aucune difference'))
        img = Image(after)
        names = [e[1:1 + (e[0] & 15)].decode() for e in img.entries(2)]
        s.ok('le repertoire de la disquette est intact : /WORKPO et NOTE',
             img.header()['name'] == 'WORKPO' and names == ['NOTE'], (img.header(), names))
    return ok_all(s, 'bootblk')


if __name__ == '__main__':
    sys.exit(main())
