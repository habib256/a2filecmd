#!/usr/bin/env python3
"""Banc de la surcouche NEWSROOM (src/plugins/newsroom.s) : photos PH.* et
bannieres BN.* de The Newsroom, BIN $4000, centrees en haute resolution.

    make all disk && A2FC_IMG=A2FILECMD-full python3 bench/newsroom.py

tools/test_newsroom.py fait tourner la surcouche sous sim65 ; ce banc la fait
tourner livree, ouverte par Retour (le nom et le type) : chaque page relue
contre tools/newsroom_ref.py, AUX (donc /RAM) intact, Droite vers la photo
voisine, Echap vers les panneaux, et le refus d'un fichier abime (son $FF
final efface). Les vrais
fichiers de ~/.cache/a2fc/newsroom servent quand ils sont la (PH.CATS a un
$FF dans son historique), des images de synthese sinon."""
import random
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from xplug import boot_hd, ok_all, RET, ESC
import newsroom_ref as ref
from test_newsroom import corpus

PORT = 6860
RIGHT = b'\x15'


def pictures():
    rng = random.Random(1984)
    real = {name: body for _disk, name, body in corpus()}
    out = {}
    for name in ('BN.LUMBER', 'PH.CATS', 'PH.MAP'):
        out[name] = real.get(name) or ref.make(rng)
    out['PH.ZMAX'] = ref.make(rng, 37, 192, x1=0, y1=0)
    return out


def settled(p, seconds=60):
    last = None
    for _ in range(int(seconds / 0.5)):
        now = bytes(p.peek(0x2000, 8192))
        if now == last:
            return now
        last = now
        time.sleep(0.5)
    raise AssertionError('la page ne se stabilise pas')


def main():
    pics = pictures()
    bad = bytearray(pics['PH.CATS'])
    bad[len(bad) - (bad[0] | bad[1] << 8) - 1] = 0      # the $FF before the bitmap
    files = {'WORK/%s#064000' % n: b for n, b in pics.items()}
    files['WORK/PH.ZZBAD#064000'] = bytes(bad)
    with tempfile.TemporaryDirectory(prefix='a2fc-newsroom-') as tmp:
        with boot_hd(Path(tmp), files, port=PORT, plugins=['newsroom']) as (p, s):
            s.key(b'/'); s.select('/WORKHD'); s.key(RET); p.stable()
            s.select('WORK'); s.key(RET); p.stable()
            s.select('BN.LUMBER')
            aux = bytes(p.peek(0x1000, 0xB000, 'aux'))
            s.key(RET)
            for i, name in enumerate(sorted(pics)):
                want = ref.page(pics[name])
                s.wait(lambda: bytes(p.peek(0x2000, 8192)) == want, name + ' rendered', 60)
                s.ok(name + ' page matches the reference', settled(p) == want)
                if i + 1 < len(pics):
                    s.key(RIGHT)
            s.ok('AUX and /RAM untouched', bytes(p.peek(0x1000, 0xB000, 'aux')) == aux)
            s.key(ESC)
            s.wait(lambda: s.has('Type  Aux'), 'panels restored', 60); p.stable()
            s.select('PH.ZZBAD'); s.key(RET)
            s.wait(lambda: s.has('Not a whole Newsroom picture'), 'refusal message', 60)
            s.ok('malformed file refused with its message', True)
    return ok_all(s, 'newsroom')


if __name__ == '__main__':
    sys.exit(main())
