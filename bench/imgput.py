#!/usr/bin/env python3
"""Banc d'IMGPUT : un fichier ProDOS ecrit DANS une image ProDOS montee.

    make all disk && python3 bench/imgput.py

L'image d'essai est fabriquee par tools/mkvolume.py et posee sur le disque
dur du banc dans /WORKHD/IMG. Le panneau droit s'ouvre *dedans* -- Retour
sur le .PO monte l'image comme un dossier -- et le gauche sur /WORKHD/IN,
ou se trouve le fichier a copier.

A l'arret, le disque dur est relu sur l'hote et l'image en est extraite,
puis lue comme un volume a son tour : le fichier doit y porter exactement
ses octets, son type et son auxtype, le fichier qui y etait deja ne doit pas
avoir bouge, et -- le controle qui compte -- chaque bloc que l'entree nomme
doit etre marque occupe dans le bitmap. Une entree qui nomme un bloc libre
est la seule panne qui donne un volume corrompu plutot que de la place
perdue ; c'est celle que tools/test_imgput.py provoque, et celle-ci verifie
qu'elle n'arrive pas dans le vrai parcours."""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from xplug import boot_hd, menu_run, ok_all, RET
from imgconv import catalog
from prodos_read import Image

PORT = 6914
ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = b'a line written into the image.\r' * 40      # 1240 octets : un sapling
KEEP = b'this one was there first\r' * 20
THIRD = b'this one came in with the C key\r' * 3
DONE = ('Copied', 'No room', 'Not enough', 'Not a ProDOS', 'ProDOS file here',
        'Image is read-only', 'Image changed')


def make_target(tmp):
    """Une image ProDOS de 280 blocs portant un seul fichier."""
    stage = tmp / 'imgstage'
    (stage).mkdir()
    (stage / 'KEEP.TXT#040000').write_bytes(KEEP)
    out = tmp / 'TARGET.PO'
    subprocess.run([sys.executable, str(ROOT / 'tools/mkvolume.py'), str(stage), str(out),
                    '--volume', 'TARGET', '--blocks', '280'], check=True, capture_output=True)
    return out.read_bytes()


def blocks_of(raw, entry):
    """Le bloc cle et, pour un sapling, tous les blocs de donnees."""
    key = int.from_bytes(entry[0x11:0x13], 'little')
    out = [key]
    if entry[0] >> 4 == 2:                              # sapling : cle = index
        idx = raw[key * 512:(key + 1) * 512]
        n = -(-int.from_bytes(entry[0x15:0x18], 'little') // 512)
        out += [idx[i] | (idx[256 + i] << 8) for i in range(n)]
    return [b for b in out if b]


def bitmap_says_used(raw, blocks):
    # Dans un en-tete de volume, le bitmap est en 0x23 et le total en 0x25 :
    # les decalages d'une entree de fichier y nomment autre chose.
    bm = int.from_bytes(raw[2 * 512 + 4 + 0x23:2 * 512 + 4 + 0x25], 'little')
    return all(not (raw[bm * 512 + ((b & 0xFFF) >> 3)] & (0x80 >> (b & 7))) for b in blocks)


def main():
    target = make_target(Path(tempfile.mkdtemp(prefix='a2fc-imgput-mk-')))
    files = {'IMG/TARGET.PO#060000': target,
             'IN/HELLO.TXT#04C001': PAYLOAD,
             'IN/OTHER.TXT#040000': b'a second source\r',
             'IN/THIRD.TXT#040000': THIRD}

    with tempfile.TemporaryDirectory(prefix='a2fc-imgput-') as tmp:
        tmp = Path(tmp)
        with boot_hd(tmp, files, port=PORT, blocks=4000, plugins=['imgput']) as (p, s):
            def open_panel(x, *names):
                if s.cursor_row(x) is None:
                    s.key(b'\t')
                s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'volumes')
                s.select('/WORKHD', x); s.key(RET)
                s.wait(lambda: s.rows()[0][x:].startswith('/WORKHD'), 'racine'); p.stable()
                path = '/WORKHD'
                for n in names:
                    s.select(n, x); s.key(RET)
                    path += '/' + n
                    s.wait(lambda: s.rows()[0][x:].startswith(path), path); p.stable()

            def run(name, answer=None):
                """`name` sous le curseur a gauche, IMGPUT, puis la reponse.

                Ctrl-R efface la ligne 22 d'abord : deux copies de suite
                disent la meme chose, et attendre que le message CHANGE
                attendrait pour rien."""
                if s.cursor_row(0) is None:
                    s.key(b'\t')
                s.key(b'\x12')
                s.wait(lambda: not s.rows()[22].strip(), 'la ligne de message vide', 60)
                s.select(name, 0); p.stable()
                menu_run(s, p, 'IMGPUT')
                q = 'Copy %s into the image?' % name
                s.wait(lambda: s.has(q) or s.rows()[22].strip(),
                       'la question d IMGPUT ou son refus', 90)
                asked = s.has(q)
                if answer and asked:
                    s.key(answer)
                    # Un refus ne dit rien : il n'y a pas de message a
                    # attendre, seulement l'ecran qui se repose.
                    if answer != b'N':
                        s.wait(lambda: any(m in s.rows()[22] for m in DONE),
                               'la fin de ' + name, 300)
                p.stable()
                return asked, s.rows()[22].strip()

            # Le panneau droit DANS l'image, le gauche sur les sources.
            open_panel(40, 'IMG')      # laisse le panneau droit actif
            s.select('TARGET.PO', 40); s.key(RET)
            s.wait(lambda: s.has('KEEP.TXT'), 'l image montee comme dossier'); p.stable()
            s.ok('le .PO s ouvre comme un dossier',
                 s.has('KEEP.TXT') and 'TARGET.PO' in s.rows()[0][40:], s.rows()[0][40:70])
            open_panel(0, 'IN')

            # 1. La question declinee n'ecrit rien.
            asked, line = run('HELLO.TXT', b'N')
            s.ok('IMGPUT pose sa question avant d ecrire', asked, line)
            s.ok('un refus ne change pas l image',
                 catalog(Path(p.hdv), 'IMG')['TARGET.PO'][2] == target)

            # 2. La copie.
            asked, line = run('HELLO.TXT', b'Y')
            s.ok('IMGPUT ecrit dans l image',
                 line == 'Copied into the image; source kept.', line)
            s.key(b'\x12')
            p.stable()
            s.ok('le panneau de l image montre le nouveau fichier',
                 s.has('HELLO.TXT') and s.has('KEEP.TXT'), s.rows()[3][40:])

            # 3. Le meme nom une seconde fois : refuse.
            asked, line = run('HELLO.TXT', b'Y')
            s.ok('un nom deja dans l image est refuse',
                 line == 'No room for that name in this directory.', line)
            saved = catalog(Path(p.hdv), 'IMG')['TARGET.PO'][2]

            # 4. Un second fichier, a cote du premier.
            asked, line = run('OTHER.TXT', b'Y')
            s.ok('un second fichier entre aussi',
                 line == 'Copied into the image; source kept.', line)

            # 5. La touche C : le geste naturel, et le meme travail. Le
            #    panneau d'en face etait refuse en lecture seule avant.
            s.key(b'\x12')
            s.wait(lambda: not s.rows()[22].strip(), 'la ligne de message vide', 60)
            s.select('THIRD.TXT', 0); p.stable()
            s.key(b'C')
            s.wait(lambda: s.has('Copy THIRD.TXT into the image?'),
                   'la question posee par C', 90)
            s.key(b'Y')
            s.wait(lambda: any(m in s.rows()[22] for m in DONE), 'la copie par C', 300)
            p.stable()
            s.ok('C copie dans l image comme le menu',
                 s.rows()[22].strip() == 'Copied into the image; source kept.',
                 s.rows()[22].strip())

        # A l'arret : l'image extraite du disque dur, lue comme un volume.
        raw = catalog(Path(p.hdv), 'IMG')['TARGET.PO'][2]
        s.ok('le refus du doublon n avait rien ecrit',
             len(saved) == len(target), (len(saved), len(target)))
        im = Image(raw)
        got = {e[1:1 + (e[0] & 15)].decode(): e for e in im.entries(2)}
        s.ok('les trois fichiers sont dans l image',
             sorted(got) == ['HELLO.TXT', 'KEEP.TXT', 'OTHER.TXT', 'THIRD.TXT'], sorted(got))
        s.ok('HELLO.TXT porte ses octets exacts',
             im.read(got['HELLO.TXT']) == PAYLOAD,
             (len(im.read(got['HELLO.TXT'])), len(PAYLOAD)))
        s.ok('son type et son auxtype sont ceux de la source',
             got['HELLO.TXT'][0x10] == 0x04 and
             int.from_bytes(got['HELLO.TXT'][0x1F:0x21], 'little') == 0xC001,
             (got['HELLO.TXT'][0x10], int.from_bytes(got['HELLO.TXT'][0x1F:0x21], 'little')))
        s.ok('OTHER.TXT aussi', im.read(got['OTHER.TXT']) == b'a second source\r')
        s.ok('THIRD.TXT, entre par C, porte ses octets',
             im.read(got['THIRD.TXT']) == THIRD)
        s.ok('le fichier qui y etait est intact', im.read(got['KEEP.TXT']) == KEEP)
        s.ok('le compte de fichiers du volume est a jour',
             int.from_bytes(raw[2 * 512 + 4 + 0x21:2 * 512 + 4 + 0x23], 'little') == 4,
             int.from_bytes(raw[2 * 512 + 4 + 0x21:2 * 512 + 4 + 0x23], 'little'))
        for n in ('HELLO.TXT', 'OTHER.TXT', 'THIRD.TXT'):
            b = blocks_of(raw, got[n])
            s.ok('les blocs de %s sont occupes dans le bitmap' % n,
                 bitmap_says_used(raw, b), b[:4])
        s.ok('les deux fichiers ne partagent aucun bloc',
             not (set(blocks_of(raw, got['HELLO.TXT'])) & set(blocks_of(raw, got['OTHER.TXT']))))
        s.ok('les sources ne sont pas touchees',
             catalog(Path(p.hdv), 'IN')['HELLO.TXT'][2] == PAYLOAD)
    return ok_all(s, 'imgput')


if __name__ == '__main__':
    sys.exit(main())
