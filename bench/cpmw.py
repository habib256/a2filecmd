#!/usr/bin/env python3
"""Banc de CPMW : des fichiers ProDOS ecrits dans un volume CP/M Apple II.

    make all disk && python3 bench/cpmw.py

Le volume d'essai est fabrique par tools/cpm_ref.py dans l'ordre de secteurs
`apple`, pose sur le disque dur du banc dans /WORKHD/IMG. Le panneau gauche
s'ouvre dessus, curseur sur l'image ; le droit sur /WORKHD/IN. C'est la
disposition du lecteur, a l'envers -- et l'ordre des secteurs n'est pas dit
a la surcouche : elle le retrouve ou elle refuse d'ecrire.

A l'arret, l'image est extraite du disque dur et relue par la meme
reference. Le controle qui compte ici : un secteur CP/M est la MOITIE d'un
bloc ProDOS, donc chaque ecriture est une lecture-modification-ecriture, et
le fichier voisin qui partage le bloc doit etre intact."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from xplug import boot_hd, menu_run, ok_all, RET
from imgconv import catalog
import cpm_ref

PORT = 6916
DONE = ('put,', 'No room', 'Not a CP/M', 'Disk image here', 'Cannot',
        'Image changed', 'Write failed', 'Entry not written')
WAS_THERE = [('KEEP.TXT', b'this one was in the volume\r\n' * 30),
             ('OTHER.COM', bytes(range(256)) * 3)]
PUT = {'HELLO.TXT': b'hello, CP/M\r\n' * 40,
       'TINY.COM': b'\xc9' * 300,
       'DATA.BIN': bytes(range(256)) * 6}


def main():
    volume = cpm_ref.make(WAS_THERE, skew='apple')
    files = {'IMG/VOL.PO#060000': volume}
    for name, data in PUT.items():
        files['IN/%s#060000' % name] = data

    with tempfile.TemporaryDirectory(prefix='a2fc-cpmw-') as tmp:
        tmp = Path(tmp)
        with boot_hd(tmp, files, port=PORT, blocks=4000, plugins=['cpmw']) as (p, s):
            def open_panel(x, *names):
                if s.cursor_row(x) is None:
                    s.key(b'\t')
                s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'volumes')
                s.select('/WORKHD', x); s.key(RET)
                s.wait(lambda: s.rows()[0][x:].startswith('/WORKHD'), 'racine'); p.stable()
                path = '/WORKHD'
                for n in names:
                    s.select(n, x); s.key(RET)
                    path += '/' + n
                    s.wait(lambda: s.rows()[0][x:].startswith(path), path); p.stable()

            def run(answer):
                if s.cursor_row(0) is None:
                    s.key(b'\t')
                # Ctrl-R efface la ligne 22 : deux passages disent la meme
                # chose, et attendre qu'elle CHANGE attendrait pour rien.
                s.key(b'\x12')
                s.wait(lambda: not s.rows()[22].strip(), 'la ligne de message vide', 60)
                s.select('VOL.PO', 0); p.stable()
                menu_run(s, p, 'CPMW')
                q = 'Put the files opposite into VOL.PO?'
                s.wait(lambda: s.has(q) or s.rows()[22].strip(),
                       'la question de CPMW ou son refus', 90)
                asked = s.has(q)
                if asked:
                    s.key(answer)
                    if answer != b'N':
                        s.wait(lambda: any(m in s.rows()[22] for m in DONE),
                               'la fin de CPMW', 300)
                p.stable()
                return asked, s.rows()[22].strip()

            open_panel(40, 'IN')
            open_panel(0, 'IMG')

            asked, line = run(b'N')
            s.ok('CPMW pose sa question avant d ecrire', asked, line)
            s.ok('un refus ne change pas le volume',
                 catalog(Path(p.hdv), 'IMG')['VOL.PO'][2] == volume)

            asked, line = run(b'Y')
            s.ok('les trois fichiers sont mis dans le volume',
                 line == '3 put, 0 skipped (name taken or unusable).', line)

            asked, line = run(b'Y')
            s.ok('au second passage les noms sont pris, rien n est ecrase',
                 line == '0 put, 3 skipped (name taken or unusable).', line)

        raw = catalog(Path(p.hdv), 'IMG')['VOL.PO'][2]
        v = cpm_ref.volume(raw)
        s.ok('le volume se relit toujours', v is not None)
        s.ok('l ordre des secteurs est celui du disque',
             v['skew'] == 'apple', v['skew'])
        got = {f['name']: f for f in v['files']}
        s.ok('les cinq fichiers sont la',
             sorted(got) == ['DATA.BIN', 'HELLO.TXT', 'KEEP.TXT', 'OTHER.COM', 'TINY.COM'],
             sorted(got))
        for name, data in PUT.items():
            body = cpm_ref.contents(raw, got[name], v['skew'])
            s.ok('%s porte ses octets exacts' % name, body[:len(data)] == data,
                 (len(body), len(data)))
            s.ok('%s est complete avec l octet de fin CP/M' % name,
                 set(body[len(data):]) <= {0x1A}, sorted(set(body[len(data):]))[:4])
        for name, data in WAS_THERE:
            s.ok('%s, qui partage des blocs ProDOS, est intact' % name,
                 cpm_ref.contents(raw, got[name], v['skew'])[:len(data)] == data)
        seen = set()
        shared = False
        for f in v['files']:
            for b in f['blocks']:
                if b in seen:
                    shared = True
                seen.add(b)
        s.ok('aucun bloc n est reclame par deux fichiers', not shared)
        s.ok('les sources ne sont pas touchees',
             catalog(Path(p.hdv), 'IN')['HELLO.TXT'][2] == PUT['HELLO.TXT'])
    return ok_all(s, 'cpmw')


if __name__ == '__main__':
    sys.exit(main())
