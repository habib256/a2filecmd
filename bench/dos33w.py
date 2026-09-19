#!/usr/bin/env python3
"""Banc de DOS33W : supprimer et renommer sur un vrai disque DOS 3.3, en
lecteur 2, sur une disquette jetable.

    make all disk && python3 bench/dos33w.py

La disquette est fabriquee par tools/mini33_fixture.py et relue par lui a
chaque etape : ce qui est verifie, ce sont les octets du disque, pas le
message. Un fichier supprime doit rendre au bitmap exactement ses secteurs
et aucun autre, son entree doit garder sa piste la ou UNDELETE la relit, et
les fichiers voisins ne doivent pas bouger d'un octet. Un refus -- fichier
verrouille, question declinee -- doit laisser la disquette identique.

DOS33W veut le panneau du disque DOS *actif* : c'est son panneau qui dit sur
quel fichier il travaille, l'autre ne sert a rien ici."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from pom2 import Pom2, Session, BUILD
from xplug import menu_run, ok_all
from mini33_fixture import make_disk, read_files, offset

PORT = 6912
KEEP = b'kept whole\r' * 60
GONE = b'to be removed\r' * 120
FILES = [('KEEP', 0x00, KEEP), ('GONE', 0x04, GONE), ('LOCKED', 0x82, b'locked\r' * 20)]


def freed(disk, sectors):
    """Les secteurs `sectors` sont-ils tous libres dans le bitmap du VTOC ?"""
    vtoc = disk[offset(17, 0):offset(17, 0) + 256]
    return all(vtoc[0x38 + t * 4 + (s < 8)] & (1 << (s & 7)) for t, s in sectors)


def main():
    with tempfile.TemporaryDirectory(prefix='dos33w-') as d:
        d = Path(d)
        hd = d / 'test.hdv'
        target = d / 'dos.dsk'
        cpu = '6502' if BUILD.name == 'build-6502' else '65C02'
        hd.write_bytes((BUILD / f'A2FILECMD-{cpu}-BOOT.hdv').read_bytes())
        original = make_disk(FILES)
        target.write_bytes(original)
        before = read_files(original)
        slot = os.environ.get('A2FC_DOS_SLOT', '6')

        with Pom2(hd, floppy2=target, port=PORT,
                  exe=os.environ.get('POM2', '/tmp/a2fc-dos-host')) as p:
            s = Session(p)
            s.boot()

            def open_dos():
                s.key(b'/')
                s.wait(lambda: s.has('[Volumes]'), 'la liste des volumes')
                for _ in range(15):
                    if 'DOS 3.3 disk' in s.line(0):
                        break
                    s.key(b'\x0a')
                s.key(b'\r')
                # LOCKED est le seul des trois qui ne soit ni supprime ni
                # renomme : c'est lui qui dit que le catalogue est la.
                s.wait(lambda: s.has('LOCKED') and '/DOS 3.3' in s.rows()[0],
                       'le catalogue DOS 3.3')
                p.stable()

            def flushed():
                """Les octets de la disquette, vraiment. POM2 ne la reecrit
                sur l'hote qu'a l'ejection : la relire sans ejecter donnerait
                l'image de depart et ferait passer n'importe quoi."""
                p.eject(1)
                data = target.read_bytes()
                p.insert(1, str(target))
                return data

            def verb(name, key=None):
                """Le fichier `name` sous le curseur, DOS33W, puis `key`.

                Les refus qui ne dependent pas du verbe -- un fichier
                verrouille, un disque protege -- tombent AVANT la question
                D/R : on attend donc l'une ou l'autre."""
                s.select(name, 0)
                p.stable()
                menu_run(s, p, 'DOS33W')
                s.wait(lambda: s.has('Delete or rename') or s.rows()[22].strip(),
                       'la question de DOS33W ou son refus', 60)
                if key and s.has('Delete or rename'):
                    s.key(key)
                    p.stable()
                return s.rows()[22].strip()

            open_dos()
            s.ok('le panneau actif est le disque DOS 3.3',
                 s.rows()[0].startswith('/DOS 3.3'), s.rows()[0][:30])

            # 1. Un fichier verrouille est refuse avant meme la question.
            line = verb('LOCKED')
            s.ok('un fichier verrouille est refuse',
                 line == 'Locked on the DOS disk; unlock it there first.', line)
            s.ok('et rien n est ecrit', flushed() == original)
            open_dos()

            # 2. La question declinee n'ecrit rien.
            verb('GONE', b'D')
            s.wait(lambda: s.has('Delete GONE on DOS 3.3 S' + slot + ',D2?'),
                   'la confirmation de suppression', 60)
            s.key(b'N')
            p.stable()
            s.ok('un refus laisse la disquette intacte', flushed() == original)
            open_dos()

            # 3. La suppression.
            verb('GONE', b'D')
            s.wait(lambda: s.has('Delete GONE on DOS 3.3 S' + slot + ',D2?'),
                   'la confirmation, seconde fois', 60)
            s.key(b'Y')
            s.wait(lambda: s.has('Deleted from the DOS 3.3 disk'), 'la suppression', 120)
            p.stable()
            disk = flushed()
            after = read_files(disk)
            s.ok('GONE a quitte le catalogue', 'GONE' not in after, sorted(after))
            s.ok('KEEP n a pas bouge', after['KEEP']['data'] == before['KEEP']['data'])
            s.ok('LOCKED n a pas bouge', after['LOCKED']['data'] == before['LOCKED']['data'])
            s.ok('ses secteurs sont rendus au bitmap',
                 freed(disk, before['GONE']['blocks'] + before['GONE']['lists']))
            track = before['GONE']['entry'][0]
            kept = any(disk[offset(17, sec) + 11 + i * 35] == 0xFF and
                       disk[offset(17, sec) + 11 + i * 35 + 32] == track
                       for sec in range(1, 16) for i in range(7))
            s.ok('l entree supprimee garde sa piste pour UNDELETE', kept)

            # 4. Le renommage.
            open_dos()
            verb('KEEP', b'R')
            s.wait(lambda: s.has('New name'), 'la question du nouveau nom', 60)
            # Le champ arrive pre-rempli du nom actuel : l'effacer d'abord,
            # sinon on renomme KEEP en KEEPGARDE.
            p.raw(b'\x08' * len('KEEP'))
            s.type('GARDE')
            s.key(b'\r')
            s.wait(lambda: s.has('Rename KEEP to GARDE?'), 'la confirmation', 60)
            s.key(b'Y')
            s.wait(lambda: s.has('Renamed on the DOS 3.3 disk'), 'le renommage', 120)
            p.stable()
            after = read_files(flushed())
            s.ok('le nom a change', 'GARDE' in after and 'KEEP' not in after, sorted(after))
            s.ok('les octets du fichier renomme sont les memes',
                 after['GARDE']['data'] == before['KEEP']['data'])
            s.ok('il occupe les memes secteurs',
                 after['GARDE']['blocks'] == before['KEEP']['blocks'])

            # 5. Un nom deja pris est refuse.
            open_dos()
            verb('GARDE', b'R')
            s.wait(lambda: s.has('New name'), 'la question, seconde fois', 60)
            p.raw(b'\x08' * len('GARDE'))
            s.type('LOCKED')
            s.key(b'\r')
            s.wait(lambda: s.has('already on the DOS 3.3 disk'), 'le refus du nom pris', 60)
            p.stable()
            s.ok('un nom deja pris est refuse',
                 sorted(read_files(flushed())) == sorted(after))
    return ok_all(s, 'dos33w')


if __name__ == '__main__':
    sys.exit(main())
