#!/usr/bin/env python3
"""Banc de UNSQ (SQueeze .QQ, archives ACU) et du listing Business BASIC.

    make all disk && A2FC_IMG=A2FILECMD-full python3 bench/squeeze.py

UNSQ, lance par le menu, extrait dans l'autre panneau, un second disque dur
(`hd2`, /WORKWR/OUT) relu a l'arret contre tools/squeeze_ref.py : un .QQ et
une archive ACU synthetiques, le .QQ de l'archive Binary II de CiderPress II
et IconEd.ACU quand ils sont dans le cache, un nom deja pris, un .QQ abime
(rien d'ecrit). Puis T sur un programme BA3 ($09) : l'ecran doit etre le
listing de tools/busbasic_ref.py, ligne a ligne ; TIMESET (exemple Apple,
cache local seulement) aussi quand il est la."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from xplug import boot_hd, menu_run, ok_all, RET, ESC, TAB
from diskcopy import volume
from imgconv import catalog
from test_intbasic import wrapped
from test_unsq import bqy_members
import busbasic_ref
import cp2_samples
import squeeze_ref as ref

PORT = 6859
DONE = ('extracted', 'Not ', 'Damaged', 'Other panel', 'Cleanup')


def main():
    text = b'SQueezed on the Apple II, the same line again.\r' * 60
    files = {
        'IN/NOTES.QQ#040000': ref.squeeze(text, b'NOTES.TXT'),
        'IN/BROKEN.QQ#040000': ref.squeeze(text, b'BROKEN')[:-20],
        'IN/PACK.ACU#E08001': ref.make_acu([
            (b'DOCS', 0x0F, 0, b'', False, True),
            (b'DOCS/README', 4, 0, b'hello from ACU\r' * 40, True, False),
            (b'Raw Data', 6, 0x2000, bytes(range(256)) * 3, False, False),
            (b'TAKEN', 4, 0, b'new\r', False, False)]),
    }
    expect = {}
    for n, sq in (('NOTES.QQ', True), ('PACK.ACU', False)):
        for name, t, a, body in ref.unsqueeze(files['IN/%s#%s' % (n, '040000' if sq else 'E08001')], n):
            if name != 'TAKEN':
                expect[name] = (4 if t is None else t, 0 if a is None else a, body)
    real = []
    bqy = cp2_samples.path('bny/SAMPLE.BQY')
    if bqy:
        qq = bqy_members(bqy.read_bytes())['SQUEEZE/BNYARCHIVE.H.QQ']
        files['IN/BNYARCH.H.QQ#040000'] = qq
        real.append(('BNYARCH.H.QQ', ref.unsqueeze(qq, 'BNYARCH.H.QQ')))
    acu = cp2_samples.path('acu/IconEd.ACU')
    if acu:
        files['IN/ICONED.ACU#E08001'] = acu.read_bytes()
        real.append(('ICONED.ACU', ref.unsqueeze(acu.read_bytes(), 'ICONED.ACU')))
    for _, got in real:
        for name, t, a, body in got:
            expect[name] = (4 if t is None else t, 0 if a is None else a, body)

    program = busbasic_ref.make([(10, b'\xc0 BUSINESS BASIC'), (20, b'\xd9"TOTAL";\xff\x9d1)'),
                                 (30, b'\x8a\xfe'), (40, b'\xc0 ' + b'X' * 90)])
    files['BB/LEDGER#090000'] = program
    timeset = cp2_samples.volume().get('/CODE/TIMESET')
    if timeset:
        files['BB/TIMESET#%02X%04X' % timeset[:2]] = timeset[2]

    with tempfile.TemporaryDirectory(prefix='a2fc-squeeze-') as tmp:
        tmp = Path(tmp)
        out_hd = volume(tmp, 'out', 'WORKWR', 2000, {'OUT/TAKEN': b'old\r'})
        with boot_hd(tmp, files, port=PORT, blocks=6000, hd2=out_hd) as (p, s):
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

            def run(name):
                before = s.rows()[22]
                if s.cursor_row(0) is None:
                    s.key(TAB)
                s.select(name, 0); p.stable()
                menu_run(s, p, 'UNSQ')
                s.wait(lambda: s.rows()[22] != before and any(m in s.rows()[22] for m in DONE),
                       'la fin de ' + name, 600)
                p.stable()
                return s.rows()[22].strip()

            open_panel(40, '/WORKWR', 'OUT')
            open_panel(0, '/WORKHD', 'IN')
            line = run('NOTES.QQ')
            s.ok('UNSQ NOTES.QQ', line == '1 extracted, 0 skipped (name taken).', line)
            line = run('PACK.ACU')
            s.ok('UNSQ PACK.ACU : dossier saute, TAKEN refuse',
                 line == '2 extracted, 1 skipped (name taken).', line)
            line = run('BROKEN.QQ')
            s.ok('UNSQ BROKEN.QQ : abime, rien de garde',
                 line == '0 extracted, 0 skipped (name taken); damaged, stopped.', line)
            for name, got in real:
                line = run(name)
                s.ok('UNSQ %s (CiderPress II)' % name,
                     line == '%d extracted, 0 skipped (name taken).' % len(got), line)

            # Business BASIC par T
            s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'volumes')
            s.select('/WORKHD', 0); s.key(RET)
            s.wait(lambda: s.rows()[0].startswith('/WORKHD '), 'la racine'); p.stable()
            s.select('BB', 0); s.key(RET)
            s.wait(lambda: s.rows()[0].startswith('/WORKHD/BB'), 'BB'); p.stable()
            progs = [('LEDGER', program)] + ([('TIMESET', timeset[2])] if timeset else [])
            for name, data in progs:
                s.select(name, 0); p.stable()
                s.key(b'T')
                s.wait(lambda: s.value('view', 1) == 2, 'BASLIST ' + name, 30)
                s.wait(lambda: s.rows()[23].startswith('/WORKHD/BB/' + name), 'la barre', 30)
                p.stable()
                lines, end = busbasic_ref.listing(data)
                want = wrapped(lines)[:22]
                rows = [r.rstrip() for r in s.rows()[:22]][:len(want)]
                s.ok('BASLIST %s : le listing de reference' % name, rows == want,
                     '\n'.join('  attendu %r\n  obtenu  %r' % (w, g) for w, g in zip(want, rows) if w != g))
                if len(wrapped(lines)) <= 22:
                    s.ok('BASLIST %s : la fin est dite' % name, ' (end)' in s.rows()[23][:52], s.rows()[23])
                s.key(ESC)
                s.wait(lambda: s.has('Type  Aux'), 'retour aux panneaux', 30); p.stable()

        out = catalog(out_hd, 'OUT')
        for name, want in expect.items():
            s.ok('OUT/%s : octets et type' % name, out.get(name) == want, out.get(name, (None,))[:2])
        s.ok('OUT/TAKEN intact', out.get('TAKEN', (0, 0, b''))[2] == b'old\r')
        s.ok('rien d autre', sorted(out) == sorted(list(expect) + ['TAKEN']), sorted(out))
    return ok_all(s, 'squeeze')


if __name__ == '__main__':
    sys.exit(main())
