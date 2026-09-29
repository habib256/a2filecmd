"""The DEMO files of tools/mkdemo_viewers.py, through each viewer's real code.

tools/test_file_viewers.py proves that every viewer gets a DEMO file; this
proves that each file is one its viewer shows, and shows right: the
harnesses of the viewers' own tests (host C, or the assembly under sim65 on
both processors) are run on the very bytes staged, and the screen they
leave is compared with the colour card or the reference decoder.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import busbasic_ref  # noqa: E402
import cpm_ref  # noqa: E402
import fantavision_ref  # noqa: E402
import mkdemo  # noqa: E402
import mkdemo_viewers as demo  # noqa: E402
import pascal_ref  # noqa: E402
import pt3_fixture  # noqa: E402
import test_arlequin  # noqa: E402
import test_docview  # noqa: E402
import test_extasie  # noqa: E402
import test_fontview  # noqa: E402
import test_intbasic  # noqa: E402
import test_newsroom  # noqa: E402
import test_packfot  # noqa: E402
import test_paint816  # noqa: E402
import test_purple  # noqa: E402
import test_sample_media  # noqa: E402
import test_unsq  # noqa: E402
import test_dgrview  # noqa: E402

FILES = demo.files()
HGR, AUX, MAIN = demo.cards()


def visible(page):
    """The 7,680 bytes on screen: the holes are nobody's business."""
    return b''.join(page[mkdemo.hgr_offset(r):mkdemo.hgr_offset(r) + 40] for r in range(192))


class DemoViewers(unittest.TestCase):
    def harness(self, cls):
        """An instance of a viewer's own test class, its programs built, none
        of its tests run: only its helpers are used."""
        cls.setUpClass()
        self.addCleanup(cls.tearDownClass)
        return cls(next(n for n in dir(cls) if n.startswith('test_')))

    def test_extasie(self):
        h = self.harness(test_extasie.Extasie)
        rc, out = h.decode(FILES['PICTURES']['EXTASIE#F20000'])
        self.assertEqual(rc, 0)
        self.assertEqual(visible(out[:8192]), visible(AUX))
        self.assertEqual(visible(out[8192:]), visible(MAIN))

    def test_packfot(self):
        h = self.harness(test_packfot.PackFot)
        rc, out = h.decode(FILES['PICTURES']['PACKFOT#084000'])
        self.assertEqual((rc, out[:8192]), (0, HGR))
        rc, out = h.decode(FILES['PICTURES']['PACKFOT.D#084001'], 2)
        self.assertEqual(rc, 0)
        self.assertEqual(visible(out[:8192]) + visible(out[8192:]), visible(AUX) + visible(MAIN))

    def test_paint816(self):
        h = self.harness(test_paint816.Paint816)
        rc, out = h.decode(FILES['PICTURES']['PAINT816#06E001'])
        self.assertEqual(rc, 0)
        h.pic(out, HGR)
        rc, out = h.decode(FILES['PICTURES']['PAINT816.D#06E002'], 2)
        self.assertEqual(rc, 0)
        h.pic(out[:8192], AUX)
        h.pic(out[8192:], MAIN)

    def test_dgrview(self):
        h = self.harness(test_dgrview.DgrView)
        for name, wide in (('LORES.DGR#060000', 0), ('DLORES.DGR#060000', 1)):
            shown, got_wide, note, aux, main = h.view(FILES['PICTURES'][name])
            self.assertEqual((shown, got_wide), (1, wide), note)
            self.assertIn('80 x 48' if wide else '40 x 48', note)
            self.assertNotEqual(main, bytes(1024))

    def test_lz4fh_and_print_shop(self):
        h = self.harness(test_sample_media.SampleMedia)
        lz = FILES['PICTURES']['LZ4FH#088066']
        self.assertEqual(test_sample_media.lz_page(lz), HGR)
        h.run_file('lz4fh', lz, expected=HGR)
        clip = FILES['PICTURES']['APPLE.CLIP#064800']
        h.run_file('printshop', clip, expected=test_sample_media.clip_page(clip))

    def test_newsroom(self):
        h = self.harness(test_newsroom.Newsroom)
        for cpu in h.programs:
            with self.subTest(cpu=cpu):
                h.good(cpu, FILES['PICTURES']['PH.SUNSET#064000'])

    def test_arlequin(self):
        h = self.harness(test_arlequin.Arlequin)
        data = FILES['PICTURES']['ARLEQUIN#F80000']
        for cpu in h.programs:
            with self.subTest(cpu=cpu):
                h.check(cpu, data)
        aux, main = test_arlequin.ref.screen(data)
        self.assertEqual((visible(aux), visible(main)), (visible(AUX), visible(MAIN)))

    def test_purple(self):
        h = self.harness(test_purple.Purple)
        a, b = FILES['PICTURES']['CARD.FOTO1#062000'], FILES['PICTURES']['CARD.FOTO2#062000']
        for selected in (1, 2):
            stats, main, aux = h.run_pair(a, b, selected=selected)
            self.assertEqual(stats, [2, 2, 1, 1, 1, 1, 5])      # double hi-res, /RAM rebuilt
            self.assertEqual((main, aux), (b, a))
        self.assertEqual((visible(a), visible(b)), (visible(AUX), visible(MAIN)))

    def test_movie_maker_sheet(self):
        sheet = FILES['PICTURES']['CARD.SHP#061DF0']
        self.assertEqual((len(sheet), sheet[528:]), (8720, HGR))

    def test_fantavision_movies_and_backdrop(self):
        movies = FILES['MOVIES']
        for name, count in (('M.BOUNCE#068400', 0), ('M.CURTAIN#068400', 2)):
            data = movies[name]
            self.assertIsNone(fantavision_ref.check(data), name)
            self.assertTrue(513 <= len(data) <= 9216)
            self.assertEqual((data[1], len(fantavision_ref.parse(data))), (count, 4))
            shown = list(fantavision_ref.Player(data).play(limit=40))
            self.assertGreater(len({bytes(p) for _, p, _ in shown}), 4, name)
        self.assertEqual(movies['CURTAIN#064000'], HGR)
        list(fantavision_ref.Player(movies['M.CURTAIN#068400'], movies['CURTAIN#064000']).play())

    def test_pt3_is_the_generated_fixture(self):
        tune, fixture = FILES['MUSIC']['DEMO.PT3#000000'], pt3_fixture.module(2048)
        self.assertEqual(tune[:30] + tune[62:66] + tune[98:], fixture[:30] + fixture[62:66] + fixture[98:])

    def test_documents(self):
        h = self.harness(test_docview.Docview)
        for name, first, last in (('EPISTOLE#040000', 'A2 FILE CMD', 'Seconde page.'),
                                  ('PAPYRUS#040000', 'PAPYRUS ET HOMEWORD', 'Page deux.')):
            pages = h.pages(FILES['DOCUMENTS'][name])
            self.assertEqual((len(pages), pages[0]['done'], pages[0]['bad']), (1, 1, 0), name)
            rows = [r.strip() for r in pages[0]['rows'] if r.strip()]
            self.assertEqual((rows[0], rows[-1]), (first, last), name)
            self.assertTrue(set(rows[-2]) == {'-'}, name)      # the page break, drawn as a rule
        # Epistole: the title centred, the letter itself not; the variable
        # is shown by its name.
        rows = [r.rstrip() for r in h.pages(FILES['DOCUMENTS']['EPISTOLE#040000'])[0]['rows'] if r.strip()]
        self.assertTrue(rows[0].startswith(' ' * 20) and rows[1].strip() == 'DOCVIEW')
        self.assertIn('Cher NOM,', rows[2])
        self.assertFalse(rows[2].startswith(' ' * 20))

    def test_integer_and_business_basic(self):
        h = self.harness(test_intbasic.IntBasic)
        status, lines = h.run_list(FILES['PROGRAMS']['HELLO.INT#FA0000'])
        self.assertEqual(status, 0)
        self.assertEqual(test_intbasic.listing(FILES['PROGRAMS']['HELLO.INT#FA0000'])[:3], lines[:3])
        self.assertIn('PRINT "HELLO FROM INTEGER BASIC"', lines[1])
        listing, ended = busbasic_ref.listing(FILES['PROGRAMS']['LEDGER.BA3#090000'])
        self.assertTrue(ended)
        self.assertEqual(listing[2], '30  PRINT "LISTED BY BASLIST"')

    def test_squeezed_archives(self):
        h = self.harness(test_unsq.Unsq)
        for name in ('SAMPLE.QQ', 'SAMPLE.ACU'):
            h.check(name, FILES['ARCHIVES'][name + '#000000'], typ=0)

    def test_mgtk_font(self):
        h = self.harness(test_fontview.FontView)
        font = FILES['FONTS.SHAPES']['MGTK.FONT#070000']
        h.shows(font, test_fontview.mgtk_page(font))

    def test_pascal_and_cpm_disks(self):
        vol = pascal_ref.volume(FILES['DISKS']['PASCAL.PO#060000'])
        self.assertIn('HELLO.TEXT', str(vol))
        cpm = cpm_ref.volume(FILES['DISKS']['CPM.PO#060000'])
        self.assertIn('HELLO', str(cpm))


if __name__ == '__main__':
    unittest.main()
