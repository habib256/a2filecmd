"""Run the actual image classifier and file-to-viewer dispatch for both CPU builds."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_six_plugins import ROOT, PREFIX

SOURCE = (ROOT / 'src/a2fc.c').read_text()
IMAGE = SOURCE[SOURCE.index('static unsigned char page_size('):SOURCE.index('/* Buffered reading:')]
ROUTING = SOURCE[SOURCE.index('static const unsigned char image_viewers[]'):SOURCE.index('static void open_selected(void)')]
HARNESS = PREFIX + r'''
#include <stdint.h>
#include "src/a2fc_plugin.h"
#include "src/viewer_ids.h"
static char input[64], full[512], chosen[80];
static unsigned char copy_buf[512];
static struct Entry selected;
static unsigned char fail_open;
static unsigned char is_dir(const struct Entry* e) { return e->type == 0x0F; }
static void overlay_run(const char*, unsigned char);
static void message(const char* msg) { (void)msg; strcpy(chosen, "ERROR"); }
static void report_error(const char* what) { (void)what; strcpy(chosen, "ERROR"); }
static FILE* probe_open(const char* path, const char* mode) {
    if (strcmp(mode, "rb")) abort();
    return fail_open == 2 ? NULL : fopen(path, mode);
}
static int probe_error(FILE* f) { return fail_open == 3 || ferror(f); }
static int probe_close(FILE* f) {
    int result = fclose(f);
    return fail_open == 4 ? EOF : result;
}
''' + IMAGE + r'''
#define fopen probe_open
#define ferror probe_error
#define fclose probe_close
''' + ROUTING + r'''
#undef fopen
#undef ferror
#undef fclose
static void overlay_run(const char* name, unsigned char arg) {
    struct A2fcApi api;
    if (!strcmp(name, "OPEN")) {
        if (fail_open == 1) return;
        api.arg = arg; open_entry(&api);
    } else strcpy(chosen, name);
}
int main(int argc, char** argv) {
    if(argc==1) {
        unsigned long size, high;
        for(high=0;high<3;++high)for(size=0;size<65536;++size) {
            unsigned long value=size+(high==1?65536UL:high==2?0x80000000UL:0);
            unsigned char expected=!high && (size==8184 || size==8192 || size==16376 || size==16384);
            if(page_size(&value)!=expected)return 1;
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
'''


class FileViewers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='viewer-routes-')
        cls.root = Path(cls.tmp.name)
        source = cls.root / 'test.c'
        source.write_text(HARNESS)
        cls.exes = []
        for cpu in ('6502', '65c02'):
            exe = cls.root / cpu
            subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-I', str(ROOT),
                            *(['-DA2FC_6502'] if cpu == '6502' else []),
                            str(source), '-o', str(exe)], check=True, capture_output=True)
            cls.exes.append(exe)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def route(self, name, typ, aux, size, expected, picture=0, fail=0, raw=False, data=bytes(8)):
        fixture = self.root / 'picture'
        fixture.write_bytes(data)
        for exe in self.exes:
            with self.subTest(cpu=exe.name, name=name, typ=typ, aux=aux, size=size, picture=picture):
                result = subprocess.check_output([str(exe), name, str(typ), str(aux),
                          str(size), str(picture), str(fail), str(fixture)], text=True).strip().split(' ', 1)
                kind = int(result[0]); chosen = result[1] if len(result) > 1 else ''
                self.assertEqual(fixture.read_bytes(), data)
                self.assertEqual(chosen, expected)
                self.assertEqual(kind == 1, raw, 'the raw album must skip specialized formats')

    def test_all_page_sizes_and_high_words(self):
        for exe in self.exes:subprocess.run([str(exe)],check=True)

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
