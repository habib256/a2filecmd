"""Run the actual image classifier and file-to-viewer dispatch for both CPU builds."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_six_plugins import ROOT, PREFIX

SOURCE = (ROOT / 'src/a2fc.c').read_text()


def section(start, end):
    """A slice of a2fc.c, without its #pragma lines (the pushes stay outside)."""
    text = SOURCE[SOURCE.index(start):SOURCE.index(end, SOURCE.index(start))]
    return '\n'.join(l for l in text.splitlines() if not l.lstrip().startswith('#pragma')) + '\n'


IMAGE = section('static unsigned char page_size(', '/* Buffered reading:')
TABLES = section('/* The tables of the classifier', "/* OPEN's entry point, open_entry")
# OPEN remains the resident neighbour classifier. IDENT dispatch is covered
# separately by test_fs_keys and the native automatic-reader benches.
OPEN_VIEWER = """static void open_viewer(unsigned char pictures) {
 input[0]=0;overlay_run("OPEN",pictures);if(input[0])overlay_run(input,0);
}
"""
REFERENCE = (ROOT / 'tools/file_viewer_ref.c').read_text()

# The same program twice: on the host with the C reference of the classifier
# (tools/file_viewer_ref.c), under sim65 with the real src/open.s. Both
# read the fixture through the harness's own fopen & co, which can fail.
COMMON = r"""
#include <stdint.h>
#include "src/a2fc_plugin.h"
#include "src/viewer_ids.h"
char input[64];
static char chosen[80];
char full[512];
unsigned char copy_buf[512];
struct Entry selected;
static unsigned char fail_open;
static unsigned char is_dir(const struct Entry* e) { return e->type == 0x0F; }
static void overlay_run(const char*, unsigned char);
void report_error(const char* what) { (void)what; strcpy(chosen, "ERROR"); }
""" + IMAGE + r"""
/* display.s, whose own test (test_display.py) runs the assembly. */
unsigned char __fastcall__ named_kind(const struct Entry* e) {
    if (e->type == 6 && e->aux == 0x1DF0 && e->size == 8720) return 1;
    if (e->type == 6 && e->aux == 0x8400 && e->size >= 513 && e->size <= 9216) return 8;
    return e->type == 6 && e->aux == 0x4000 && e->name[2] == '.' &&
        ((e->name[0] == 'P' && e->name[1] == 'H') || (e->name[0] == 'B' && e->name[1] == 'N')) ? 7 : 0;
}
IO
""" + TABLES + r"""
CLASSIFIER
""" + OPEN_VIEWER + r"""
static void overlay_run(const char* name, unsigned char arg) {
    static struct A2fcApi api;
    if (!strcmp(name, "OPEN")) {
        if (fail_open == 1) return;
        api.arg = arg; open_entry(&api);
    } else strcpy(chosen, name);
}
int main(int argc, char** argv) {
    if (argc == 1) {
        unsigned long size, high, value;
        unsigned char expected;
        for (high = 0; high < 3; ++high) for (size = 0; size < 65536UL; ++size) {
            value = size + (high == 1 ? 65536UL : high == 2 ? 0x80000000UL : 0);
            expected = !high && ((size >= 8184 && size <= 8199) || (size >= 16376 && size <= 16391));
            if (page_size(&value) != expected) return 1;
        }
        return 0;
    }
    strncpy(selected.name, argv[1], NAME_LEN - 1);
    selected.type = strtoul(argv[2], 0, 0); selected.aux = strtoul(argv[3], 0, 0);
    selected.size = strtoul(argv[4], 0, 0); fail_open = atoi(argv[6]);
    strcpy(full, argv[7]); strcpy(input, "RUN");
    memcpy(copy_buf, "DGR\1\x50\x30\1\0", 8); /* previous probe */
    if (argc > 8) strcpy((char*)copy_buf, argv[8]);  /* or what a viewer left */
    open_viewer(atoi(argv[5]));
    printf("%u %s\n", image_kind(&selected), chosen);
    return 0;
}
"""
HOST_IO = r"""
static FILE* probe_open(const char* path, const char* mode) {
    if (strcmp(mode, "rb")) abort();
    return fail_open == 2 ? NULL : fopen(path, mode);
}
static int probe_error(FILE* f) { return fail_open == 3 || ferror(f); }
static int probe_close(FILE* f) {
    int result = fclose(f);
    return fail_open == 4 ? EOF : result;
}
#define fopen probe_open
#define ferror probe_error
#define fclose probe_close
"""
HOST_CLASSIFIER = REFERENCE + r"""
#undef fopen
#undef ferror
#undef fclose
static unsigned char file_viewer(const struct Entry* e, unsigned char p) { return ref_file_viewer(e, p); }
#define open_entry ref_open_entry
"""
HOST = PREFIX + COMMON.replace('IO\n', HOST_IO).replace('CLASSIFIER\n', HOST_CLASSIFIER)
# sim65: open.s calls _fopen & co directly; the harness's own definitions
# win over the library's at link time.
SIM_IO = r"""
#include <fcntl.h>
#include <unistd.h>
static int hfd = -1;
FILE* __fastcall__ fopen(const char* p, const char* m) {
    if (strcmp(m, "rb")) abort();
    if (fail_open == 2) return 0;
    hfd = open(p, O_RDONLY);
    return hfd < 0 ? 0 : (FILE*)1;
}
size_t __fastcall__ fread(void* b, size_t s, size_t n, FILE* f) {
    int r = read(hfd, b, s * n);
    (void)f;
    return r < 0 ? 0 : (size_t)r / s;
}
int __fastcall__ ferror(FILE* f) { (void)f; return fail_open == 3; }
int __fastcall__ fclose(FILE* f) { (void)f; close(hfd); return fail_open == 4 ? EOF : 0; }
"""
SIM = r"""#include <string.h>
#include <stdlib.h>
#include <stdio.h>
""" + COMMON.replace('IO\n', SIM_IO).replace(
    'CLASSIFIER\n', 'unsigned char __fastcall__ file_viewer(const struct Entry*, unsigned char);   /* open.s */\n'
    'void __fastcall__ open_entry(const struct A2fcApi*);                       /* open.s */\n')


class FileViewers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='viewer-routes-')
        cls.root = Path(cls.tmp.name)
        (cls.root / 'host.c').write_text(HOST)
        (cls.root / 'sim.c').write_text(SIM)
        # A copy under OPEN's segments renamed for the simulator's layout.
        (cls.root / 'open.s').write_text((ROOT / 'src/open.s').read_text()
                                         .replace('"OPENRO"', '"RODATA"').replace('"OPEN"', '"CODE"'))
        cls.exes = []
        for cpu in ('6502', '65c02'):
            exe = cls.root / cpu
            subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-I', str(ROOT),
                            *(['-DA2FC_6502'] if cpu == '6502' else []),
                            str(cls.root / 'host.c'), '-o', str(exe)], check=True, capture_output=True)
            cls.exes.append([str(exe)])
        for cpu, target in (('6502', 'sim6502'), ('65c02', 'sim65c02')):
            exe = cls.root / ('sim' + cpu)
            subprocess.run(['cl65', '-t', target, '-I', str(ROOT), '-O',
                            *(['-DA2FC_6502'] if cpu == '6502' else []),
                            '-o', str(exe), str(cls.root / 'sim.c'), str(cls.root / 'open.s')],
                           check=True, capture_output=True, cwd=cls.root)
            cls.exes.append(['sim65', str(exe)])

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def answers(self, name, typ, aux, size, picture=0, fail=0, data=bytes(8), stale=None):
        """What each build answers: [kind, viewer] for the host reference
        (6502, 65C02 defines) and the assembly under sim65 (both CPUs).
        `stale`: the bytes copy_buf holds before the probe (a previous
        probe's otherwise)."""
        fixture = self.root / 'picture'
        fixture.write_bytes(data)
        out = []
        for exe in self.exes:
            result = subprocess.check_output(exe + [name, str(typ), str(aux), str(size), str(picture),
                                                    str(fail), str(fixture)] + ([stale] if stale else []),
                                             text=True, timeout=30)
            result = result.strip().split(' ', 1)
            out.append((int(result[0]), result[1] if len(result) > 1 else ''))
            self.assertEqual(fixture.read_bytes(), data)
        return out

    def route(self, name, typ, aux, size, expected, picture=0, fail=0, raw=False, data=bytes(8), stale=None):
        with self.subTest(name=name, typ=typ, aux=aux, size=size, picture=picture, fail=fail, stale=stale):
            for (kind, chosen), exe in zip(self.answers(name, typ, aux, size, picture, fail, data, stale),
                                           self.exes):
                self.assertEqual(chosen, expected, exe[-1])
                self.assertEqual(kind == 1, raw, 'the raw album must skip specialized formats')

    def test_the_assembly_answers_as_the_reference_does(self):
        # Random entries built from the values each rule looks at, and their
        # neighbours: the four builds (the C reference with each edition's
        # defines, open.s under sim65 on each processor) must agree.
        import random
        rng = random.Random(1986)
        names = ['A', 'X.MB', 'SONG.PT3', 'T.ED', '.ED', 'P.FOTO1', 'P.FOTO2', 'MAC.MAC', 'S.AS',
                 'X.BSC', 'X.BSQ', 'S.SHAPE', 'A.QQ', 'D.ACU', 'P.BA3', 'M.SONG', 'M.', 'PH.CAT',
                 'BN.SUN', 'PN.X', 'DOG.SHP', 'LONGNAMEXX.FOTO1', 'X.RLE', 'RLE', 'M.APPLE', 'EPISTOLE',
                 'MV.SHUTTLE.DISC', 'MV.', 'MV', 'MW.X', 'NV.X', 'MVX', 'ROCKET.LOGO', '.LOGO',
                 'A.LOGOX', 'INSPI.PICT', 'ASCII.SET', '.SET', 'GOTHIC.FONT', 'X.SETS', 'CHR.STS']
        types = [0x00, 0x04, 0x06, 0x07, 0x08, 0x09, 0x19, 0x1A, 0x1B, 0xC0, 0xD5, 0xE0, 0xF2, 0xF8,
                 0xFA, 0xFC, 0xFF, 0x0F]
        auxes = [0, 1, 0x0400, 0x1DF0, 0x2000, 0x4000, 0x4001, 0x4800, 0x5800, 0x7800, 0x4801, 0x8066,
                 0x8400, 0xD0E7, 0xE001, 0xE002, 0x0801, 0x8029, 0x8028, 0x0029, 0x0840, 0x63D0]
        sizes = [0, 1, 8, 572, 576, 574, 767, 768, 769, 1023, 1024, 1025, 768 + 65536, 2048, 2049, 2096, 8183, 8184, 8186, 8188, 8191, 8192, 8194, 8196, 8199, 8200,
                 8720, 16384, 16376, 16386,
                 65536 + 572, 70000]
        datas = [bytes(8), b'DGR\1\x50\x30\1\0', b'DG', b'\0\0gsXXXX', b'HGRR\1\0\0\x20',
                 b'DHRR\1\0\0\x40', b'HGRR\1\0\0\x21', b'_MG10_MD', b'\xffabc', b'\x7f', b'',
                 b'\1\2\3\4\5\6\7\x08', b'\1\0\0\0\5\6\7\x08', b'ab',
                 b'\x83\xc7\xe5\xf9\xf3\xe5\xf2\xf3', b'\xc1\xc2\x8d', b'\xc1\x41\xc3',
                 bytes.fromhex('2280000AA1170A25'), bytes.fromhex('600FE00A0A00'), b'\x24\x80\x00',
                 bytes.fromhex('2041102000'), b'\x24\x28\x00', b'\x20\x22\x24\x26']
        for case in range(300):
            args = (rng.choice(names), rng.choice(types), rng.choice(auxes), rng.choice(sizes),
                    rng.choice([0, 0, 1, 2, 3, 4]), rng.choice([0, 0, 0, 2, 3, 4]), rng.choice(datas))
            with self.subTest(case=case, args=args):
                answers = self.answers(*args)
                self.assertEqual(len(set(answers)), 1, answers)

    def test_all_page_sizes_and_high_words(self):
        for exe in self.exes[:2]: subprocess.run(exe, check=True)

    def test_specialized_images_use_their_decoder_for_return_and_i(self):
        for typ, aux, size, viewer in [(0xF2, 0, 4012, 'EXTASIE'),
                (0x08, 0x4000, 64, 'PACKFOT'), (0x08, 0x4001, 128, 'PACKFOT'),
                (0x06, 0xE001, 123, 'PAINT816'), (0x06, 0xE002, 6130, 'PAINT816'),
                (0x06, 0x0400, 1016, 'DGRVIEW'), (0x08, 0x0400, 2032, 'DGRVIEW')]:
            for picture in (0, 1):
                self.route('PICTURE', typ, aux, size, viewer, picture)

    def test_sample_media_dispatch(self):
        for picture in (0, 1):
            self.route('DIP.CHIPS', 8, 0x8066, 3785, 'LZ4FH', picture)
            self.route('PACKED.PAGE', 8, 0x8066, 8192, 'LZ4FH', picture)
            self.route('SYSTEM.EN', 7, 0, 1283, 'FONTVIEW', picture)
            for aux in (0x4800, 0x5800, 0x6800, 0x7800):
                for size in (572, 576):
                    self.route('CLIP', 6, aux, size, 'PRINTSHOP', picture)
        for name in ('WOZ.BREAKOUT', 'APPLEVISION'):
            self.route(name, 0xFA, 0, 1859, 'RUN')
        self.route('AUTUMN.PT3', 0, 0, 4461, 'PT3')
        self.route('OTHER.BIN', 6, 0x2000, 576, 'HEX')

    def test_hrcg_fonts_by_suffix_and_size(self):
        """DOS Tool Kit character sets (.SET) and Beagle's copies (.FONT):
        BIN files of 768 bytes (96 glyphs) or 1,024 (128) -- 244 + 116 of
        them in a 1,892-disk Asimov sample, with no other file matching both
        the suffix and the size. A .SET of another size (CommunityLink's
        8,192-byte PIC.SET picture, a 1,028-byte plot) or type keeps its
        usual viewer."""
        for picture in (0, 1):
            for name in ('ASCII.SET', 'GOTHIC.FONT'):
                for aux in (0x8100, 0x4000, 0):
                    for size in (768, 1024):
                        self.route(name, 6, aux, size, 'FONTVIEW', picture)
        self.route('PIC.SET', 6, 0x2000, 8192, 'IMAGE', raw=True)
        self.route('PLOT.SET', 6, 0x4000, 1028, 'HEX')
        self.route('ASCII.SET', 6, 0x8100, 769, 'HEX')
        self.route('ASCII.SET', 6, 0x8100, 768 + 65536, 'HEX')
        self.route('NOTES.SET', 4, 0, 768, 'TEXT')
        self.route('.SET', 6, 0, 768, 'HEX')                  # nothing before the suffix
        self.route('ASCII.STS', 6, 0x6100, 768, 'HEX')        # Graphics Magician's: not routed
        self.route('ASCII', 6, 0x8100, 768, 'HEX')            # a plain 768-byte BIN stays HEX

    def test_newsroom_photos_and_banners(self):
        for picture in (0, 1):
            for name in ('PH.CAT', 'BN.SUN', 'PH.'):
                self.route(name, 6, 0x4000, 2096, 'NEWSROOM', picture)
            # Even a size that looks like a hi-res page: the name says more.
            self.route('PH.MAP', 6, 0x4000, 8192, 'NEWSROOM', picture)
        # Panels and pages, other load addresses and types keep their viewer.
        for name, typ, aux, viewer in (('PN.CAT', 6, 0x4000, 'HEX'), ('PG.PAGE', 6, 0x4000, 'HEX'),
                                       ('PH.CAT', 6, 0x2000, 'HEX'), ('PH.CAT', 4, 0x4000, 'TEXT'),
                                       ('PHOTO', 6, 0x4000, 'HEX'), ('XPH.CAT', 6, 0x4000, 'HEX')):
            self.route(name, typ, aux, 2096, viewer)
        self.route('PH.SONG.PT3', 6, 0x4000, 2096, 'PT3')   # a music suffix says more

    def test_movie_maker_backgrounds_and_shape_sheets(self):
        for picture in (0, 1):
            self.route('LAKE.BKG', 6, 0x4000, 8192, 'IMAGE', picture, raw=True)
            self.route('DOG.SHP', 6, 0x1DF0, 8720, 'IMAGE', picture, raw=True)
        self.route('DOG.SHP', 6, 0x1DF0, 8719, 'HEX')
        self.route('DOG.SHP', 6, 0x2000, 8720, 'HEX')
        self.route('DOG.ANI', 6, 0x6000, 7240, 'HEX')

    def test_epistole_and_papyrus_documents_go_to_docview(self):
        self.route('EXEMPLE.LETTRE', 4, 0, 1229, 'DOCVIEW', data=b'_MG10_MD65_JD\r')
        self.route('JARDINS', 4, 0, 922, 'DOCVIEW', data=b'\xff\x0d\x07\x05\xff\xff\x06\xff')
        for data in (b'Hello world\r', b'\xa0\xa0LIONS\x8d', b'#NOM]\r', b''):
            self.route('LETTRE', 4, 0, len(data), 'TEXT', data=data)
        self.route('NOTTEXT', 6, 0, 13, 'HEX', data=b'_MG10_MD65_JD')

    def test_visicalc_worksheets_go_to_visicalc(self):
        # A /SS file starts with its last cell, `>B3:`; DOS 3.3 writes it
        # with the high bit set. VISICALC checks the rest of the file.
        self.route('BUDGET', 4, 0, 730, 'VISICALC', data=b'>D19:/F-"-\r')
        self.route('BUDGET.VC', 4, 0, 730, 'VISICALC', data=bytes(c | 0x80 for c in b'>A1:5\r/W1'))
        self.route('NOTES', 4, 0, 9, 'TEXT', data=b'A1:>B2\r')
        self.route('WORKSHEET', 6, 0, 8, 'HEX', data=b'>A1:5\r/W')

    def test_graphics_magician_pictures_go_to_gmagic(self):
        # A BIN whose first commands are picture commands
        # (docs/GRAPHICS-MAGICIAN-FORMAT.md, section 3); GMAGIC checks
        # the whole file. Return only: I keeps its own rules.
        h02 = bytes.fromhex('2280000AA1170A25A0001480001EA1171E00')
        for aux in (0x4000, 0x6800, 0x6000, 0x1201, 0):
            self.route('R12', 6, aux, len(h02), 'GMAGIC', data=h02[:8])
        for data in (bytes.fromhex('600FE00A0A00'),             # G01's first: ends early
                     bytes.fromhex('24800A0AA0C89600'),
                     bytes.fromhex('A0001480000A00'),            # a line, then its start (rule 4)
                     bytes.fromhex('8000A08000AA8000'),          # two line starts in a row
                     bytes.fromhex('80004BA0324BA032'),          # the same line twice, not at once
                     bytes.fromhex('A03468E0C7A42146'),          # R02: lines before the start
                     bytes.fromhex('26A01E7746E00DB0'),          # R58
                     bytes.fromhex('605CE0EC9F605B47'),          # pattern, fill, pattern, brush
                     bytes.fromhex('80976780EC852323'),          # R31: a colour twice
                     bytes.fromhex('2020800014A00014')):         # a colour twice, a line
            self.route('PICTURE', 6, 0x4000, max(len(data), 9), 'GMAGIC', data=data[:8])
        for data in (b'',                                       # nothing read
                     b'\x00' + h02[:7],                          # the end byte first
                     b'\xC0\x10\x10\x00',                         # a brush first
                     b'\xE0\x10\x10\x00', b'\x10\x10\x10\x00', b'\x30A\x00', b'\x50A\x00',
                     b'\x28\x00',                                 # colour 8
                     b'\x24\x48\x00',                             # brush 8
                     b'\x24\x61\x05\x00',                         # a pattern nibble
                     b'\x24\x82\x00\x0A\x00',                     # X high part 2
                     b'\x24\x70\x00', b'\x24\x90', b'\x24\xB1', b'\x24\xD0', b'\x24\xF0', b'\x24\x01',
                     b'\x24\x80\x00',                             # a short file, no end
                     b'\x26\x00', b'\x60\x05\x00',                  # draw nothing (rule 5)
                     bytes.fromhex('204110200000'),              # colour, brush, text cursor
                     bytes.fromhex('243041504100'),              # XOR text, text
                     bytes.fromhex('8000BF6000') + b'\0\0\0',     # a line start alone
                     bytes.fromhex('A1170A2000'),                # a line without its start (rule 4)
                     bytes.fromhex('26A0001400'),
                     # Programs and data that start like pictures, which
                     # Return opened in GMAGIC (a refusal) instead of HEX:
                     bytes.fromhex('A000B900B09900D0'),          # LDY #0, LDA abs,Y: a line, the end
                     bytes.fromhex('A000A900853CA910'),          # LDY #0, LDA #0
                     bytes.fromhex('8000000000000000'),          # a line start, the end
                     bytes.fromhex('8080808080808080'),          # a table of $80: one start, again
                     bytes.fromhex('A0A0A0A0A0A0A0A0'),
                     bytes.fromhex('80FF0080FF0080FF'),          # 80 FF 00 repeated
                     bytes.fromhex('2020202020202020'),          # spaces
                     bytes.fromhex('2222222222222222'),
                     bytes.fromhex('4040404040404040'),
                     bytes.fromhex('2030142030142030'),          # three bytes repeated
                     b'\x20\x22\x24\x26',
                     b'\x20\x58\xFC\x20\x00\xBF\xC8\x03',            # JSR HOME, JSR MLI
                     b'\x4C\x00\x40\x00', b'\xA9\x00\x8D\x00'):
            self.route('PROGRAM', 6, 0x4000, max(len(data), 1), 'HEX', data=data)
        # Not for other types, not for I, and a picture page wins.
        self.route('R12', 4, 0, len(h02), 'TEXT', data=h02[:8])
        self.route('R12', 0, 0, len(h02), 'HEX', data=h02[:8])
        self.route('R12', 6, 0x4000, len(h02), 'DGRVIEW', picture=1, data=h02[:8])   # I: a lo-res pixmap
        self.route('R12', 6, 0x2000, 8192, 'IMAGE', raw=True, data=h02[:8])
        for fail in (2, 3, 4):
            self.route('R12', 6, 0x4000, len(h02), 'ERROR', fail=fail, data=h02[:8])

    def test_every_specified_picture_goes_to_gmagic(self):
        # Appendix B of docs/GRAPHICS-MAGICIAN-FORMAT.md (every picture
        # GMAGIC accepts, the random ones drawing lines before their first
        # line start) and DEMO's HOUSE.GMAGIC: the stricter probe of 0.9.5 must
        # not lose one. Return is the only way to GMAGIC: a picture the
        # probe misses only shows in hex.
        import sys
        sys.path.insert(0, str(ROOT / 'tools'))
        import gmagic_ref
        import mkdemo_viewers
        pictures = dict(gmagic_ref.corpus(), DEMO=mkdemo_viewers.gmagic())
        accepted = 0
        for name, data in pictures.items():
            try:
                gmagic_ref.parts(data)
            except gmagic_ref.Malformed:
                continue                                # H01 and the empty random ones
            accepted += 1
            self.route('R12', 6, 0x4000, len(data), 'GMAGIC', data=data[:8])
        self.assertGreaterEqual(accepted, 40)

    def test_an_empty_text_file_ignores_stale_probe_bytes(self):
        # VISICALC reads its worksheet into copy_buf, which OPEN's probe
        # also reads into: an empty text file read nothing, and copy_buf[0]
        # was still the worksheet's `>` ($BE in DOS 3.3 form), so Return
        # sent the empty file to VISICALC (DOCVIEW after a Papyrus $FF or
        # an Epistole `_`). It is TEXT's.
        for stale in (b'\xbeA1:5\r/W1', b'>B3:', b'\xff\x01', b'_MG10'):
            self.route('EMPTY', 4, 0, 0, 'TEXT', data=b'', stale=stale)
        self.route('SHEET', 4, 0, 6, 'VISICALC', data=b'>A1:5\r', stale=b'\xbeA1:5\r/W1')
        self.route('LETTER', 4, 0, 6, 'TEXT', data=b'Dear\r\n', stale=b'\xbeA1:5\r/W1')

    def test_fantavision_movies_go_to_run(self):
        # RUN hands them to FANTA.SYSTEM (test_launch.py).
        for picture in (0, 1):
            for size in (513, 4000, 9216):
                self.route('M.APPLE', 6, 0x8400, size, 'RUN', picture)
        for size in (512, 9217):
            self.route('M.APPLE', 6, 0x8400, size, 'HEX')

    def test_bank_street_writer_documents_go_to_docview(self):
        # BIN at $0840 or $63D0 (DOS 3.3 editions) or 0 (ProDOS ones),
        # high-bit text from the first byte.
        text = bytes(c | 0x80 for c in b'Geysers')
        for aux in (0x0840, 0x63D0, 0):
            self.route('JIMMY', 6, aux, 751, 'DOCVIEW', data=b'\x83' + text)
            self.route('JIMMY', 6, aux, 3, 'DOCVIEW', data=b'\x89\xc1\x8d')
        for aux, data in ((0x0840, b'\x83Geysers'), (0x2000, b'\x83' + text), (0, b'\x00' + text[:7]),
                          (0x63D0, b'')):
            self.assertNotIn('DOCVIEW', [v for _, v in self.answers('JIMMY', 6, aux, 8, 0, 0, data)])
        # I asks for a picture: a small high-bit BIN at 0 (a sprite, a lo-res
        # pixmap: bench/open_images.py's SPRITE, 48 bytes of $F7) stays one.
        for aux in (0, 0x0840):
            self.route('SPRITE', 6, aux, 48, 'DGRVIEW', picture=1, data=b'\xf7' * 8)
        self.route('SPRITE', 6, 0, 48, 'DOCVIEW', data=b'\xf7' * 8)

    def test_page_sized_pictures_are_not_bank_street_documents(self):
        """A hi-res page saved as a BIN at 0 (or $0840, $63D0) whose top row
        starts with eight bytes of $80 or more -- a white or palette-bit
        black border -- is a picture for Return as it is for I and for
        IMAGE's album. Before the fix, Return opened it in DOCVIEW on all
        four builds while I and the album called it an image."""
        for aux in (0, 0x0840, 0x63D0):
            for size in (8184, 8192, 8194, 16376, 16384):
                for data in (b'\x80' * 8, b'\xff' * 8, b'\xd5\xaa' * 4):
                    self.route('PICTURE', 6, aux, size, 'IMAGE', raw=True, data=data)
            self.route('PICTURE.RLE', 6, aux, 3000, 'IMAGE', raw=True, data=b'\xc8' * 8)
        # A Bank Street document of any other size still goes to DOCVIEW.
        self.route('JIMMY', 6, 0, 8183, 'DOCVIEW', data=b'\x80' * 8)
        self.route('JIMMY', 6, 0, 8200, 'DOCVIEW', data=b'\x80' * 8)

    def test_take1_movies_go_to_run(self):
        # RUN hands them to TAKE1.SYSTEM (test_launch.py): BIN $8029 once
        # extracted, aux 0 as a DOS 3.3 catalog shows them. Not for I.
        for aux in (0x8029, 0):
            self.route('MV.SHUTTLE.DISC', 6, aux, 85, 'RUN')
            self.assertNotIn('RUN', [v for _, v in self.answers('MV.X', 6, aux, 85, 1)])
        for name, typ, aux in (('MV.X', 6, 0x8028), ('MV.X', 6, 0x0029), ('MV.X', 4, 0),
                               ('MW.X', 6, 0x8029), ('MVX', 6, 0x8029), ('SN.X', 6, 0)):
            self.assertNotIn('RUN', [v for _, v in self.answers(name, typ, aux, 85)])

    def test_purple_pair_suffixes_and_name_boundaries(self):
        for picture in (0,1):
            for suffix in ('FOTO1','FOTO2'):
                self.route('A.'+suffix,6,0x2000,8192,'PURPLE',picture,raw=True)
                self.route('LONGNAMEX.'+suffix,6,0,1,'PURPLE',picture)
            for name in ('FOTO1','.FOTO1','A.FOTO','A.FOTO0','A.FOTO3','A.FOTO12'):
                self.route(name,6,0,4096,'IMAGE' if picture else 'HEX',picture)

    def test_appleworks_types(self):
        for typ, viewer in ((0x19, 'AWDATA'), (0x1A, 'AWP'), (0x1B, 'AWDATA'), (0x18, 'HEX'),
                            (0x1D, 'HEX'), (0x39, 'HEX')):
            self.route('DOC', typ, 0, 1000, viewer)

    def test_squeezed_archives_and_business_basic(self):
        for picture in (0, 1):
            for name in ('ARCH.QQ', 'DISK.ACU'):
                self.route(name, 0, 0, 5000, 'UNSQ', picture)
                self.route(name, 6, 0x2000, 5000, 'UNSQ', picture)
            self.route('LEDGER.BA3', 6, 0, 5000, 'BASLIST', picture)
        self.route('LEDGER', 0x09, 0, 5000, 'BASLIST')      # the ProDOS type alone
        self.route('LEDGER.BA3', 0x09, 0, 5000, 'BASLIST')
        for name in ('.QQ', 'QQ', 'A.QQX', 'A.Q', '.ACU', 'A.ACUX', '.BA3', 'A.BA', 'A.BA33'):
            self.route(name, 0, 0, 5000, 'HEX')
        for picture, name in ((2, 'ARCH.QQ'), (3, 'DISK.ACU'), (4, 'LEDGER.BA3')):
            self.route(name, 6, 0, 5000, 'HEX', picture)    # the music album skips them

    def test_macpaint_suffixes(self):
        for picture in (0, 1):
            for name, typ in (('SEAGULL.MAC', 0), ('A.MAC', 0x08)):
                self.route(name, typ, 0x2000, 40000, 'MACPAINT', picture)
        for name in ('.MAC', 'MAC', 'A.MACX', 'A.MA', 'A.PNTG'):
            self.route(name, 0, 0, 40000, 'HEX')

    def test_audio_scan_filter_and_format_precedence(self):
        self.route('TUNE.MB',6,0,100,'MUSIC',picture=2)
        self.route('TUNE.PT3',0,0,100,'PT3',picture=3)
        self.route('TUNE.ED',6,0x2000,100,'DUET',picture=4)
        self.route('JESU.JOY',0xD5,0xD0E7,1179,'DUET',picture=4)
        for picture,name in ((2,'TUNE.PT3'),(3,'TUNE.MB'),(2,'TUNE.ED'),(4,'TUNE.MB'),(4,'TUNE.PT3')):
            self.route(name,6,0,100,'HEX',picture,fail=2)
        self.route('TUNE.MB',6,0,100,'DGRVIEW',picture=2,data=b'DGR')
        self.route('TUNE.MB',6,0,100,'ERROR',picture=2,fail=4)
        self.route('TUNE.PT3',7,0,100,'FONTVIEW',picture=3)

    def test_packed_metadata_wins_over_raw_page_size(self):
        for typ, aux, viewer in ((0xF2, 0, 'EXTASIE'), (8, 0x4000, 'PACKFOT'),
                                 (6, 0xE001, 'PAINT816')):
            for size in (8184, 8192, 16376, 16384):
                self.route('PICTURE', typ, aux, size, viewer)

    def test_raw_and_rle_keep_the_standard_viewer(self):
        for typ in (6, 8):
            for size in (8184, 8192, 16376, 16384):
                self.route('PICTURE', typ, 0x2000, size, 'IMAGE', raw=True)
            self.route('PICTURE.RLE', typ, 0, 321, 'IMAGE', raw=True)

    def test_terrapin_logo_procedures_and_pictures(self):
        # Terrapin Logo saves procedures as a B file at $2000 holding plain
        # CR-ended text, NAME.LOGO, and SAVEPICT the page plus two bytes.
        for typ in (4, 6):
            self.route('ROCKET.LOGO', typ, 0x2000, 540, 'TEXT')
        for name in ('.LOGO', 'A.LOGOX', 'LOGO'):
            self.route(name, 6, 0x2000, 540, 'HEX')
        for picture in (0, 1):
            self.route('INSPI.PICT', 6, 0x2000, 8194, 'IMAGE', picture, raw=True)
        # Every nearly-a-page size is a page (KoalaPad's re-saved 8,191 too);
        # one byte beyond the range on either side is not.
        for size in (8188, 8190, 8191, 8196, 8199, 16391):
            self.route('PICTURE', 6, 0x2000, size, 'IMAGE', raw=True)
        for size in (8183, 8200, 16375, 16392):
            self.route('PICTURE', 6, 0x2000, size, 'HEX')

    def test_unrelated_binaries_and_unsupported_pictures_keep_hex(self):
        for typ, aux, size in ((6, 0x2000, 1024), (6, 0, 2048), (8, 0x8067, 9000),
                               (6, 0x4000, 64), (8, 0xE001, 123), (6, 0, 65536 + 8192)):
            self.route('UNKNOWN', typ, aux, size, 'HEX')

    def test_text_music_documents_and_programs_keep_existing_routes(self):
        for name, typ, expected in [('TEXT', 4, 'TEXT'), ('DOC', 0x1A, 'AWP'),
                    ('TUNE.MB', 6, 'MUSIC'), ('PROGRAM', 0xFF, 'RUN'), ('BASIC', 0xFC, 'RUN')]:
            self.route(name, typ, 0, 100, expected)

    def test_electric_duet_by_desktop_type_or_suffix(self):
        for name, typ, aux in [('JESU.JOY', 0xD5, 0xD0E7), ('CANON.ED', 0xD5, 0xD0E7),
                               ('CANON.ED', 6, 0x2000), ('SONG.ED', 0, 0), ('M.ED', 4, 0)]:
            self.route(name, typ, aux, 1179, 'DUET')
        for name, typ, aux, expected in [('JESU.JOY', 0xD5, 0xD0E8, 'HEX'), ('JESU.JOY', 0xD6, 0xD0E7, 'HEX'),
                                         ('SONG.EDX', 6, 0x2000, 'HEX'), ('ED', 6, 0x2000, 'HEX'), ('SONG.ED', 4, 0, 'DUET')]:
            self.route(name, typ, aux, 1179, expected)
        self.route('CANON.ED', 6, 0x2000, 8192, 'IMAGE', 1, raw=True)

    def test_legacy_dos_duet_candidates_and_io_errors(self):
        song = bytes([12,100,152,12,90,140,8,80,130,0,0,0])
        for picture in (0,4):
            self.route('M.FUR.ELISE',6,0,len(song),'DUET',picture,data=song)
            self.route('M.FUR.ELISE',6,0x2000,len(song),'DUET',picture,data=song)
            self.route('M.SLOW',6,0,len(song),'DUET',picture,data=bytes([255])+song[1:3]+bytes([200])+song[4:])
            self.route('M.NOT.MUSIC',6,0,8,'HEX',picture,data=bytes(8))
            for fail in (2,3,4):self.route('M.FUR.ELISE',6,0,len(song),'ERROR',picture,fail,data=song)

    def test_headers_identify_pictures_without_filename_or_type_hints(self):
        for picture in (0, 1):
            for typ in (0, 4, 6, 8):
                for data, viewer in ((b'DGR\x01\x50\x30\x01\0', 'DGRVIEW'),
                                     (b'HGRR\1\0\0\x20', 'IMAGE'),
                                     (b'DHRR\1\0\0\x40', 'IMAGE')):
                    self.route('NOHINT', typ, 0, 123, viewer, picture, data=data)

    def test_short_headers_do_not_use_stale_probe_bytes(self):
        for picture in (0, 1):
            for data in (b'DGR', b'DGR\1', b'DGR\1\x50\x30\1'):
                self.route('SHORT', 6, 0, len(data), 'DGRVIEW', picture, data=data)
        for data in (b'', b'D', b'DG', b'HGRR\1\0\0', b'DHRR\1\0\0'):
            self.route('SHORT', 6, 0, len(data), 'HEX', data=data)

    def test_i_opens_unmarked_lores_and_sprites(self):
        for size in (1, 48, 962, 1024, 1922, 2048):
            self.route('NOHINT', 6, 0, size, 'DGRVIEW', picture=1)
            self.route('NOHINT', 6, 0, size, 'HEX')
        self.route('LARGE', 6, 0, 2049, 'IMAGE', picture=1)

    def test_probe_failures_stop_both_commands_even_with_matching_header(self):
        for picture in (0, 1):
            for fail in (2, 3, 4):
                self.route('NOHINT', 6, 0, 123, 'ERROR', picture, fail,
                           data=b'DGR\1\x50\x30\1\0')

    def test_explicit_packed_metadata_wins_over_signature_coincidence(self):
        for data in (b'DGR\1\x50\x30\1\0', b'HGRR\1\0\0\x20'):
            self.route('PACKED', 8, 0x4000, 64, 'PACKFOT', data=data)

    def test_directory_and_failed_dispatch_never_reuse_previous_command(self):
        self.route('DIR', 0x0F, 0, 8192, '')
        self.route('PIC', 0xF2, 0, 100, '', fail=1)

    def test_demo_folder_holds_every_viewer(self):
        """The XL disk's DEMO: at least one file for every viewer Return
        opens, each routed there by the real classifier on every build."""
        import re
        import sys
        sys.path.insert(0, str(ROOT / 'tools'))
        import mkvolume
        import stage_demo
        ids = (ROOT / 'src/viewer_ids.h').read_text()
        names = re.findall(r'"([A-Z0-9]+)"', ids[ids.index('media_names'):])
        wanted = (set(names) - {'DOCVIEW'}) | {'FANTAVISION', 'MOVIE MAKER', 'EPISTOLE', 'PAPYRUS'}
        found = {}
        with tempfile.TemporaryDirectory(prefix='demo-') as tmp:
            demo = stage_demo.stage(Path(tmp) / 'DEMO')
            for path in sorted(p for p in demo.rglob('*') if p.is_file()):
                name, typ, aux = mkvolume.prodos_name(path.name)
                data = path.read_bytes()
                routes = {chosen for _, chosen in self.answers(name, typ, aux, len(data), data=data)}
                self.assertEqual(len(routes), 1, (path, routes))
                viewer = routes.pop()
                # The ones that share a viewer, told apart by what they are.
                if viewer == 'RUN' and typ == 6 and aux == 0x8400:
                    viewer = 'FANTAVISION'
                elif viewer == 'IMAGE' and typ == 6 and aux == 0x1DF0:
                    viewer = 'MOVIE MAKER'
                elif viewer == 'DOCVIEW':
                    viewer = 'EPISTOLE' if data[:1] == b'_' else 'PAPYRUS'
                found.setdefault(viewer, []).append(str(path.relative_to(demo)))
        self.assertEqual(sorted(wanted - set(found)), [], found)


if __name__ == '__main__':
    unittest.main()
