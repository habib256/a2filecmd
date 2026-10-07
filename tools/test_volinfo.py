"""Execute the actual C allocation walker against controlled ProDOS images."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS = r'''
#define __fastcall__
#define VOLINFO_HOST
#include "src/plugins/volinfo.c"
#include <stdlib.h>
static FILE* disk;
static unsigned int reject;
static unsigned char selection_mode, listing_mode, named_mode, path_mode, press_mode, export_mode;
static int layout, failat, writes, reads;
static char line[81], msgbuf[128], notebuf[128], inbuf[80], outfull[256];
static unsigned char scratch[512];
static unsigned char mock_mli(unsigned char cmd, void* p) {
    struct Blk* b = p;
    if (cmd == 0xC5 && path_mode) {
        /* Path mode, panel on /V. layout 1: two drives named V (S5,D1 and
         * S6,D2). layout 2: W, then the zero terminator, then a stale V
         * record past it (old copy_buf bytes). layout 3: W, then V at $E0. */
        struct Onl* o = p;
        memset(o->buf, 0, 256);
        if (layout == 1) { o->buf[0] = 0x51; o->buf[1] = 'V'; o->buf[16] = 0xE1; o->buf[17] = 'V'; }
        if (layout == 2) { o->buf[0] = 0x51; o->buf[1] = 'W'; o->buf[32] = 0xE1; o->buf[33] = 'V'; }
        if (layout == 3) { o->buf[0] = 0x51; o->buf[1] = 'W'; o->buf[16] = 0xE1; o->buf[17] = 'V'; }
        return 0;
    }
    if (cmd == 0xC0 && export_mode) {
        /* The exclusive CREATE of the report, on the host. */
        struct Create { unsigned char n; unsigned char* path; } *c = p;
        char path[256]; FILE* f;
        memcpy(path, c->path + 1, c->path[0]); path[c->path[0]] = 0;
        if ((f = fopen(path, "rb")) != NULL) { fclose(f); return 0x47; }
        f = fopen(path, "wb"); if (!f) return 0x27; fclose(f); return 0;
    }
    if (path_mode && b->unit != 0xE0) abort();
    ++reads;
    if (cmd == 0xC5 && selection_mode) {
        struct Onl* o = p;
        memset(o->buf, 0, 256);
        o->buf[0] = 0x51; o->buf[1] = 'V';
        o->buf[16] = 0xE1; o->buf[17] = 'V';
        return 0;
    }
    if (selection_mode && b->unit != 0xE0) abort();
    if (cmd != 0x80) abort(); /* A write is a test failure. */
    if (b->block == reject) return 0x27;
    if (fseek(disk, (long)b->block * 512, SEEK_SET)) return 0x27;
    return fread(b->buf, 1, 512, disk) == 512 ? 0 : 0x27;
}
static void noop(void) {}
/* The directory file of /V, as fopen of the panel's path reads it: block 2. */
static FILE* dir_file(const char* p, const char* m) {
    unsigned char blk[512]; FILE* f = tmpfile();
    if (strcmp(p, "/V") || fseek(disk, 1024, SEEK_SET) || fread(blk, 1, 512, disk) != 512) abort();
    fwrite(blk, 1, 512, f); rewind(f); return f;
}
static void puts_noop(const char* s) {}
static unsigned char ftype; static unsigned int atype;
/* E: "rb" on /V is the directory, anything else is the report itself. */
static FILE* export_open(const char* p, const char* m) {
    return strcmp(p, "/V") ? fopen(p, m) : dir_file(p, m);
}
static void unexpected(const char* s) { abort(); }
static int printf_noop(const char* s, ...) { return 0; }
static char key_return(void) { return 13; }
static void keep_message(const char* s) { strcpy(msgbuf, s); }
static unsigned char take_default(const char* q, const char* d, unsigned char h) { strcpy(inbuf, d); return 1; }
/* Disk full on the report's destination at write number failat. */
static size_t full_disk(const void* p, size_t s, size_t n, FILE* f) {
    if (++writes == failat) { fwrite(p, s, n / 2, f); return 0; }
    return fwrite(p, s, n, f);
}
int main(int argc, char** argv) {
    struct A2fcApi api = {0};
    struct Panel panels[2] = {0};
    struct Entry selected = {0};
    unsigned char active = 0;
    disk = fopen(argv[1], "rb");
    if (!disk) return 2;
    selection_mode = argc > 2 && !strcmp(argv[2], "unit");
    listing_mode = argc > 2 && !strcmp(argv[2], "list");
    named_mode = argc > 4 && !strcmp(argv[2], "named");
    path_mode = argc > 3 && !strcmp(argv[2], "path");
    press_mode = argc > 3 && !strcmp(argv[2], "press");
    export_mode = argc > 4 && !strcmp(argv[2], "export");
    reject = argc > 2 && !selection_mode && !listing_mode && !named_mode && !path_mode &&
             !press_mode && !export_mode ? atoi(argv[2]) : 65535U;
    api.mli = mock_mli; api.memcpy = memcpy; api.memset = memset;
    A = &api; buf = scratch; io.n = 3;
    io.unit = 0xE0;
    total = 65535U; base = failed = cancelled = 0;
    if (!readblock(2, buf)) return 3;
    total = word(buf+41); bitmap = word(buf+39);
    if (listing_mode) {
        api.sprintf = sprintf; api.fwrite = fwrite; api.other_full = line;
        memcpy(entry, buf+43, 39); listing = 1;
        reportfile = fopen(argv[3], "wb"); file(); fclose(reportfile); reportfile = 0;
    } else if (named_mode) {
        api.panels = panels; api.active = &active; api.selected = &selected;
        api.fopen = dir_file; api.fread = fread; api.fclose = fclose; api.strcmp = strcmp;
        api.sprintf = sprintf; api.fwrite = fwrite; api.other_full = line;
        strcpy(panels[0].path, "/V"); strcpy(selected.name, argv[3]); selected.type = 4;
        if (selected_file()) {
            listing = 1; reportfile = fopen(argv[4], "wb"); file(); fclose(reportfile); reportfile = 0;
        }
    } else if (selection_mode) {
        api.panels = panels; api.active = &active; api.selected = &selected;
        api.copy_buf = scratch; api.clrscr = noop; api.cputs = puts_noop;
        api.sprintf = sprintf; api.cprintf = printf_noop; api.cgetc = key_return; api.message = unexpected;
        strcpy(selected.name, "/V"); selected.mdate = 14;
        plugin_entry(&api);
    } else if (path_mode) {
        layout = atoi(argv[3]);
        api.panels = panels; api.active = &active; api.selected = &selected;
        api.copy_buf = scratch; api.clrscr = noop; api.cputs = puts_noop;
        api.sprintf = sprintf; api.cprintf = printf_noop; api.cgetc = key_return;
        api.message = keep_message; api.note = notebuf;
        strcpy(panels[0].path, "/V"); strcpy(selected.name, "A"); selected.type = 4;
        reads = 0; plugin_entry(&api);
        printf("{\"message\":\"%s\",\"note\":\"%s\",\"reads\":%d}\n", msgbuf, notebuf, reads);
        fclose(disk); return 0;
    } else if (press_mode || export_mode) {
        /* The audit, then F pressed n times (press), or E with the
         * destination full at write number failat (export). */
        int n;
        api.panels = panels; api.active = &active; api.selected = &selected;
        api.fopen = dir_file; api.fread = fread; api.fclose = fclose; api.strcmp = strcmp;
        api.sprintf = sprintf; api.fwrite = fwrite; api.other_full = line;
        api.clrscr = noop; api.cputs = puts_noop; api.cgetc = key_return; api.message = keep_message;
        strcpy(panels[0].path, "/V"); strcpy(selected.name, "A"); selected.type = 4;
        audit();
        if (press_mode && argc > 4) reject = atoi(argv[4]);   /* F meets a read error */
        if (press_mode) for (n = atoi(argv[3]); n; --n) file_list();
        else {
            api.fopen = export_open; api.fwrite = full_disk; api.strlen = strlen;
            api.prompt = take_default; api.input = inbuf; api.other_full = outfull;
            api.filetype = &ftype; api.auxtype = &atype; api.memcpy = memcpy;
            strcpy(panels[1].path, argv[3]); failat = atoi(argv[4]);
            export_report();
        }
        printf("{\"files\":%u,\"bad\":%u,\"incomplete\":%u,\"failed\":%u,\"cancelled\":%u,\"message\":\"%s\"}\n",
               files, bad, incomplete, failed, cancelled, msgbuf);
        fclose(disk); return 0;
    } else audit();
    printf("{\"files\":%u,\"fragmented\":%u,\"lost\":%u,\"shared\":%u,"
           "\"usedfree\":%u,\"bad\":%u,\"counts\":%u,\"free\":%u,"
           "\"incomplete\":%u,\"failed\":%u}\n",
           files, fragmented, lost, shared, usedfree, bad, counts, freeblocks, incomplete, failed);
    fclose(disk); return 0;
}
'''.replace('#include <stdlib.h>', '#include <stdlib.h>\n#include <string.h>')


def word(data, offset, value):
    data[offset:offset+2] = value.to_bytes(2, 'little')


def entry(kind=1, key=4, blocks=1, eof=1):
    e = bytearray(39)
    e[0:2] = bytes([(kind << 4) | 1, ord('A')])
    word(e, 17, key)
    word(e, 19, blocks)
    e[21:24] = eof.to_bytes(3, 'little')
    return e


def fixture(total=280, entries=()):
    d = bytearray(total*512)
    d[1028:1030] = b'\xf1V'
    d[1059:1061] = bytes([39, 13])
    word(d, 1061, len(entries))
    word(d, 1063, 3)
    word(d, 1065, total)
    for i, e in enumerate(entries):
        d[1028+39*(i+1):1028+39*(i+2)] = e
    for b in range(total):
        d[1536+(b >> 3)] |= 0x80 >> (b & 7)
    for b in range(3+(total+4095)//4096):
        allocated(d, b)
    return d


def allocated(d, b):
    d[1536+(b >> 3)] &= ~(0x80 >> (b & 7))


def ptr(d, index, slot, b):
    d[index*512+slot] = b & 255
    d[index*512+256+slot] = b >> 8


class Volinfo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='volinfo-test-')
        cls.work = Path(cls.tmp.name)
        c = cls.work/'walker.c'
        c.write_text(HARNESS)
        cls.exe = cls.work/'walker'
        subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-I', str(ROOT),
                        str(c), '-o', str(cls.exe)], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def scan(self, d, reject=None):
        path = self.work/'disk.po'
        path.write_bytes(d)
        args = [str(self.exe), str(path)]
        if reject is not None:
            args.append(str(reject))
        r = json.loads(subprocess.check_output(args, timeout=10))
        self.assertEqual(path.read_bytes(), d, 'audit must never write')
        return r

    def clean(self, r):
        for key in ('lost', 'shared', 'usedfree', 'bad', 'counts', 'incomplete', 'failed'):
            self.assertEqual(r[key], 0, (key, r))

    def block_list(self, d):
        path = self.work/'disk.po'; path.write_bytes(d)
        report = self.work/'blocks.txt'
        subprocess.check_output([str(self.exe), str(path), 'list', str(report)], timeout=10)
        self.assertEqual(path.read_bytes(), d)
        return report.read_text()

    def named_list(self, d, name):
        path = self.work/'disk.po'; path.write_bytes(d)
        report = self.work/'named.txt'
        if report.exists(): report.unlink()
        r = json.loads(subprocess.check_output([str(self.exe), str(path), 'named', name, str(report)], timeout=10))
        self.assertEqual(path.read_bytes(), d)
        return (report.read_bytes().decode() if report.exists() else None), r

    def test_selected_file_named_like_its_directory_is_not_the_header(self):
        """The volume header of /V is named V too: the file V is the entry
        in slot 2, never the storage-$F header in slot 0."""
        e = entry(1, 4, 1, 1); e[1] = ord('V')
        text, r = self.named_list(fixture(entries=[entry(1, 7, 1, 1), e]), 'V')
        self.assertEqual(text, 'D     4 ($0004)\r\n')
        self.assertEqual(r['failed'], 0)
        self.assertEqual(r['incomplete'], 0)

    def test_selected_file_absent_is_not_found(self):
        text, r = self.named_list(fixture(entries=[entry()]), 'V')
        self.assertIsNone(text)
        self.assertEqual(r['failed'], 1)

    def test_selected_tree_lists_roles_in_order(self):
        d = fixture(entries=[entry(3, 4, 4, 1024)])
        ptr(d, 4, 0, 5); ptr(d, 5, 0, 6); ptr(d, 5, 1, 8)
        lines = self.block_list(d).splitlines()
        self.assertEqual(lines, ['M     4 ($0004)', 'I     5 ($0005)',
                                 'D     6 ($0006)', 'D     8 ($0008)'])

    def test_selected_extended_lists_both_forks(self):
        d = fixture(entries=[entry(5, 4, 3, 1)])
        d[2048] = d[2304] = 1
        word(d, 2049, 5); word(d, 2305, 6)
        self.assertEqual(self.block_list(d).splitlines(),
                         ['E     4 ($0004)', 'D     5 ($0005)', 'D     6 ($0006)'])

    def test_selected_invalid_pointer_is_explicit(self):
        d = fixture(entries=[entry(key=280)])
        self.assertEqual(self.block_list(d).strip(), 'D   280 ($0118) INVALID')

    def test_selected_sparse_holes_are_not_block_zero(self):
        d = fixture(entries=[entry(2, 4, 2, 1024)])
        ptr(d, 4, 1, 5)
        self.assertEqual(self.block_list(d).splitlines(), ['I     4 ($0004)', 'D     5 ($0005)'])

    def test_empty(self):
        r = self.scan(fixture())
        self.clean(r)
        self.assertEqual(r['free'], 276)

    def test_duplicate_volume_names_use_selected_drive(self):
        self.clean(self.scan(fixture(), 'unit'))

    def run_mode(self, d, *args):
        path = self.work/'disk.po'; path.write_bytes(d)
        r = json.loads(subprocess.check_output([str(self.exe), str(path)] + list(args),
                                               cwd=self.work, timeout=10))
        self.assertEqual(path.read_bytes(), d, 'VOLINFO must never write the volume')
        return r

    def test_duplicate_volume_names_refuse_a_path(self):
        """Before: a panel on /V with two drives named V audited the first
        ON_LINE record's drive while F and E read the selected file through
        ProDOS, which resolves /V on its own. Now refused, no block read."""
        r = self.run_mode(fixture(), 'path', '1')
        self.assertEqual(r['note'], 'Two volumes named /V: pick it in the volume list.')
        self.assertEqual(r['reads'], 0)

    def test_online_table_stops_at_its_terminator(self):
        """Before: the scan went on past the zero record into stale copy_buf
        bytes, and a phantom V record there passed for the volume (here read
        at unit $E0). Now: not on line, and nothing read."""
        r = self.run_mode(fixture(), 'path', '2')
        self.assertEqual((r['message'], r['reads']), ('Volume not on line.', 0))
        r = self.run_mode(fixture(), 'path', '3')
        self.assertNotEqual(r['message'], 'Volume not on line.')
        self.assertGreater(r['reads'], 0)

    def test_file_blocks_leave_the_audit_figures_alone(self):
        """Before: each F press on a file with a pointer off the volume raised
        "Invalid structure/pointers" (bad 2, 3, 4...). Now the audit's count
        stays what the audit found."""
        d = fixture(entries=[entry(2, 300, 1, 10)])
        once = self.run_mode(d, 'press', '0')
        thrice = self.run_mode(d, 'press', '3')
        self.assertEqual(thrice['bad'], once['bad'])
        self.assertEqual(thrice['incomplete'], once['incomplete'])
        self.assertEqual((thrice['failed'], thrice['cancelled']), (0, 0))

    def test_file_blocks_read_error_does_not_fail_the_audit(self):
        """A read error during F is F's own: the audit is not marked failed,
        which would disable F and M and call the scan incomplete."""
        d = fixture(entries=[entry(2, 4, 2, 1024)]); allocated(d, 4)
        r = self.run_mode(d, 'press', '1', '4')
        self.assertEqual(r['message'], 'Block read failed.')
        self.assertEqual((r['failed'], r['cancelled']), (0, 0))

    def test_export_disk_full_leaves_the_audit_complete(self):
        """Before: the destination full during the file part of E set
        cancelled (listed) and the summary then said "Scan incomplete" and F
        and M were disabled. Now: a partial report, the audit untouched."""
        d = fixture(entries=[entry(2, 4, 2, 1024)])
        ptr(d, 4, 0, 5); allocated(d, 4); allocated(d, 5)
        out = self.work/'exp'
        out.mkdir(exist_ok=True)
        for f in out.iterdir(): f.unlink()
        r = self.run_mode(d, 'export', 'exp', '3')
        self.assertEqual(r['message'], 'Partial report (error/cancelled).')
        self.assertEqual((r['failed'], r['cancelled'], r['incomplete']), (0, 0, 0))
        report = (out/'VOLINFO.TXT').read_bytes()
        self.assertIn(b'Scan complete.', report)
        self.assertNotIn(b'END REPORT', report)
        for f in out.iterdir(): f.unlink()
        r = self.run_mode(d, 'export', 'exp', '0')
        self.assertEqual(r['message'], 'Report saved in other panel.')
        self.assertTrue((out/'VOLINFO.TXT').read_bytes().endswith(b'D     5 ($0005)\r\nEND REPORT\r\n'))

    def test_seedling(self):
        d = fixture(entries=[entry()]); allocated(d, 4)
        r = self.scan(d); self.clean(r)
        self.assertEqual(r['files'], 1)

    def test_lost(self):
        d = fixture(); allocated(d, 40)
        self.assertEqual(self.scan(d)['lost'], 1)

    def test_used_marked_free(self):
        r = self.scan(fixture(entries=[entry()]))
        self.assertEqual(r['usedfree'], 1)

    def test_shared(self):
        d = fixture(entries=[entry(), entry()]); allocated(d, 4)
        self.assertEqual(self.scan(d)['shared'], 1)

    def test_sapling_fragmentation_and_sparse(self):
        d = fixture(entries=[entry(2, 4, 3, 1536)])
        ptr(d, 4, 0, 5); ptr(d, 4, 1, 7)
        for b in (4, 5, 7): allocated(d, b)
        r = self.scan(d); self.clean(r)
        self.assertEqual(r['fragmented'], 1)
        ptr(d, 4, 1, 0); ptr(d, 4, 2, 7)
        self.assertEqual(self.scan(d)['fragmented'], 0)

    def test_tree(self):
        d = fixture(entries=[entry(3, 4, 3, 1)])
        ptr(d, 4, 0, 5); ptr(d, 5, 0, 6)
        for b in (4, 5, 6): allocated(d, b)
        self.clean(self.scan(d))

    def test_extended_forks(self):
        d = fixture(entries=[entry(5, 4, 3, 512)])
        d[2048] = d[2304] = 1
        word(d, 2049, 5); word(d, 2305, 6)
        for b in (4, 5, 6): allocated(d, b)
        self.clean(self.scan(d))

    def test_subdirectory(self):
        d = fixture(entries=[entry(13, 4, 1, 512)])
        d[2052:2054] = b'\xe1D'
        d[2083:2085] = bytes([39, 13])
        word(d, 2085, 1)
        d[2091:2130] = entry(1, 5)
        allocated(d, 4); allocated(d, 5)
        r = self.scan(d); self.clean(r)
        self.assertEqual(r['files'], 1)

    def test_counts(self):
        d = fixture(entries=[entry(blocks=2)]); allocated(d, 4)
        word(d, 1061, 2)
        self.assertEqual(self.scan(d)['counts'], 2)

    def test_out_of_range(self):
        r = self.scan(fixture(entries=[entry(key=280)]))
        self.assertEqual(r['bad'], 1)
        self.assertEqual(r['incomplete'], 1)

    def test_directory_cycle(self):
        d = fixture(); word(d, 1026, 2)
        r = self.scan(d)
        self.assertEqual(r['incomplete'], 1)

    def test_unknown_storage(self):
        r = self.scan(fixture(entries=[entry(4)]))
        self.assertEqual(r['incomplete'], 1)

    def test_missing_key(self):
        r = self.scan(fixture(entries=[entry(key=0, blocks=0)]))
        self.assertEqual(r['incomplete'], 1)

    def test_io_error(self):
        d = fixture(entries=[entry(2)]); allocated(d, 4)
        self.assertEqual(self.scan(d, 4)['failed'], 1)

    def test_xl_last_block(self):
        d = fixture(65535, [entry(key=65534)]); allocated(d, 65534)
        r = self.scan(d); self.clean(r)
        self.assertEqual(r['files'], 1)
        self.assertEqual(r['free'], 65515)

    def test_window_boundary_shared(self):
        d = fixture(8193, [entry(key=4096), entry(key=4096)])
        allocated(d, 4096)
        r = self.scan(d)
        self.assertEqual(r['shared'], 1)
        self.assertEqual(r['files'], 2)
        self.assertEqual(r['lost'], 0)

if __name__ == '__main__':
    unittest.main()
