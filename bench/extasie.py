#!/usr/bin/env python3
"""Banc de la surcouche EXTASIE (src/plugins/extasie.c) : les images $F2 de
Purplesoft, double hi-res compressee, montrees dans le mode MIXTE de la carte
Le Chat Mauve.

    make build/extasie.PLG && A2FC_IMG=A2FILECMD-full python3 bench/extasie.py

C'est ici, et nulle part ailleurs, qu'est verifiee la GEOMETRIE : le code qui
pose les octets colonne par colonne, la gauche d'abord, puis passe le plan
auxiliaire en banque auxiliaire, est en 6502 (src/plugins/extasie.s) parce que
cc65 y depensait un dixieme de la fenetre de 1 280 octets.
tools/test_extasie.py fait tourner le C sur l'hote et couvre le flux ; ce banc
fait tourner la surcouche livree dans l'emulateur et relit les deux plans
octet par octet.

Le specimen est BASTILLE, une image des disquettes Extasie d'origine
(tools/test_extasie.py la porte en base64), et la page attendue est rebatie a
partir de la regle du format, pas du decodeur."""
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from xplug import boot_hd, menu_run, ok_all, RET, ESC
from test_extasie import BASTILLE, unrle, page_of, COLS, ROWS

PORT = 6817


def picture_bytes(page):
    """Les 7 680 octets visibles : les trous d'ecran ne sont pas a l'image."""
    return b''.join(bytes(page[i:i + 120]) for i in range(0, 8192, 128))


def settled(p, seconds=60):
    """La page une fois le decodage fini. Rien sur l'ecran de texte ne dit
    quand il l'est -- la surcouche n'y ecrit pas -- alors on relit $2000
    jusqu'a ce que deux lectures se suivent identiques."""
    last = None
    for _ in range(int(seconds / 0.4)):
        now = bytes(p.peek(0x2000, 8192))
        if now == last:
            return now
        last = now
        time.sleep(0.4)
    raise AssertionError('la page graphique ne se stabilise pas')


def main():
    stream = unrle(BASTILLE)
    assert len(stream) == COLS * ROWS * 2
    aux = page_of(stream[:COLS * ROWS])
    main_plane = page_of(stream[COLS * ROWS:])
    files = {
        'WORK/BASTILLE#F20000': BASTILLE,
        'WORK/HALF#F20000': BASTILLE[:len(BASTILLE) // 2],   # tronquee
        'WORK/PLAIN.BIN#062000': bytes(8192),                # pas une $F2
    }
    with tempfile.TemporaryDirectory(prefix='a2fc-extasie-') as tmp:
        with boot_hd(tmp, files, port=PORT, plugins=['extasie']) as (p, s):
            s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'volumes')
            s.select('/WORKHD'); s.key(RET)
            s.wait(lambda: s.rows()[0].startswith('/WORKHD '), 'la racine'); p.stable()
            s.select('WORK'); s.key(RET)
            s.wait(lambda: s.has('/WORKHD/WORK'), 'WORK'); p.stable()

            # 1. Un fichier qui n'est pas du type $F2 est refuse.
            s.select('PLAIN.BIN', 0); p.stable()
            menu_run(s, p, 'EXTASIE')
            s.wait(lambda: s.has('Not an Extasie'), 'le refus', 20); p.stable()
            s.ok('refuse un binaire ordinaire',
                 s.rows()[22].strip() == 'Not an Extasie $F2 picture.', s.rows()[22].strip())

            # 2. Une image coupee est signalee, pas montree a moitie.
            s.select('HALF', 0); p.stable()
            menu_run(s, p, 'EXTASIE')
            s.wait(lambda: s.has('truncated'), 'le flux coupe', 30); p.stable()
            s.ok('signale un flux tronque', s.rows()[22].strip() == 'Picture truncated.',
                 s.rows()[22].strip())

            # 3. L'image entiere : les deux plans, octet par octet. Le plan
            #    auxiliaire est aussi le seul controle du passage de banque.
            s.select('BASTILLE', 0); p.stable()
            menu_run(s, p, 'EXTASIE')
            got_main = settled(p)
            got_aux = bytes(p.peek(0x2000, 8192, 'aux'))
            s.ok('le plan auxiliaire', picture_bytes(got_aux) == picture_bytes(aux),
                 '%d octets differents' % sum(1 for a, b in
                     zip(picture_bytes(got_aux), picture_bytes(aux)) if a != b))
            s.ok('le plan principal', picture_bytes(got_main) == picture_bytes(main_plane),
                 '%d octets differents' % sum(1 for a, b in
                     zip(picture_bytes(got_main), picture_bytes(main_plane)) if a != b))
            s.key(ESC)
            s.wait(lambda: s.has('/RAM rebuilt'), 'la note sur /RAM', 30); p.stable()
            s.ok('dit que /RAM a ete refait', s.rows()[22].strip() == '/RAM rebuilt.',
                 s.rows()[22].strip())
            s.ok('le curseur est reste sur le fichier', s.line(0).startswith('BASTILLE '),
                 s.line(0))
    return ok_all(s, 'extasie')


if __name__ == '__main__':
    sys.exit(main())
