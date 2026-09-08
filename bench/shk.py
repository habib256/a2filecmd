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
banque auxiliaire que le disque /RAM et l'ecraserait.

Regression : voir une image HGR/DHGR avant de decompresser, puis verifier
les deux panneaux AVANT toute navigation (qui pourrait masquer une table
corrompue), la progression et chaque octet des fichiers extraits sur disque."""

import re, shutil, sys, tempfile, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from pom2 import Pom2, Session, ROOT
from run import scratch_volume, RET, TAB, volume
import mkshk
from prodos_read import Image

TEXT = b"SHRINKIT ON THE APPLE II. " * 400        # ~10 Ko, tres compressible
NOTE = b"HELLO FROM A STORED THREAD.\r" * 3
FORMATS = ((3, 'LZW/2 after DHGR', 'OUTA', 'DHGR.RLE'),
           (2, 'LZW/1 after HGR', 'OUTB', 'HGR.RLE'),
           (0, 'stored', 'OUTC', None))


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
        output = tmp / 'output'
        output.mkdir()
        for fmt, _, out, _ in FORMATS:
            (output / out).mkdir()
            mkshk.write_shk(stage / (out + '.SHK'), [
                {'name': 'READ.ME', 'data': TEXT, 'filetype': 0x04, 'auxtype': 0, 'fmt': fmt},
                {'name': 'NOTE', 'data': NOTE, 'filetype': 0x04, 'auxtype': 0, 'fmt': 0}])
        hdv = volume(stage, tmp / 'SCRATCH.hdv', 'SCRATCH', 1600)

        target = volume(output, tmp / 'OUTPUT.po', 'OUTPUT', 280)

        with Pom2(hdv, floppy=floppy, floppy2=target, port=6692, mouse=True) as p:
            s = Session(p)
            s.boot()

            def open_panel(x, *names, vol='SCRATCH'):
                """Amene le panneau qui commence en x sur /vol/<names...>."""
                # rendre ce panneau actif
                other = 40 - x
                if s.cursor_row(x) is None:
                    s.key(TAB)
                s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'volumes')
                if s.cursor_row(x) is None:
                    s.key(TAB)
                s.select('/' + vol, x); s.key(RET)
                s.wait(lambda: s.rows()[0][x:].startswith('/' + vol), 'scratch')
                p.stable()
                for n in names:
                    s.select(n, x); s.key(RET)
                    s.wait(lambda: ('/' + vol + '/' + n) in s.rows()[0][x:], 'dossier ' + n)
                    p.stable()

            for fmt, label, out, picture in FORMATS:
                open_panel(40, out, vol='OUTPUT')                          # panneau droit : la cible
                if picture:
                    open_panel(0, 'DEMO')
                    s.select(picture, 0); s.key(RET)
                    s.wait(lambda: s.value('view', 1) == 1, 'image ' + picture)
                    p.stable()
                    s.key(b'\x1b')
                    s.wait(lambda: s.value('view', 1) == 0, 'retour image')
                    p.stable()
                open_panel(0)                                # panneau gauche : /SCRATCH, l'archive
                s.select(out + '.SHK', 0); p.stable()
                source_rows = [r[:38] for r in s.rows()[2:20]]
                s.key(b'!'); s.wait(lambda: s.has('the overlays'), 'menu', 30); p.stable()
                s.key(b'U'); p.stable(); s.key(RET, pause=0)
                progress = []
                deadline = time.time() + 60
                while time.time() < deadline:
                    rows = s.rows()
                    line = rows[22]
                    if re.match(r'\s*\d+/\d+\s+\S+\s+\[', line):
                        progress.append(line)
                    if any(word in line for word in ('extracted', 'failed', 'Corrupt', 'Unsupported')):
                        break
                    time.sleep(0.01)
                p.stable()
                ok(label + ' : progression initialisee sur deux fichiers',
                   bool(progress) and all(re.match(r'\s*[12]/2\s', line) for line in progress),
                   progress[-1].strip() if progress else 'aucune progression observee')
                ok(label + ' : octets avances pendant le premier fichier',
                   any((m := re.search(r'\]\s+(\d+)/(\d+)', line))
                       and 0 < int(m[1]) < int(m[2]) for line in progress))
                ok('UNSHRINK %s : deux fichiers extraits' % label,
                   s.has('2 file(s) extracted'), s.rows()[22].strip()[:45])
                ok(label + ' : panneau source intact avant toute navigation',
                   [r[:38] for r in s.rows()[2:20]] == source_rows)
                ok(label + ' : panneau cible relu avant toute navigation',
                   all(any(r[40:].startswith(name + ' ') for r in s.rows()[2:20])
                       for name in ('NOTE', 'READ.ME')))
                # verifier READ.ME dans la cible : taille puis contenu
                open_panel(0, out, vol='OUTPUT')
                s.select('READ.ME', 0); p.stable()
                ok('%s : READ.ME fait la bonne taille (%d)' % (label, len(TEXT)),
                   str(len(TEXT)) in s.line(0), s.line(0).rstrip()[:42])
                s.key(RET); s.wait(lambda: s.value('view', 1) == 2, 'texte ' + label, 20); p.stable()
                ok('%s : le contenu extrait est correct' % label,
                   s.has('SHRINKIT ON THE APPLE II'), ''.join(s.rows()[2:3]).strip()[:34])
                s.key(b'\x1b'); s.wait(lambda: s.value('view', 1) == 0, 'retour'); p.stable()

        # Le lecteur 2 est une disquette avec write-back (le disque dur du
        # banc reste en memoire). Relire APRES l'arret et le flush de POM2.
        # La premiere page du viewer seule ne prouve pas une extraction correcte.
        img = Image(target.read_bytes())
        dirs = {e[1:1 + (e[0] & 15)].decode(): e for e in img.entries(2)}
        for _, label, out, _ in FORMATS:
            files = {e[1:1 + (e[0] & 15)].decode(): e
                     for e in img.entries(int.from_bytes(dirs[out][0x11:0x13], 'little'))}
            for name, expected in (('READ.ME', TEXT), ('NOTE', NOTE)):
                e = files.get(name)
                ok(label + ' : ' + name + ' identique octet par octet',
                   e is not None and img.read(e) == expected)

    passed = sum(1 for c in checks if c)
    print(f'\n{passed}/{len(checks)} controles', flush=True)
    return 0 if passed == len(checks) else 1


if __name__ == '__main__':
    sys.exit(main())
