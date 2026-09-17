#!/usr/bin/env python3
"""Banc de UNWRAP (AppleSingle, MacBinary) et de SCIIBIN (BinSCII) : les
fichiers emballes, deballes dans l'autre panneau par les surcouches livrees.

    make all disk && A2FC_IMG=A2FILECMD-full python3 bench/wrappers.py

Les sources sont les exemples de data/CP2/ARCHIVES (CiderPress II : trois
AppleSingle, ShrinkIt en BinSCII, Z-Link en cinq parties) et un MacBinary
synthetique (tools/unwrap_ref.py). Retour ouvre chaque surcouche ; les
resultats vont sur un second disque dur (`hd2`, /WORKWR/OUT), recopie dans
son fichier a l'arret et relu contre les references ; un nom deja pris est
refuse sans rien toucher."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from xplug import boot_hd, menu_run, ok_all, RET, TAB
from diskcopy import volume
from imgconv import catalog
import binscii_ref
import cp2_samples
import unwrap_ref

PORT = 6857
DONE = ('bytes', 'removed', 'exists', 'Not ', 'missing', 'damaged', 'Parts')


def main():
    v = cp2_samples.volume()
    arch = {k.split('/')[-1]: d for k, (t, a, d) in v.items() if k.startswith('/ARCHIVES/')}
    mb = unwrap_ref.make_mb(b'Mac Game', b'p\x06\x08\x00pdos', bytes(range(256)) * 9, b'rsrc')
    files = {'IN/%s#%02X%04X' % (k, v['/ARCHIVES/' + k][0], v['/ARCHIVES/' + k][1]): d
             for k, d in arch.items()}
    files['IN/GAME.BIN#000000'] = mb
    with tempfile.TemporaryDirectory(prefix='a2fc-wrappers-') as tmp:
        tmp = Path(tmp)
        out_hd = volume(tmp, 'out', 'WORKWR', 2000, {'OUT/SHRINKIT': b'already here\r'})
        with boot_hd(tmp, files, port=PORT, blocks=6000,
                     plugins=['unwrap', 'sciibin'], hd2=out_hd) as (p, s):
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

            def run(name, menu=None, seconds=600):
                before = s.rows()[22]
                if s.cursor_row(0) is None:
                    s.key(TAB)
                s.select(name, 0); p.stable()
                if menu:
                    menu_run(s, p, menu)
                else:
                    s.key(RET)
                s.wait(lambda: s.rows()[22] != before and any(m in s.rows()[22] for m in DONE),
                       'la fin de ' + name, seconds)
                p.stable()
                return s.rows()[22].strip()

            open_panel(40, '/WORKWR', 'OUT')
            open_panel(0, '/WORKHD', 'IN')
            expect = {}
            for name in ('HELLO.AS', 'GSHK.HFS.AS', 'MACIP.RES.AS'):
                got = unwrap_ref.unwrap(arch[name], name)
                expect[got[0]] = got
                line = run(name)
                want = '%s: %d bytes, $%02X/$%04X.%s' % (got[0], len(got[3]), got[1], got[2],
                                                         ' Resource fork left out.' if got[4] else '')
                s.ok('UNWRAP %s : %s' % (name, want), line == want, line)
            got = unwrap_ref.unwrap(mb, 'GAME.BIN')
            expect[got[0]] = got
            line = run('GAME.BIN', 'UNWRAP')
            s.ok('UNWRAP GAME.BIN (MacBinary, par le menu)', line.startswith('MAC.GAME: 2304 bytes, $06/$0800.'), line)
            line = run('HELLO.AS')
            s.ok('UNWRAP : un nom deja pris est refuse', line == 'HELLO...... exists or cannot be created.', line)

            line = run('SHRINKIT.BSC')
            s.ok('SCIIBIN : SHRINKIT existe deja, refuse', line == 'SHRINKIT exists or cannot be created.', line)
            line = run('ZLINK.01.BSQ')
            zname, _, zt, za, zdata = binscii_ref.decode([arch['ZLINK.%02d.BSQ' % i] for i in range(1, 6)])
            s.ok('SCIIBIN : Z-Link en cinq parties',
                 line == '%s: %d bytes, $%02X/$%04X, 5 chunks.' % (zname, len(zdata), zt, za), line)
            line = run('ZLINK.02.BSQ', 'SCIIBIN')
            s.ok('SCIIBIN : la deuxieme partie seule est refusee', line == 'Parts out of order or missing', line)

        out = catalog(out_hd, 'OUT')
        for name, (n, t, a, fork, r) in expect.items():
            got = out.get(name)
            s.ok('OUT/%s : les octets et le type' % name,
                 got is not None and got == (t, a, fork), got and got[:2])
        s.ok('OUT/SHRINKIT intact', out.get('SHRINKIT', (0, 0, b''))[2] == b'already here\r')
        s.ok('OUT/%s : le fichier de Z-Link' % zname, out.get(zname) == (zt, za, zdata))
        s.ok('rien d autre', sorted(out) == sorted(list(expect) + ['SHRINKIT', zname]), sorted(out))
    return ok_all(s, 'wrappers')


if __name__ == '__main__':
    sys.exit(main())
