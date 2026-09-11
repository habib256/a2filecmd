#!/usr/bin/env python3
"""Banc de la surcouche TXTCONV (src/plugins/txtconv.c) : fins de ligne
CR/LF/CRLF, bit haut, tabulations, accents UTF-8, vers l'autre panneau ou
sur place.

    make build-6502/txtconv.PLG ARCH=6502 && python3 bench/txtconv.py

Les sources sont sur le disque dur du banc (/WORKHD/WORK : LF, CRLF) et le
panneau droit sur une disquette en lecteur 2 (/WORKPO/WORK/OUT, vide) --
le disque dur reste en memoire dans POM2, la disquette est ecrite dans son
.po a l'arret, et c'est elle que l'on relit sur l'hote pour verifier les
octets, le type et l'auxtype produits. Les conversions sur place (bit haut,
accents, tabulations) se font sur des fichiers de la disquette, pour la
meme raison. CRLF a une paire CR LF a cheval sur les octets 255-256 et
511-512 : la limite des morceaux de 256 octets que lit la surcouche."""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from xplug import boot_hd, menu_run, ok_all, RET, TAB, ESC
from pom2 import ROOT
from prodos_read import Image

PORT = 6801

LF = b''.join(b'line %02d\twith a tab and caf\xc3\xa9\n' % i for i in range(30)) + b'\tfin \xc3\x89t\xc3\xa9\n'
CRLF = b'A' * 255 + b'\r\n' + b'B' * 254 + b'\r\n' + b'tail\r\nlone\rline\nend\r\n'
HI = bytes(b | 0x80 for b in b'HELLO WORLD\rSECOND LINE\r')
ACC = b'caf\xc3\xa9 \xc3\x80 \xc3\xa7a \xc3\x9f \xc3\xbf \xe2\x82\xac \xc2\xa0end\n'
ACC_OUT = b'cafe A ca s y ? ?end\n'
TABS = b'a\tb\n\tx\nabcdefgh\ty\n\t\tz\n'
BROKEN = b'A' * 255 + b'\xc3Z / \xe2X / \xf0\x9f'
BROKEN_OUT = b'A' * 255 + b'?Z / ?X / ?'

HD_FILES = {'WORK/LF.TXT': LF, 'WORK/CRLF#040123': CRLF}
RECOVERY = b'previous conversion to recover\r'
PO_FILES = {'WORK/HI.TXT': HI, 'WORK/ACC.TXT': ACC, 'WORK/TABS.TXT': TABS,
            'WORK/BROKEN.TXT': BROKEN,
            'WORK/COLLIDE/TXTCONV.TMP#040000': RECOVERY,
            'WORK/COLLIDE/KEEP#040000': b'keep this source\r'}


def to_cr(data):
    return data.replace(b'\r\n', b'\r').replace(b'\n', b'\r')


def to_lf(data):
    return data.replace(b'\r\n', b'\n').replace(b'\r', b'\n')


def tabs(data):
    out, col = bytearray(), 0
    for b in data:
        if b == 9:
            out += b' ' * (8 - col % 8); col = 0
        else:
            out.append(b); col = 0 if b in (10, 13) else col + 1
    return bytes(out)


def stage_floppy(tmp):
    stage = tmp / 'flop'
    (stage / 'WORK/OUT').mkdir(parents=True)          # vide : la cible
    for rel, data in PO_FILES.items():
        (stage / rel).parent.mkdir(parents=True, exist_ok=True)
        (stage / rel).write_bytes(data)
    po = tmp / 'WORKPO.po'
    subprocess.run([sys.executable, str(ROOT / 'tools/mkvolume.py'), str(stage), str(po),
                    '--volume', 'WORKPO', '--blocks', '280'], check=True, capture_output=True)
    return po


def catalog(po, path):
    """{nom: (type, auxtype, donnees)} du repertoire `path` ('WORK/OUT') de l'image."""
    img = Image(po.read_bytes())
    key = 2
    for part in path.split('/'):
        entries = {e[1:1 + (e[0] & 15)].decode(): e for e in img.entries(key)}
        key = int.from_bytes(entries[part][0x11:0x13], 'little')
    return {e[1:1 + (e[0] & 15)].decode(): (e[0x10], int.from_bytes(e[0x1F:0x21], 'little'), img.read(e))
            for e in img.entries(key) if e[0] >> 4 != 0xD}          # les fichiers, pas OUT/


def main():
    with tempfile.TemporaryDirectory(prefix='a2fc-txtconv-') as tmp:
        tmp = Path(tmp)
        po = stage_floppy(tmp)
        with boot_hd(tmp, HD_FILES, port=PORT, plugins=['txtconv'], floppy2=po) as (p, s):
            def open_panel(x, vol, *names):
                """Amene le panneau qui commence en colonne x sur /vol/names..."""
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

            def convert(name, x, mode, inplace, overwrite=None):
                s.select(name, x); p.stable()
                menu_run(s, p, 'TXTCONV')
                s.wait(lambda: s.has('C)R L)F D)CRLF'), 'la question de la conversion', 20)
                s.key(mode)
                s.wait(lambda: s.has('In place?'), 'la question sur place', 20)
                s.key(b'Y' if inplace else b'N')
                if overwrite is not None:
                    s.wait(lambda: s.has('Overwrite'), "la question d'ecrasement", 20)
                    s.key(b'Y' if overwrite else b'N')
                    if not overwrite:
                        p.stable()
                        return s.rows()[22].strip()
                s.wait(lambda: s.has('Converted') or s.has('failed') or
                       s.has('TXTCONV.TMP already exists'), 'la fin de la conversion', 90)
                p.stable()
                return s.rows()[22].strip()

            # Panneau droit sur la disquette, /WORKPO/WORK/OUT (vide) ; gauche sur /WORKHD/WORK.
            open_panel(40, '/WORKPO', 'WORK', 'OUT')
            s.ok('le panneau droit est sur /WORKPO/WORK/OUT', s.rows()[0][40:].startswith('/WORKPO/WORK/OUT'),
                 s.rows()[0][40:70])

            # 1. Refus dans un panneau vide.
            menu_run(s, p, 'TXTCONV')
            s.ok('refuse un panneau vide', s.has('Select a file to convert'), s.rows()[22].strip())

            open_panel(0, '/WORKHD', 'WORK')
            s.ok('le panneau gauche est sur /WORKHD/WORK', s.rows()[0].startswith('/WORKHD/WORK'), s.rows()[0][:38])

            # 2. ESC a la question annule.
            s.select('LF', 0); p.stable()
            menu_run(s, p, 'TXTCONV')
            s.wait(lambda: s.has('C)R L)F D)CRLF'), 'la question', 20)
            s.key(ESC); p.stable()
            s.ok('ESC annule sans rien ecrire', not s.has('Converted') and s.has('Type  Aux'), s.rows()[22].strip())

            # 3. LF -> CR vers l'autre panneau (meme taille), puis accents par-dessus, refuse.
            line = convert('LF', 0, b'C', inplace=False)
            s.ok('LF -> CR : "Converted %d bytes -> %d bytes"' % (len(LF), len(LF)),
                 line == 'Converted %d bytes -> %d bytes' % (len(LF), len(LF)), line)
            s.ok('le panneau droit montre LF', any(r[40:].startswith('LF ') for r in s.rows()[2:20]),
                 [r[40:78] for r in s.rows()[2:20] if r[40:].strip()][:3])
            line = convert('LF', 0, b'A', inplace=False, overwrite=False)
            s.ok("N a l'ecrasement : rien n'est converti", not s.has('Converted'), line)

            # 4. CRLF -> LF vers l'autre panneau : la paire a cheval sur 256 et 512, l'auxtype garde.
            line = convert('CRLF', 0, b'L', inplace=False)
            s.ok('CRLF -> LF : "Converted %d bytes -> %d bytes"' % (len(CRLF), len(to_lf(CRLF))),
                 line == 'Converted %d bytes -> %d bytes' % (len(CRLF), len(to_lf(CRLF))), line)

            # 5. Sur place, sur la disquette : bit haut, accents, tabulations.
            open_panel(40, '/WORKPO', 'WORK')
            line = convert('HI', 40, b'H', inplace=True)
            s.ok('bit haut retire sur place : "Converted %d bytes -> %d bytes"' % (len(HI), len(HI)),
                 line == 'Converted %d bytes -> %d bytes' % (len(HI), len(HI)), line)
            s.ok('le curseur reste sur HI, pas de TXTCONV.TMP',
                 s.line(40).startswith('HI ') and not s.has('TXTCONV.TMP'), s.line(40))
            line = convert('ACC', 40, b'A', inplace=True)
            s.ok('accents sur place : "Converted %d bytes -> %d bytes"' % (len(ACC), len(ACC_OUT)),
                 line == 'Converted %d bytes -> %d bytes' % (len(ACC), len(ACC_OUT)), line)
            line = convert('TABS', 40, b'T', inplace=True)
            s.ok('tabulations sur place : "Converted %d bytes -> %d bytes"' % (len(TABS), len(tabs(TABS))),
                 line == 'Converted %d bytes -> %d bytes' % (len(TABS), len(tabs(TABS))), line)
            line = convert('BROKEN', 40, b'A', inplace=True)
            s.ok('broken UTF-8 converts with replacement markers',
                 line == 'Converted %d bytes -> %d bytes' % (len(BROKEN), len(BROKEN_OUT)), line)

            # 6. Refus quand l'autre panneau est le meme dossier.
            open_panel(0, '/WORKPO', 'WORK')
            s.select('HI', 0); p.stable()
            menu_run(s, p, 'TXTCONV')
            s.wait(lambda: s.has('C)R L)F D)CRLF'), 'la question', 20)
            s.key(b'C'); s.wait(lambda: s.has('In place?'), 'sur place', 20); s.key(b'N'); p.stable()
            s.ok("refuse l'autre panneau quand c'est le meme dossier", s.has('Other panel'), s.rows()[22].strip())

            # A previous recovery result must survive both another in-place
            # conversion and selection of TXTCONV.TMP itself as the source.
            open_panel(40, '/WORKPO', 'WORK', 'COLLIDE')
            for name in ('KEEP', 'TXTCONV.TMP'):
                line = convert(name, 40, b'S', inplace=True)
                s.ok('existing temporary file refuses conversion of ' + name,
                     'TXTCONV.TMP already exists' in line, line)

        # La disquette, ecrite dans son fichier a l'arret de POM2 (SIGTERM -> flush).
        out = catalog(po, 'WORK/OUT')
        work = catalog(po, 'WORK')
        s.ok('OUT/LF : les fins de ligne en CR, tabulations et UTF-8 intacts, type $04',
             out.get('LF', (0, 0, b''))[2] == to_cr(LF) and out['LF'][:2] == (0x04, 0),
             (out.get('LF', (None, None, b''))[:2], out.get('LF', (0, 0, b''))[2][:40]))
        s.ok('OUT/CRLF : les paires a cheval sur 256 et 512 reduites, auxtype $0123 garde',
             out.get('CRLF', (0, 0, b''))[2] == to_lf(CRLF) and out['CRLF'][:2] == (0x04, 0x0123),
             (out.get('CRLF', (None, None, b''))[:2], out.get('CRLF', (0, 0, b''))[2][250:262]))
        s.ok('WORK/HI : le bit haut retire, sous son nom, type $04',
             work.get('HI', (0, 0, b''))[2] == bytes(b & 0x7F for b in HI) and work['HI'][:2] == (0x04, 0),
             work.get('HI', (None, None, b''))[2][:24])
        s.ok('WORK/ACC : e a c s y ? ? en ASCII',
             work.get('ACC', (0, 0, b''))[2] == ACC_OUT, work.get('ACC', (None, None, b''))[2])
        s.ok('WORK/TABS : tabulations au multiple de 8 suivant',
             work.get('TABS', (0, 0, b''))[2] == tabs(TABS), work.get('TABS', (None, None, b''))[2])
        s.ok('pas de TXTCONV.TMP laisse dans WORK', 'TXTCONV.TMP' not in work, sorted(work))
        s.ok('broken UTF-8 preserves following ASCII and marks incomplete EOF',
             work.get('BROKEN', (0, 0, b''))[2] == BROKEN_OUT)
        s.ok('existing recovery result is unchanged',
             catalog(po, 'WORK/COLLIDE').get('TXTCONV.TMP', (0, 0, b''))[2] == RECOVERY)
        s.ok('source survives a temporary-file collision',
             catalog(po, 'WORK/COLLIDE').get('KEEP', (0, 0, b''))[2] == b'keep this source\r')
    return ok_all(s, 'txtconv')


if __name__ == '__main__':
    sys.exit(main())
