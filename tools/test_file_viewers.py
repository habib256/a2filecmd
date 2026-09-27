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
TABLES = section('/* The tables of the classifier', 'void __fastcall__ open_entry')
OPEN_ENTRY = section('void __fastcall__ open_entry', '#pragma rodata-name(pop)')
OPEN_VIEWER = section('static void open_viewer(', 'static void open_selected(void)')
REFERENCE = (ROOT / 'tools/file_viewer_ref.c').read_text()

# The same program twice: on the host with the C reference of the classifier
# (tools/file_viewer_ref.c), under sim65 with the real src/open.s. Both
# read the fixture through the harness's own fopen & co, which can fail.
COMMON = r"""
#include <stdint.h>
#include "src/a2fc_plugin.h"
#include "src/viewer_ids.h"
static char input[64], chosen[80];
char full[512];
unsigned char copy_buf[512];
static struct Entry selected;
static unsigned char fail_open;
static unsigned char is_dir(const struct Entry* e) { return e->type == 0x0F; }
static void overlay_run(const char*, unsigned char);
static void report_error(const char* what) { (void)what; strcpy(chosen, "ERROR"); }
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
""" + OPEN_ENTRY + OPEN_VIEWER + r"""
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
            expected = !high && (size == 8184 || size == 8192 || size == 16376 || size == 16384);
            if (page_size(&value) != expected) return 1;
        }
        return 0;
    }
    strncpy(selected.name, argv[1], NAME_LEN - 1);
    selected.type = strtoul(argv[2], 0, 0); selected.aux = strtoul(argv[3], 0, 0);
    selected.size = strtoul(argv[4], 0, 0); fail_open = atoi(argv[6]);
    strcpy(full, argv[7]); strcpy(input, "RUN");
    memcpy(copy_buf, "DGR\1\x50\x30\1\0", 8); /* previous probe */
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
    'CLASSIFIER\n', 'unsigned char __fastcall__ file_viewer(const struct Entry*, unsigned char);   /* open.s */\n')


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

    def answers(self, name, typ, aux, size, picture=0, fail=0, data=bytes(8)):
        """What each build answers: [kind, viewer] for the host reference
        (6502, 65C02 defines) and the assembly under sim65 (both CPUs)."""
        fixture = self.root / 'picture'
        fixture.write_bytes(data)
        out = []
        for exe in self.exes:
            result = subprocess.check_output(exe + [name, str(typ), str(aux), str(size), str(picture),
                                                    str(fail), str(fixture)], text=True, timeout=30)
            result = result.strip().split(' ', 1)
            out.append((int(result[0]), result[1] if len(result) > 1 else ''))
            self.assertEqual(fixture.read_bytes(), data)
        return out

    def route(self, name, typ, aux, size, expected, picture=0, fail=0, raw=False, data=bytes(8)):
        with self.subTest(name=name, typ=typ, aux=aux, size=size, picture=picture, fail=fail):
            for (kind, chosen), exe in zip(self.answers(name, typ, aux, size, picture, fail, data), self.exes):
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
                 'BN.SUN', 'PN.X', 'DOG.SHP', 'LONGNAMEXX.FOTO1', 'X.RLE', 'RLE', 'M.APPLE', 'EPISTOLE']
        types = [0x00, 0x04, 0x06, 0x07, 0x08, 0x09, 0x19, 0x1A, 0x1B, 0xC0, 0xD5, 0xE0, 0xF2, 0xF8,
                 0xFA, 0xFC, 0xFF, 0x0F]
        auxes = [0, 1, 0x0400, 0x1DF0, 0x2000, 0x4000, 0x4001, 0x4800, 0x5800, 0x7800, 0x4801, 0x8066,
                 0x8400, 0xD0E7, 0xE001, 0xE002, 0x0801]
        sizes = [0, 1, 8, 572, 576, 574, 1024, 2048, 2049, 2096, 8184, 8192, 8720, 16384, 16376,
                 65536 + 572, 70000]
        datas = [bytes(8), b'DGR\1\x50\x30\1\0', b'DG', b'\0\0gsXXXX', b'HGRR\1\0\0\x20',
                 b'DHRR\1\0\0\x40', b'HGRR\1\0\0\x21', b'_MG10_MD', b'\xffabc', b'\x7f', b'',
                 b'\1\2\3\4\5\6\7\x08', b'\1\0\0\0\5\6\7\x08', b'ab']
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

    def test_fantavision_movies_go_to_run(self):
        # RUN hands them to FANTA.SYSTEM (test_launch.py).
        for picture in (0, 1):
            for size in (513, 4000, 9216):
                self.route('M.APPLE', 6, 0x8400, size, 'RUN', picture)
        for size in (512, 9217):
            self.route('M.APPLE', 6, 0x8400, size, 'HEX')

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


if __name__ == '__main__':
    unittest.main()
