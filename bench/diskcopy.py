#!/usr/bin/env python3
"""Banc de DiskCopy 4.2 : une image .DC ouverte comme un dossier (le resident,
src/a2fc.c img_open) et convertie dans les deux sens par IMGCONV.

    make all disk && A2FC_IMG=A2FILECMD-full python3 bench/diskcopy.py

Le disque d'amorcage porte les sources (/WORKHD/IMG) : un volume ProDOS de
800 Ko fait par tools/mkvolume.py, le meme en DiskCopy (tools/dc42.py), une
copie dont la somme de controle est fausse, et une image DiskCopy qui n'est
pas du ProDOS (le disque HFS des essais de CiderPress II s'il est la, sinon
des blocs quelconques). Les resultats vont sur un second disque dur
(`--hd2`, /WORKDC/OUT), recopie dans son fichier a l'arret de POM2 et relu
octet a octet contre la reference."""
import random
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from xplug import boot_hd, menu_run, ok_all, RET, TAB, ESC
from pom2 import ROOT
from imgconv import catalog
from prodos_read import Image
import cp2_samples
import dc42

PORT = 6856
DONE = (' -> ', 'failed', 'mismatch', 'Not a DiskCopy', 'DiskCopy holds', 'Select a disk image')


def volume(tmp, tag, name, blocks, files):
    stage = tmp / ('src-' + tag)
    for rel, data in files.items():
        (stage / rel).parent.mkdir(parents=True, exist_ok=True)
        (stage / rel).write_bytes(data)
    out = tmp / (tag + '.po')
    subprocess.run([sys.executable, str(ROOT / 'tools/mkvolume.py'), str(stage), str(out),
                    '--volume', name, '--blocks', str(blocks)], check=True, capture_output=True)
    return out


def main():
    with tempfile.TemporaryDirectory(prefix='a2fc-diskcopy-') as tmp:
        tmp = Path(tmp)
        deep = b'deep inside a DiskCopy image\r' * 30
        raw = volume(tmp, 'disk', 'DISK800', 1600,
                     {'HELLO.TXT': b'hello from 800K\r', 'INSIDE/DEEP.TXT': deep}).read_bytes()
        dc = dc42.wrap(raw, b'DISK800')
        bad = dc[:0x4B] + bytes([dc[0x4B] ^ 0x40]) + dc[0x4C:]
        real = cp2_samples.path('diskcopy/Installer Disk 1.image')
        if real:
            foreign = real.read_bytes()
        else:
            rng = random.Random(1)
            foreign = dc42.wrap(bytes(rng.randrange(256) for _ in range(1600 * 512)), b'Mac')
        hd_files = {
            'IMG/DISK800.DC#E08005': dc,
            'IMG/DISK800.PO': raw,
            'IMG/BADSUM.DC': bad,
            'IMG/MAC.IMAGE': foreign,
        }
        out_hd = volume(tmp, 'out', 'WORKDC', 4000, {'OUT/KEEP.TXT': b'keep\r'})
        with boot_hd(tmp, hd_files, port=PORT, blocks=8000, plugins=['imgconv'], hd2=out_hd) as (p, s):
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

            def convert(name, key, seconds=600):
                before = s.rows()[22]
                if s.cursor_row(0) is None:
                    s.key(TAB)
                s.select(name, 0); p.stable()
                menu_run(s, p, 'IMGCONV')
                s.wait(lambda: s.has('Convert to P)'), 'la question du format', 20)
                s.key(key)
                s.wait(lambda: s.rows()[22] != before and any(m in s.rows()[22] for m in DONE),
                       'la fin de la conversion', seconds)
                p.stable()
                return s.rows()[22].strip()

            open_panel(40, '/WORKDC', 'OUT')
            open_panel(0, '/WORKHD', 'IMG')

            # 1. Retour ouvre le .DC comme un dossier ; C copie un fichier de dedans.
            s.select('DISK800.DC', 0); s.key(RET)
            s.wait(lambda: s.has('HELLO ') and s.has('INSIDE/'), 'le dossier DiskCopy', 60); p.stable()
            s.ok('DISK800.DC s ouvre comme un dossier', s.rows()[0].startswith('/WORKHD/IMG/DISK800.DC'),
                 s.rows()[0][:40])
            s.select('INSIDE', 0); s.key(RET)
            s.wait(lambda: s.has('DEEP '), 'INSIDE', 30); p.stable()
            s.select('DEEP', 0); s.key(b'C')
            s.wait(lambda: 'DEEP' in ''.join(r[40:] for r in s.rows()[2:20]), 'la copie', 60); p.stable()
            s.ok('C copie DEEP.TXT hors de l image', True)
            s.key(ESC); p.stable()
            s.key(ESC)
            s.wait(lambda: s.rows()[0].startswith('/WORKHD/IMG '), 'sortir de l image', 30); p.stable()

            # 2. Une image DiskCopy qui n'est pas du ProDOS : le message, pas de dossier.
            s.select('MAC.IMAGE', 0); s.key(RET)
            s.wait(lambda: 'Not a ProDOS disk image' in s.rows()[22], 'le refus', 30); p.stable()
            s.ok('MAC.IMAGE : refuse, le panneau reste sur IMG', s.rows()[0].startswith('/WORKHD/IMG '),
                 s.rows()[22].strip())

            # 3. IMGCONV dans les deux sens, et la somme fausse.
            line = convert('DISK800.DC', b'P')
            s.ok('DISK800.DC -> .PO', line == 'DISK800.DC -> DISK800.PO, 1600 blocks', line)
            line = convert('BADSUM.DC', b'P')
            s.ok('BADSUM.DC : refusee', line == 'DiskCopy checksum mismatch: nothing written.', line)
            open_panel(40, '/WORKDC')
            line = convert('DISK800.PO', b'C')
            s.ok('DISK800.PO -> .DC', line == 'DISK800.PO -> DISK800.DC, 1600 blocks', line)

        out = catalog(out_hd, 'OUT')
        s.ok('OUT/DEEP : les octets du fichier de l image',
             out.get('DEEP', (0, 0, b''))[2] == deep, sorted(out))
        s.ok('OUT/DISK800.PO : les blocs du DiskCopy', out.get('DISK800.PO', (0, 0, b''))[2] == raw)
        s.ok('rien ecrit pour BADSUM', 'BADSUM.PO' not in out, sorted(out))
        img = Image(out_hd.read_bytes())
        root = {e[1:1 + (e[0] & 15)].decode(): e for e in img.entries(2)}
        e = root.get('DISK800.DC')
        s.ok('/WORKDC/DISK800.DC : exactement tools/dc42.py',
             e is not None and img.read(e) == dc42.wrap(raw, b'DISK800.DC'))
        s.ok('/WORKDC/DISK800.DC : type $E0, auxtype $8005',
             e is not None and e[0x10] == 0xE0 and int.from_bytes(e[0x1F:0x21], 'little') == 0x8005)
    return ok_all(s, 'diskcopy')


if __name__ == '__main__':
    sys.exit(main())
