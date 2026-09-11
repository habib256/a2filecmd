#!/usr/bin/env python3
"""Banc de la surcouche PAINT816 (src/plugins/paint816.c) : les images que
816/Paint enregistre compressees, un $06 d'auxtype $E001 (hi-res) ou $E002
(double hi-res).

    make build/paint816.PLG && A2FC_IMG=A2FILECMD-full python3 bench/paint816.py

C'est ici, et nulle part ailleurs, qu'est verifiee la GEOMETRIE : le code
qui pose les octets colonne par colonne, la plus a droite d'abord, est en
6502 (src/plugins/paint816.s) parce que cc65 y depensait un treizieme de la
fenetre de 1 280 octets. tools/test_paint816.py fait tourner le C sur
l'hote et couvre la grammaire des enregistrements ; ce banc fait tourner la
surcouche livree dans l'emulateur et relit la page graphique octet par
octet.

Les deux specimens sont des fichiers que 816/Paint a reellement ecrits
(tools/test_paint816.py les porte en base64) et les pages attendues sont
rebaties a partir de leur description, pas du decodeur."""
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from xplug import boot_hd, menu_run, ok_all, RET, ESC
from test_paint816 import (LADDER_PACKED, RUNS_PACKED, ladder_stream, runs_stream,
                           page_left_to_right, COLS, ROWS)

PORT = 6816


def picture_bytes(page):
    """Les 7 680 octets visibles : les trous d'ecran ne sont pas a l'image."""
    return b''.join(bytes(page[i:i + 120]) for i in range(0, 8192, 128))


def settled(p, bank='main', seconds=60):
    """La page une fois le decodage fini. Rien sur l'ecran de texte ne dit
    quand il l'est -- la surcouche n'y ecrit pas -- alors on relit $2000
    jusqu'a ce que deux lectures se suivent identiques."""
    last = None
    for _ in range(int(seconds / 0.4)):
        now = bytes(p.peek(0x2000, 8192, bank))
        if now == last:
            return now
        last = now
        time.sleep(0.4)
    raise AssertionError('la page graphique ne se stabilise pas')


def main():
    ladder = page_left_to_right(ladder_stream())
    runs = page_left_to_right(runs_stream())
    shifted = page_left_to_right(bytes(runs_stream()[((c + 1) % COLS) * ROWS + r]
                                       for c in range(COLS) for r in range(ROWS)))
    files = {
        'WORK/LADDER.P#06E001': LADDER_PACKED,      # hi-res
        'WORK/RUNS.P#06E002': RUNS_PACKED,          # double hi-res
        'WORK/PLAIN.BIN#062000': bytes(8192),       # ni l'un ni l'autre : refuse
    }
    with tempfile.TemporaryDirectory(prefix='a2fc-paint816-') as tmp:
        with boot_hd(tmp, files, port=PORT, plugins=['paint816']) as (p, s):
            s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'volumes')
            s.select('/WORKHD'); s.key(RET)
            s.wait(lambda: s.rows()[0].startswith('/WORKHD '), 'la racine'); p.stable()
            s.select('WORK'); s.key(RET)
            s.wait(lambda: s.has('/WORKHD/WORK'), 'WORK'); p.stable()

            # 1. Un fichier qui n'a pas l'auxtype est refuse, et l'ecran reste
            #    en texte.
            s.select('PLAIN.BIN', 0); p.stable()
            menu_run(s, p, 'PAINT816')
            s.wait(lambda: s.has('Not a packed'), 'le refus', 20); p.stable()
            s.ok('refuse un binaire ordinaire', s.rows()[22].strip() == 'Not a packed 816/Paint page.',
                 s.rows()[22].strip())

            # 2. L'image hi-res : la page $2000-$3FFF, octet par octet.
            s.select('LADDER.P', 0); p.stable()
            menu_run(s, p, 'PAINT816')
            got = settled(p)
            s.ok('hi-res : les 7 680 octets visibles de la page',
                 picture_bytes(got) == picture_bytes(ladder),
                 '%d octets differents' % sum(1 for a, b in
                                              zip(picture_bytes(got), picture_bytes(ladder)) if a != b))
            s.key(ESC)
            s.wait(lambda: s.has('/WORKHD/WORK'), 'le retour aux panneaux', 20); p.stable()
            s.ok('le curseur est reste sur le fichier', s.line(0).startswith('LADDER.P '), s.line(0))

            # 3. L'image double hi-res : le plan auxiliaire d'abord, puis le
            #    principal. C'est l'ordre des plans, et c'est aussi le seul
            #    controle du passage en banque auxiliaire.
            s.select('RUNS.P', 0); p.stable()
            menu_run(s, p, 'PAINT816')
            main = settled(p)
            aux = bytes(p.peek(0x2000, 8192, 'aux'))
            s.ok('double hi-res : le plan auxiliaire',
                 picture_bytes(aux) == picture_bytes(runs),
                 '%d octets differents' % sum(1 for a, b in
                                              zip(picture_bytes(aux), picture_bytes(runs)) if a != b))
            s.ok('double hi-res : le plan principal',
                 picture_bytes(main) == picture_bytes(shifted),
                 '%d octets differents' % sum(1 for a, b in
                                              zip(picture_bytes(main), picture_bytes(shifted)) if a != b))
            s.key(ESC)
            s.wait(lambda: s.has('/RAM rebuilt'), 'la note sur /RAM', 30); p.stable()
            s.ok('dit que /RAM a ete refait', s.rows()[22].strip() == '/RAM rebuilt.', s.rows()[22].strip())
    return ok_all(s, 'paint816')


if __name__ == '__main__':
    sys.exit(main())
