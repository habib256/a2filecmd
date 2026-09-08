#!/usr/bin/env python3
"""Banc UNSHRINK : une archive ShrinkIt (.SHK) extraite vers un dossier ProDOS.

    make disk && POM2=/chemin/vers/pom2_playtest python3 bench/shk.py

tools/mkshk.py fabrique trois archives -- stockee, LZW/1, LZW/2 -- portant le
meme fichier tres compressible plus un fil stocke, verifie contre nulib2. Le
banc les pose sur /SCRATCH, boot A2FC, ouvre chaque archive par le menu ! (la
surcouche A2FILE/UNSHRINK.PLG) vers un dossier a elle, puis relit le fichier
extrait et compare sa taille et son contenu a l'original. C'est la preuve du
decodeur LZW en banque auxiliaire (coeur assembleur src/unshrink.s, recopie
en AUX). La cible n'est jamais /RAM : le dictionnaire LZW occupe la meme
banque auxiliaire que le disque /RAM et l'ecraserait."""

import shutil, sys, tempfile, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from pom2 import Pom2, Session, ROOT
from run import scratch_volume, RET, TAB, volume
import mkshk

TEXT = b"SHRINKIT ON THE APPLE II. " * 400        # ~10 Ko, tres compressible
NOTE = b"HELLO FROM A STORED THREAD.\r" * 3
FORMATS = ((3, 'LZW/2', 'OUTA'), (2, 'LZW/1', 'OUTB'), (0, 'stored', 'OUTC'))


def main():
    checks = []
    def ok(label, cond, detail=''):
        checks.append(bool(cond))
        print(('PASS ' if cond else 'FAIL ') + label + (' ' + str(detail) if detail else ''), flush=True)

    with tempfile.TemporaryDirectory(prefix='a2fc-shk-') as tmp:
        tmp = Path(tmp)
        floppy = tmp / 'A2FILECMD.po'
        shutil.copyfile(ROOT / 'dist/A2FILECMD.po', floppy)
        hdv = scratch_volume(tmp)
        stage = tmp / 'scratch'
        for fmt, _, out in FORMATS:
            (stage / out).mkdir()
            mkshk.write_shk(stage / (out + '.SHK'), [
                {'name': 'READ.ME', 'data': TEXT, 'filetype': 0x04, 'auxtype': 0, 'fmt': fmt},
                {'name': 'NOTE', 'data': NOTE, 'filetype': 0x04, 'auxtype': 0, 'fmt': 0}])
        hdv = volume(stage, tmp / 'SCRATCH.hdv', 'SCRATCH', 1600)

        with Pom2(hdv, floppy=floppy, port=6692, mouse=True) as p:
            s = Session(p)
            s.boot()

            def open_panel(x, *names):
                """Amene le panneau qui commence en x sur /SCRATCH/<names...>."""
                # rendre ce panneau actif
                other = 40 - x
                if s.cursor_row(x) is None:
                    s.key(TAB)
                s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'volumes')
                if s.cursor_row(x) is None:
                    s.key(TAB)
                s.select('/SCRATCH', x); s.key(RET)
                s.wait(lambda: s.rows()[0][x:x + 8] == '/SCRATCH', 'scratch')
                p.stable()
                for n in names:
                    s.select(n, x); s.key(RET)
                    s.wait(lambda: ('/SCRATCH/' + n) in s.rows()[0][x:], 'dossier ' + n)
                    p.stable()

            for fmt, label, out in FORMATS:
                open_panel(40, out)                          # panneau droit : la cible
                open_panel(0)                                # panneau gauche : /SCRATCH, l'archive
                s.select(out + '.SHK', 0); p.stable()
                s.key(b'!'); s.wait(lambda: s.has('the overlays'), 'menu', 30); p.stable()
                s.key(b'U'); p.stable(); s.key(RET)
                s.wait(lambda: s.has('extracted') or s.has('failed') or s.has('Corrupt')
                       or s.has('Unsupported'), 'extraction ' + label, 60); p.stable()
                ok('UNSHRINK %s : deux fichiers extraits' % label,
                   s.has('2 file(s) extracted'), s.rows()[22].strip()[:45])
                # verifier READ.ME dans la cible : taille puis contenu
                open_panel(0, out)
                s.select('READ.ME', 0); p.stable()
                ok('%s : READ.ME fait la bonne taille (%d)' % (label, len(TEXT)),
                   str(len(TEXT)) in s.line(0), s.line(0).rstrip()[:42])
                s.key(RET); s.wait(lambda: s.value('view', 1) == 2, 'texte ' + label, 20); p.stable()
                ok('%s : le contenu extrait est correct' % label,
                   s.has('SHRINKIT ON THE APPLE II'), ''.join(s.rows()[2:3]).strip()[:34])
                s.key(b'\x1b'); s.wait(lambda: s.value('view', 1) == 0, 'retour'); p.stable()

    passed = sum(1 for c in checks if c)
    print(f'\n{passed}/{len(checks)} controles', flush=True)
    return 0 if passed == len(checks) else 1


if __name__ == '__main__':
    sys.exit(main())
