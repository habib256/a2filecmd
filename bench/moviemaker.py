#!/usr/bin/env python3
"""Banc des images de Movie Maker (Interactive Picture Systems, 1984) :
decors .BKG (BIN $4000, une page haute resolution brute) et planches de
formes .SHP (BIN $1DF0, 8 720 octets : 528 octets d'en-tete, puis la page).

    make all disk && A2FC_IMG=A2FILECMD-full python3 bench/moviemaker.py

Ouverts par Retour avec IMAGE : chaque page relue doit etre celle du fichier
(la planche sans son en-tete), Droite passe de l'un a l'autre, AUX intact.
Les vrais fichiers de ~/.cache/a2fc/moviemaker/out servent quand ils sont
la, des pages de synthese sinon. IMAGE demande d'abord l'accord pour AUX
(il peut afficher du double haute resolution) : une page simple n'y touche pas."""
import random
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from xplug import boot_hd, ok_all, RET, ESC

PORT = 6861
RIGHT = b'\x15'
OUT = Path.home() / '.cache/a2fc/moviemaker/out'


def pictures():
    rng = random.Random(1984)
    def real(suffix, size):
        for path in sorted(OUT.glob('*' + suffix + '.bin')):
            data = path.read_bytes()
            if len(data) == size:
                return data
        return bytes(rng.randrange(256) for _ in range(size))
    return {'A.BKG': (0x4000, real('.BKG', 8192)), 'B.SHP': (0x1DF0, real('.SHP', 8720))}


def main():
    pics = pictures()
    files = {'WORK/%s#06%04X' % (n, aux): data for n, (aux, data) in pics.items()}
    with tempfile.TemporaryDirectory(prefix='a2fc-moviemaker-') as tmp:
        with boot_hd(Path(tmp), files, port=PORT) as (p, s):
            s.key(b'/'); s.select('/WORKHD'); s.key(RET); p.stable()
            s.select('WORK'); s.key(RET); p.stable()
            s.select('A.BKG')
            aux = bytes(p.peek(0x1000, 0xB000, 'aux'))
            s.key(RET)
            # IMAGE may show double hi-res, so it would ask first -- but /RAM
            # is empty here, so no question (2026-10-03); a single page then
            # leaves AUX alone all the same.
            s.allow_aux()
            for name in sorted(pics):
                want = pics[name][1][-8192:]
                s.wait(lambda: bytes(p.peek(0x2000, 8192)) == want, name + ' rendered', 60)
                s.ok(name + ' page is the file\'s (after its header)', True)
                s.key(RIGHT)
            s.ok('AUX and /RAM untouched', bytes(p.peek(0x1000, 0xB000, 'aux')) == aux)
            s.key(ESC)
            s.wait(lambda: s.has('Type  Aux'), 'panels restored', 60)
            s.ok('Escape returns to the panels', True)
    return ok_all(s, 'moviemaker')


if __name__ == '__main__':
    sys.exit(main())
