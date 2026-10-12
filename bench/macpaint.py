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
(.MAC/.PNTG ou en-tête MacBinary PNTG). Les images viennent de l'encodeur de
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


def import_checks(p,s,short,volume,floor):
    for name in ('MBBIN','MBPAGE','RAW.PNTG'):
        for key in (RET,b'I'):
            s.select(name);s.ram_occupied();aux=p.peek(0x1000,0xB000,'aux');s.key(key)
            s.wait(lambda:s.has('ALL /RAM files will be LOST'),name+' consent',60)
            s.ok(name+' waits before AUX '+repr(key),p.peek(0x1000,0xB000,'aux')==aux)
            s.key(b'N');p.stable();s.ok(name+' refusal preserves AUX '+repr(key),p.peek(0x1000,0xB000,'aux')==aux)
            s.select(name);s.key(key);s.allow_aux()
            s.wait(lambda:shown(p,short,0),name+' first pixels',120)
            s.ok(name+' automatic MacPaint pixels '+repr(key),True)
            s.key(DOWN);s.ok(name+' scrolled pixels '+repr(key),shown(p,short,96))
            s.key(ESC);s.wait(lambda:s.has('Type  Aux'),name+' exit',60)
            s.ok(name+' RAM rebuilt empty '+repr(key),s.ram_files()==0)
    # A complete container can still contain a malformed PackBits body.
    for key in (RET,b'I'):
        s.select('BADMB');aux=p.peek(0x1000,0xB000,'aux');s.key(key)
        s.wait(lambda:s.has('Not a whole MacPaint picture.'),'malformed import refused',120)
        s.ok('Malformed MacBinary import refused '+repr(key),True)
        s.ok('Malformed MacBinary preserves AUX '+repr(key),p.peek(0x1000,0xB000,'aux')==aux)
    s.ok('Import stack floor preserved',p.peek(floor,8)==b'\xa5'*8)
    p.sync_disks();s.ok('Whole import source volume preserved',Path(p.hdv).read_bytes()==volume)


def album_checks(p,s,first,second,volume,floor):
    s.select('NEXT.PNTG');s.ram_occupied();aux=p.peek(0x1000,0xB000,'aux');s.key(RET)
    s.wait(lambda:s.has('ALL /RAM files will be LOST'),'PNTG album consent',60)
    s.ok('PNTG album waits before AUX',p.peek(0x1000,0xB000,'aux')==aux)
    s.key(b'N');p.stable();s.ok('PNTG album refusal preserves AUX',p.peek(0x1000,0xB000,'aux')==aux)
    s.select('NEXT.PNTG');s.key(RET);s.allow_aux()
    s.wait(lambda:shown(p,first,0),'PNTG album first',120);s.ok('PNTG album first pixels',True)
    s.key(b'\x15');s.wait(lambda:shown(p,second,0),'PNTG album next',120);s.ok('PNTG album right pixels',True)
    s.key(b'\x08');s.wait(lambda:shown(p,first,0),'PNTG album previous',120);s.ok('PNTG album left pixels',True)
    s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'PNTG album exit',60)
    s.ok('PNTG album rebuilds empty RAM',s.ram_files()==0)
    s.ok('PNTG album stack floor preserved',p.peek(floor,8)==b'\xa5'*8)
    p.sync_disks();s.ok('Whole PNTG album volume preserved',Path(p.hdv).read_bytes()==volume)


def navigation_checks(p,s,data,volume,floor):
    s.select('NAV.MAC');s.ram_occupied();aux=p.peek(0x0800,0xB800,'aux');s.key(RET)
    s.wait(lambda:s.has('ALL /RAM files will be LOST'),'navigation RAM consent',60)
    s.ok('Navigation waits before AUX',p.peek(0x0800,0xB800,'aux')==aux)
    s.key(b'N');p.stable();s.ok('Navigation refusal preserves RAM',p.peek(0x0800,0xB800,'aux')==aux)
    s.select('NAV.MAC');s.key(RET);s.allow_aux()
    for key,top,label in ((None,0,'initial'),(b'+',48,'fine down'),(b'-',0,'fine up'),(b'-',0,'fine up at top'),
                          (b'B',528,'bottom'),(b'+',528,'fine down at bottom'),(b'-',480,'fine up from bottom'),
                          (b'+',528,'fine down to bottom'),(DOWN,528,'down at bottom'),
                          (UP,432,'up after bottom'),(b'T',0,'top'),(UP,0,'up at top'),
                          (DOWN,96,'down after top'),(b'b',528,'lowercase bottom'),
                          (b'B',528,'bottom again'),(b't',0,'lowercase top'),(b'+',48,'fine down after top'),
                          (DOWN,144,'coarse after fine')):
        if key:s.key(key)
        s.wait(lambda:shown(p,data,top),label+' pixels',120)
        s.ok('MacPaint '+label+' pixels',True)
    s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'navigation exit',60)
    s.ok('Navigation rebuilds empty RAM',s.ram_files()==0)
    s.ok('Navigation stack floor preserved',p.peek(floor,8)==b'\xa5'*8)
    p.sync_disks();s.ok('Whole navigation volume preserved',Path(p.hdv).read_bytes()==volume)


def main():
    rng = random.Random(11)
    full = ref.pack(ref.random_lines(rng), rng, version=2)
    mbin = ref.pack(ref.random_lines(rng), rng, version=0, macbinary=True, noise=True)
    short=ref.pack([bytes([0x55 if (y//48)%2 else 0xAA])*72 for y in range(720)],macbinary=True)
    reverse=ref.pack([bytes([0xAA if (y//48)%2 else 0x55])*72 for y in range(720)])
    files = {
        'WORK/FULL.MAC#000000': full,
        'WORK/WRAPPED.PNTG#000000': mbin,
        'WORK/MBBIN#060000':short,
        'WORK/MBPAGE#062000':short+bytes(8192-len(short)),
        'WORK/RAW.PNTG#000000':short[128:],
        'WORK/BADMB#060000':short[:640]+b'\xFF\0'+short[642:],
        'WORK/CUT.MAC#000000': full[:len(full) - 3],
        'WORK/OLDHEAD.MAC#000000': b'\0\0\0\x01' + full[4:],
        'WORK/PLAIN.BIN#062000': bytes(8192),
    }
    real = cp2_samples.volume().get('/GRAPHICS/ESCHERWATER.MAC')
    if real:
        files['WORK/ESCHER.MAC#000000'] = real[2]
    if '--album-only' in sys.argv:
        files={'WORK/NEXT.PNTG#000000':reverse,'WORK/RAW.PNTG#000000':short[128:]}
    if '--navigation-only' in sys.argv:
        nav=ref.pack([bytes([((y//48)*17+y%13)&255])*72 for y in range(720)])
        files={'WORK/NAV.MAC#000000':nav}
    with tempfile.TemporaryDirectory(prefix='a2fc-macpaint-') as tmp:
        with boot_hd(tmp, files, port=PORT, plugins=['macpaint'],speed=4000000) as (p, s):
            stack = p.peek(0x80, 2)
            p.poke(s.sym['_a2fc_ops'], b'\x2a\x00')
            s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'volumes')
            s.select('/WORKHD'); s.key(RET)
            s.wait(lambda: s.rows()[0].startswith('/WORKHD '), 'la racine'); p.stable()
            s.select('WORK'); s.key(RET)
            s.wait(lambda: s.has('/WORKHD/WORK'), 'WORK'); p.stable()
            if '--imports-only' in sys.argv or '--album-only' in sys.argv or '--navigation-only' in sys.argv:
                volume=Path(p.hdv).read_bytes();floor=s.sym['__HIMEM__']-s.sym['__STACKSIZE__'];p.poke(floor,b'\xa5'*8)
                if '--navigation-only' in sys.argv:
                    navigation_checks(p,s,nav,volume,floor)
                    return ok_all(s,'macpaint navigation')
                if '--album-only' in sys.argv:
                    album_checks(p,s,reverse,short,volume,floor)
                    return ok_all(s,'macpaint album')
                import_checks(p,s,short,volume,floor)
                return ok_all(s,'macpaint imports')

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
