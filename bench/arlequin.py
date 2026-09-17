#!/usr/bin/env python3
"""Banc de la surcouche ARLEQUIN (src/plugins/arlequin.c) : les images $F8
d'ARLEQUIN 1.1 (Le Chat Mauve, 1985), montrees dans le mode MIXTE de la
carte, sur une Feline (`pom2_playtest --chatmauve feline`).

    make all disk && A2FC_IMG=A2FILECMD-full python3 bench/arlequin.py

tools/test_arlequin.py fait tourner le decodeur 6502 sous sim65 ; ce banc
fait tourner la surcouche livree : le passage de verification avant toute
ecriture en AUX, les deux plans relus octet par octet contre
tools/arlequin_ref.py, une fenetre centree sur du noir, les refus, /RAM
refait, et l'ouverture par Retour (le tri des fichiers du resident). Les
images viennent de l'encodeur de reference ; si le disque d'exemples est la
(A2FC_SAMPLE_DISK, /GISTDATA), AIGLE et FE1 du constructeur s'y ajoutent,
sur le disque jetable du banc."""
import os
import random
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from xplug import boot_hd, menu_run, ok_all, RET, ESC
import arlequin_ref as ref

PORT = 6852


def visible(page):
    """Les 7 680 octets des 192 lignes : les trous d'ecran ne sont pas a l'image."""
    return b''.join(page[ref.row_address(y):ref.row_address(y) + 40] for y in range(192))


def settled(p, seconds=90):
    last = None
    for _ in range(int(seconds / 0.4)):
        now = bytes(p.peek(0x2000, 8192)) + bytes(p.peek(0x2000, 8192, 'aux'))
        if now == last:
            return now[:8192], now[8192:]
        last = now
        time.sleep(0.4)
    raise AssertionError('les pages graphiques ne se stabilisent pas')


def samples():
    """AIGLE et FE1 du disque d'exemples, s'il est la."""
    disk = Path(os.environ.get('A2FC_SAMPLE_DISK', str(Path.home() / 'src/pom2/hdv/GISTDATA.hdv')))
    if not disk.exists():
        return {}
    from prodos_read import Image
    img = Image(disk.read_bytes())
    out = {}

    def find(key, name):
        for e in img.entries(key):
            if e[1:1 + (e[0] & 15)].decode() == name:
                return e

    try:
        d = find(int.from_bytes(find(2, 'IMG')[0x11:0x13], 'little'), 'PURPLE')
        key = int.from_bytes(d[0x11:0x13], 'little')
        for name in ('AIGLE', 'FE1'):
            out[name] = img.read(find(key, name))
    except (TypeError, AttributeError):
        return {}
    return out


def main():
    rng = random.Random(4)
    full = ref.encode(20, ref.random_rows(20, 192, rng), rng)
    window = ref.encode(9, ref.random_rows(9, 81, rng), rng)
    files = {
        'WORK/FULL#F80385': full,
        'WORK/WINDOW#F80000': window,
        'WORK/CUT#F80385': full[:len(full) * 3 // 4],
        'WORK/NOTGS#F80000': b'\x14\xc0xx' + full[4:],
        'WORK/PLAIN.BIN#062000': bytes(8192),
    }
    real = samples()
    for name, data in real.items():
        files['WORK/%s#F80385' % name] = data
    pictures = [('FULL', full), ('WINDOW', window)] + sorted(real.items())
    with tempfile.TemporaryDirectory(prefix='a2fc-arlequin-') as tmp:
        with boot_hd(tmp, files, port=PORT, plugins=['arlequin'], chatmauve='feline') as (p, s):
            stack = p.peek(0x80, 2)
            p.poke(s.sym['_a2fc_ops'], b'\x2a\x00')
            s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'volumes')
            s.select('/WORKHD'); s.key(RET)
            s.wait(lambda: s.rows()[0].startswith('/WORKHD '), 'la racine'); p.stable()
            s.select('WORK'); s.key(RET)
            s.wait(lambda: s.has('/WORKHD/WORK'), 'WORK'); p.stable()

            # 1. Les refus : ni $F8, ni signature, ni flux entier -- et AUX
            #    (ou vit /RAM) intacte apres chacun.
            aux_before = bytes(p.peek(0x0800, 0xB800, 'aux'))
            for name, want in (('PLAIN.BIN', 'Not an Arlequin $F8 picture.'),
                               ('NOTGS', 'Not an Arlequin $F8 picture.'),
                               ('CUT', 'Picture truncated.')):
                s.select(name, 0); p.stable()
                menu_run(s, p, 'ARLEQUIN')
                s.wait(lambda: s.rows()[22].strip() == want, 'le refus de ' + name, 60)
                p.stable()
                s.ok('refuse %s : %s' % (name, want), s.rows()[22].strip() == want,
                     s.rows()[22].strip())
            s.ok('un refus ne touche pas AUX ($0800-$BFFF)',
                 bytes(p.peek(0x0800, 0xB800, 'aux')) == aux_before)

            # 2. Chaque image : les deux plans, relus contre la reference.
            for name, data in pictures:
                want_aux, want_main = ref.screen(data)
                s.select(name, 0); p.stable()
                menu_run(s, p, 'ARLEQUIN')
                got_main, got_aux = settled(p)
                windowed = (data[0], data[1]) != (20, 192)
                if windowed:          # le noir autour est ecrit : tout compte
                    s.ok('%s : le plan principal, noir compris' % name, got_main == want_main)
                    s.ok('%s : le plan auxiliaire, noir compris' % name, got_aux == want_aux)
                else:
                    s.ok('%s : le plan principal' % name, visible(got_main) == visible(want_main))
                    s.ok('%s : le plan auxiliaire' % name, visible(got_aux) == visible(want_aux))
                s.key(ESC)
                s.wait(lambda: s.rows()[22].strip() == '/RAM rebuilt.', 'la note sur /RAM', 60)
                p.stable()
                s.ok('%s : /RAM refait, curseur sur le fichier' % name,
                     s.line(0).startswith(name + ' '), s.line(0))
                s.ok('%s : resident et pile C preserves' % name,
                     s.value('ops') == 42 and p.peek(0x80, 2) == stack)

            # 3. Retour ouvre une image $F8 signee (le tri du resident).
            s.select('WINDOW', 0); p.stable()
            s.key(RET)
            if s.has('ALL /RAM files will be LOST'):
                s.allow_aux()
            got_main, got_aux = settled(p)
            want_aux, want_main = ref.screen(window)
            s.ok('Retour ouvre ARLEQUIN', got_main == want_main and got_aux == want_aux)
            s.key(ESC)
            s.wait(lambda: s.has('! More'), 'retour aux panneaux', 60); p.stable()
    return ok_all(s, 'arlequin')


if __name__ == '__main__':
    sys.exit(main())
