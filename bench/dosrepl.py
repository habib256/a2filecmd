#!/usr/bin/env python3
"""Banc de DOSREPL : remplacer un fichier d'un vrai disque DOS 3.3 par le
fichier ProDOS du meme nom, en lecteur 2, sur une disquette jetable.

    make all disk && python3 bench/dosrepl.py

La disquette porte un HELLO et un TIGER qui ne sont pas ceux du disque dur.
Le remplacement doit y mettre exactement les octets du ProDOS, avec le
prefixe qu'un Applesoft (longueur) ou un binaire (adresse et longueur)
porte sous DOS, rendre au bitmap les secteurs de l'ancien, et ne pas
toucher au voisin. TIGER fait 8 Ko : c'est lui qui fait travailler la liste
T/S et les trente-trois secteurs qu'il faut reserver avant la bascule.

DOSREPL veut le panneau ProDOS actif -- c'est lui qui nomme le fichier -- et
le disque DOS en face.

Ce qui est verifie, ce sont les octets de la disquette, et POM2 ne la sauve
qu'environ une seconde apres la fin d'une ecriture : chaque controle passe
par `flushed()`, qui force la sauvegarde et attend. Sans cela, un « rien
n'a ete ecrit » passerait quoi que fasse le programme."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from pom2 import Pom2, Session, BUILD
from xplug import menu_run, ok_all
from mini33_fixture import make_disk, read_files, offset
from prodos_read import Image

PORT = 6913
KEEP = b'a neighbour that must not move\r' * 40
OLD_BAS = b'the old HELLO, quite different\r' * 30
OLD_BIN = b'the old TIGER, much shorter\r' * 20
FILES = [('KEEP', 0x00, KEEP), ('HELLO', 0x02, OLD_BAS), ('TIGER', 0x04, OLD_BIN)]


def freed(disk, sectors):
    """Les secteurs `sectors` sont-ils tous libres dans le bitmap du VTOC ?"""
    vtoc = disk[offset(17, 0):offset(17, 0) + 256]
    return all(vtoc[0x38 + t * 4 + (s < 8)] & (1 << (s & 7)) for t, s in sectors)


def dos_bytes(prefix, payload):
    """Les octets qu'un fichier ProDOS prend sous DOS 3.3 : son prefixe, ses
    octets, et le dernier secteur complete de zeros."""
    out = prefix + payload
    return out + bytes((-len(out)) % 256)


def crowded(want, old):
    """Une disquette ou il manque un secteur pour la nouvelle copie.

    Les secteurs de l'ancien restent alloues tant que la nouvelle copie
    s'ecrit : le disque doit porter les deux a la fois. On laisse libre
    exactement un secteur de moins qu'il n'en faut, listes T/S comprises, en
    bourrant le reste dans un fichier."""
    data = len(want) // 256
    needed = data + max(1, -(-data // 122))
    free = 31 * 16 - len(old['blocks']) - len(old['lists'])   # 496 utilisables
    room = free - (needed - 1)
    n = next(k for k in range(room, 0, -1) if k + -(-k // 122) == room)
    disk = make_disk([('FILLER', 0x00, bytes(n * 256)), ('TIGER', 0x04, OLD_BIN)])
    vtoc = disk[offset(17, 0):offset(17, 0) + 256]
    left = sum(bin(vtoc[0x38 + t * 4 + h]).count('1')
               for t in range(35) for h in (0, 1))
    assert left == needed - 1, (left, needed)
    return disk


def main():
    with tempfile.TemporaryDirectory(prefix='dosrepl-') as d:
        d = Path(d)
        hd = d / 'test.hdv'
        target = d / 'dos.dsk'
        cpu = '6502' if BUILD.name == 'build-6502' else '65C02'
        source = (BUILD / f'A2FILECMD-{cpu}-BOOT.hdv').read_bytes()
        hd.write_bytes(source)
        im = Image(source)

        def find(folder, name):
            top = next(e for e in im.entries(2) if e[1:1 + len(folder)] == folder)
            return next(e for e in im.entries(int.from_bytes(top[17:19], 'little'))
                        if e[1:1 + len(name)] == name)

        hello = find(b'DEMO', b'HELLO')
        tiger = find(b'IMGHGR', b'TIGER')
        bas = im.read(hello)
        bin_ = im.read(tiger)
        want_bas = dos_bytes(len(bas).to_bytes(2, 'little'), bas)
        want_bin = dos_bytes(tiger[31:33] + len(bin_).to_bytes(2, 'little'), bin_)

        original = make_disk(FILES)
        target.write_bytes(original)
        before = read_files(original)
        slot = os.environ.get('A2FC_DOS_SLOT', '6')

        with Pom2(hd, floppy2=target, port=PORT,
                  exe=os.environ.get('POM2', '/tmp/a2fc-dos-host')) as p:
            s = Session(p)
            s.boot()

            def flushed():
                """Les octets de la disquette, vraiment : sauvegarde forcee,
                puis lecture. Voir `Pom2.sync_disks`."""
                p.sync_disks()
                return target.read_bytes()

            def open_dos():
                """Le disque DOS dans le panneau droit, le ProDOS a gauche."""
                s.key(b'\t')
                s.key(b'/')
                s.wait(lambda: s.has('[Volumes]'), 'la liste des volumes')
                for _ in range(15):
                    if 'DOS 3.3 disk' in s.line(41):
                        break
                    s.key(b'\x0a')
                s.key(b'\r')
                s.wait(lambda: s.has('/DOS 3.3'), 'le catalogue DOS 3.3')
                p.stable()
                s.key(b'\t')

            def enter(folder):
                s.select('..', 0)
                s.key(b'\r')
                p.stable()
                s.select(folder, 0)
                s.key(b'\r')
                p.stable()

            def run(name):
                """`name` sous le curseur a gauche, DOSREPL, puis la question."""
                s.select(name, 0)
                p.stable()
                menu_run(s, p, 'DOSREPL')
                q = 'Replace %s on DOS S%s,D2?' % (name, slot)
                s.wait(lambda: s.has(q) or s.rows()[22].strip(),
                       'la question de DOSREPL ou son refus', 90)
                return s.has(q)

            def replace(name, what, old, note='Replaced; source kept.'):
                s.ok('DOSREPL nomme ' + name + ' et son lecteur', run(name),
                     s.rows()[22].strip())
                s.key(b'Y')
                s.wait(lambda: s.has(note), 'le remplacement de ' + name, 300)
                p.stable()
                disk = flushed()
                after = read_files(disk)
                s.ok(name + ' porte les octets du fichier ProDOS',
                     after[name]['data'] == what,
                     (len(after[name]['data']), len(what)))
                s.ok('les secteurs de l ancien ' + name + ' sont rendus au bitmap',
                     freed(disk, old['blocks'] + old['lists']))
                s.ok('la nouvelle copie de ' + name + ' est ailleurs',
                     not (set(after[name]['blocks']) & set(old['blocks'])),
                     (after[name]['blocks'][:3], old['blocks'][:3]))
                s.ok('KEEP n a pas bouge pendant ' + name,
                     after['KEEP']['data'] == before['KEEP']['data'])
                return after

            s.select('DEMO', 0)
            s.key(b'\r')
            s.wait(lambda: s.has('HELLO'), 'le dossier DEMO')
            p.stable()
            open_dos()

            # 1. La question declinee n'ecrit rien.
            s.ok('DOSREPL pose sa question sur HELLO', run('HELLO'),
                 s.rows()[22].strip())
            s.key(b'N')
            p.stable()
            s.ok('un refus laisse la disquette intacte', flushed() == original)

            # 2. Un Applesoft : deux octets de longueur en tete.
            after = replace('HELLO', want_bas, before['HELLO'])
            s.ok('le type DOS de HELLO est Applesoft', after['HELLO']['type'] == 2,
                 after['HELLO']['type'])
            s.ok('TIGER n a pas bouge non plus',
                 after['TIGER']['data'] == before['TIGER']['data'])

            # 3. Un binaire de 8 Ko : adresse, longueur, et une liste T/S
            #    entierement remplie.
            enter('IMGHGR')
            after = replace('TIGER', want_bin, before['TIGER'])
            s.ok('le type DOS de TIGER est binaire', after['TIGER']['type'] == 4,
                 after['TIGER']['type'])
            s.ok('HELLO remplace plus tot est toujours la',
                 after['HELLO']['data'] == want_bas)
            s.ok('le disque dur source n a pas bouge', hd.read_bytes() == source)

            # 4. Recommencer doit redonner le meme disque : un remplacement ne
            #    laisse pas un etat ou le suivant echoue.
            again = replace('TIGER', want_bin, after['TIGER'])
            s.ok('le second remplacement de TIGER donne les memes octets',
                 again['TIGER']['data'] == want_bin)

            # 5. Un disque qui ne peut pas porter les deux copies est refuse.
            p.eject(1)
            full = crowded(want_bin, before['TIGER'])
            target.write_bytes(full)
            p.insert(1, str(target))
            open_dos()
            asked = run('TIGER')
            line = s.rows()[22].strip()
            s.ok('un disque trop plein pour deux copies est refuse',
                 not asked and 'free sectors' in line, line)
            s.ok('et il n y est rien ecrit', flushed() == full)
    return ok_all(s, 'dosrepl')


if __name__ == '__main__':
    sys.exit(main())
