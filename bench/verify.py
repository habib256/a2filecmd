#!/usr/bin/env python3
"""Le banc de la surcouche VERIFY (src/plugins/verify.c), edition disquette.

Un disque dur de 800 blocs avec WORK/BIG (20 480 octets) et WORK/NOTE : la
surcouche lit BIG en entier et le dit en ligne de message, de meme NOTE, de
meme le dossier WORK lui-meme (un dossier se lit comme un fichier) ; puis,
depuis la liste des volumes, elle lit les 800 blocs de /WORKHD, la barre de
progression visible pendant la lecture, et ESC interrompt une seconde
lecture du volume. POM2 ne rend jamais d'erreur sur son disque dur : le
compte de blocs illisibles ne peut etre que zero ici, et la liste des blocs
refuses ne peut pas etre eprouvee.

Deux precautions pour voir la lecture pendant qu'elle court : POM2 tourne
par defaut a 200 000 cycles par trame (une douzaine de fois la vitesse du
Apple II), ou les 800 blocs passent en un clin d'oeil -- on le ramene a la
vitesse reelle par /speed le temps des deux lectures de volume ; et la
ligne de message est relue seule ($750, 40 octets par banque) au lieu de
tout l'ecran, deux requetes au lieu de huit.

Le compteur de pile C (c_sp, $80) est relu avant et apres une lecture :
sprintf est variadique, cc65 lui passe la taille de ses arguments en Y, et
un appel qui l'oublierait laisserait ses arguments sur la pile a chaque
passage (src/plugins/verify.c, l'en-tete).

    make build-6502/verify.PLG ARCH=6502 && python3 bench/verify.py
"""
import re
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pom2 import BUILD, Pom2
from xplug import boot_hd, menu_run, ok_all, RET, ESC

PORT = 6804
BAR = re.compile(r'\[#*\.*\] ')      # la barre de progression du programme, quarante cases
FAST = 200000                        # cycles par trame : le reglage de bench/pom2.py
SLOW = 17030                         # la vitesse reelle, pour voir passer la barre
ROW22 = 0x400 + 0x350                # la ligne de message, $750 (40 octets par banque)


def speed(p, cycles):
    """La cadence de l'emulateur, en cycles par trame."""
    try:
        p.rq('/speed', {'cycles_per_frame': cycles})
    except Exception as e:              # un POM2 sans /speed : le banc tourne encore
        print('/speed indisponible (%s)' % e, flush=True)


def line22(p):
    """La ligne de message seule, sans relire tout l'ecran."""
    main, aux = p.peek(ROW22, 40), p.peek(ROW22, 40, 'aux')
    return ''.join(Pom2._cell(aux[c // 2] if c % 2 == 0 else main[c // 2]) for c in range(80))


def bar_fill(p):
    """Le nombre de cases pleines de la barre, ou None s'il n'y a pas de barre.

    Les deux banques de l'ecran 80 colonnes sont relues l'une apres l'autre :
    une barre qui bouge donne des lectures panachees, ce qui suffit ici (on
    ne compare que des nombres de cases, jamais deux moities d'une meme
    image) et prouve deja qu'elle avance."""
    row = line22(p).rstrip()
    return row.count('#') if BAR.search(row) else None


def wait_bar(p, least=1, seconds=60):
    """Attend une barre d'au moins `least` cases pleines et rend ce compte."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        n = bar_fill(p)
        if n is not None and n >= least:
            return n
        if 'blocks read' in line22(p):      # la lecture est deja finie : trop tard
            return None
    return None


def menu_pick(s, p, name, tries=40):
    """Ouvre le menu des surcouches et pose le curseur sur `name`, sans
    Entree : la lecture qui suit doit etre observee pendant qu'elle court."""
    s.key(b'!')
    s.wait(lambda: s.has('the overlays'), 'le menu des surcouches', 30)
    p.stable()
    for _ in range(tries):
        r = s.cursor_row(2)
        if r is not None and s.rows()[r][2:14].strip() == name:
            return
        s.key(name[0].encode())
        p.stable()
    raise AssertionError(f'{name} introuvable dans le menu\n' + '\n'.join(s.rows()))


def verdict(s, p, needle, what):
    """Attend la ligne de message qui contient `needle` et la rend."""
    s.wait(lambda: needle in line22(p), what, 90)
    p.stable()
    return s.rows()[22].strip()


def main():
    plg = (BUILD / 'verify.PLG').read_bytes()
    big = bytes(range(256)) * 80                 # 20 480 octets, quarante blocs
    note = b'A short note, to be read again.\r'
    files = {'WORK/BIG.BIN': big, 'WORK/NOTE.TXT': note}
    with tempfile.TemporaryDirectory(prefix='a2fc-verify-') as tmp:
        with boot_hd(tmp, files, port=PORT, blocks=800, plugins=['verify']) as (p, s):
            s.ok("VERIFY.PLG est une petite surcouche signee PLUGIN_MAGIC, sous 1 280 octets",
                 plg[:2] == b'\xfc\xa2' and plg[2] == 0 and len(plg) <= 1280, len(plg))

            # 1. un fichier, puis un petit, puis le dossier qui les contient
            s.select('WORK'); s.key(RET)
            s.wait(lambda: s.has('/WORKHD/WORK'), 'le dossier WORK'); p.stable()
            s.select('BIG'); p.stable()
            sp_before = p.peek(0x80, 2)                   # la pile C avant la surcouche
            menu_run(s, p, 'VERIFY')
            row = verdict(s, p, 'bytes read', 'le verdict de BIG')
            s.ok('BIG est lu en entier : "BIG: 20480 bytes read OK"', row == 'BIG: 20480 bytes read OK', row)
            s.ok('A2FC a repris la main sur ses panneaux', s.has('Type  Aux'))
            s.ok('la pile C est rendue telle quelle (sprintf appele avec sa taille en Y)',
                 p.peek(0x80, 2) == sp_before, (sp_before.hex(), p.peek(0x80, 2).hex()))

            s.select('NOTE'); p.stable()
            menu_run(s, p, 'VERIFY')
            row = verdict(s, p, 'bytes read', 'le verdict de NOTE')
            s.ok('NOTE aussi, a l\'octet pres', row == 'NOTE: %d bytes read OK' % len(note), row)

            s.select('..'); s.key(RET)
            s.wait(lambda: not s.has('/WORKHD/WORK'), 'la racine'); p.stable()
            s.select('WORK'); p.stable()
            menu_run(s, p, 'VERIFY')
            row = verdict(s, p, 'WORK', 'le verdict du dossier WORK')
            s.ok('un dossier se lit comme un fichier : ses blocs, a la taille de son entree',
                 re.fullmatch(r'WORK: \d+ bytes read OK', row) is not None, row)

            # 2. le volume entier, depuis la liste des volumes, la barre pendant la lecture
            s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'la liste des volumes'); p.stable()
            s.select('/WORKHD'); p.stable()
            menu_pick(s, p, 'VERIFY')
            speed(p, SLOW)                               # sinon les 800 blocs passent trop vite
            p.raw(RET)
            seen = wait_bar(p)
            s.ok('la barre de progression avance sur la ligne 22 pendant la lecture',
                 seen is not None, seen)
            row = verdict(s, p, 'blocks read', 'le verdict de /WORKHD')
            speed(p, FAST)
            s.ok('les 800 blocs de /WORKHD sont lus : "/WORKHD: 800 blocks read, 0 bad"',
                 row == '/WORKHD: 800 blocks read, 0 bad', row)
            s.ok('la liste des volumes est toujours a l\'ecran', s.has('[Volumes]'))

            # 3. ESC interrompt une lecture du volume
            menu_pick(s, p, 'VERIFY')
            speed(p, SLOW)
            p.raw(RET)
            s.ok('la barre repart pour la seconde lecture', wait_bar(p) is not None)
            p.raw(ESC)
            row = verdict(s, p, 'blocks read', "l'interruption")
            speed(p, FAST)
            m = re.fullmatch(r'/WORKHD: (\d+) blocks read, interrupted, 0 bad', row)
            s.ok('ESC arrete la lecture et le message le dit, avec le compte atteint',
                 m is not None and 0 < int(m.group(1)) < 800, row)

            # 4. la surcouche resert apres tout cela : rien ne s'est use en route
            s.select('/WORKHD'); s.key(RET)
            s.wait(lambda: s.rows()[0][:8] == '/WORKHD ', 'la racine de /WORKHD'); p.stable()
            s.select('WORK'); s.key(RET)
            s.wait(lambda: s.has('/WORKHD/WORK'), 'le dossier WORK'); p.stable()
            s.select('BIG'); p.stable()
            menu_run(s, p, 'VERIFY')
            row = verdict(s, p, 'bytes read', 'le verdict de BIG, la seconde fois')
            s.ok('apres six passages, BIG est encore lu en entier',
                 row == 'BIG: 20480 bytes read OK', row)
            s.ok('la pile C n\'a pas bouge de tout le banc', p.peek(0x80, 2) == sp_before,
                 (sp_before.hex(), p.peek(0x80, 2).hex()))
    return ok_all(s, 'bench/verify.py')


if __name__ == '__main__':
    sys.exit(main())
