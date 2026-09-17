#!/usr/bin/env python3
"""Banc de la surcouche MACPAINT (src/plugins/macpaint.s) : les documents
MacPaint, 576 x 720 points, montres 192 lignes a la fois en double
haute resolution noir et blanc, avec Haut et Bas pour defiler.

    make all disk && A2FC_IMG=A2FILECMD-full python3 bench/macpaint.py

tools/test_macpaint.py fait tourner le decodeur sous sim65 ; ce banc fait
tourner la surcouche livree, point d'entree compris : les en-tetes (MacPaint
et MacBinary), le passage de verification avant toute ecriture en AUX, les
deux plans relus contre tools/macpaint_ref.py a chaque position du
defilement, les butees, les refus, /RAM refait, et l'ouverture par Retour
(le suffixe .MAC ; un .PNTG passe par le menu). Les images viennent de l'encodeur de
reference, plus ESCHERWATER.MAC des fichiers d'essai de CiderPress II quand
ils sont la (tools/cp2_samples.py)."""
import random
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from xplug import boot_hd, menu_run, ok_all, RET, ESC
import macpaint_ref as ref
import cp2_samples

PORT = 6853
UP, DOWN = b'\x0b', b'\x0a'


def visible(page):
    """Les 7 680 octets des 192 lignes : les trous d'ecran ne sont pas a l'image."""
    return b''.join(page[ref.row_address(y):ref.row_address(y) + 40] for y in range(192))


def settled(p, seconds=120):
    last = None
    for _ in range(int(seconds / 0.5)):
        now = bytes(p.peek(0x2000, 8192)) + bytes(p.peek(0x2000, 8192, 'aux'))
        if now == last:
            return now[:8192], now[8192:]
        last = now
        time.sleep(0.5)
    raise AssertionError('les pages graphiques ne se stabilisent pas')


def shown(p, data, top):
    """La vue a partir de la ligne `top`, relue et comparee."""
    main, aux = settled(p)
    want_aux, want_main = ref.screen(data, top)
    return visible(main) == visible(want_main) and visible(aux) == visible(want_aux)


def main():
    rng = random.Random(11)
    full = ref.pack(ref.random_lines(rng), rng, version=2)
    mbin = ref.pack(ref.random_lines(rng), rng, version=0, macbinary=True, noise=True)
    files = {
        'WORK/FULL.MAC#000000': full,
        'WORK/WRAPPED.PNTG#000000': mbin,    # not a routed suffix: opened from the menu
        'WORK/CUT.MAC#000000': full[:len(full) - 3],
        'WORK/OLDHEAD.MAC#000000': b'\0\0\0\x01' + full[4:],
        'WORK/PLAIN.BIN#062000': bytes(8192),
    }
    real = cp2_samples.volume().get('/GRAPHICS/ESCHERWATER.MAC')
    if real:
        files['WORK/ESCHER.MAC#000000'] = real[2]
    with tempfile.TemporaryDirectory(prefix='a2fc-macpaint-') as tmp:
        with boot_hd(tmp, files, port=PORT, plugins=['macpaint']) as (p, s):
            stack = p.peek(0x80, 2)
            p.poke(s.sym['_a2fc_ops'], b'\x2a\x00')
            s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'volumes')
            s.select('/WORKHD'); s.key(RET)
            s.wait(lambda: s.rows()[0].startswith('/WORKHD '), 'la racine'); p.stable()
            s.select('WORK'); s.key(RET)
            s.wait(lambda: s.has('/WORKHD/WORK'), 'WORK'); p.stable()

            # 1. Les refus : un fichier quelconque, un flux coupe, une
            #    version d'en-tete inconnue -- et AUX (ou vit /RAM) intacte.
            want = 'Not a whole MacPaint picture.'
            aux_before = bytes(p.peek(0x0800, 0xB800, 'aux'))
            for name in ('PLAIN.BIN', 'CUT.MAC', 'OLDHEAD.MAC'):
                s.select(name, 0); p.stable()
                menu_run(s, p, 'MACPAINT')
                s.wait(lambda: s.rows()[22].strip() == want, 'le refus de ' + name, 120)
                p.stable()
                s.ok('refuse %s' % name, s.rows()[22].strip() == want, s.rows()[22].strip())
            s.ok('un refus ne touche pas AUX ($0800-$BFFF)',
                 bytes(p.peek(0x0800, 0xB800, 'aux')) == aux_before)

            # 2. Retour sur un .MAC, puis le defilement jusqu'aux butees.
            s.select('FULL.MAC', 0); p.stable()
            s.key(RET)
            if s.has('ALL /RAM files will be LOST'):
                s.allow_aux()
            s.ok('FULL : Retour ouvre MACPAINT, lignes 0-191', shown(p, full, 0))
            steps = [(DOWN, 96), (DOWN, 192), (DOWN, 288), (DOWN, 384), (DOWN, 480),
                     (DOWN, 528), (DOWN, 528), (UP, 432), (UP, 336)]
            for k, top in steps:
                s.key(k)
                s.ok('FULL : %s, lignes %d-%d' % ('Bas' if k == DOWN else 'Haut', top, top + 191),
                     shown(p, full, top))
            for _ in range(4):
                s.key(UP)
                settled(p)
            s.ok('FULL : Haut jusqu\'a la butee, lignes 0-191', shown(p, full, 0))
            s.key(ESC)
            s.wait(lambda: s.rows()[22].strip() == '/RAM rebuilt.', 'la note sur /RAM', 60)
            p.stable()
            s.ok('FULL : /RAM refait, curseur sur le fichier', s.line(0).startswith('FULL.MAC '),
                 s.line(0))
            s.ok('FULL : resident et pile C preserves',
                 s.value('ops') == 42 and p.peek(0x80, 2) == stack)

            # 3. MacBinary, par le menu : l'en-tete de 128 octets saute.
            s.select('WRAPPED.PNTG', 0); p.stable()
            menu_run(s, p, 'MACPAINT')
            s.ok('WRAPPED : MacBinary, lignes 0-191', shown(p, mbin, 0))
            s.key(DOWN)
            s.ok('WRAPPED : Bas, lignes 96-287', shown(p, mbin, 96))
            s.key(ESC)
            s.wait(lambda: s.has('! More'), 'retour aux panneaux', 60); p.stable()
            s.ok('WRAPPED : curseur sur le fichier', s.line(0).startswith('WRAPPED.PNTG '),
                 s.line(0))

            # 4. Un vrai document (CiderPress II, TestData), s'il est la.
            if real:
                s.select('ESCHER.MAC', 0); p.stable()
                s.key(RET)
                if s.has('ALL /RAM files will be LOST'):
                    s.allow_aux()
                s.ok('ESCHER : lignes 0-191', shown(p, real[2], 0))
                for _ in range(6):
                    s.key(DOWN)
                    settled(p)          # the keyboard holds one key: one redraw at a time
                s.ok('ESCHER : Bas jusqu\'a la butee, lignes 528-719', shown(p, real[2], 528))
                s.key(ESC)
                s.wait(lambda: s.has('! More'), 'retour aux panneaux', 60); p.stable()
    return ok_all(s, 'macpaint')


if __name__ == '__main__':
    sys.exit(main())
