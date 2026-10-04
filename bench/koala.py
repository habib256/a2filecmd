#!/usr/bin/env python3
"""KoalaPad pictures, end to end on POM2: a Micro-Illustrator data disk
(DOS 3.3, `PICTR.*` B files saved at $4000 for $1FF8 bytes) is copied with
C, and the copies open in the hi-res viewer byte for byte -- Return, I,
Right to the neighbour, S slideshow. A C64 KoalaPainter file still opens in
hex. The pictures are drawn by tools/test_koala.py, not Koala artwork.

    make disk && python3 bench/koala.py                       # 6502 build
    A2FC_IMG=A2FILECMD-full python3 bench/koala.py            # 65C02 build
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from xplug import boot_hd, ok_all, RET, TAB, ESC
from prodos_read import Image
from test_koala import picture, micro_illustrator_save, c64_koala, data_disk, visible, SAVE_LEN

RIGHT = b'\x15'


def main():
    pages = {'PICTR.HOUSE': picture(0), 'PICTR.TREE': picture(1)}
    disk = data_disk([(name, micro_illustrator_save(page)) for name, page in pages.items()])
    files = {'WORK/KOALA.DSK': disk, 'OUT/PICA.KOALA#066000': c64_koala()}
    with tempfile.TemporaryDirectory(prefix='a2fc-koala-') as tmp:
        with boot_hd(Path(tmp), files, port=6866) as (p, s):
            def shows(name):
                return visible(bytes(p.peek(0x2000, 8192))) == visible(pages[name])

            def panels(what):
                s.wait(lambda: s.has('Type  Aux'), 'panels after ' + what, 30)
                p.stable()

            # Right panel on /WORKHD/OUT, left panel inside the data disk.
            s.key(TAB); s.key(b'/'); s.select('/WORKHD', 40); s.key(RET)
            s.select('OUT', 40); s.key(RET); p.stable()
            s.key(TAB); s.key(b'/'); s.select('/WORKHD'); s.key(RET)
            s.select('WORK'); s.key(RET); p.stable()
            s.select('KOALA.DSK'); s.key(RET)
            s.wait(lambda: s.has('PICTR.HOUSE') and s.has('PICTR.TREE'), 'the DOS 3.3 catalog', 60)
            p.stable()
            for name in pages:
                s.select(name); s.key(b' '); p.stable()
            s.key(b'C')
            s.wait(lambda: s.has('2 files extracted.'), 'the two pictures copied', 120); p.stable()

            s.key(TAB)
            for name in pages:
                s.select(name, 40)
                line = s.line(40)
                s.ok(name + ' copied as a BIN at $4000, 8184 bytes',
                     'BIN' in line and '$4000' in line and str(SAVE_LEN) in line, line)

            # Return: the page as saved. I: the same viewer.
            for key, label in ((RET, 'Return'), (b'I', 'I')):
                s.select('PICTR.HOUSE', 40); s.key(key); s.allow_aux()
                s.wait(lambda: shows('PICTR.HOUSE'), 'PICTR.HOUSE with ' + label, 60)
                s.ok(label + ' shows PICTR.HOUSE byte for byte', True)
                s.key(ESC); panels(label)

            # Right: the next picture of the folder, the C64 file skipped.
            s.select('PICTR.HOUSE', 40); s.key(RET); s.allow_aux()
            s.wait(lambda: shows('PICTR.HOUSE'), 'first picture', 60)
            s.key(RIGHT)
            s.wait(lambda: shows('PICTR.TREE'), 'Right to PICTR.TREE', 60)
            s.ok('Right goes to the neighbouring Koala picture', True)
            s.key(RIGHT)
            s.wait(lambda: shows('PICTR.HOUSE'), 'Right round to PICTR.HOUSE', 60)
            s.ok('Right on the last goes round to the first, past the C64 file', True)

            # S: the slideshow brings the other picture by itself.
            s.key(b'S')
            s.wait(lambda: shows('PICTR.TREE'), 'the slideshow', 90)
            s.ok('S brings the next Koala picture by itself', True)
            s.key(ESC); panels('the slideshow')

            # A C64 KoalaPainter file is not an Apple picture.
            s.select('PICA.KOALA', 40); s.key(RET)
            s.wait(lambda: s.value('view', 1) == 3, 'the C64 file in hex', 30)
            s.ok('a C64 Koala file opens in hex, not as a picture', True)
            s.key(ESC); panels('hex')

            hdv = Path(p.hdv)
        # The machine is off: what the hard disk holds now. The copies are
        # there (so the image was written back at all), byte for byte, and
        # the DOS data disk the pictures came from is unchanged.
        img = Image(hdv.read_bytes())
        out = {e[1:1 + (e[0] & 15)].decode(): e for e in img.entries(dir_key(img, 'OUT'))}
        work = {e[1:1 + (e[0] & 15)].decode(): e for e in img.entries(dir_key(img, 'WORK'))}
        for name, page in pages.items():
            e = out.get(name)
            s.ok('on disk: ' + name + ' is BIN $4000 with the 8184 saved bytes',
                 e is not None and e[0x10] == 6 and int.from_bytes(e[0x1F:0x21], 'little') == 0x4000
                 and img.read(e) == page[:SAVE_LEN])
        s.ok('on disk: the DOS 3.3 data disk is unchanged', img.read(work['KOALA.DSK']) == disk)
    return ok_all(s, 'koala')


def dir_key(img, name):
    for e in img.entries(2):
        if e[1:1 + (e[0] & 15)].decode() == name:
            return int.from_bytes(e[0x11:0x13], 'little')
    raise KeyError(name)


if __name__ == '__main__':
    sys.exit(main())
