#!/usr/bin/env python3
"""DIRSORT on a real ProDOS 8, then ProDOS itself on what it wrote.

    make && python3 bench/dirsort.py
    make ARCH=6502 && python3 bench/dirsort.py

A disposable floppy in drive 2 holds PRODOS, A.SYSTEM, B.SYSTEM, fourteen
data files and ZSUB, a subdirectory of twelve files whose entry sits in the
second block of the volume directory. Under A2FC, DIRSORT carries ZSUB to
the top (into the first block: its header's parent link must follow) and
B.SYSTEM above A.SYSTEM, and writes. Then ProDOS itself works through what
DIRSORT wrote: K creates a directory in ZSUB, its thirteenth entry, so
ProDOS grows ZSUB by a block and updates ZSUB's entry through that parent
link -- a wrong link would land on another entry. The host then checks the
floppy with tools/prodos_check.py, every file's bytes, and the order. Last,
the floppy is booted: each .SYSTEM leaves its own mark at $0300, and the
one ProDOS 8 starts must be B.SYSTEM."""
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from pom2 import Pom2, ROOT
from xplug import boot_hd, menu_run, ok_all, wait_note, RET
import subprocess
from prodos_read import Image
from prodos_check import check

PORT = 6909
UP, DOWN = b'\x0b', b'\x0a'


def marker(c):
    """A SYS program: LDA #c; STA $0300; JMP * -- the mark of who booted."""
    return bytes([0xA9, c, 0x8D, 0x00, 0x03, 0x4C, 0x05, 0x20])


def contents(img):
    """Every file's path and bytes, and every directory."""
    out = {}
    def walk(key, prefix):
        for e in img.entries(key):
            name = prefix + '/' + e[1:1 + (e[0] & 15)].decode()
            if e[0] >> 4 == 0xD:
                out[name] = 'DIR'
                walk(int.from_bytes(e[0x11:0x13], 'little'), name)
            else:
                out[name] = img.read(e)
    walk(2, '')
    return out


def names(img, key=2):
    return [e[1:1 + (e[0] & 15)].decode() for e in img.entries(key)]


def main():
    files = {'PRODOS#FF0000': (ROOT / 'data/PRODOS.SYS').read_bytes(),
             'A.SYSTEM#FF2000': marker(0xC1), 'B.SYSTEM#FF2000': marker(0xC2)}
    for i in range(1, 15):
        files['D%02d#060000' % i] = bytes((i * 37 + n) & 255 for n in range(300 * i))
    for i in range(1, 13):
        files['ZSUB/Z%02d#040000' % i] = ('file %d of ZSUB\r' % i).encode() * i
    with tempfile.TemporaryDirectory(prefix='a2fc-dirsort-') as tmp:
        tmp = Path(tmp)
        stage = tmp / 'stage'
        for rel, data in files.items():
            (stage / rel).parent.mkdir(parents=True, exist_ok=True)
            (stage / rel).write_bytes(data)
        po = tmp / 'SORTME.po'
        subprocess.run([sys.executable, str(ROOT / 'tools/mkvolume.py'), str(stage), str(po),
                        '--volume', 'SORTME', '--boot', str(ROOT / 'data/prodos_boot.tmpl'),
                        '--blocks', '280'], check=True, capture_output=True)
        before = po.read_bytes()
        img = Image(before)
        order = names(img)
        assert order[:2] == ['A.SYSTEM', 'B.SYSTEM'] and order[-1] == 'ZSUB', order
        assert not check(before).findings, 'the fixture itself must be healthy'
        with boot_hd(tmp, {}, port=PORT, plugins=['dirsort'], floppy2=po) as (p, s):
            s.key(b'/'); s.wait(lambda: s.rows()[0].startswith('[Volumes]'), 'volumes'); p.stable()
            s.select('/SORTME'); s.key(RET)
            s.wait(lambda: s.has('ZSUB'), 'the floppy', 30); p.stable()
            menu_run(s, p, 'DIRSORT')
            s.wait(lambda: s.has('DIRSORT /SORTME'), 'DIRSORT', 30); p.stable()
            s.ok('the volume directory in disk order, A.SYSTEM boots',
                 s.has('A.SYSTEM        $FF  <- boots') and not s.has('B.SYSTEM        $FF  <-'),
                 '\n'.join(s.rows()))
            # ZSUB, last, carried to the top; then B.SYSTEM above A.SYSTEM.
            last = len(order) - 1
            for _ in range(last): s.key(DOWN, 0.05)
            s.key(b' ')
            for _ in range(last): s.key(UP, 0.05)
            s.key(b' ')
            for _ in range(2): s.key(DOWN, 0.05)
            s.key(b' ')
            for _ in range(2): s.key(UP, 0.05)
            s.key(b' '); p.stable()
            s.ok('the mark follows the order before anything is written',
                 s.has('B.SYSTEM        $FF  <- boots') and not s.has('A.SYSTEM        $FF  <-'),
                 '\n'.join(s.rows()))
            s.key(b'W')
            s.wait(lambda: s.has('Write this order to /SORTME?'), 'the confirmation', 20); p.stable()
            s.ok('the warning names the risk', s.has('A power cut while writing can damage this directory.'))
            s.key(b'Y')
            note = wait_note(s, p, 60, gone='Write this order')
            s.ok('written and read back', note == 'Reordered: every block read back.', note)
            # ProDOS now: a thirteenth entry in ZSUB grows it by a block.
            s.select('ZSUB'); s.key(RET)
            s.wait(lambda: s.has('Z12'), 'ZSUB', 30); p.stable()
            s.key(b'K'); s.wait(lambda: s.has('New directory'), 'mkdir'); p.stable()
            s.type('NEWDIR'); s.key(RET)
            s.wait(lambda: s.has('NEWDIR'), 'the new directory', 30); p.stable()
        after = po.read_bytes()
        img = Image(after)
        found = check(after)
        s.ok('ProDOS check: no finding on the sorted floppy', found.complete and not found.findings,
             str(found.findings))
        s.ok('the order written',
             names(img)[:3] == ['B.SYSTEM', 'ZSUB', 'A.SYSTEM'] and
             sorted(names(img)) == sorted(order), str(names(img)))
        want = contents(Image(before))
        want['/ZSUB/NEWDIR'] = 'DIR'
        s.ok('every file byte for byte, NEWDIR added', contents(img) == want)
        zsub = next(e for e in img.entries(2) if e[1:5] == b'ZSUB')
        s.ok('ProDOS grew ZSUB through the rewritten link',
             int.from_bytes(zsub[0x13:0x15], 'little') == 2, zsub.hex())
        # The boot: ProDOS 8 starts the first SYS .SYSTEM of the volume.
        hdv = next(tmp.glob('*.hdv'))
        with Pom2(hdv, floppy=po, port=PORT + 1) as p:
            mark = 0
            for _ in range(100):
                time.sleep(0.2)
                mark = p.peek(0x300, 1)[0]
                if mark in (0xC1, 0xC2):
                    break
            s.ok('ProDOS 8 boots B.SYSTEM, as DIRSORT showed', mark == 0xC2, hex(mark))
        return ok_all(s, 'dirsort')


if __name__ == '__main__':
    raise SystemExit(main())
