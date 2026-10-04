"""KoalaPad pictures: Micro-Illustrator's saves open in the hi-res viewer.

What the KoalaPad software for the Apple II saves (read off its own
Applesoft storage menu, "STANDARD DOS 3.3 PICTURE", and checked on every
saved picture of 15 archived disks): a DOS 3.3 B file named `PICTR.` + the
user's name, BSAVEd from hi-res page 2 with A$4000,L$1FF8 -- the 8,184
bytes of a hi-res page without its last screen hole. Nothing is packed:
once C has copied it from the DOS disk it is a BIN, aux $4000, 8,184
bytes, which the raw HGR route already takes.

This runs the real code on both CPU editions:
- DOSGET's dos_extract (host build) on a Micro-Illustrator data disk made
  here, and on the archived disks when they are present (private, never in
  the repository: ~/.cache/a2fc/koala/ia or $A2FC_KOALA);
- the classifier and Return/I dispatch (image_kind in C, src/open.s under
  sim65 on the 6502 and the 65C02), through test_file_viewers' harness.
A C64 or Atari "Koala" file is another machine's format (C64: 10,003 bytes,
load address $6000, multicolour bitmap + colour RAM): it must not be taken
for an Apple picture.
"""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import mkdos33
import test_dos_extract
import test_file_viewers

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = Path(os.environ.get('A2FC_KOALA', Path.home() / '.cache/a2fc/koala/ia'))
SAVE_ADDR, SAVE_LEN = 0x4000, 0x1FF8        # BSAVE PICTR.name,A16384,L8184


def row_address(y):
    return (y & 7) * 1024 + ((y >> 3) & 7) * 128 + (y >> 6) * 40


def picture(seed):
    """A hi-res page drawn here (no Koala artwork): colour bands with both
    palette bits, a box, a circle and a diagonal, different for each seed.
    The eight bytes of each screen hole hold a marker no viewer shows."""
    page = bytearray(8192)
    for y in range(192):
        a = row_address(y)
        for x in range(40):
            band = (y // 24 + x // 10 + seed) % 6
            page[a + x] = (0x00, 0x2A, 0x55, 0xAA, 0xD5, 0x7F)[band] if y % 48 < 40 else 0

    def plot(x, y):
        if 0 <= x < 280 and 0 <= y < 192:
            page[row_address(y) + x // 7] |= 1 << (x % 7)

    for x in range(20 + seed * 7, 200):
        plot(x, 30 + seed); plot(x, 150)
    for y in range(30 + seed, 151):
        plot(20 + seed * 7, y); plot(199, y)
    import math
    for t in range(720):
        plot(int(140 + (40 + seed * 5) * math.cos(t * math.pi / 360)),
             int(96 + 40 * math.sin(t * math.pi / 360)))
    for i in range(180):
        plot(50 + i, 10 + i)
    for hole in range(120, 8192, 128):
        page[hole:hole + 8] = bytes([0xA0 + seed] * 8)
    return bytes(page)


def micro_illustrator_save(page):
    """The DOS 3.3 B file Micro-Illustrator writes: its 4-byte header
    (address, length) then the first 8,184 bytes of the page."""
    return SAVE_ADDR.to_bytes(2, 'little') + SAVE_LEN.to_bytes(2, 'little') + page[:SAVE_LEN]


def c64_koala(seed=0):
    """A C64 KoalaPainter file as a C64 disk holds it: load address $6000,
    8,000 bitmap bytes, 1,000 screen, 1,000 colour, one background byte."""
    body = bytes((i * 7 + seed) & 255 for i in range(10001))
    return b'\x00\x60' + body


def visible(page):
    return b''.join(page[i:i + 120] for i in range(0, 8192, 128))


def data_disk(files):
    """A DOS 3.3 data disk holding `files` [(name, data)] as B files."""
    return mkdos33.build([(name, 0x04, data) for name, data in files])


# --- the private archive: an independent DOS 3.3 reader, for the expected bytes
def dos_sector(disk, t, s):
    return disk[(t * 16 + s) * 256:(t * 16 + s + 1) * 256]


def dos_catalog(disk):
    """[(name, type byte, (tslt, tsls), sector count)] in catalog order."""
    vtoc = dos_sector(disk, 17, 0)
    t, s, seen, out = vtoc[1], vtoc[2], set(), []
    while t and t < 35 and s < 16 and (t, s) not in seen:
        seen.add((t, s))
        c = dos_sector(disk, t, s)
        for i in range(7):
            e = c[11 + i * 35:46 + i * 35]
            if e[0] in (0, 0xFF):
                continue
            name = bytes(b & 0x7F for b in e[3:33]).decode('latin-1').rstrip()
            out.append((name, e[2], (e[0], e[1]), e[33] | e[34] << 8))
        t, s = c[1], c[2]
    return out


def dos_bin(disk, ts):
    """(address, data) of a B file, or None if its sectors do not hold the
    whole length its header announces."""
    t, s = ts
    raw = bytearray()
    while t:
        if t >= 35 or s >= 16:
            return None
        lst = dos_sector(disk, t, s)
        for i in range(122):
            tt, ss = lst[12 + i * 2], lst[13 + i * 2]
            if not tt:
                break
            raw += dos_sector(disk, tt, ss)
        else:
            t, s = lst[1], lst[2]
            continue
        break
    if len(raw) < 4:
        return None
    length = raw[2] | raw[3] << 8
    return (raw[0] | raw[1] << 8, bytes(raw[4:4 + length])) if len(raw) >= 4 + length else None


def private_disks():
    return sorted(p for p in PRIVATE.glob('*') if p.suffix.lower() in ('.dsk', '.do')
                  and p.stat().st_size == 143360) if PRIVATE.is_dir() else []


# --- DOSGET's real extraction, fed with a whole disk
EXTRACT = test_dos_extract.C[:test_dos_extract.C.index('int main(')] + r'''
int main(int argc,char** argv){
 FILE* f=fopen(argv[1],"rb");
 if(!f||fread(sectors,256,560,f)!=560)return 2;
 fclose(f);
 strcpy(panels[1].path,argv[2]);strcpy(panels[0].path,"X");panels[0].img_len=1;panels[0].count=1;
 strcpy(entries[0].name,"PICTURE");entries[0].type=6;
 entries[0].mdate=atoi(argv[3]);entries[0].blocks=atoi(argv[4]);
 dos_extract();
 printf("%u %u %u %s\n",a2fc_ops,_filetype,_auxtype,note);return 0;
}
'''


class KoalaPictures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ktmp = tempfile.TemporaryDirectory(prefix='koala-')
        cls.kroot = Path(cls.ktmp.name)
        src = cls.kroot / 'extract.c'
        src.write_text(EXTRACT)
        cls.extractor = cls.kroot / 'extract'
        r = subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-fsanitize=address,undefined',
                            str(src), '-o', str(cls.extractor)], capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError(r.stderr)
        # The classifier builds (host reference, open.s under sim65 on both
        # CPUs): FileViewers' own set-up, which fills cls.tmp/root/exes.
        test_file_viewers.FileViewers.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()
        cls.ktmp.cleanup()

    answers = test_file_viewers.FileViewers.answers
    route = test_file_viewers.FileViewers.route

    def extract(self, disk, entry):
        """DOSGET on one catalog entry: (ok, filetype, auxtype, bytes or None)."""
        name, _typ, (t, s), count = entry
        with tempfile.TemporaryDirectory(dir=self.kroot) as d:
            image = Path(d) / 'disk.dsk'
            image.write_bytes(disk)
            out_dir = Path(d) / 'out'
            out_dir.mkdir()
            line = subprocess.check_output([str(self.extractor), str(image), str(out_dir),
                                            str(t << 8 | s), str(count)], text=True).split(' ', 3)
            out = out_dir / 'PICTURE'
            self.assertEqual(image.read_bytes(), disk, 'the source disk is never written')
            return line[0] == '1', int(line[1]), int(line[2]), out.read_bytes() if out.exists() else None

    def check_save(self, disk, entry, page=None):
        """The whole user path: C copies the save, Return/I show it raw."""
        ok, filetype, aux, data = self.extract(disk, entry)
        self.assertTrue(ok, entry)
        self.assertEqual((filetype, aux, len(data)), (6, SAVE_ADDR, SAVE_LEN), entry)
        if page is not None:
            self.assertEqual(data, page[:SAVE_LEN])
        prodos_name = entry[0].upper()[:15]
        for key in (0, 1):            # Return, I
            self.route(prodos_name, filetype, aux, len(data), 'IMAGE', key, raw=True, data=data[:8])
        return data

    def test_a_micro_illustrator_data_disk_copies_and_opens_as_a_raw_page(self):
        pages = [picture(0), picture(1)]
        disk = data_disk([('PICTR.HOUSE', micro_illustrator_save(pages[0])),
                          ('PICTR.MR. STERN\'S B-DAY', micro_illustrator_save(pages[1]))])
        catalog = dos_catalog(disk)
        self.assertEqual([c[3] for c in catalog], [33, 33])   # 32 data sectors + the T/S list, as saved
        for entry, page in zip(catalog, pages):
            self.check_save(disk, entry, page)

    def test_the_names_a_dos_catalog_gives_keep_the_picture_viewer(self):
        # read_dos33_panel turns other characters into periods and cuts at 15.
        for name in ('PICTR.HOUSE', 'PICTR.MR..STERN', 'PICTR.MARK.S.AP', 'PICTR.', 'SAILBOAT',
                     'EIGHTBALL', 'TITLE', 'HELP'):
            for key in (0, 1):
                self.route(name, 6, SAVE_ADDR, SAVE_LEN, 'IMAGE', key, raw=True)
        # Graphics Exhibitor's own pictures are the same page at $2000.
        self.route('SAILING', 6, 0x2000, SAVE_LEN, 'IMAGE', 0, raw=True)
        # The Newsroom's photos share the address; their prefix still wins.
        self.route('PH.COBRA', 6, SAVE_ADDR, 2096, 'NEWSROOM', 0)

    def test_a_truncated_save_is_refused_and_leaves_no_file(self):
        # One archived save (PICTR.111) announces $1FF8 bytes and holds two
        # sectors: DOSGET must not hand the viewer a short page.
        save = micro_illustrator_save(picture(2))
        disk = bytearray(data_disk([('PICTR.SHORT', save)]))
        entry = dos_catalog(bytes(disk))[0]
        t, s = entry[2]
        at = (t * 16 + s) * 256
        disk[at + 12 + 4:at + 12 + 244] = bytes(240)          # two data sectors left
        ok, _f, _a, data = self.extract(bytes(disk), (entry[0], entry[1], entry[2], 3))
        self.assertFalse(ok)
        self.assertIsNone(data)

    def test_c64_and_atari_koala_files_are_not_apple_pictures(self):
        data = c64_koala()
        for name, typ, aux, size in (('PICA.KOALA', 6, 0x6000, 10003), ('PICA.KOALA', 6, 0, 10003),
                                     ('KOALA', 6, 0x6000, 10001), ('PICTR.C64', 6, 0x4000, 10003)):
            # Return opens it in hex; I would only ask IMAGE, which refuses it.
            (kind, viewer), = set(self.answers(name, typ, aux, size, 0, 0, data[:8]))
            self.assertEqual((kind, viewer), (0, 'HEX'), (name, typ, aux, size))
        # Untyped, it is not a picture either.
        (kind, viewer), = set(self.answers('PICA.KOALA', 0, 0, 10003, 0, 0, data[:8]))
        self.assertEqual(kind, 0)
        self.assertNotIn(viewer, ('IMAGE', 'NEWSROOM'))

    def test_the_archived_saves_copy_exactly_and_open_raw(self):
        disks = private_disks()
        if not disks:
            self.skipTest('no archived KoalaPad disk in ' + str(PRIVATE))
        saves = refused = 0
        for path in disks:
            disk = path.read_bytes()
            for entry in dos_catalog(disk):
                name, typ = entry[0], entry[1] & 0x7F
                if typ != 0x04 or not name.startswith('PICTR.'):
                    continue
                with self.subTest(disk=path.name, name=name):
                    expected = dos_bin(disk, entry[2])
                    if expected is None:          # a damaged save: refused, nothing written
                        ok, _f, _a, data = self.extract(disk, entry)
                        self.assertFalse(ok)
                        self.assertIsNone(data)
                        refused += 1
                        continue
                    self.assertEqual((expected[0], len(expected[1])), (SAVE_ADDR, SAVE_LEN))
                    self.check_save(disk, entry, expected[1])
                    saves += 1
        self.assertGreater(saves, 0)
        print(f'\n  {saves} archived Micro-Illustrator saves, {refused} damaged one(s) refused',
              flush=True)


if __name__ == '__main__':
    unittest.main()
