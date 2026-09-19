#!/usr/bin/env python3
"""Banc de PASCAL et de CPM : deux systemes de fichiers etrangers lus dans
une image et extraits dans un dossier ProDOS.

    make all disk && python3 bench/foreignfs.py

Les deux images d'essai sont fabriquees par les references de l'hote,
tools/pascal_ref.py et tools/cpm_ref.py, et posees sur le disque dur du banc
dans /WORKHD/IMG. Le panneau gauche s'ouvre dessus, le droit sur
/WORKHD/OUT, et chaque surcouche est lancee depuis le menu. A l'arret, le
disque dur est relu sur l'hote : chaque fichier extrait doit porter
exactement les octets que la reference lit dans la meme image, et l'image
elle-meme ne doit pas avoir bouge d'un octet -- ces deux lecteurs n'ecrivent
jamais dedans.

Le disque CP/M est ecrit dans l'ordre de secteurs `apple` sans que la
surcouche le sache : elle essaie ses tables candidates et garde celle dont
le repertoire s'explique. C'est le seul controle du banc qui porte sur ce
choix-la ; les autres ordres sont couverts par tools/test_cpm.py."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from xplug import boot_hd, menu_run, ok_all, RET
from imgconv import catalog
import pascal_ref
import cpm_ref

PORT = 6911
DONE = ('extracted', 'Not ', 'Other panel', 'Select a disk')

PASCAL_FILES = [('HELLO.TEXT', 3, bytes(1024) + b'Hello, Pascal.\r'.ljust(1024, b'\0')),
                ('SYSTEM.APPLE', 2, bytes(range(256)) * 20),
                ('SHORT', 5, b'x' * 300)]
CPM_FILES = [('HELLO.TXT', b'Hello, CP/M.\r\n' * 10),
             ('BIG.DAT', bytes(range(256)) * 90),
             ('TINY.COM', b'\xc9')]


def main():
    pascal = pascal_ref.make('MYVOL', PASCAL_FILES)
    cpm = cpm_ref.make(CPM_FILES, skew='apple')
    files = {'IMG/PASCAL.PO#060000': pascal, 'IMG/CPM.PO#060000': cpm,
             'OUT/KEEP.TXT#040000': b'untouched\r'}

    with tempfile.TemporaryDirectory(prefix='a2fc-foreignfs-') as tmp:
        tmp = Path(tmp)
        with boot_hd(tmp, files, port=PORT, blocks=4000,
                     plugins=['pascal', 'cpm']) as (p, s):
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

            def run(name, overlay):
                if s.cursor_row(0) is None:
                    s.key(b'\t')
                # Ctrl-R relit les deux panneaux et efface la ligne 22 : les
                # deux extractions disent la meme chose, et attendre que le
                # message CHANGE aurait attendu pour rien.
                s.key(b'\x12')
                s.wait(lambda: not s.rows()[22].strip(), 'la ligne de message vide', 60)
                s.select(name, 0); p.stable()
                menu_run(s, p, overlay)
                s.wait(lambda: any(m in s.rows()[22] for m in DONE),
                       'la fin de ' + name, 600)
                p.stable()
                return s.rows()[22].strip()

            open_panel(40, 'OUT')
            open_panel(0, 'IMG')

            line = run('PASCAL.PO', 'PASCAL')
            s.ok('PASCAL extrait le volume UCSD',
                 line == '3 extracted, 0 skipped (name taken).', line)
            line = run('CPM.PO', 'CPM')
            s.ok('CPM trouve l ordre des secteurs et extrait',
                 line == '3 extracted, 0 skipped (name taken).', line)
            # Un nom deja pris est saute, pas ecrase.
            line = run('PASCAL.PO', 'PASCAL')
            s.ok('les trois noms sont pris au second passage',
                 line == '0 extracted, 3 skipped (name taken).', line)

        out = catalog(Path(p.hdv), 'OUT')
        img = catalog(Path(p.hdv), 'IMG')
        s.ok('les images ne sont pas touchees',
             img['PASCAL.PO'][2] == pascal and img['CPM.PO'][2] == cpm)
        s.ok('le fichier deja la est intact', out['KEEP.TXT'][2] == b'untouched\r')

        v = pascal_ref.volume(pascal)
        for entry in v['files']:
            name = entry['name'].replace('-', '.')
            want = pascal_ref.contents(pascal, entry)
            s.ok('Pascal %s : octets exacts' % name,
                 out.get(name, (0, 0, b''))[2] == want,
                 (len(out.get(name, (0, 0, b''))[2]), len(want)))
        s.ok('Pascal : le type ProDOS de chaque genre',
             out['HELLO.TEXT'][0] == 0x03 and out['SYSTEM.APPLE'][0] == 0x02
             and out['SHORT'][0] == 0x05,
             (out['HELLO.TEXT'][0], out['SYSTEM.APPLE'][0], out['SHORT'][0]))

        c = cpm_ref.volume(cpm)
        s.ok('CP/M : la reference lit la meme image', c is not None and c['skew'] == 'apple')
        for entry in c['files']:
            want = cpm_ref.contents(cpm, entry, c['skew'])
            s.ok('CP/M %s : octets exacts' % entry['name'],
                 out.get(entry['name'], (0, 0, b''))[2] == want,
                 (len(out.get(entry['name'], (0, 0, b''))[2]), len(want)))
        s.ok('rien d autre dans OUT',
             sorted(out) == sorted(['KEEP.TXT'] + [f['name'].replace('-', '.') for f in v['files']]
                                   + [f['name'] for f in c['files']]), sorted(out))
    return ok_all(s, 'foreignfs')


if __name__ == '__main__':
    sys.exit(main())
