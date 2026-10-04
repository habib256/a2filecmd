#!/usr/bin/env python3
"""Banc de la surcouche NRCLIP (src/plugins/nrclip.s) : les pages d'une
disquette de clip art commerciale de The Newsroom, enregistrees en pages HGR.

    make all disk && A2FC_IMG=A2FILECMD-full python3 bench/nrclip.py

tools/test_nrclip.py fait tourner la surcouche sous sim65, chaque service
simule ; ce banc la fait tourner livree, dans le vrai programme. Le disque
d'amorcage porte la disquette de clip art (/WORKHD/IMG/CLIP.DSK : la vraie
NEWSROOM_CLIPART_S1.dsk de ~/.cache/a2fc/newsroom si elle est la, une de
synthese sinon), ouverte par Retour comme un catalogue DOS 3.3 dans le
panneau de gauche. Les pages vont sur un second disque dur (`--hd2`,
/WORKNR/OUT, qui porte deja un fichier au nom de la premiere page),
recopie dans son fichier a l'arret de POM2 et relu octet a octet contre
tools/newsroom_ref.py. AUX (donc /RAM) doit rester intact. Puis la meme
chose depuis une vraie disquette, lecteur 2 du Disk II (la face 2,
NEWSROOM_CLIPART_S2.dsk, ou une autre de synthese), lue par READ_BLOCK,
vers /WORKNR/OUT2."""
import random
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from xplug import boot_hd, menu_run, ok_all, RET, TAB
from pom2 import ROOT
from imgconv import catalog
import newsroom_ref as ref
from test_nrclip import CORPUS, expected, prodos_name

PORT = 6864


def volume(tmp, tag, name, blocks, files):
    stage = tmp / ('src-' + tag)
    stage.mkdir(parents=True, exist_ok=True)
    for rel, data in files.items():
        (stage / rel).parent.mkdir(parents=True, exist_ok=True)
        (stage / rel).write_bytes(data)
    out = tmp / (tag + '.po')
    subprocess.run([sys.executable, str(ROOT / 'tools/mkvolume.py'), str(stage), str(out),
                    '--volume', name, '--blocks', str(blocks)], check=True, capture_output=True)
    return out


def clip(name, seed):
    real = CORPUS / name
    return real.read_bytes() if real.exists() else ref.make_clip_disk(random.Random(seed), 6, (2, 8))[0]


def main():
    disk = clip('NEWSROOM_CLIPART_S1.dsk', 1984)
    drive = clip('NEWSROOM_CLIPART_S2.dsk', 1985)
    saved2, there2, damaged2 = expected(drive)
    _, _, names = ref.clip_index(disk)
    first = prodos_name(names[0])
    saved, there, damaged = expected(disk, {first: b'keep'})
    with tempfile.TemporaryDirectory(prefix='a2fc-nrclip-') as tmp:
        tmp = Path(tmp)
        out_hd = volume(tmp, 'out', 'WORKNR', 4000, {'OUT/' + first: b'keep', 'OUT2/KEEP': b'keep'})
        floppy = tmp / 'CLIP2.dsk'
        floppy.write_bytes(drive)
        with boot_hd(tmp, {'IMG/CLIP.DSK': disk}, port=PORT, plugins=['nrclip'], hd2=out_hd,
                     floppy2=floppy) as (p, s):
            def open_panel(x, vol, *names):
                if s.cursor_row(x) is None:
                    s.key(TAB)
                s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'volumes')
                s.select(vol, x); s.key(RET)
                s.wait(lambda: s.rows()[0][x:].startswith(vol), vol); p.stable()
                path = vol
                for n in names:
                    s.select(n, x); s.key(RET)
                    path += '/' + n
                    s.wait(lambda: s.rows()[0][x:].startswith(path), path); p.stable()

            open_panel(40, '/WORKNR', 'OUT')
            open_panel(0, '/WORKHD', 'IMG', 'CLIP.DSK')
            s.ok('CLIP.DSK ouverte comme un catalogue DOS 3.3', s.rows()[0].startswith('/WORKHD/IMG/CLIP.DSK'),
                 s.rows()[0][:40])
            aux = bytes(p.peek(0x1000, 0xB000, 'aux'))
            menu_run(s, p, 'NRCLIP')
            want = 'Clip art: %d saved, %d already there, %d damaged.' % (len(saved), there, damaged)
            s.wait(lambda: 'Clip art:' in s.rows()[22] or 'error' in s.rows()[22] or 'failed' in s.rows()[22],
                   'la fin', 1200)
            p.stable()
            s.ok('le message de fin', s.rows()[22].strip() == want, s.rows()[22].strip())
            s.ok('AUX et /RAM intacts', bytes(p.peek(0x1000, 0xB000, 'aux')) == aux)
            top = sorted(set(saved) | {first})[0]
            s.ok('les panneaux relus : ' + top + ' en face',
                 any(r[40:].split()[:1] == [top] for r in s.rows()[2:20]), '|'.join(r[40:60] for r in s.rows()[2:6]))

            # The same from the real floppy in drive 2, read by READ_BLOCK.
            open_panel(40, '/WORKNR', 'OUT2')
            if s.cursor_row(0) is None:
                s.key(TAB)
            s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'volumes'); p.stable()
            for _ in range(15):
                if 'DOS 3.3' in s.line(0):
                    break
                s.key(b'\x0a')
            s.key(RET)
            s.wait(lambda: '/DOS 3.3' in s.rows()[0][:40], 'le catalogue de la disquette', 60); p.stable()
            menu_run(s, p, 'NRCLIP')
            want = 'Clip art: %d saved, %d already there, %d damaged.' % (len(saved2), there2, damaged2)
            s.wait(lambda: 'Clip art:' in s.rows()[22] or 'error' in s.rows()[22] or 'failed' in s.rows()[22],
                   'la fin (disquette)', 3600)
            p.stable()
            s.ok('disquette : le message de fin', s.rows()[22].strip() == want, s.rows()[22].strip())
            s.ok('disquette : AUX et /RAM intacts', bytes(p.peek(0x1000, 0xB000, 'aux')) == aux)
        out = catalog(out_hd, 'OUT')
        s.ok('le fichier deja la est intact', out.get(first, (0, 0, b''))[2] == b'keep')
        s.ok('une page par fichier, rien d autre', set(out) == set(saved) | {first}, sorted(out))
        for name, page in saved.items():
            typ, aux, data = out.get(name, (0, 0, b''))
            s.ok(name + ' : BIN $2000, la page de la reference', (typ, aux, data) == (6, 0x2000, page))
        out = catalog(out_hd, 'OUT2')
        s.ok('disquette : une page par fichier', set(out) == set(saved2) | {'KEEP'}, sorted(out))
        s.ok('disquette : chaque page, BIN $2000, celle de la reference',
             all(out.get(n, (0, 0, b'')) == (6, 0x2000, pg) for n, pg in saved2.items()))
        s.ok('disquette : la disquette n a pas change', floppy.read_bytes() == drive)
    return ok_all(s, 'nrclip')


if __name__ == '__main__':
    sys.exit(main())
