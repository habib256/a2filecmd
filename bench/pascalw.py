#!/usr/bin/env python3
"""Banc de PASCALW : des fichiers ProDOS ecrits dans un volume Apple Pascal.

    make all disk && python3 bench/pascalw.py

Le volume d'essai est fabrique par tools/pascal_ref.py et pose sur le disque
dur du banc dans /WORKHD/IMG. Le panneau gauche s'ouvre dessus, curseur sur
l'image ; le droit sur /WORKHD/IN, ou sont les fichiers a y mettre. C'est la
disposition du lecteur, a l'envers.

A l'arret, le disque dur est relu sur l'hote, l'image en est extraite et lue
par la meme reference : chaque fichier doit y porter ses octets exacts, son
genre UCSD doit etre l'inverse de celui que le lecteur donne, le fichier qui
y etait ne doit pas avoir bouge, et les plages de blocs ne doivent pas se
chevaucher -- un volume UCSD n'a pas de bitmap pour le rattraper."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from xplug import boot_hd, menu_run, ok_all, RET
from imgconv import catalog
import pascal_ref

PORT = 6915
DONE = ('put,', 'No room', 'directory is full', 'Not an Apple Pascal',
        'Other panel', 'Select a disk image', 'Cannot', 'Image changed')
WAS_THERE = ('ALREADY', 5, b'this one was in the volume\r' * 20)
PUT = {'HELLO': (0x03, b'hello, pascal\r' * 40),
       'CODE': (0x02, bytes(range(256)) * 4),
       'PLAIN': (0x04, b'a ProDOS text file\r' * 30)}


def main():
    volume = pascal_ref.make('MYVOL', [WAS_THERE])
    files = {'IMG/VOL.PO#060000': volume}
    for name, (type_, data) in PUT.items():
        files['IN/%s#%02X0000' % (name, type_)] = data

    with tempfile.TemporaryDirectory(prefix='a2fc-pascalw-') as tmp:
        tmp = Path(tmp)
        with boot_hd(tmp, files, port=PORT, blocks=4000, plugins=['pascalw']) as (p, s):
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
                """L'image sous le curseur a gauche, PASCALW, puis la reponse.

                Ctrl-R efface la ligne 22 : deux passages disent la meme
                chose, et attendre que le message CHANGE attendrait pour
                rien."""
                if s.cursor_row(0) is None:
                    s.key(b'\t')
                s.key(b'\x12')
                s.wait(lambda: not s.rows()[22].strip(), 'la ligne de message vide', 60)
                s.select('VOL.PO', 0); p.stable()
                menu_run(s, p, 'PASCALW')
                q = 'Put the files opposite into VOL.PO?'
                s.wait(lambda: s.has(q) or s.rows()[22].strip(),
                       'la question de PASCALW ou son refus', 90)
                asked = s.has(q)
                if asked:
                    s.key(answer)
                    if answer != b'N':
                        s.wait(lambda: any(m in s.rows()[22] for m in DONE),
                               'la fin de PASCALW', 300)
                p.stable()
                return asked, s.rows()[22].strip()

            open_panel(40, 'IN')
            open_panel(0, 'IMG')

            # 1. La question declinee n'ecrit rien.
            asked, line = run(b'N')
            s.ok('PASCALW pose sa question avant d ecrire', asked, line)
            s.ok('un refus ne change pas le volume',
                 catalog(Path(p.hdv), 'IMG')['VOL.PO'][2] == volume)

            # 2. Les trois fichiers entrent.
            asked, line = run(b'Y')
            s.ok('les trois fichiers sont mis dans le volume',
                 line == '3 put, 0 skipped (name taken or empty).', line)

            # 3. Un second passage : les trois noms sont pris.
            asked, line = run(b'Y')
            s.ok('au second passage les noms sont pris, rien n est ecrase',
                 line == '0 put, 3 skipped (name taken or empty).', line)

        raw = catalog(Path(p.hdv), 'IMG')['VOL.PO'][2]
        v = pascal_ref.volume(raw)
        s.ok('le volume se relit toujours', v is not None)
        got = {f['name']: f for f in v['files']}
        s.ok('les quatre fichiers sont la',
             sorted(got) == ['ALREADY', 'CODE', 'HELLO', 'PLAIN'], sorted(got))
        s.ok('le fichier qui y etait est intact',
             pascal_ref.contents(raw, got['ALREADY']) == WAS_THERE[2])
        for name, (type_, data) in PUT.items():
            s.ok('%s porte ses octets exacts' % name,
                 pascal_ref.contents(raw, got[name]) == data,
                 (len(pascal_ref.contents(raw, got[name])), len(data)))
        s.ok('les genres UCSD sont l inverse de ceux du lecteur',
             (got['HELLO']['kind'], got['CODE']['kind'], got['PLAIN']['kind']) == (3, 2, 0),
             (got['HELLO']['kind'], got['CODE']['kind'], got['PLAIN']['kind']))
        runs = sorted((f['first'], f['last']) for f in v['files'])
        s.ok('aucune plage de blocs n en chevauche une autre',
             all(l <= f for (_, l), (f, _) in zip(runs, runs[1:])), runs)
        s.ok('les sources ne sont pas touchees',
             catalog(Path(p.hdv), 'IN')['HELLO'][2] == PUT['HELLO'][1])
    return ok_all(s, 'pascalw')


if __name__ == '__main__':
    sys.exit(main())
