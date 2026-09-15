#!/usr/bin/env python3
"""MOVE's raw bitmap write against ProDOS 8's own allocation.

    make ARCH=6502 && python3 bench/move_bitmap.py
    make && A2FC_BUILD=build A2FC_IMG=A2FILECMD-full python3 bench/move_bitmap.py

When MOVE grows a full directory it takes a block by editing the volume
bitmap with WRITE_BLOCK, behind ProDOS's back. ProDOS 8 keeps a copy of a
bitmap block in memory while it allocates; if that copy outlived the file
that loaded it, the next CREATE/WRITE on the volume would hand out MOVE's
block a second time and cross-link a directory with a file.

The sequence gives ProDOS every chance to do so: a file is copied onto the
floppy first (ProDOS reads and updates its bitmap), MOVE then grows a
directory there (raw bitmap write), and a second file is copied onto the
same floppy. The floppy is in drive 2, so POM2 writes it back and the host
reads the whole volume: every block must have exactly one owner and be
marked used, and the three files must read back intact."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from xplug import boot_hd, menu_run, ok_all, RET, TAB
from prodos_read import Image

PORT = 6823
COPY1 = bytes(range(256)) * 6          # 1,536 bytes: a sapling, index + 3 data blocks
COPY2 = bytes(range(255, -1, -1)) * 5  # 1,280 bytes
HELLO = b'hello' * 20


def owners(img):
    """Every block of the volume -> the list of what uses it."""
    own = {}

    def take(b, what):
        own.setdefault(b, []).append(what)

    h = img.header()
    for b in [0, 1] + list(range(h['bitmap'], h['bitmap'] + (h['blocks'] - 1) // 4096 + 1)):
        take(b, 'boot/bitmap')              # the root chain is walked below

    def walk(key, path):
        b = key
        while b:
            take(b, path + ' dir')
            blk = img.block(b)
            for k in range(13):
                e = blk[4 + 39 * k:4 + 39 * (k + 1)]
                st = e[0] >> 4
                if not st or st >= 14:
                    continue
                name = path + '/' + e[1:1 + (e[0] & 15)].decode('ascii', 'replace')
                ekey = int.from_bytes(e[0x11:0x13], 'little')
                if st == 13:
                    walk(ekey, name)
                elif st == 1:
                    take(ekey, name)
                elif st == 2:
                    take(ekey, name + ' index')
                    ix = img.block(ekey)
                    for i in range(256):
                        d = ix[i] | (ix[256 + i] << 8)
                        if d:
                            take(d, name)
            b = int.from_bytes(blk[2:4], 'little')

    walk(2, '')
    return own


def main():
    with tempfile.TemporaryDirectory(prefix='a2fc-movebitmap-') as tmp:
        tmp = Path(tmp)
        po_stage = tmp / 'stage_MVPO'
        (po_stage / 'SRC').mkdir(parents=True)
        (po_stage / 'DST').mkdir()
        (po_stage / 'SRC' / 'HELLO#040000').write_bytes(HELLO)
        for i in range(12):
            (po_stage / 'DST' / ('F%02d#040000' % i)).write_bytes(b'x' * 16)
        import subprocess
        from pom2 import ROOT
        po = tmp / 'MVPO.po'
        subprocess.run([sys.executable, str(ROOT / 'tools/mkvolume.py'), str(po_stage), str(po),
                        '--volume', 'MVPO', '--blocks', '280'], check=True, capture_output=True)
        files = {'WORK/COPY1#060000': COPY1, 'WORK/COPY2#060000': COPY2}
        with boot_hd(tmp, files, port=PORT, plugins=['move'], floppy2=po) as (p, s):
            def panel(x, vol, *parts):
                if s.cursor_row(x) is None:
                    s.key(TAB); p.stable()
                s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'volumes'); p.stable()
                s.select(vol, x); s.key(RET); p.stable()
                for part in parts:
                    s.select(part, x); s.key(RET); p.stable()

            def copy(name):
                panel(40, '/MVPO')
                panel(0, '/WORKHD', 'WORK')
                s.select(name, 0); s.key(b'C')
                s.wait(lambda: s.has('1 file copied'), 'copy of ' + name, 60); p.stable()
                s.ok(name + ' copied onto /MVPO by the core', s.has('1 file copied'))

            copy('COPY1')                       # ProDOS loads and updates the bitmap
            panel(40, '/MVPO', 'DST')
            panel(0, '/MVPO', 'SRC')
            s.select('HELLO', 0); p.stable()
            menu_run(s, p, 'MOVE')
            s.wait(lambda: s.has('must grow a block'), 'growth question', 30); p.stable()
            s.key(b'Y')
            s.wait(lambda: s.has('moved:'), 'the move', 60); p.stable()
            s.ok('MOVE grew /MVPO/DST and moved HELLO', 'nothing copied' in s.rows()[22],
                 s.rows()[22].strip())
            copy('COPY2')                       # the next ProDOS allocation

        img = Image(po.read_bytes())
        own = owners(img)
        shared = {b: w for b, w in own.items() if len(w) > 1}
        s.ok('no block of /MVPO has two owners', not shared, shared)
        h = img.header()
        bits = img.d[h['bitmap'] * 512:]
        marked_free = [b for b in own if (bits[b >> 3] >> (7 - (b & 7))) & 1]
        s.ok('every used block is marked used in the bitmap', not marked_free, marked_free)
        dst = [e for e in img.entries(2) if e[1:1 + (e[0] & 15)] == b'DST'][0]
        dstkey = int.from_bytes(dst[0x11:0x13], 'little')
        grown = int.from_bytes(img.block(dstkey)[2:4], 'little')
        copy2 = min(b for b, w in own.items() if any(x.startswith('/COPY2') for x in w))
        # Sensitivity: ProDOS allocates first fit, so a stale bitmap copy
        # would have handed MOVE's block to COPY2. The sequence can only
        # prove anything if that block was ProDOS's next choice.
        s.ok("the check can fail: COPY2 starts right after MOVE's block, the first free one",
             grown and copy2 == grown + 1 and all(b in own for b in range(7, grown)),
             (grown, copy2))
        got = {}
        for key, names in ((2, ('COPY1', 'COPY2')), (dstkey, ('HELLO',))):
            for e in img.entries(key):
                n = e[1:1 + (e[0] & 15)].decode()
                if n in names:
                    got[n] = img.read(e)
        s.ok('COPY1, COPY2 and the moved HELLO read back intact',
             got.get('COPY1') == COPY1 and got.get('COPY2') == COPY2 and got.get('HELLO') == HELLO,
             sorted(got))
    return ok_all(s, 'move_bitmap')


if __name__ == '__main__':
    sys.exit(main())
