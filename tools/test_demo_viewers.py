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
import test_gmagic  # noqa: E402
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
CARDS = FILES['PICTURES/CARDS']
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
        rc, out = h.decode(CARDS['EXTASIE#F20000'])
        self.assertEqual(rc, 0)
        self.assertEqual(visible(out[:8192]), visible(AUX))
        self.assertEqual(visible(out[8192:]), visible(MAIN))

    def test_packfot(self):
        h = self.harness(test_packfot.PackFot)
        rc, out = h.decode(CARDS['PACKFOT#084000'])
        self.assertEqual((rc, out[:8192]), (0, HGR))

    def test_paint816(self):
        h = self.harness(test_paint816.Paint816)
        rc, out = h.decode(CARDS['PAINT816#06E002'], 2)
        self.assertEqual(rc, 0)
        h.pic(out[:8192], AUX)
        h.pic(out[8192:], MAIN)

    def test_dgrview(self):
        h = self.harness(test_dgrview.DgrView)
        for name, wide in (('LORES.DGR#060000', 0), ('DLORES.DGR#060000', 1)):
            shown, got_wide, note, aux, main = h.view(CARDS[name])
            self.assertEqual((shown, got_wide), (1, wide), note)
            self.assertIn('80 x 48' if wide else '40 x 48', note)
            self.assertNotEqual(main, bytes(1024))

    def test_lz4fh_and_print_shop(self):
        h = self.harness(test_sample_media.SampleMedia)
        lz = CARDS['LZ4FH#088066']
        self.assertEqual(test_sample_media.lz_page(lz), HGR)
        h.run_file('lz4fh', lz, expected=HGR)
        clip = FILES['PICTURES']['APPLE.PRINTSHOP#064800']
        h.run_file('printshop', clip, expected=test_sample_media.clip_page(clip))

    def test_newsroom(self):
        h = self.harness(test_newsroom.Newsroom)
        for cpu in h.programs:
            with self.subTest(cpu=cpu):
                h.good(cpu, FILES['PICTURES']['PH.SUNSET#064000'])

    def test_gmagic(self):
        h = self.harness(test_gmagic.Gmagic)
        data = FILES['PICTURES']['HOUSE.GMAGIC#064000']
        ref = test_gmagic.ref
        for cpu in ('6502', '65c02'):
            with self.subTest(cpu=cpu):
                r = h.run_gm(cpu, data, 'NND')
                self.assertEqual(r.pages, [ref.view(data, ref.V82, 0, 0), ref.view(data, ref.V82, 1, 1),
                                           ref.view(data, ref.V82, 2, 2), ref.view(data, ref.V84, 2, 2)])

    def test_arlequin(self):
        h = self.harness(test_arlequin.Arlequin)
        data = CARDS['ARLEQUIN#F80000']
        for cpu in h.programs:
            with self.subTest(cpu=cpu):
                h.check(cpu, data)
        aux, main = test_arlequin.ref.screen(data)
        self.assertEqual((visible(aux), visible(main)), (visible(AUX), visible(MAIN)))

    def test_purple(self):
        h = self.harness(test_purple.Purple)
        a, b = CARDS['PURPLE.FOTO1#062000'], CARDS['PURPLE.FOTO2#062000']
        for selected in (1, 2):
            stats, main, aux = h.run_pair(a, b, selected=selected)
            self.assertEqual(stats, [2, 2, 1, 1, 1, 1, 5])      # double hi-res, /RAM rebuilt
            self.assertEqual((main, aux), (b, a))
        self.assertEqual((visible(a), visible(b)), (visible(AUX), visible(MAIN)))

    def test_movie_maker_sheet(self):
        sheet = CARDS['MOVIEMAKER.SHP#061DF0']
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
        for name, first, last in (('LETTRE.EPISTOLE#040000', 'A2 FILE CMD', 'Seconde page.'),
                                  ('NOTE.PAPYRUS#040000', 'PAPYRUS ET HOMEWORD', 'Page deux.')):
            pages = h.pages(FILES['DOCUMENTS'][name])
            self.assertEqual((len(pages), pages[0]['done'], pages[0]['bad']), (1, 1, 0), name)
            rows = [r.strip() for r in pages[0]['rows'] if r.strip()]
            self.assertEqual((rows[0], rows[-1]), (first, last), name)
            self.assertTrue(set(rows[-2]) == {'-'}, name)      # the page break, drawn as a rule
        # Epistole: the title centred, the letter itself not; the variable
        # is shown by its name.
        rows = [r.rstrip() for r in h.pages(FILES['DOCUMENTS']['LETTRE.EPISTOLE#040000'])[0]['rows'] if r.strip()]
        self.assertTrue(rows[0].startswith(' ' * 20) and rows[1].strip() == 'DOCVIEW')
        self.assertIn('Cher NOM,', rows[2])
        self.assertFalse(rows[2].startswith(' ' * 20))

    def test_integer_and_business_basic(self):
        h = self.harness(test_intbasic.IntBasic)
        status, lines = h.run_list(FILES['PROGRAMS']['HELLO.INT#FA0000'])
        self.assertEqual(status, 0)
        self.assertEqual(test_intbasic.listing(FILES['PROGRAMS']['HELLO.INT#FA0000'])[:3], lines[:3])
        self.assertIn('PRINT "HELLO FROM INTEGER BASIC"', lines[1])
        listing, ended = busbasic_ref.listing(FILES['PROGRAMS']['HELLO.BA3#090000'])
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

    def test_hrcg_font(self):
        """BOLD.SET: a DOS Tool Kit character set (BIN, 768 bytes), shown
        by FONTVIEW as a hi-res font."""
        h = self.harness(test_fontview.FontView)
        font = FILES['FONTS.SHAPES']['BOLD.SET#068100']
        self.assertEqual(len(font), 768)
        h.shows(font, test_fontview.raw_page(font), ftype=6)

    def test_text_screen(self):
        """TITLE.SCREEN: a text page, which DGRVIEW shows as text."""
        h = self.harness(test_dgrview.DgrView)
        shown, wide, note, aux, main = h.view(FILES['PICTURES']['TITLE.SCREEN#060400'], aux=0x0400)
        self.assertEqual((shown, wide, h.state['text']), (1, 0, 1), note)
        self.assertIn('Text screen, 40 columns', note)

    def test_pascal_and_cpm_disks(self):
        vol = pascal_ref.volume(FILES['DISKS']['PASCAL.PO#060000'])
        self.assertIn('HELLO.TEXT', str(vol))
        cpm = cpm_ref.volume(FILES['DISKS']['CPM.PO#060000'])
        self.assertIn('HELLO', str(cpm))

    # -- the formats of 0.9.5: the generators called directly, with the
    # host names (NAME#TTAAAA) their files are meant to be staged under.

    def routes(self, host, data, viewer, raw=False, pictures=(0,)):
        """The real classifier (the C reference, open.s under sim65 on both
        processors) sends `data`, staged as `host`, to `viewer`: Return,
        and I when `pictures` holds 1."""
        import mkvolume
        import test_file_viewers
        if not hasattr(self, 'classifier'):
            self.classifier = self.harness(test_file_viewers.FileViewers)
        h = self.classifier
        name, typ, aux = mkvolume.prodos_name(host)
        for picture in pictures:
            h.route(name, typ, aux, len(data), viewer, picture, raw=raw, data=data)

    def test_bank_street_writer(self):
        """MEMO.BANKSTREET: a Bank Street Writer document, laid out by DOCVIEW."""
        doc = demo.bank_street()
        self.routes('MEMO.BANKSTREET#060840', doc, 'DOCVIEW')
        h = self.harness(test_docview.Docview)
        pages = h.pages(doc)
        h.check_clean(pages)
        rows = [r.rstrip() for pg in pages for r in pg['rows'] if r.strip()]
        self.assertEqual(rows[0].index('BANK STREET WRITER'), (79 - 18) // 2, 'centred')
        self.assertTrue(rows[1].startswith('    A Bank Street Writer document'), 'a tab of four')
        text = bytes(c & 0x7F for c in doc[:doc.index(0)] if c not in (0x83, 0x89))
        self.assertEqual(h.words(pages), text.decode('ascii').split())

    def test_terrapin_logo(self):
        """FLOWER.LOGO, shown as text by its suffix; FLOWER.PICT, what it
        draws, 8,194 bytes: a raw page for IMAGE (load_image reads its first
        8,192 bytes into page 1)."""
        self.routes('FLOWER.LOGO#062000', demo.LOGO, 'TEXT')
        self.assertTrue(all(c == 13 or 32 <= c < 127 for c in demo.LOGO))
        pict = demo.logo_picture()
        self.assertEqual(len(pict), 8194)
        self.routes('FLOWER.PICT#062000', pict, 'IMAGE', raw=True, pictures=(0, 1))
        lit = lambda x, y: pict[mkdemo.hgr_offset(y) + x // 7] >> (x % 7) & 1
        self.assertTrue(lit(140, 96) and lit(140, 36) and lit(200, 36) and lit(200, 96))  # SQUARE 60
        self.assertFalse(lit(5, 5) or lit(274, 186))

    def test_koalapad_picture(self):
        """PICTR.BALLOON: 8,184 bytes at $4000, a page without its last hole:
        IMAGE's raw route, the whole visible screen in the file."""
        pic = demo.koala_picture()
        self.assertEqual(len(pic), 8184)
        self.routes('PICTR.BALLOON#064000', pic, 'IMAGE', raw=True, pictures=(0, 1))
        self.assertLessEqual(max(mkdemo.hgr_offset(r) + 40 for r in range(192)), len(pic))
        self.assertGreater(len(set(visible(pic + bytes(8)))), 8, 'a picture, not a fill')

    def test_beagle_font(self):
        """ITALIC.FONT: a Beagle Bros .FONT (BIN, 768 bytes), shown by
        FONTVIEW; not BOLD.SET's glyphs."""
        font = demo.italic_font()
        self.routes('ITALIC.FONT#064000', font, 'FONTVIEW', pictures=(0, 1))
        self.harness(test_fontview.FontView).shows(font, test_fontview.raw_page(font), ftype=6)
        a = demo.standard_font()[ord('A') * 8:ord('A') * 8 + 8]
        self.assertEqual(font[0x21 * 8:0x22 * 8], bytes([a[0] << 1, a[1] << 1, a[2] << 1, a[3], a[4], a[5],
                                                         a[6] >> 1, a[7] >> 1]))
        self.assertNotEqual(font, demo.hrcg_font())

    def test_eighty_column_text_screen(self):
        """WIDE.SCREEN: 2,048 bytes at $0400, which DGRVIEW shows as 80
        columns of text in the alternate (MouseText) set."""
        import textscreen_ref
        screen = demo.wide_text_screen()
        self.routes('WIDE.SCREEN#060400', screen, 'DGRVIEW', pictures=(0, 1))
        self.assertTrue(textscreen_ref.looks_text(screen))
        h = self.harness(test_dgrview.DgrView)
        shown, wide, note, aux, main = h.view(screen, aux=0x0400)
        self.assertEqual((shown, h.state['text'], h.state['alt']), (1, 1, 1), note)
        self.assertIn('Text screen, 80 columns', note)
        self.assertEqual((test_dgrview.visible(aux), test_dgrview.visible(main)),
                         (test_dgrview.visible(screen[:1024]), test_dgrview.visible(screen[1024:])))
        lines = textscreen_ref.render(screen)
        self.assertEqual(lines[4].strip(), '#' + ' ' * 25 + '## A2 File Cmd - 80 columns' + ' ' * 18 + '#')
        self.assertIn('Return shows it in 80 columns', lines[10])

    def test_newsroom_banner(self):
        """BN.DEMO.NEWS: a Newsroom banner, in the corpus's banner frame."""
        import newsroom_ref
        banner = demo.newsroom_banner()
        self.routes('BN.DEMO.NEWS#064000', banner, 'NEWSROOM', pictures=(0, 1))
        wb, rows, _ = newsroom_ref.parse(banner)
        self.assertEqual((wb, rows, tuple(banner[2:6])), (35, 80, (43, 122, 7, 246)))
        h = self.harness(test_newsroom.Newsroom)
        for cpu in h.programs:
            with self.subTest(cpu=cpu):
                h.good(cpu, banner)

    def test_newsroom_clip_art_disk(self):
        """CLIPART.DSK: a Newsroom clip-art disk, which NRCLIP turns into
        HOUSE and NIGHT, each page the drawings of clip_shapes at their
        place; a DOS 3.3 volume to A2FC (dos_vtoc_ok) with no free sector."""
        import newsroom_ref as ref
        import test_koala
        import test_nrclip
        disk = demo.clip_disk()
        shapes = demo.clip_shapes()
        self.assertEqual(ref.clip_index(disk), ('A2 FILE CMD DEMO', 1, list(shapes)))
        for locs, pieces in zip(ref.clip_table(disk, len(shapes)), shapes.values()):
            want = bytearray(8192)
            for y1, x1, h, w, white in pieces:
                for y in range(h):
                    for x in range(w):
                        if white(x, y):
                            X = x1 + x + ref.CLIP_LEFT
                            want[ref.row_address(y1 + y) + X // 7] |= 1 << (X % 7)
            self.assertEqual(ref.clip_page(disk, locs), bytes(want))
        vtoc = disk[17 * 4096:17 * 4096 + 256]
        self.assertEqual((vtoc[1], vtoc[2], vtoc[3], vtoc[0x27], vtoc[0x34]), (17, 1, 3, 0x7A, 35))
        self.assertEqual(vtoc[0x38:0x38 + 35 * 4], bytes(140), 'no free sector to write in')
        self.assertEqual([(n, t, ts) for n, t, ts, _ in test_koala.dos_catalog(disk)],
                         [('NEWSROOM CLIP ART: A2FC DEMO', 8, (0x24, 0xFF)),
                          ('COPY ITS PAGES WITH NRCLIP', 8, (0x24, 0xFF))])
        h = self.harness(test_nrclip.Nrclip)
        for cpu in h.programs:
            for kind in ('dsk', '2mg'):
                with self.subTest(cpu=cpu, kind=kind):
                    r = h.whole(cpu, disk, kind)
                    self.assertEqual(sorted(r.files), ['HOUSE', 'NIGHT'])


if __name__ == '__main__':
    unittest.main()
