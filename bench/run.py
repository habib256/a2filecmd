"""Le banc fonctionnel d'A2 File Cmd, sur la disquette telle qu'elle est publiee.

Il amorce dist/A2FILECMD.po dans POM2 sans fenetre, avec un second volume
vide comme cible, et joue une session complete : naviguer, marquer, copier,
deplacer, renommer, supprimer, creer un dossier, changer type et verrou,
lire un texte et des octets, editer et sauver, afficher les deux formats
d'image et les comparer octet a octet, jouer une musique, ouvrir le
formateur, et enfin lancer un programme Applesoft.

    make disk && POM2=/chemin/vers/pom2 python3 bench/run.py [--out DOSSIER]

Chaque controle imprime PASS ou FAIL ; le premier echec arrete le banc et
imprime l'ecran. Avec --out, les captures et un resume JSON y sont ecrits.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from pom2 import Pom2, Session, ROOT
import mkdemo
import mkdos33

README_LEN = (ROOT / 'data/README.TXT').stat().st_size

ESC, RET, DOWN, UP, LEFT, RIGHT, TAB = b'\x1b', b'\r', b'\x0a', b'\x0b', b'\x08', b'\x15', b'\t'


def decode_rle(stream, size):
    """La boucle de decode_rle() dans src/a2fc.c, pour l'attendu du banc."""
    out, i = bytearray(), 8
    while len(out) < size:
        t = stream[i]; i += 1
        if t & 0x80:
            out += bytes((stream[i],)) * ((t & 0x7F) + 3); i += 1
        else:
            out += stream[i:i + t + 1]; i += t + 1
    return bytes(out)


def volume(stage, out, name, blocks):
    subprocess.run([sys.executable, str(ROOT / 'tools/mkvolume.py'), str(stage), str(out),
                    '--volume', name, '--blocks', str(blocks)], check=True, capture_output=True)
    return out


def scratch_volume(dirpath, name='SCRATCH', blocks=1600):
    """Un disque dur vide : POM2 en veut un, et les copies ont besoin d'une cible.
    Il porte aussi TINY.PO, une petite image ProDOS de 64 blocs (un texte, un
    dossier) pour les essais d'images disque."""
    stage = dirpath / 'scratch'
    (stage / 'WORK').mkdir(parents=True)
    (stage / 'WORK/NOTE.TXT').write_bytes(b'scratch\r')
    tiny = dirpath / 'tiny'
    (tiny / 'INSIDE').mkdir(parents=True)
    (tiny / 'INSIDE/DEEP.TXT').write_bytes(b'deep inside the image\r')
    (tiny / 'HELLO.TXT').write_bytes(b'hello from inside a disk image\r' * 20)
    volume(tiny, stage / 'TINY.PO', 'TINY', 64)
    # une image DOS 3.3 (18 pistes : VTOC + catalogue + fichiers, sous 128 Ko)
    dos = mkdos33.build([
        ('GREETINGS', 0x00, b'HELLO FROM A DOS 3.3 DISK\r' * 4 + b'\x00'),
        ('MYPROG', 0x02, bytes([0x05, 0x00]) + b'\x00\x00'),
        ('BINFILE', 0x04, bytes([0x00, 0x20, 0x04, 0x00]) + b'\x01\x02\x03\x04'),
    ])[:18 * 16 * 256]
    (stage / 'DOS33.DSK').write_bytes(dos)
    (stage / 'OUT').mkdir()
    # le dossier DEMO, tel que le .2mg le livre mais en petit : la disquette
    # publiee n'en porte plus, c'est ici que le banc l'essaie
    mkdemo.make(stage / 'DEMO', full=False)
    shutil.copyfile(ROOT / 'data/README.TXT', stage / 'DEMO/README.TXT')
    return volume(stage, dirpath / 'SCRATCH.hdv', name, blocks)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, help='ou ecrire captures et resume')
    ap.add_argument('--port', type=int, default=6610)
    args = ap.parse_args()
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix='a2fc-bench-') as tmp:
        tmp = Path(tmp)
        floppy = tmp / 'A2FILECMD.po'
        shutil.copyfile(ROOT / 'dist/A2FILECMD.po', floppy)
        with Pom2(scratch_volume(tmp), floppy=floppy, port=args.port, mouse=True) as p:
            s = Session(p)

            def shot(name):
                if not args.out:
                    return
                (args.out / f'{name}.ppm').write_bytes(
                    urllib.request.urlopen(p.base + '/screen.ppm').read())
                (args.out / f'{name}.txt').write_text('\n'.join(r.rstrip() for r in s.rows()))

            # ── 1. le demarrage ───────────────────────────────────────────
            s.boot()
            s.ok('la disquette amorce sur les deux panneaux', s.has('/A2FILECMD'), s.rows()[0][:30])
            s.ok('la version est affichee', s.has('A2 FILE CMD 0.6.6'))
            s.ok('le panneau droit, sans DEMO sur la disquette, montre les volumes',
                 '[Volumes]' in s.rows()[0][40:], s.rows()[0][40:70])
            s.ok('les blocs libres sont comptes',
                 re.search(r'\d+ of 280 blocks free', s.rows()[20]) is not None, s.rows()[20][:70])
            shot('01-panels')

            # ── 2. naviguer ───────────────────────────────────────────────
            s.select('A2FILE'); s.key(RET)
            s.wait(lambda: s.has('/A2FILECMD/A2FILE'), 'ouvrir A2FILE'); p.stable()
            s.ok('Entree ouvre un dossier', any(r.startswith('A2FILE.CODE') for r in s.rows()))
            s.key(ESC); s.wait(lambda: s.rows()[0][:11] == '/A2FILECMD ', 'remonter'); p.stable()
            s.ok('Echap remonte et reselectionne le dossier quitte',
                 s.line().startswith('A2FILE '), s.line()[:20])
            before = s.line()
            s.key(RIGHT); p.stable()
            s.ok('la fleche droite fait une page, elle n ouvre pas',
                 s.rows()[0][:11] == '/A2FILECMD ' and s.line() != before, s.line()[:20])
            s.key(b'['); p.stable()
            s.ok('[ revient a la premiere entree', s.line().startswith('.. '), s.line()[:12])

            # ── 3. les images ─────────────────────────────────────────────
            dhgr = decode_rle(mkdemo.image(b'DHRR', 16384, mkdemo.dhgr_card()), 16384)
            hgr = decode_rle(mkdemo.image(b'HGRR', 8192, mkdemo.hgr_card()), 8192)
            s.key(TAB)                                    # le panneau droit : /SCRATCH/DEMO
            s.select('/SCRATCH', 40); s.key(RET)
            s.wait(lambda: s.rows()[0][40:].startswith('/SCRATCH '), 'SCRATCH droit'); p.stable()
            s.select('DEMO', 40); s.key(RET)
            s.wait(lambda: s.has('/SCRATCH/DEMO'), 'DEMO droit'); p.stable()
            s.select('DHGR.RLE', 40); s.key(RET)
            s.wait(lambda: s.value('view', 1) == 1, 'image DHGR', 40); time.sleep(1.5)
            page = p.peek(0x2000, 8192, 'aux') + p.peek(0x2000, 8192)
            s.ok('la mire DHGR est decodee octet a octet dans les deux banques', page == dhgr)
            shot('02-dhgr')
            s.key(ESC); s.wait(lambda: s.value('view', 1) == 0, 'retour'); p.stable()
            s.ok('le format et la taille sont annonces', s.has('DHGR RLE, 16384 bytes on screen'),
                 s.rows()[22].strip())
            s.ok('/RAM est refait a neuf apres une image DHGR', s.has('/RAM was rebuilt empty'),
                 s.rows()[22].strip())
            s.select('DHGR.RLE', 40); s.key(RET)
            s.wait(lambda: s.value('view', 1) == 1, 'image DHGR'); time.sleep(1.5)
            s.key(RIGHT); time.sleep(1.5)
            s.ok("la fleche droite feuillette l'album sans revenir aux panneaux",
                 s.value('view', 1) == 1)
            s.key(ESC); s.wait(lambda: s.value('view', 1) == 0, 'retour'); p.stable()
            s.select('HGR.RLE', 40); s.key(RET)
            s.wait(lambda: s.value('view', 1) == 1, 'image HGR', 40); time.sleep(1.5)
            s.ok('la mire HGR est decodee en banque principale',
                 p.peek(0x2000, 8192) == hgr)
            shot('03-hgr')
            s.key(ESC); s.wait(lambda: s.value('view', 1) == 0, 'retour'); p.stable()
            s.ok('une image HGR simple ne touche pas a /RAM', not s.has('rebuilt'),
                 s.rows()[22].strip())

            # ── 4. texte, hexa, aide ──────────────────────────────────────
            s.select('SAMPLE', 40); s.key(RET)
            s.wait(lambda: s.value('view', 1) == 2, 'visionneuse texte'); p.stable()
            s.ok('le texte se lit page par page', s.has('SAMPLE TEXT'), s.rows()[0][:40])
            shot('04-text')
            s.key(ESC); s.wait(lambda: s.value('view', 1) == 0, 'retour')
            s.key(b'H'); s.wait(lambda: s.value('view', 1) == 3, 'hexa'); p.stable()
            s.ok('la vue hexadecimale montre adresses et ASCII', s.has('00000 '), s.rows()[0][:40])
            shot('05-hex')
            s.key(ESC); s.wait(lambda: s.value('view', 1) == 0, 'retour')
            s.key(b'?'); s.wait(lambda: s.value('view', 1) == 4, 'aide'); p.stable()
            s.ok("l'aide est lue sur la disquette", s.has('A2 FILE CMD 0.6.6'), s.rows()[0][:50])
            shot('06-help')
            s.key(b' '); s.wait(lambda: s.value('view', 1) == 0, 'retour'); p.stable()

            # ── 5. la musique ─────────────────────────────────────────────
            # Attendre le message plutot qu'un sleep fixe : la surcouche MUSIC
            # se charge du disque, et selon la vitesse de l'emulateur le
            # message arrive juste avant ou juste apres un demi-quart de seconde.
            s.select('WELCOME.MB', 40); s.key(RET)
            s.wait(lambda: s.has('Playing WELCOME.MB'), 'la fanfare demarre', 10)
            s.ok('la fanfare joue sur la Mockingboard', s.has('Playing WELCOME.MB'),
                 s.rows()[22].strip())
            # Le banc fait tourner la machine bien plus vite que le temps reel :
            # les trois secondes de musique passent en un clin d'oeil. On
            # verifie donc qu'elle s'arrete d'elle-meme, ce qui prouve aussi
            # que le paquet END termine bien le flux fabrique par mkdemo.py.
            s.wait(lambda: p.peek(s.sym['_music_active'], 1)[0] == 0, 'fin du flux', 20)
            s.ok('le flux MB1 se termine seul, sur son paquet END', True)

            # ── 5b. les images disque ──────────────────────────────────────
            # R lit la disquette d'amorce (slot 6 lecteur 1) dans une image
            # ordre DOS 3.3 (BACK.DSK) ; un aller-retour la reecrit sur une
            # disquette vierge (lecteur 2), qui doit reproduire la disquette
            # d'amorce octet a octet. W ecrit une image .PO de 64 blocs
            # (TINY.PO) sur une disquette, comparee apres ejection. O copie la
            # disquette d'amorce sur la vierge, lecteur a lecteur, comparee
            # aussi. On ne relit jamais une disquette inseree en cours de
            # session (POM2 ne la nibblise qu'une fois ecrite) : la source
            # d'une lecture est toujours la disquette d'amorce ou un fichier
            # du disque dur, dont le contenu vient du dossier de preparation.
            blank = tmp / 'BLANK.po'
            (tmp / 'empty').mkdir()

            def blank_disk():
                # une disquette vierge /BLANK, neuve, dans le lecteur 2 : apres
                # une ecriture, la precedente porte le volume qu'on y a copie,
                # que le graveur refuserait comme « en cours d'utilisation ».
                volume(tmp / 'empty', blank, 'BLANK', 280)
                p.insert(1, 'BLANK.po')

            blank_disk()
            if s.cursor_row(0) is None:      # le panneau gauche actif : / et select y agissent
                s.key(TAB)
            s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'volumes')
            s.select('/SCRATCH'); s.key(RET)
            s.wait(lambda: s.rows()[0][:9] == '/SCRATCH ', 'ouvrir SCRATCH'); p.stable()

            def drive_key(slot, drive):
                for _ in range(20):
                    for r in s.rows():
                        if f'slot {slot} drive {drive}' in r:
                            return r.strip()[0].encode()
                    time.sleep(0.1)     # la liste se dessine peut-etre encore
                raise AssertionError('lecteur absent de la liste\n' + '\n'.join(s.rows()))

            def write_back(label):
                s.key(b'W'); s.wait(lambda: s.has('DISK IMAGES'), 'menu ' + label)
                s.key(b'W'); s.wait(lambda: s.has('to which disk?'), 'lecteur ' + label); p.stable()
                s.key(drive_key(6, 2)); s.wait(lambda: s.has('Type ERASE'), 'erase ' + label)
                s.type('ERASE'); s.key(RET)
                s.wait(lambda: s.has('written to slot 6 drive 2') or s.has('Failed'), label, 200)
                p.stable()

            # R : lire la disquette d'amorce dans une image DOS 3.3
            s.select('WORK'); s.key(b'W')
            s.wait(lambda: s.has('DISK IMAGES'), 'menu des images'); p.stable()
            s.ok('W ouvre la surcouche des images disque',
                 s.has('R  Read a disk') and s.has('O  Copy a disk'), s.rows()[5:7])
            shot('10-diskimg')
            s.key(b'R'); s.wait(lambda: s.has('Read which disk'), 'choix du lecteur'); p.stable()
            s.ok('la liste des lecteurs nomme la disquette du programme et la vierge',
                 s.has('/A2FILECMD') and s.has('/BLANK') and s.has('IN USE'), s.rows()[4:8])
            s.key(drive_key(6, 1)); s.wait(lambda: s.has('Image name'), 'nom')
            s.type('BACK'); s.key(RET); s.wait(lambda: s.has('ProDOS order (.PO) or D'), 'ordre')
            s.key(b'D')
            s.wait(lambda: s.has('280 blocks read from slot 6 drive 1') or s.has('Failed'), 'lecture', 200)
            p.stable()
            s.ok('R lit la disquette d amorce dans BACK.DSK, selectionnee au retour',
                 s.has('280 blocks read from') and s.line().startswith('BACK.DSK ') and '143360' in s.line(),
                 s.line()[:40])
            # aller-retour : reecrire BACK.DSK sur la disquette vierge
            s.select('BACK.DSK'); write_back('reecriture')
            s.ok('l aller-retour DOS 3.3 reecrit 280 blocs sur la disquette',
                 s.has('280 blocks written to slot 6 drive 2'), s.rows()[22].strip())
            p.eject(1); time.sleep(.5)
            s.ok("l'image DOS 3.3 reproduit la disquette d amorce octet a octet",
                 blank.read_bytes() == floppy.read_bytes())
            blank_disk()

            # W : ecrire l'image .PO de 64 blocs sur la disquette vierge
            s.select('TINY.PO'); s.key(b'W')
            s.wait(lambda: s.has('W  Write TINY.PO to a disk'), 'menu W'); p.stable()
            s.key(b'W'); s.wait(lambda: s.has('to which disk?'), 'choix du lecteur'); p.stable()
            s.key(drive_key(6, 2)); s.wait(lambda: s.has('Type ERASE'), 'avertissement')
            s.ok("l'avertissement nomme le lecteur et son volume",
                 s.has('slot 6 drive 2 (/BLANK) WILL BE LOST'), s.rows()[20].strip())
            s.type('ERASE'); s.key(RET)
            s.wait(lambda: s.has('64 blocks written to slot 6 drive 2') or s.has('Failed'), 'ecriture', 120)
            p.stable()
            s.ok("l'image .PO est ecrite sur la disquette, les panneaux reviennent",
                 s.has('64 blocks written to slot 6 drive 2') and s.rows()[0][:9] == '/SCRATCH ',
                 s.rows()[22].strip())
            p.eject(1); time.sleep(.5)
            tiny = (tmp / 'scratch/TINY.PO').read_bytes()
            s.ok('la disquette porte les 64 blocs de TINY.PO, octet a octet',
                 blank.read_bytes()[:len(tiny)] == tiny and len(blank.read_bytes()) == 143360)
            blank_disk()

            # O : copier la disquette d'amorce sur la vierge, lecteur a lecteur
            s.key(b'W'); s.wait(lambda: s.has('DISK IMAGES'), 'menu des images')
            s.key(b'O'); s.wait(lambda: s.has('Copy FROM which disk'), 'source'); p.stable()
            s.key(drive_key(6, 1)); s.wait(lambda: s.has('Copy TO which disk'), 'cible'); p.stable()
            s.key(drive_key(6, 2)); s.wait(lambda: s.has('Type ERASE'), 'avertissement'); p.stable()
            s.ok('O enchaine source, cible et avertissement avant toute ecriture',
                 s.has('slot 6 drive 2') and s.has('WILL BE LOST'), s.rows()[20].strip())
            s.type('ERASE'); s.key(RET)
            s.wait(lambda: s.has('280 blocks copied to slot 6 drive 2') or s.has('Failed'), 'copie', 300)
            p.stable()
            s.ok('O copie la disquette d amorce sur l autre lecteur',
                 s.has('280 blocks copied to slot 6 drive 2'), s.rows()[22].strip())
            p.eject(1); time.sleep(.5)
            s.ok('la copie est la disquette d amorce, octet a octet',
                 blank.read_bytes() == floppy.read_bytes())

            # ── 5c. une image disque comme dossier (IMGFS) ────────────────
            # Entree sur TINY.PO l'ouvre en lecture comme un dossier ; on y
            # navigue, et C extrait un fichier vers l'autre panneau, dont on
            # verifie le contenu octet a octet. Le panneau gauche reste sur
            # /SCRATCH (la cible), le droit ouvre l'image.
            if s.cursor_row(40) is None:        # activer le panneau droit
                s.key(TAB)
            s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'volumes')
            s.select('/SCRATCH', 40); s.key(RET)
            s.wait(lambda: s.rows()[0][40:].startswith('/SCRATCH '), 'scratch droit'); p.stable()
            s.select('TINY.PO', 40); s.key(RET)
            s.wait(lambda: s.has('/SCRATCH/TINY.PO') or s.has('Not a ProDOS'), 'ouvrir image', 20); p.stable()
            s.ok("Entree ouvre une image .PO comme un dossier",
                 s.has('/SCRATCH/TINY.PO') and any(r[40:].startswith('HELLO ') for r in s.rows()),
                 s.rows()[0][40:70])
            shot('11-imgfs')
            s.select('INSIDE', 40); s.key(RET)
            s.wait(lambda: s.has('/SCRATCH/TINY.PO/INSIDE'), 'sous-dossier'); p.stable()
            s.ok("on descend dans les sous-dossiers de l'image",
                 any(r[40:].startswith('DEEP ') for r in s.rows()))
            s.key(ESC); s.wait(lambda: s.rows()[0][40:].startswith('/SCRATCH/TINY.PO '), 'remonter'); p.stable()
            s.ok("Echap remonte a la racine de l'image",
                 any(r[40:].startswith('INSIDE ') for r in s.rows()))
            # C : extraire HELLO vers le panneau gauche (/SCRATCH)
            s.select('HELLO', 40); s.key(b' '); p.stable()
            s.key(b'C'); s.wait(lambda: s.has('extracted') or s.has('folder') or s.has('failed'), 'extraction', 30)
            p.stable()
            s.ok('C extrait un fichier de l image vers un vrai dossier', s.has('1 file extracted'),
                 s.rows()[22].strip())
            s.ok("le fichier extrait parait dans le panneau cible",
                 any(r.startswith('HELLO ') and 'TXT' in r for r in s.rows()),
                 next((r[:40] for r in s.rows() if r.startswith('HELLO ')), 'absent'))
            # verifier le contenu du fichier extrait
            if s.cursor_row(0) is None:
                s.key(TAB)
            s.select('HELLO'); s.key(b'T'); s.wait(lambda: s.value('view', 1) == 2, 'texte extrait', 15); p.stable()
            s.ok("le contenu extrait est correct octet a octet",
                 s.has('hello from inside a disk image'), s.rows()[0][:40])
            s.key(ESC); s.wait(lambda: s.value('view', 1) == 0, 'retour'); p.stable()
            # sortir de l'image et rendre au panneau droit son dossier DEMO,
            # que la suite attend
            if s.cursor_row(40) is None:
                s.key(TAB)
            s.key(ESC); s.wait(lambda: s.rows()[0][40:].startswith('/SCRATCH '), 'sortir image'); p.stable()
            s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'volumes')
            s.select('/SCRATCH', 40); s.key(RET)
            s.wait(lambda: s.rows()[0][40:].startswith('/SCRATCH '), 'racine droite'); p.stable()
            s.select('DEMO', 40); s.key(RET)
            s.wait(lambda: s.has('/SCRATCH/DEMO'), 'DEMO droit'); p.stable()

            # ── 5d. une disquette DOS 3.3 (image) ─────────────────────────
            # Entree sur DOS33.DSK montre son catalogue DOS 3.3 (types T/A/B) ;
            # C en extrait un texte, dont on verifie le contenu. Le panneau
            # gauche ouvre /SCRATCH/OUT (cible), le droit l'image.
            if s.cursor_row(0) is None:         # panneau gauche actif
                s.key(TAB)
            s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'volumes')
            s.select('/SCRATCH'); s.key(RET)
            s.wait(lambda: s.rows()[0][:9] == '/SCRATCH ', 'scratch gauche'); p.stable()
            s.select('OUT'); s.key(RET); s.wait(lambda: s.has('/SCRATCH/OUT'), 'OUT'); p.stable()
            if s.cursor_row(40) is None:
                s.key(TAB)
            s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'volumes')
            s.select('/SCRATCH', 40); s.key(RET)
            s.wait(lambda: s.rows()[0][40:].startswith('/SCRATCH '), 'scratch droit'); p.stable()
            s.select('DOS33.DSK', 40); s.key(RET)
            s.wait(lambda: s.has('/SCRATCH/DOS33.DSK') or s.has('Not a ProDOS'), 'ouvrir DOS 3.3', 20)
            p.stable()
            s.ok('Entree ouvre une image DOS 3.3 et montre son catalogue',
                 s.has('/SCRATCH/DOS33.DSK') and any(r[40:].startswith('GREETINGS ') for r in s.rows()),
                 s.rows()[0][40:70])
            shot('12-dos33')
            s.ok('les types DOS 3.3 sont traduits en ProDOS',
                 any(r[40:].startswith('GREETINGS ') and 'TXT' in r for r in s.rows())
                 and any(r[40:].startswith('MYPROG ') and 'BAS' in r for r in s.rows())
                 and any(r[40:].startswith('BINFILE ') and 'BIN' in r for r in s.rows()))
            s.select('GREETINGS', 40); s.key(b'C')
            s.wait(lambda: s.has('extracted') or s.has('folder') or s.has('failed'), 'extraction DOS', 30)
            p.stable()
            s.ok('C extrait un fichier DOS 3.3 vers un dossier ProDOS', s.has('1 file extracted'),
                 s.rows()[22].strip())
            if s.cursor_row(0) is None:
                s.key(TAB)
            s.select('GREETINGS'); s.key(b'T')
            s.wait(lambda: s.value('view', 1) == 2, 'texte DOS extrait', 15); p.stable()
            s.ok('le fichier DOS 3.3 extrait a le bon contenu',
                 s.has('HELLO FROM A DOS 3.3 DISK'), s.rows()[0][:40])
            s.key(ESC); s.wait(lambda: s.value('view', 1) == 0, 'retour'); p.stable()
            # sortir de l'image et rendre au panneau droit son dossier DEMO
            if s.cursor_row(40) is None:
                s.key(TAB)
            s.key(ESC); s.wait(lambda: s.rows()[0][40:].startswith('/SCRATCH '), 'sortir DOS 3.3'); p.stable()
            s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'volumes')
            s.select('/SCRATCH', 40); s.key(RET)
            s.wait(lambda: s.rows()[0][40:].startswith('/SCRATCH '), 'racine droite'); p.stable()
            s.select('DEMO', 40); s.key(RET)
            s.wait(lambda: s.has('/SCRATCH/DEMO'), 'DEMO droit 2'); p.stable()

            # ── 6. copier, deplacer, renommer, supprimer ──────────────────
            s.key(TAB)                                    # le panneau gauche, la racine
            s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'volumes')
            s.select('/SCRATCH'); s.key(RET)
            s.wait(lambda: s.rows()[0][:9] == '/SCRATCH ', 'ouvrir SCRATCH'); p.stable()
            s.ok('la liste des volumes ouvre le disque dur', s.has('WORK '), s.line()[:20])
            s.key(TAB)                                    # retour a DEMO, la source
            s.select('SAMPLE', 40); s.key(b' '); s.select('HGR.RLE', 40); s.key(b' '); p.stable()
            s.ok('Espace marque deux fichiers', s.has('2 tagged'), s.rows()[21][60:])
            ops = s.value('ops')
            s.key(b'C'); s.wait(lambda: s.has('files copied') or s.has('failed'), 'copie', 90)
            p.stable()
            s.ok('C copie les fichiers marques vers l autre panneau',
                 s.has('2 files copied'), s.rows()[22].strip())
            s.ok('le compteur d operations a avance', s.value('ops') > ops)
            shot('07-copy')
            # V : copier puis supprimer l'original, en une touche
            s.select('README', 40); s.key(b'V')
            s.wait(lambda: s.has('moved') or s.has('failed'), 'deplacement', 90); p.stable()
            s.ok('V deplace le fichier', s.has('1 file moved'), s.rows()[22].strip())
            s.ok("l'original a bien disparu de la source",
                 not any(r[40:].startswith('README ') for r in s.rows()))
            s.key(TAB)
            s.ok('et se retrouve dans la cible',
                 any(r.startswith('README ') and '%d' % README_LEN in r for r in s.rows()),
                 next((r[:40] for r in s.rows() if r.startswith('README ')), 'absent'))
            s.ok('la copie garde nom, type et taille',
                 any(r.startswith('SAMPLE ') and 'TXT' in r and '712' in r for r in s.rows()),
                 next((r[:40] for r in s.rows() if r.startswith('SAMPLE ')), 'absent'))
            s.select('SAMPLE'); s.key(b'R'); s.wait(lambda: s.has('New name:'), 'renommer')
            p.raw(b'\x08' * 6); s.type('COPIE'); s.key(RET); p.stable()
            s.ok('R renomme', any(r.startswith('COPIE ') for r in s.rows()))
            s.select('COPIE'); s.key(b'L'); p.stable()
            s.ok('L verrouille', s.has('locked'), s.rows()[22].strip())
            s.key(b'D'); s.wait(lambda: s.has('Delete COPIE?'), 'confirmation'); s.key(b'Y'); p.stable()
            s.ok('un fichier verrouille refuse la suppression', s.has('Delete failed'),
                 s.rows()[22].strip())
            s.key(b'L'); p.stable()
            s.key(b'A'); s.wait(lambda: s.has('File type: $04'), 'type')
            p.raw(b'\x08\x08'); s.type('F1'); s.key(RET)
            s.wait(lambda: s.has('Aux type:'), 'auxtype')
            p.raw(b'\x08' * 4); s.type('1234'); s.key(RET); p.stable()
            s.ok('A change type et auxtype',
                 any(r.startswith('COPIE ') and '$F1 $1234' in r for r in s.rows()),
                 next((r[:40] for r in s.rows() if r.startswith('COPIE ')), ''))
            s.key(b'K'); s.wait(lambda: s.has('New directory'), 'mkdir')
            s.type('NEUF'); s.key(RET); p.stable()
            s.ok('K cree un dossier', any(r.startswith('NEUF ') and '<DIR>' in r for r in s.rows()))
            s.select('COPIE'); s.key(b'D'); s.wait(lambda: s.has('Delete COPIE?'), 'suppression')
            s.key(b'Y'); p.stable()
            s.ok('D supprime', not any(r.startswith('COPIE ') for r in s.rows()))

            # ── 7. l'editeur ──────────────────────────────────────────────
            s.select('HGR.RLE'); s.key(b'E')
            s.wait(lambda: s.value('view', 1) == 5, 'editeur'); p.stable()
            s.type('HELLO'); s.key(ESC)
            s.wait(lambda: s.has('Save and exit'), 'menu editeur'); p.stable()
            shot('08-editor')
            s.key(b'Q'); s.wait(lambda: s.has('Discard'), 'abandon'); s.key(b'Y')
            s.wait(lambda: s.value('view', 1) == 0, 'sortie editeur'); p.stable()
            s.ok("l'editeur s'ouvre, edite et sait abandonner",
                 any(r.startswith('HGR.RLE ') and '978' in r for r in s.rows()),
                 next((r[:40] for r in s.rows() if r.startswith('HGR.RLE ')), ''))

            # ── 9. le formateur ───────────────────────────────────────────
            s.key(b'F'); s.wait(lambda: s.has('Open the disk formatter?'), 'F')
            s.key(b'Y'); s.wait(lambda: s.has('ERASES EVERYTHING'), 'formateur', 60); p.stable()
            s.ok('F ouvre le formateur, qui liste les lecteurs',
                 s.has('Disk II 5.25') and s.has('/A2FILECMD'), s.rows()[3][:60])
            shot('09-format')
            # ESC relance A2FILE.SYSTEM : on attend l'en-tete des panneaux, pas
            # le titre -- l'ecran d'attente du lanceur le porte aussi.
            s.key(ESC); s.wait(lambda: s.has('Type  Aux     Size'), 'retour au gestionnaire', 90)
            p.stable()
            s.ok('Echap relance le gestionnaire, qui retrouve ses panneaux (A2FILE.CFG)',
                 s.rows()[0].startswith('/SCRATCH ') and '/SCRATCH/DEMO' in s.rows()[0], s.rows()[0][:60])

            # ── 10. la souris ─────────────────────────────────────────────
            # Une AppleMouse II en slot 4 depuis le debut de la session : tout ce
            # qui precede s'est fait au clavier avec elle en place, sans que le
            # pointeur ne s'affiche -- il ne parait qu'une fois la souris bougee.
            s.ok('la souris est vue en slot 4, la ligne de statut le dit',
                 s.value('mouse', 1) == 4 and s.has(' Mouse '), s.rows()[20][60:])
            s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'volumes')
            s.select('/SCRATCH'); s.key(RET)
            s.wait(lambda: s.rows()[0][:9] == '/SCRATCH ', 'racine'); p.stable()
            s.select('DEMO'); s.key(RET); s.wait(lambda: s.has('/SCRATCH/DEMO'), 'DEMO')
            p.stable()
            x0 = 0 if s.cursor_row(0) is not None else 40      # le panneau actif
            other = 40 - x0

            def cell(x, y):
                base = 0x400 + (y & 7) * 0x80 + (y >> 3) * 40 + (x >> 1)
                return p.peek(base, 1, 'aux' if x % 2 == 0 else 'main')[0]
            p.home(); p.mouse(x=50, y=10); time.sleep(.3)
            s.ok('le pointeur suit la souris, une fleche MouseText',
                 cell(50, 10) == 0x42 and p.peek(s.sym['_mouse_x'], 2) == bytes([50, 10]),
                 (hex(cell(50, 10)), p.peek(s.sym['_mouse_x'], 2).hex()))
            p.mouse(x=150); time.sleep(.3)                 # +100 : hors de l'ecran
            s.ok("le firmware borne la souris a l'ecran", p.peek(s.sym['_mouse_x'], 1)[0] == 79,
                 p.peek(s.sym['_mouse_x'], 1)[0])
            p.home()
            p.click(x0 + 37, 5)                            # DEMO trie : ligne 5 = HGR.RLE ; en bout de ligne, hors du nom
            s.ok('un clic selectionne la ligne', s.line(x0).startswith('HGR.RLE'), s.line(x0)[:20])
            p.click(x0 + 37, 5)
            s.wait(lambda: s.value('view', 1) == 1, 'image par la souris', 40); time.sleep(1)
            s.ok("un second clic sur la selection l'ouvre", s.value('view', 1) == 1)
            s.key(ESC); s.wait(lambda: s.value('view', 1) == 0, 'retour'); p.stable()
            p.click(other + 5, 2)
            s.ok("un clic dans l'autre panneau l'active et y pose le curseur",
                 s.cursor_row(other) == 2 and s.cursor_row(x0) is None,
                 (s.cursor_row(other), s.cursor_row(x0)))
            p.click(74, 23)                                # le bouton ? Help
            s.wait(lambda: s.value('view', 1) == 4, 'aide par la souris'); p.stable()
            s.ok("un clic sur la barre des commandes vaut la touche", s.value('view', 1) == 4)
            s.key(b' '); s.wait(lambda: s.value('view', 1) == 0, 'retour'); p.stable()
            p.click(3, 23)                                 # TAB Panel
            s.ok('un clic sur TAB Panel change de panneau', s.cursor_row(x0) is not None,
                 (s.cursor_row(x0), s.cursor_row(other)))
            p.mouse(x=79, y=20); time.sleep(.2)            # le pointeur hors du chemin

            # ── 11. Applesoft, en dernier : on ne revient pas ─────────────
            s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'volumes')
            s.select('/SCRATCH'); s.key(RET)
            s.wait(lambda: s.rows()[0][:9] == '/SCRATCH ', 'racine'); p.stable()
            s.select('DEMO'); s.key(RET); s.wait(lambda: s.has('/SCRATCH/DEMO'), 'DEMO')
            p.stable()
            # T sur un BAS : la surcouche BASLIST le detokenise (au lieu de l'hexa)
            s.select('HELLO'); p.stable()
            s.key(b'T'); s.wait(lambda: s.value('view', 1) == 2, 'BASLIST', 20); p.stable()
            s.ok('T sur un BAS liste le programme Applesoft detokenise',
                 s.has('10  HOME') and s.has('PRINT "A2 FILE CMD RUNS APPLESOFT."'),
                 s.rows()[0].strip()[:40])
            s.key(ESC); s.wait(lambda: s.value('view', 1) == 0, 'retour liste'); p.stable()
            s.select('HELLO'); s.key(RET)
            s.wait(lambda: s.has('Run HELLO?'), 'confirmation')
            s.ok('un BAS demande confirmation avant de partir', s.has('No return'),
                 s.rows()[22].strip())
            s.key(b'Y')
            s.wait(lambda: any('A2 FILE CMD RUNS APPLESOFT' in r for r in s.rows40()),
                   'Applesoft', 60)
            s.ok('BASIC.SYSTEM execute le programme Applesoft', True)
            s.wait(lambda: any(r.startswith(']') for r in s.rows40()), 'invite Applesoft', 30)
            s.ok('Applesoft rend la main', any(r.startswith(']') for r in s.rows40()))
            # HELLO est sur /SCRATCH, qui n'a pas de BASIC.SYSTEM : RUN a pris
            # celui de la disquette amorcee et lance "-/SCRATCH/DEMO/HELLO".
            # BASIC.SYSTEM pose le prefixe sur son propre volume, /A2FILECMD :
            # le retour annonce par le programme, -A2FILE.SYSTEM, s'y resout.
            # Le lanceur repose le prefixe sur le volume amorce (BASIC.SYSTEM
            # l'a vide en partant), donc A2FC revient sur ses panneaux (ceux
            # d'A2FILE.CFG), pas sur la liste des volumes -- on l'exige ici.
            s.type('-A2FILE.SYSTEM'); s.key(RET)
            s.wait(lambda: s.has('Type  Aux     Size'), 'retour a A2FC', 90); p.stable()
            s.ok('-A2FILE.SYSTEM relance A2 File Cmd depuis Applesoft',
                 s.rows()[0].startswith('/SCRATCH') and '/SCRATCH/DEMO' in s.rows()[0], s.rows()[0][:60])

            passed = sum(1 for c in s.checks if c['ok'])
            print(f'\n{passed} controles, tous passes', flush=True)
            if args.out:
                (args.out / 'bench.json').write_text(
                    json.dumps({'checks': s.checks, 'passed': passed}, indent=2) + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
