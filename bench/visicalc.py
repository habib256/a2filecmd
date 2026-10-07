#!/usr/bin/env python3
"""Banc de la surcouche VISICALC (src/plugins/visicalc.s) : feuilles VisiCalc
(/SS) recalculees et montrees comme VisiCalc les montre.

    make all disk && A2FC_IMG=A2FILECMD-full python3 bench/visicalc.py
    make ARCH=6502 all disk && A2FC_BUILD=build-6502 A2FC_IMG=A2FILECMD-full \\
        A2FC_PRESET=iie_unenh python3 bench/visicalc.py

tools/test_visicalc.py fait tourner la surcouche sous sim65 ; ce banc fait
tourner celle qui est livree, ouverte par Retour sur un texte qui commence
par `>` : chaque ecran (lignes 0 a 21) est compare a celui que calcule
tools/visicalc_ref.py, apres des touches (fleches, Espace, B, >, <, R), puis
Echap rend les panneaux. Les feuilles sont ecrites ici (celle de DEMO, une
feuille large rangee par colonnes avec ses ERROR de reference en avant, une
racine carree et des puissances sur la ROM) ; un texte qui commence par `>`
sans etre une feuille est refuse avec une note qui renvoie a T. Les feuilles
de ~/.cache/a2fc/visicalc/samples sont ajoutees quand elles sont la (elles ne
sont pas publiees).

Echap pendant le recalcul : une feuille dont le recalcul dure une heure et
demie (120 formules de treize @NPV sur 120 cellules), ouverte, puis Echap
des que la cellule d'activite tourne -- « Stopped. », les panneaux, le
dossier toujours la (la touche est consommee : elle ne remonte pas au
dossier parent) ; la meme avec la table en memoire auxiliaire, « Stopped.
/RAM rebuilt. » et /RAM relisible ; et une autre touche tapee pendant le
calcul, qui attend la feuille."""
import os
import re
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'bench'))
sys.path.insert(0, str(ROOT / 'tools'))
from xplug import boot_hd, ok_all, RET, ESC
from pom2 import BUILD
import mkdemo_viewers
import mkdos33
import visicalc_ref as ref

PORT = 6941
HI = lambda t: bytes(c | 0x80 for c in t)
PRIVATE = Path(os.environ.get('A2FC_VISICALC', Path.home() / '.cache/a2fc/visicalc/samples'))


def wide():
    """Twelve columns of 40 rows, column by column: totals at the left read
    the columns on their right before they are recalculated (ERROR)."""
    cells = {}
    for c in range(1, 12):
        for r in range(1, 41):
            cells[(c, r)] = '%d' % (c * 100 + r) if r % 3 else '+%s%d*2' % (ref.col_name(c), r - 1)
    for r in range(1, 41):
        cells[(0, r)] = '@SUM(B%d...L%d)' % (r, r)
    lines = ['>%s%d:%s' % (ref.col_name(c), r, v) for (c, r), v in
             sorted(cells.items(), key=lambda kv: (-kv[0][1], -kv[0][0]))]
    return '\r'.join(lines + ['/W1', '/GOC', '/GRA', '/GC7', '/X>A1:>A1:']).encode() + b'\r'


ROM = ('>A6:@LN(1)\r>A5:@SQRT(2)\r>A4:2^10\r>A3:9^.5\r>A2:@SQRT(16)\r>A1:/FI@SQRT(1E4)\r'
       '/W1\r/GOC\r/GRA\r/GC12\r/X>A1:>A1:\r').encode()


def sheets():
    out = {'BUDGET': mkdemo_viewers.visicalc(), 'WIDE': HI(wide()), 'ROM': ROM}
    if PRIVATE.is_dir():
        for name in ('HO121', 'HO128', 'HO253', 'V13716', 'VCDSK01', 'VCDSK03'):
            p = PRIVATE / (name + '.txt')
            if p.exists():
                out['P' + name] = HI(p.read_text().replace('\n', '\r').encode('latin-1'))
    return out


def slow(n, k):
    """n numbers and n formulas of k @NPV over them: with 120 and 13, an hour
    and a half of recalculation at 1 MHz (tools/test_visicalc.py)."""
    lines = ['>B%d:%s' % (r, '+'.join(['@NPV(.1,A1...A%d)' % n] * k)) for r in range(n, 0, -1)]
    lines += ['>A%d:%d' % (r, r) for r in range(n, 0, -1)]
    lines.sort(key=lambda l: -int(re.match(r'>[AB](\d+)', l)[1]))      # VisiCalc's order: rows down
    return '\r'.join(lines + ['/W1', '/GOC', '/GRA', '/GC9', '/X>A1:>A1:']).encode() + b'\r'


def main_room():
    """The values the main bank holds: $4000 - the BSS's end, 8 bytes each
    (the note said 2,047 before, from column A's count)."""
    m = re.search(r'^BSS\s+([0-9A-F]+)\s+[0-9A-F]+\s+([0-9A-F]+)', (BUILD / 'visicalc.map').read_text(), re.M)
    return (0x4000 - int(m[1], 16) - int(m[2], 16)) // 8


def expected(data, keys):
    sh = ref.load(bytes(b & 0x7F for b in data).decode('latin-1'))
    v = ref.View(sh)
    shots = [v.screen()[0]]
    for k in keys:
        v.key(k)
        shots.append(v.screen()[0])
    return shots


def main():
    files = {'WORK/%s#040000' % n: d for n, d in sheets().items()}
    files['WORK/QUOTE#040000'] = b'> a quoted line\rnot a worksheet\r'
    files['WORK/SLOW#040000'] = slow(120, 13)
    files['WORK/SLOWAUX#040000'] = slow(150, 13)
    files['WORK/AHEAD#040000'] = slow(30, 1)
    # The way from a DOS 3.3 disk: C extracts the T file, Return opens it.
    files['WORK/VCDISK.DSK#000000'] = mkdos33.build([('VCSHEET', 0x00, mkdemo_viewers.visicalc() + b'\0')])
    keys = {'BUDGET': '', 'WIDE': '\x15\x15\x15\x15\x15\x15\x15\x15\x15\x15 \x0a\x0bB>R<',
            'ROM': '', 'PHO121': ' ', 'PHO128': '>', 'PHO253': '  ', 'PV13716': '', 'PVCDSK01': '>',
            'PVCDSK03': '\x15'}
    with tempfile.TemporaryDirectory(prefix='a2fc-visicalc-') as tmp:
        with boot_hd(Path(tmp), files, port=PORT, plugins=['visicalc']) as (p, s):
            s.key(b'/'); s.select('/WORKHD'); s.key(RET); p.stable()
            s.select('WORK'); s.key(RET); p.stable()
            # Refused: /RAM holds a file, the sheet needs the auxiliary
            # bank, N -- nothing written there, /RAM's directory intact.
            s.ram_occupied(1)
            s.select('WIDE'); s.key(RET)
            s.wait(lambda: s.has('ALL /RAM files will be LOST'), 'the AUX warning', 120)
            s.key(b'N')
            s.wait(lambda: s.has('Sheet too big'), 'the refusal', 60)
            s.ok('refused: the sheet too big for MAIN, said so', s.has('room for %d.' % main_room()))
            s.ok('refused: /RAM untouched', s.ram_files() == 1)
            s.ram_occupied(0)
            p.stable()
            for name, data in sheets().items():
                s.select(name); s.key(RET)
                big = len(ref.load(bytes(b & 0x7F for b in data).decode('latin-1')).cells) > 200
                if big:
                    s.allow_aux()           # /RAM empty: no question (checked)
                want = expected(data, keys.get(name, ''))
                s.wait(lambda: '<> Cols' in s.rows()[23], 'the sheet of ' + name, 300)
                p.stable()
                for i, k in enumerate(keys.get(name, '') + '\x00'):
                    got = s.rows()[:22]
                    bad = [r for r in range(22) if got[r].rstrip() != want[i][r].rstrip()]
                    if bad:
                        print('\n'.join('%2d sim %r\n   ref %r' % (r, got[r], want[i][r]) for r in bad[:4]))
                    s.ok('%s screen %d as the reference' % (name, i), not bad)
                    if k != '\x00':
                        s.key(k.encode('latin-1'))
                        p.stable()
                s.key(ESC); s.wait(lambda: s.has('Type  Aux'), 'panels restored', 60); p.stable()
                if name == 'WIDE':
                    s.ok('WIDE used the auxiliary bank: /RAM rebuilt, said so', s.has('/RAM rebuilt'))
                    s.ok('/RAM empty again, readable', s.ram_files() == 0)
            # Escape while the sheet is computed. The activity cell (row
            # 21, column 79) turning says the overlay is at work.
            spin = lambda: s.rows()[21][79] in '/\\'
            s.select('SLOW'); s.key(RET)
            s.wait(spin, 'the slow sheet being read', 120)
            time.sleep(1.5)                 # reading still, or recalculating: either stops
            s.ok('the slow sheet is still being computed', spin() and '<> Cols' not in s.rows()[23])
            s.key(ESC)
            s.wait(lambda: s.has('Stopped.'), 'Escape stops the recalculation', 60)
            s.wait(lambda: s.has('Type  Aux'), 'panels restored', 60); p.stable()
            s.ok('Escape stopped it: the panels, the note', s.has('Stopped.') and not s.has('/RAM rebuilt'))
            s.ok('Escape was taken: still in the folder', s.has('SLOWAUX') and s.has('BUDGET'))
            s.select('SLOWAUX'); s.key(RET)
            s.allow_aux()                   # /RAM empty: no question (checked)
            s.wait(spin, 'the larger slow sheet being read', 120)
            time.sleep(4)                   # the table is in the auxiliary bank
            s.ok('the larger sheet is still being computed', spin() and '<> Cols' not in s.rows()[23])
            s.key(ESC)
            s.wait(lambda: s.has('Stopped. /RAM rebuilt.'), 'Escape with the table in AUX', 60)
            s.wait(lambda: s.has('Type  Aux'), 'panels restored', 60); p.stable()
            s.ok('Escape with the table in AUX: /RAM rebuilt, said so', s.has('Stopped. /RAM rebuilt.'))
            s.ok('/RAM empty again, readable, still in the folder', s.ram_files() == 0 and s.has('SLOWAUX'))
            # A Y typed while the sheet is read, before the /RAM question
            # exists, must not answer it (bug hunt 2: it did, and /RAM's
            # files were lost unasked). The question shows and waits.
            s.ram_occupied(1)
            s.select('SLOWAUX'); s.key(RET)
            s.wait(spin, 'the larger sheet being read again', 120)
            s.key(b'Y')
            s.wait(lambda: s.has('ALL /RAM files will be LOST'), 'the AUX question after a Y typed ahead', 120)
            time.sleep(3)
            s.ok('a Y typed ahead does not answer the /RAM question',
                 s.has('ALL /RAM files will be LOST') and s.ram_files() == 1)
            s.key(b'N')
            s.wait(lambda: s.has('Sheet too big'), 'the refusal after the question', 60)
            s.wait(lambda: s.has('Type  Aux'), 'panels restored', 60); p.stable()
            s.ok('refused after the type-ahead: /RAM untouched', s.ram_files() == 1)
            s.ram_occupied(0)
            # Another key typed meanwhile is not read there: it waits for
            # the sheet, whose first screen it pages.
            data = files['WORK/AHEAD#040000']
            s.select('AHEAD'); s.key(RET)
            s.wait(spin, 'the third sheet being read', 120)
            s.key(b' ')
            s.wait(lambda: '<> Cols' in s.rows()[23], 'the sheet typed ahead of', 600)
            p.stable()
            got, want = s.rows()[:22], expected(data, ' ')[1][:22]
            s.ok('a Space typed during the recalculation pages the sheet once',
                 [r.rstrip() for r in got] == [r.rstrip() for r in want])
            s.key(ESC); s.wait(lambda: s.has('Type  Aux'), 'panels restored', 60); p.stable()
            s.select('QUOTE'); s.key(RET)
            s.wait(lambda: s.has('Not a VisiCalc worksheet'), 'refusal of a quoted text', 60)
            s.ok('a text starting with > is refused, T suggested', s.has('T shows it as text'))
            p.stable()
            s.select('BUDGET')
            s.ok('the panels answer after the ROM was used', s.has('BUDGET'))
            # DOS 3.3: the other panel on WORK, the image opened, C, Return
            s.key(b'\t'); s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'volumes')
            s.select('/WORKHD', 40); s.key(RET); p.stable()
            s.select('WORK', 40); s.key(RET); p.stable()
            s.key(b'\t'); p.stable()
            s.select('VCDISK.DSK'); s.key(RET); p.stable()
            s.select('VCSHEET'); s.key(b'C')
            s.wait(lambda: 'extracted' in s.rows()[22], 'the extraction', 300)
            p.stable()
            s.key(b'\t'); s.select('VCSHEET', 40); s.key(RET)
            s.wait(lambda: '<> Cols' in s.rows()[23], 'the extracted sheet', 300)
            p.stable()
            s.ok('a worksheet extracted from DOS 3.3 opens with Return',
                 [r.rstrip() for r in s.rows()[:22]] ==
                 [r.rstrip() for r in expected(mkdemo_viewers.visicalc(), '')[0][:22]])
            s.key(ESC); s.wait(lambda: s.has('Type  Aux'), 'panels restored', 60)
    return ok_all(s, 'visicalc')


if __name__ == '__main__':
    sys.exit(main())
