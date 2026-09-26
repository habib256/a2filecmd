#!/usr/bin/env python3
"""Windows of a large directory stay exact across a disk swap and writes.

A directory larger than a window (139 entries) is paged: each page skips the
blocks before its window by counting their active entries (dir_count_block).
Nothing is remembered from one page to the next, so a page after a disk swap
or after the directory changed must show exactly what a walk of the disk now
in the drive gives. Each window is read from A2FC's own entry table (the
whole window, not the 18 rows on screen) and compared with the directory
read back from the image files by tools/prodos_read.py.

1. Two floppies with the same volume name and the same path, /FLOP/BIG,
   different entries (200 A-names; 180 B-names). A window is read, the
   floppy is swapped, and the previous and next windows are the new disk's.
2. On the hard disk, a 300-entry /WORKHD/BIG: the left panel on window 2,
   the right panel deletes an entry of window 0 and copies a file in (ProDOS
   puts it in the hole: the same file count, another order). Every window
   of the left panel then matches the image read back after the run.

Disposable images only. A2FC_PORT_OFFSET shifts the port (6908).
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from xplug import boot_hd, RET, TAB, ok_all    # noqa: E402
from run import volume                          # noqa: E402
from prodos_read import Image                   # noqa: E402

WINDOW = 139
PANEL_SIZE = 98          # sizeof(struct Panel): offsets in src/a2fc_plugin.h
ENTRY_SIZE = 29


def big_order(image_bytes, *path):
    """The live names of a directory, in disk order."""
    img = Image(image_bytes)
    key = 2
    for name in path:
        e = next(e for e in img.entries(key) if e[1:1 + (e[0] & 15)].decode() == name)
        key = int.from_bytes(e[0x11:0x13], 'little')
    return [e[1:1 + (e[0] & 15)].decode() for e in img.entries(key)]


def window(p, s, panel):
    """(path, first, more, names) of a panel, read from A2FC's own table."""
    base = s.sym['__LOWBSS_RUN__'] + panel * PANEL_SIZE      # panels[] opens LOWBSS
    raw = bytes(p.peek(base, PANEL_SIZE))
    path = raw[:64].split(b'\0')[0].decode('ascii', 'replace')
    count, more = raw[64], raw[67]
    first = int.from_bytes(raw[68:70], 'little')
    e = int.from_bytes(raw[74:76], 'little')
    table = bytes(p.peek(e, count * ENTRY_SIZE)) if count else b''
    names = [table[i * ENTRY_SIZE:(i + 1) * ENTRY_SIZE][:17].split(b'\0')[0].decode('ascii', 'replace')
             for i in range(count)]
    return path, first, more, names


def expect(names, first):
    """What window `first` shows: '..' on top of window 0."""
    return (['..'] if not first else []) + names[first:first + WINDOW]


def open_dir(s, p, x, *names):
    s.key(b'/')
    s.wait(lambda: '[Volumes]' in s.rows()[0][x:x + 38], 'volume list')
    p.stable()
    for n in names:
        s.select(n, x)
        s.key(RET)
        s.wait(lambda: s.rows()[0][x:x + 38].strip().endswith(n.lstrip('/')), n)
        p.stable()


def page(s, p, key):
    """Up from the top of a window or Down from its end: the neighbour window."""
    before = s.rows()[1]
    s.key(b'[' if key == 'up' else b']')
    p.stable()
    s.key(b'\x0b' if key == 'up' else b'\x0a')
    s.wait(lambda: s.rows()[1] != before, 'window change', 60)
    p.stable()


def main():
    with tempfile.TemporaryDirectory(prefix='paging-swap-') as tmp:
        tmp = Path(tmp)
        floppies = {}
        for label, prefix, n in (('A', 'A', 200), ('B', 'B', 180)):
            stage = tmp / f'stage{label}'
            (stage / 'BIG').mkdir(parents=True)
            for i in range(n):
                (stage / 'BIG' / f'{prefix}{i:03}#040000').write_bytes(b'x')
            floppies[label] = volume(stage, tmp / f'{label}.po', 'FLOP', 280)
        orig = {k: v.read_bytes() for k, v in floppies.items()}
        order = {k: big_order(v, 'BIG') for k, v in orig.items()}
        files = {f'BIG/F{i:04}#040000': b'data %d' % i for i in range(300)}
        files['SRC/NEWFILE#040000'] = b'new file'
        with boot_hd(tmp, files, port=6908, blocks=2000, floppy=floppies['A'], boot=None) as (p, s):
            hdv = Path(p.hdv)
            path, *_ = window(p, s, 0)
            s.ok('the panel table is found at the start of LOWBSS', path.startswith('/WORKHD'), path)

            # 1. the floppy swap
            open_dir(s, p, 0, '/FLOP', 'BIG')
            got = window(p, s, 0)
            s.ok('window 0 of disk A', got == ('/FLOP/BIG', 0, 1, expect(order['A'], 0)), got[:3])
            page(s, p, 'down')
            got = window(p, s, 0)
            s.ok('window 1 of disk A', got == ('/FLOP/BIG', 139, 0, expect(order['A'], 139)), got[:3])
            p.insert(0, 'B.po')
            page(s, p, 'up')
            got = window(p, s, 0)
            s.ok('after the swap, window 0 is disk B', got == ('/FLOP/BIG', 0, 1, expect(order['B'], 0)), got[:3])
            page(s, p, 'down')
            got = window(p, s, 0)
            s.ok('and window 1 is disk B', got == ('/FLOP/BIG', 139, 0, expect(order['B'], 139)), got[:3])
            p.insert(0, 'A.po')
            page(s, p, 'up')
            got = window(p, s, 0)
            s.ok('swapped back, window 0 is disk A again', got[3] == expect(order['A'], 0), got[:3])
            p.sync_disks()
            s.ok('the floppies are not written', all(floppies[k].read_bytes() == orig[k] for k in orig))

            # 2. the directory written from the other panel
            open_dir(s, p, 0, '/WORKHD', 'BIG')
            page(s, p, 'down')
            page(s, p, 'down')
            s.key(TAB)
            open_dir(s, p, 40, '/WORKHD', 'BIG')
            s.select('F0005', 40)
            s.key(b'D')
            s.wait(lambda: '?' in s.rows()[22], 'delete confirmation')
            s.key(b'Y')
            s.wait(lambda: 'F0005 ' not in ''.join(r[40:] for r in s.rows()), 'deleted', 60)
            p.stable()
            open_dir(s, p, 40, '/WORKHD', 'SRC')
            s.select('NEWFILE', 40)
            s.key(b'C')                 # into the other panel's directory: BIG
            s.wait(lambda: 'copied' in s.rows()[22] or 'failed' in s.rows()[22], 'copy', 60)
            p.stable()
            s.ok('the copy is done', 'copied' in s.rows()[22], s.rows()[22].strip())
            s.key(TAB)
            p.stable()
            windows = [window(p, s, 0)]
            page(s, p, 'up')
            windows.append(window(p, s, 0))
            page(s, p, 'up')
            windows.append(window(p, s, 0))
            page(s, p, 'down')
            windows.append(window(p, s, 0))
            page(s, p, 'down')
            windows.append(window(p, s, 0))
        after = big_order(hdv.read_bytes(), 'BIG')
        s.ok('the hard disk directory changed as intended',
             'F0005' not in after and 'NEWFILE' in after and len(after) == 300, after[:8])
        for got in windows:
            path, first, more, names = got
            s.ok(f'window {first // WINDOW} after the writes is the directory on disk',
                 path == '/WORKHD/BIG' and names == expect(after, first)
                 and more == (first + WINDOW < len(after)), (first, len(names)))
        s.ok('the three windows were all seen', sorted({w[1] for w in windows}) == [0, 139, 278])
    return ok_all(s, 'paging across a disk swap and writes')


if __name__ == '__main__':
    raise SystemExit(main())
