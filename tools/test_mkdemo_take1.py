#!/usr/bin/env python3
"""DEMO/MOVIES/TAKE1.DSK (tools/mkdemo_take1.py), from the panel to the end.

  Disk      the image A2 File Cmd opens: a DOS 3.3 140K disk whose catalog
            lists the movie's six binary files under their own names.
  Routing   Return on MV.DEMO in that catalog: the real classifier (C
            reference and src/open.s, both editions) answers RUN, and RUN's
            launcher (src/launch.h) hands TAKE1.SYSTEM the image path and
            the movie's T/S list.
  Reference tools/take1_ref.py plays the movie without a refusal, and every
            frame it shows holds, dot for dot, the picture intended: the
            background, the planted title, the car and the bird where the
            module puts them.
  Engine    the assembled engine (src/take1/engine.s, both processors)
            plays it to its end, byte for byte as the reference (the
            harness of tools/test_take1.py).
  System    TAKE1.SYSTEM, assembled here, from $2000 under sim65 with a
            fake MLI, given the launcher's command: it reads the image,
            plays the movie to its end, starts it again, and Escape takes
            it back to A2FILE.SYSTEM (tools/test_take1.py's SysSim).

The engine and the system need cc65 master (CC65_HEAD); without it they skip.
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import mkdemo_take1 as demo  # noqa: E402
import mkvolume  # noqa: E402
import take1_ref as ref  # noqa: E402
import test_take1  # noqa: E402

FILES = demo.files()
DSK = FILES[demo.HOST_NAME]
IMAGE = ref.DosImage(DSK)
HEAD = test_take1.HEAD
# the longer of the two XL volumes (A2XL6502, A2XL65C02)
IMAGE_PATH = '/A2XL65C02/DEMO/MOVIES/' + mkvolume.prodos_name(demo.HOST_NAME)[0]


def parts():
    """{DOS name: data} as TAKE1.SYSTEM reads them from the image."""
    return {name: IMAGE.read_file(*IMAGE.find(name)) for name in demo.parts()}


def catalog():
    """[(name as A2 File Cmd's panel shows it, ProDOS type, aux, size, T/S
    word)] -- read_dos33_panel (src/a2fc.c) on the image."""
    out = []
    t, s = IMAGE.sector(17, 0)[1:3]
    types = {0x00: 0x04, 0x01: 0xFA, 0x02: 0xFC, 0x04: 0x06}
    while t:
        sec = IMAGE.sector(t, s)
        t, s = sec[1], sec[2]
        for i in range(7):
            d = sec[11 + 35 * i:46 + 35 * i]
            if d[0] == 0:
                t = 0
                break
            if d[0] == 0xFF:
                continue
            name = bytes(c & 0x7F for c in d[3:33]).decode('latin-1').rstrip(' ') or ' '
            name = ''.join(c.upper() if c.isalnum() else '.' for c in name[:15])
            if not 'A' <= name[0] <= 'Z':
                name = 'X' + name[1:]
            sectors = d[0x21] | d[0x22] << 8
            out.append((name, types.get(d[2] & 0x7F, 0), 0, sectors << 8, d[0] << 8 | d[1]))
    return out


def movie_ts():
    return next(ts for name, _, _, _, ts in catalog() if name == demo.MOVIE)


class Disk(unittest.TestCase):
    def test_the_folder_holds_one_image(self):
        self.assertEqual(list(FILES), ['TAKE1.DSK#060000'])
        self.assertEqual(mkvolume.prodos_name(demo.HOST_NAME), ('TAKE1.DSK', 0x06, 0))
        self.assertEqual(len(DSK), 143360)
        self.assertEqual(FILES, demo.files(), 'the same bytes every time')

    def test_a2fc_opens_it_as_a_dos33_disk(self):
        # open_image: a .DSK suffix, whole blocks; read_panel: not ProDOS
        # (no volume header in block 2), then dos_vtoc_ok.
        self.assertTrue(IMAGE_PATH.endswith('.DSK') and len(DSK) % 512 == 0)
        block2 = IMAGE.sector(0, 11) + IMAGE.sector(0, 10)       # DOS order: block 2 = sectors 11, 10
        self.assertNotEqual(block2[4] >> 4, 0xF)
        vtoc = IMAGE.sector(17, 0)
        self.assertTrue(1 <= vtoc[3] <= 3 and 0 < vtoc[1] < 35 and vtoc[2] < 16)
        self.assertEqual((vtoc[0x34], vtoc[0x27]), (35, 0x7A))
        # the catalog: the movie first, its five parts, all binary files
        self.assertEqual([e[:2] for e in catalog()],
                         [('MV.DEMO', 6), ('SN.DEMO', 6), ('BK.MEADOW', 6), ('AC.CAR', 6),
                          ('AC.BIRD', 6), ('CS.FONT', 6)])
        for name, data in parts().items():
            self.assertEqual(data, demo.parts()[name], name)
        # what the binary headers say: the editor's load addresses
        for name in demo.parts():
            t, s = IMAGE.find(name)
            ts = IMAGE.sector(t, s)
            first = IMAGE.sector(ts[12], ts[13])
            self.assertEqual(first[0] | first[1] << 8, demo.LOAD[name[:3].decode()], name)


class Routing(unittest.TestCase):
    def test_return_on_the_movie_goes_to_run(self):
        import test_file_viewers
        h = test_file_viewers.FileViewers
        h.setUpClass()
        self.addCleanup(h.tearDownClass)
        fv = h('test_take1_movies_go_to_run')
        for name, typ, aux, size, _ in catalog():
            answers = {chosen for _, chosen in fv.answers(name, typ, aux, size)}
            if name == demo.MOVIE:
                self.assertEqual(answers, {'RUN'})
            else:
                self.assertNotIn('RUN', answers, name)

    def test_run_hands_take1_system_the_image_and_the_movie(self):
        import test_launch
        h = test_launch.Launch
        h.setUpClass()
        self.addCleanup(h.tearDownClass)
        lc = h('test_take1_movie_commands')
        out = lc.run_case(kind=6, disk_type=255, cfg='/TOOLS/A2FILE/A2FILE.CFG', path=IMAGE_PATH,
                          panel_aux=0, env={'T1_NAME': demo.MOVIE, 'T1_FS': '2',
                                            'T1_IMGLEN': str(len(IMAGE_PATH)), 'T1_KEY': '0',
                                            'T1_MDATE': str(movie_ts())})
        self.assertEqual(out[:3], ['1', '/TOOLS/A2FILE/TAKE1.SYSTEM', '%s,%04X' % (IMAGE_PATH, movie_ts())])
        self.assertLessEqual(len(out[2]), 46)


# -- the frames intended ----------------------------------------------------------------

def dots_of(page):
    """[row][dot] of a page's visible dots (bit 7 aside)."""
    out = []
    for y in range(192):
        a = demo.row_offset(y)
        out.append([page[a + x // 7] >> (x % 7) & 1 for x in range(280)])
    return out


def paint(rows, art, left, top):
    """An outlined snapshot as the module's art means it."""
    for r, line in enumerate(art):
        y = top + r
        put = {}
        for start, run in demo.runs(line):
            put[start - 1] = 0
            for k, c in enumerate(run):
                put[start + k] = 1 if c == '#' else 0
            put[start + len(run)] = 0
        for k, v in put.items():
            if 0 <= y < 192 and 0 <= left + k < 280:
                rows[y][left + k] = v


def intended(i):
    """The dots of frame i: background, title, car, bird."""
    rows = dots_of(demo.background())
    x0, y0 = demo.TITLE_AT
    for n, ch in enumerate(demo.TITLE.decode()):
        glyph = demo.GLYPHS.get(ch)
        for r in range(7 if glyph else 0):
            for c in range(10):
                if glyph[r][c // 2] == '#':
                    rows[y0 + r][x0 + 12 * n + c] ^= 1
    paint(rows, demo.CAR[i % 2], demo.car_x(i), demo.CAR_TOP)
    paint(rows, demo.BIRD[i % 2], demo.bird_x(i), demo.BIRD_TOP)
    return rows


def reference_play():
    """(frames shown, events) of the reference: the first frame is the page
    the fade-in leaves, the others are shown."""
    pp = parts()
    movie = pp.pop(demo.MOVIE.encode())
    player = ref.Player(movie, ref.dict_loader(pp), movie_name=demo.MOVIE.encode())
    events = list(player.play())
    shown, last = [], None
    for e in events:
        if e[0] == 'show':
            if not shown:
                shown.append(last)
            shown.append(e[-1])
        elif e[0] == 'delay':
            last = e[-1]
    return shown, events


class Reference(unittest.TestCase):
    def test_the_frames_are_the_ones_intended(self):
        shown, events = reference_play()
        self.assertEqual(len(shown), demo.NFRAMES)
        for i, page in enumerate(shown):
            self.assertEqual(dots_of(page), intended(i), 'frame %d' % i)
        self.assertEqual([e for e in events if e[0] in ('fade', 'fc')],
                         [('fade', demo.FADE_IN), ('fc', 2, demo.HORN_SOUND), ('fc', 1, demo.END_PAUSE),
                          ('fade', demo.FADE_OUT)])
        # the title stays (planted) after the actors have left
        bg = dots_of(demo.background())
        self.assertNotEqual(dots_of(shown[-1])[10:17], bg[10:17])
        self.assertEqual(dots_of(shown[-1])[17:], bg[17:])
        # the fade-out ends on a black screen; the movie is over
        last = [e for e in events if e[0] == 'delay'][-1][-1]
        self.assertEqual(sum(map(sum, dots_of(last))), 0)
        self.assertEqual(events[-1], ('end',))

    def test_the_background_decodes_to_the_page(self):
        self.assertEqual(bytes(ref.decode_bk(parts()[b'BK.MEADOW'])), demo.background())


# -- the real player ----------------------------------------------------------------------

class Engine(unittest.TestCase):
    def test_the_engine_plays_it_as_the_reference(self):
        h = test_take1.Take1
        h.setUpClass()                       # (skips without cc65 master)
        self.addCleanup(h.tearDownClass)
        t1 = h('test_synthetic')
        pp = parts()
        movie = pp.pop(demo.MOVIE.encode())
        shown, _ = reference_play()
        for cpu in ('6502', '65c02'):
            res, refused = t1.compare(cpu, movie, pp, '%s demo' % cpu)
            self.assertIsNone(refused)
            self.assertEqual(res['code'], 0, cpu + ': t1_play returned cleanly')
            pages = [e[-1] for e in res['events'] if e[0] == 'show']
            self.assertEqual(pages, shown[1:], cpu)


def build_take1(out):
    """TAKE1.SYSTEM.SYS assembled as the Makefile does, into out."""
    env = dict(os.environ, CC65_HOME=str(HEAD / 'share/cc65'))
    objs = []
    for name in ('take1', 'dos', 'engine'):
        o = out / (name + '.o')
        subprocess.run([str(HEAD / 'bin/ca65'), '-t', 'apple2', '--cpu', '6502', '-o', str(o),
                        str(ROOT / 'src/take1' / (name + '.s'))], check=True, env=env)
        objs.append(str(o))
    binary = out / 'TAKE1.SYSTEM.SYS'
    subprocess.run([str(HEAD / 'bin/ld65'), '-C', str(ROOT / 'src/take1/take1.cfg'), '-o', str(binary)] + objs,
                   check=True, env=env)
    return binary.read_bytes()


class System(unittest.TestCase):
    def test_take1_system_plays_it_from_the_image_and_returns(self):
        if not (HEAD / 'bin/sim65').exists():
            self.skipTest('cc65 master (CC65_HEAD) is needed')
        tmp = tempfile.TemporaryDirectory(prefix='a2fc-demo-take1-')
        self.addCleanup(tmp.cleanup)
        work = Path(tmp.name)
        (work / 'run').mkdir()
        sim = test_take1.SysSim(work / 'run', build_take1(work))
        command = '%s,%04X' % (IMAGE_PATH, movie_ts())
        ts = movie_ts()
        movie_list = (16 * (ts >> 8) + (ts & 255)) * 256
        # one pass reads the movie and its five parts; Escape arrives while
        # the third pass loads them: two whole plays, the 2-second hold
        # between them included
        res = sim.run(command, {IMAGE_PATH: DSK}, escape_at=200)
        sys_check = test_take1.System('test_play_and_escape')
        sys_check.common(res, 'demo')       # read-only, bitmap given back, A2FILE.SYSTEM loaded
        marks = [a | b << 16 for c, a, b in res['calls'] if c == 0xCE]
        self.assertGreaterEqual(marks.count(movie_list), 2, 'the movie started again: it played to its end')
        for name in demo.parts():
            t, s = IMAGE.find(name)
            self.assertIn((16 * t + s) * 256, marks, name)
        rows = test_take1.text_rows(res['text'])
        self.assertFalse(any('TAKE 1' in r or 'FILE' in r for r in rows), rows)   # no refusal


if __name__ == '__main__':
    unittest.main()
