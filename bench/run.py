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


def scratch_volume(dirpath, name='SCRATCH', blocks=1600):
    """Un disque dur vide : POM2 en veut un, et les copies ont besoin d'une cible."""
    stage = dirpath / 'scratch'
    (stage / 'WORK').mkdir(parents=True)
    (stage / 'WORK/NOTE.TXT').write_bytes(b'scratch\r')
    hdv = dirpath / 'SCRATCH.hdv'
    subprocess.run([sys.executable, str(ROOT / 'tools/mkvolume.py'), str(stage), str(hdv),
                    '--volume', name, '--blocks', str(blocks)], check=True, capture_output=True)
    return hdv


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
            s.ok('la version est affichee', s.has('A2 FILE CMD 0.5'))
            s.ok('le panneau droit ouvre DEMO', s.rows()[0][40:].startswith('/A2FILECMD/DEMO'),
                 s.rows()[0][40:70])
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
            s.key(TAB)                                    # le panneau droit est sur DEMO
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
            s.ok("l'aide est lue sur la disquette", s.has('A2 FILE CMD 0.5'), s.rows()[0][:50])
            shot('06-help')
            s.key(b' '); s.wait(lambda: s.value('view', 1) == 0, 'retour'); p.stable()

            # ── 5. la musique ─────────────────────────────────────────────
            s.select('WELCOME.MB', 40); s.key(RET); time.sleep(.5)
            s.ok('la fanfare joue sur la Mockingboard', s.has('Playing WELCOME.MB'),
                 s.rows()[22].strip())
            # Le banc fait tourner la machine bien plus vite que le temps reel :
            # les trois secondes de musique passent en un clin d'oeil. On
            # verifie donc qu'elle s'arrete d'elle-meme, ce qui prouve aussi
            # que le paquet END termine bien le flux fabrique par mkdemo.py.
            s.wait(lambda: p.peek(s.sym['_music_active'], 1)[0] == 0, 'fin du flux', 20)
            s.ok('le flux MB1 se termine seul, sur son paquet END', True)

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
                 any(r.startswith('README ') and '1184' in r for r in s.rows()),
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

            # ── 8. le formateur ───────────────────────────────────────────
            s.key(b'F'); s.wait(lambda: s.has('Open the disk formatter?'), 'F')
            s.key(b'Y'); s.wait(lambda: s.has('ERASES EVERYTHING'), 'formateur', 60); p.stable()
            s.ok('F ouvre le formateur, qui liste les lecteurs',
                 s.has('Disk II 5.25') and s.has('/A2FILECMD'), s.rows()[3][:60])
            shot('09-format')
            # ESC relance A2FILE.SYSTEM : on attend l'en-tete des panneaux, pas
            # le titre -- l'ecran d'attente du lanceur le porte aussi.
            s.key(ESC); s.wait(lambda: s.has('Type  Aux     Size'), 'retour au gestionnaire', 90)
            p.stable()
            s.ok('Echap relance le gestionnaire depuis la disquette',
                 s.has('/A2FILECMD'), s.rows()[0][:30])

            # ── 9. la souris ──────────────────────────────────────────────
            # Une AppleMouse II en slot 4 depuis le debut de la session : tout ce
            # qui precede s'est fait au clavier avec elle en place, sans que le
            # pointeur ne s'affiche -- il ne parait qu'une fois la souris bougee.
            s.ok('la souris est vue en slot 4, la ligne de statut le dit',
                 s.value('mouse', 1) == 4 and s.has(' Mouse '), s.rows()[20][60:])
            s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'volumes')
            s.select('/A2FILECMD'); s.key(RET)
            s.wait(lambda: s.rows()[0][:11] == '/A2FILECMD ', 'racine'); p.stable()
            s.select('DEMO'); s.key(RET); s.wait(lambda: s.has('/A2FILECMD/DEMO'), 'DEMO')
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

            # ── 10. Applesoft, en dernier : on ne revient pas ─────────────
            s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'volumes')
            s.select('/A2FILECMD'); s.key(RET)
            s.wait(lambda: s.rows()[0][:11] == '/A2FILECMD ', 'racine'); p.stable()
            s.select('DEMO'); s.key(RET); s.wait(lambda: s.has('/A2FILECMD/DEMO'), 'DEMO')
            p.stable()
            s.select('HELLO'); s.key(RET)
            s.wait(lambda: s.has('Run HELLO?'), 'confirmation')
            s.ok('un BAS demande confirmation avant de partir', s.has('No return'),
                 s.rows()[22].strip())
            s.key(b'Y')
            s.wait(lambda: any('A2 FILE CMD RUNS APPLESOFT' in r for r in s.rows40()),
                   'Applesoft', 60)
            s.ok('BASIC.SYSTEM execute le programme Applesoft', True)
            s.ok('Applesoft rend la main', any(r.startswith(']') for r in s.rows40()))

            passed = sum(1 for c in s.checks if c['ok'])
            print(f'\n{passed} controles, tous passes', flush=True)
            if args.out:
                (args.out / 'bench.json').write_text(
                    json.dumps({'checks': s.checks, 'passed': passed}, indent=2) + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
