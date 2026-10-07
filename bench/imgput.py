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
qu'elle n'arrive pas dans le vrai parcours.

Puis le parcours des references (src/plugins/prodos_claims.h), tel que cc65
le compile, sur la machine : un volume de 800 blocs portant un arbre, un
arbrisseau, un fichier etendu et trois niveaux de dossiers (le verger de
tools/test_imgput.py) recoit un fichier a sa racine puis un autre dans un
sous-dossier, et reste sain pour tools/prodos_check.py ; le meme volume avec
un bloc de donnees marque libre est refuse sans qu'un octet bouge ; un .2MG
protege en ecriture aussi. Les cycles de la copie dans le verger sont
affiches : sur un vrai IIe, un million de cycles font une seconde.

Enfin les deux autres conteneurs, que seuls les tests sur l'hote ecrivaient :
la meme image en .DSK (les moities de chaque bloc rangees dans l'ordre des
secteurs DOS) et en .2MG (un en-tete devant), relues a l'arret. C'est le
chemin d'ecriture d'imageio.h, commun a IMGPUT, PASCALW et CPMW."""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from xplug import boot_hd, menu_run, ok_all, RET
from imgconv import catalog
from po22mg import to_2mg
from po2dsk import to_dsk
from prodos_read import Image
import prodos_check
import test_imgput as fixtures

PORT = 6914
ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = b'a line written into the image.\r' * 40      # 1240 octets : un sapling
KEEP = b'this one was there first\r' * 20
THIRD = b'this one came in with the C key\r' * 3
DONE = ('Copied', 'No room', 'Not enough', 'Not a ProDOS', 'ProDOS file here',
        'Image is read-only', 'Image changed', 'Image damaged', 'Stopped', 'Source changed',
        'Cannot', 'Bitmap writ', 'Write failed', 'Too big')


def cycles(p):
    return p.rq('/status')['cpu']['cycles']


def damaged_orchard(orchard):
    """Le verger, le premier bloc de donnees de SUB/KEEP.TXT marque libre."""
    d = bytearray(orchard)
    sub = fixtures.key_of(fixtures.find(orchard, 'SUB'))
    keep = fixtures.key_of(fixtures.find(orchard, 'KEEP.TXT', sub))
    fixtures.set_free(d, d[keep * 512] | d[keep * 512 + 256] << 8)
    return bytes(d)


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
    orchard = fixtures.orchard()
    damaged = damaged_orchard(orchard)
    locked = bytearray(to_2mg(target))
    locked[0x13] |= 0x80                    # drapeaux 2IMG, bit 31 : protege en ecriture
    locked = bytes(locked)
    frag = fixtures.scattered(8192)             # deux pages de bitmap, un sapling a cheval
    files = {'IMG/TARGET.PO#060000': target,
             'IMG/ORCHARD.PO#060000': orchard,
             'IMG/DAMAGED.PO#060000': damaged,
             'IMG/FRAG.PO#060000': frag,
             'IMG/LOCKED.2MG#060000': locked,
             'IMG/ORDER.DSK#060000': to_dsk(target),
             'IMG/HEADER.2MG#060000': to_2mg(target),
             'IN/HELLO.TXT#04C001': PAYLOAD,
             'IN/OTHER.TXT#040000': b'a second source\r',
             'IN/THIRD.TXT#040000': THIRD}

    with tempfile.TemporaryDirectory(prefix='a2fc-imgput-') as tmp:
        tmp = Path(tmp)
        with boot_hd(tmp, files, port=PORT, blocks=16000, plugins=['imgput']) as (p, s):
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
                run.cycles = cycles(p)
                if answer and asked:
                    s.key(answer)
                    # Un refus ne dit rien : il n'y a pas de message a
                    # attendre, seulement l'ecran qui se repose.
                    if answer != b'N':
                        s.wait(lambda: any(m in s.rows()[22] for m in DONE),
                               'la fin de ' + name, 300)
                run.cycles = cycles(p) - run.cycles
                p.stable()
                return asked, s.rows()[22].strip()

            def mount(image, shows):
                """Le panneau droit dans une autre image de /WORKHD/IMG."""
                open_panel(40, 'IMG')
                s.select(image, 40); s.key(RET)
                s.wait(lambda: s.has(shows), image + ' montee comme dossier'); p.stable()

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
                 line == 'No room for that name here.', line)
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

            # 6. Le verger : tout ce que le parcours doit suivre, sur la machine.
            mount('ORCHARD.PO', 'BIG.BIN')
            asked, line = run('HELLO.TXT', b'Y')
            s.ok('un volume a arbre, fichier etendu et sous-dossiers recoit le fichier',
                 line == 'Copied into the image; source kept.', line)
            print('cycles : parcours et copie dans le verger %d' % run.cycles, flush=True)

            # 7. Dans un sous-dossier de l'image.
            if s.cursor_row(40) is None:
                s.key(b'\t')
            s.select('SUB', 40); s.key(RET)
            s.wait(lambda: s.has('KEEP.TXT') and s.has('DEEP'), 'le sous-dossier de l image'); p.stable()
            asked, line = run('THIRD.TXT', b'Y')
            s.ok('un fichier entre dans un sous-dossier de l image',
                 line == 'Copied into the image; source kept.', line)

            # 7b. Un sapling dont les 256 pointeurs alternent entre deux pages
            #     du bitmap (4 096 blocs) : le parcours chargeait une page par
            #     pointeur, 256 lectures sans signe de vie ; une page par page
            #     maintenant. Mesure (65C02) : 11,4 millions de cycles avant,
            #     3,8 a 4,2 millions apres.
            mount('FRAG.PO', 'FRAG')
            asked, line = run('HELLO.TXT', b'Y')
            s.ok('un sapling disperse sur deux pages du bitmap recoit le fichier',
                 line == 'Copied into the image; source kept.', line)
            print('cycles : parcours et copie, sapling sur deux pages %d' % run.cycles, flush=True)
            s.ok('le parcours du sapling disperse ne recharge pas une page par pointeur',
                 run.cycles < 8000000, run.cycles)

            # 8. Le meme volume, un bloc de donnees marque libre : rien n'est ecrit.
            mount('DAMAGED.PO', 'BIG.BIN')
            asked, line = run('HELLO.TXT', b'Y')
            s.ok('la question est posee avant le parcours', asked, line)
            s.ok('un bitmap qui dit libre un bloc reference est refuse',
                 line == 'Image damaged: nothing written. Run FIXIT.', line)

            # 9. Un .2MG protege en ecriture.
            mount('LOCKED.2MG', 'KEEP.TXT')
            asked, line = run('HELLO.TXT', b'Y')
            s.ok('un .2MG protege en ecriture est refuse sans question',
                 not asked and line == 'Image is read-only.', (asked, line))

            # 10. Les deux autres conteneurs.
            for image in ('ORDER.DSK', 'HEADER.2MG'):
                mount(image, 'KEEP.TXT')
                asked, line = run('HELLO.TXT', b'Y')
                s.ok('IMGPUT ecrit dans %s' % image,
                     line == 'Copied into the image; source kept.', line)

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

        # Le verger : sain pour l'oracle, les deux fichiers a leur place,
        # ceux qui y etaient intacts.
        images = catalog(Path(p.hdv), 'IMG')
        raw = images['ORCHARD.PO'][2]
        found = [(f.id, f.block) for f in prodos_check.check(raw).findings]
        s.ok('le verger est sain pour prodos_check apres deux copies', not found, found[:4])
        sub = fixtures.key_of(fixtures.find(raw, 'SUB'))
        hello, third = fixtures.find(raw, 'HELLO.TXT'), fixtures.find(raw, 'THIRD.TXT', sub)
        im = Image(raw)
        s.ok('HELLO.TXT est a la racine du verger avec ses octets',
             hello is not None and im.read(hello) == PAYLOAD)
        s.ok('THIRD.TXT est dans SUB, pointe vers l en-tete de SUB, avec ses octets',
             third is not None and im.read(third) == THIRD and
             fixtures.word(third, 0x25) == sub and fixtures.find(raw, 'THIRD.TXT') is None)
        s.ok('le compte de SUB a monte de un, celui du volume aussi',
             fixtures.file_count(raw, sub) == fixtures.file_count(orchard, sub) + 1 and
             fixtures.file_count(raw) == fixtures.file_count(orchard) + 1,
             (fixtures.file_count(raw, sub), fixtures.file_count(raw)))
        s.ok('l arbre, l arbrisseau et le fichier etendu du verger sont intacts',
             im.read(fixtures.find(raw, 'BIG.BIN')) == fixtures.BIG and
             im.read(fixtures.find(raw, 'KEEP.TXT', sub)) == fixtures.KEEP and
             all(raw[b * 512:(b + 1) * 512] == orchard[b * 512:(b + 1) * 512]
                 for b in range(800) if not fixtures.is_free(orchard, b)
                 and b not in (2, sub, fixtures.bitmap_at(orchard))))
        s.ok('le volume refuse est octet pour octet celui qui a ete pose',
             images['DAMAGED.PO'][2] == damaged)
        s.ok('le .2MG protege aussi', images['LOCKED.2MG'][2] == locked)
        for image, unwrap in (('ORDER.DSK', to_dsk), ('HEADER.2MG', lambda d: d[64:])):
            stored = images[image][2]
            raw = unwrap(stored)
            hello = fixtures.find(raw, 'HELLO.TXT')
            found = [(f.id, f.block) for f in prodos_check.check(raw).findings]
            s.ok('%s : le fichier y est avec ses octets, KEEP.TXT intact, le volume sain' % image,
                 hello is not None and Image(raw).read(hello) == PAYLOAD and
                 Image(raw).read(fixtures.find(raw, 'KEEP.TXT')) == KEEP and not found,
                 found[:4])
        s.ok('l en-tete du .2MG n a pas bouge',
             images['HEADER.2MG'][2][:64] == to_2mg(target)[:64])
    return ok_all(s, 'imgput')


if __name__ == '__main__':
    sys.exit(main())
