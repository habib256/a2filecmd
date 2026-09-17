#!/usr/bin/env python3
"""Banc de la surcouche SHAPES (src/plugins/shapes.s) : les shape tables
Applesoft, 24 formes par page sur l'ecran haute resolution.

    make all disk && A2FC_IMG=A2FILECMD-full python3 bench/shapes.py

tools/test_shapes.py fait tourner la surcouche entiere sous sim65 ; ce banc
la fait tourner sous POM2 avec les trois tables de data/CP2 (CiderPress II)
et une table synthetique : chaque page HGR relue et comparee octet a octet
a tools/shapes_ref.py, la ligne d'etat du mode mixte, Espace et B, un
fichier refuse, Echap et le retour aux panneaux, /RAM intact."""
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from xplug import boot_hd, menu_run, ok_all, RET, ESC
import cp2_samples
import shapes_ref as ref

PORT = 6858


def settled(p, seconds=60):
    last = None
    for _ in range(int(seconds / 0.4)):
        now = bytes(p.peek(0x2000, 8192))
        if now == last:
            return now
        last = now
        time.sleep(0.4)
    raise AssertionError('la page ne se stabilise pas')


def main():
    v = cp2_samples.volume()
    tables = {k.split('/')[-1]: d for k, (t, a, d) in v.items() if k.startswith('/GRAPHICS/SHAPETABLE/')}
    boxes = ref.make([[0x12, 0x3F, 0x20, 0x64, 0x2D, 0x15, 0x36, 0x1E, 0x07]] * 30)
    files = {'WORK/%s#060000' % n: d for n, d in tables.items()}
    files['WORK/BOXES.SHAPE#060000'] = boxes
    files['WORK/EMPTY#060000'] = b'\x00\x00\x02\x00'
    with tempfile.TemporaryDirectory(prefix='a2fc-shapes-') as tmp:
        with boot_hd(tmp, files, port=PORT, plugins=['shapes']) as (p, s):
            stack = p.peek(0x80, 2)
            p.poke(s.sym['_a2fc_ops'], b'\x2a\x00')
            aux = bytes(p.peek(0x0800, 0xB800, 'aux'))
            s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'volumes')
            s.select('/WORKHD'); s.key(RET)
            s.wait(lambda: s.rows()[0].startswith('/WORKHD '), 'la racine'); p.stable()
            s.select('WORK'); s.key(RET)
            s.wait(lambda: s.has('/WORKHD/WORK'), 'WORK'); p.stable()

            s.select('EMPTY', 0); p.stable()
            menu_run(s, p, 'SHAPES')
            s.wait(lambda: 'Not a shape table.' in s.rows()[22], 'le refus', 30); p.stable()
            s.ok('EMPTY : refuse', s.rows()[22].strip() == 'Not a shape table.', s.rows()[22])

            # Retour sur un .SHAPE, puis la page 2 et le retour a la page 1.
            s.select('BOXES.SHAPE', 0); p.stable()
            s.key(RET)
            for first, key in ((1, None), (25, b' '), (25, b' '), (1, b'B')):
                if key:
                    s.key(key)
                page = settled(p)
                time.sleep(0.5)
                s.ok('BOXES : page %d' % first, page == ref.page(boxes, first))
                s.ok('BOXES : etat %d' % first, s.rows()[21].strip() == ref.status(boxes, first),
                     s.rows()[21])
            s.key(ESC)
            s.wait(lambda: s.has('! More'), 'retour aux panneaux', 30); p.stable()
            s.ok('BOXES : curseur sur le fichier', s.line(0).startswith('BOXES.SHAPE '), s.line(0))

            # Les vraies tables, par le menu, toutes leurs pages.
            for name, data in sorted(tables.items()):
                s.select(name, 0); p.stable()
                menu_run(s, p, 'SHAPES')
                n = ref.shape_count(data)
                bad = []
                for i, first in enumerate(range(1, n + 1, 24)):
                    if i:
                        s.key(b' ')
                    page = settled(p)
                    time.sleep(0.3)
                    if page != ref.page(data, first) or s.rows()[21].strip() != ref.status(data, first):
                        bad.append(first)
                s.ok('%s : %d formes, toutes les pages' % (name, n), not bad, bad)
                s.key(ESC)
                s.wait(lambda: s.has('! More'), 'retour aux panneaux', 30); p.stable()
            s.ok('resident et pile C preserves', s.value('ops') == 42 and p.peek(0x80, 2) == stack)
            s.ok('/RAM intact (AUX $0800-$BFFF)', bytes(p.peek(0x0800, 0xB800, 'aux')) == aux)
    return ok_all(s, 'shapes')


if __name__ == '__main__':
    sys.exit(main())
