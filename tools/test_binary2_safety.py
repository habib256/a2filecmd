"""Run the real Binary II extractor on disposable files with injected I/O faults."""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'src/a2fc.c').read_text()
START = SOURCE.index('static const char b2_create_failed[]')
END = SOURCE.index('#pragma static-locals (pop)', START)
C = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#define __fastcall__
#define A2FC_BIG_BINARY2
#define PATH_LEN 64
struct A2fcApi { int unused; };
struct Entry { char name[17]; };
struct Panel { char path[64]; unsigned char fs; };
static struct Panel panels[2];
static struct Entry selected;
static unsigned char active, copy_buf[512], _filetype;
static unsigned int _auxtype;
static char full[64], other_full[64], note[100], question[100];
static int fault, cleanup_bad, read_calls, failed_read, output_open, removes;
static FILE *archive, *output;
static int is_dir(struct Entry* e) { return 0; }
static void report_error(const char* s) { strcpy(note,s); }
static int reserve(const char* p, int flags) {
    if(flags!=(O_WRONLY|O_CREAT|O_EXCL))abort();
    if(fault==1)return -1;
    if(fault==9){FILE* f=fopen(p,"wx");if(!f)abort();fputs("arrival",f);fclose(f);}
    return open(p,flags,0600);
}
static int close_reserved(int fd) { int r=close(fd);return fault==2?-1:r; }
static FILE* open_file(const char* p,const char* mode) {
    FILE* f;
    if(!strcmp(mode,"wb") && fault==2)abort();
    if(!strcmp(mode,"wb") && fault==3)return NULL;
    if(!strcmp(mode,"rb") && strcmp(p,full)) { if(fault==12)return NULL; }   /* the output, read back */
    f=fopen(p,mode);
    if(!strcmp(p,full))archive=f;
    else {output=f;output_open=f!=NULL;}
    return f;
}
static size_t read_file(void* p,size_t s,size_t n,FILE* f) {
    ++read_calls;
    if((fault==4 && read_calls==2) || (fault==10 && read_calls==3) || (fault==11 && read_calls==4)) {
        failed_read=1;return 0;
    }
    return fread(p,s,n,f);
}
static int error_file(FILE* f) { return failed_read || ferror(f); }
static size_t write_file(const void* p,size_t s,size_t n,FILE* f) {
    if(fault==5)return fwrite(p,s,n/2,f);
    if(fault==13){unsigned char c[512];memcpy(c,p,n);c[3]^=1;return fwrite(c,s,n,f);}   /* a wrong byte on the medium */
    return fwrite(p,s,n,f);
}
static int close_file(FILE* f) {
    int is_output=output_open && f==output;
    int r=fclose(f);
    if(is_output)output_open=0;
    return (fault==6 && is_output) || (fault==7 && !is_output)?-1:r;
}
static int remove_file(const char* p) {++removes;return cleanup_bad?-1:remove(p);}
static unsigned int progress_done, progress_total;
static void progress_bar(const char* s,unsigned long d,unsigned long t) {
    fprintf(stderr,"BAR %u/%u %s %lu %lu\n",progress_done+1,progress_total,s,d,t);
}
#define open reserve
#define close close_reserved
#define fopen open_file
#define fread read_file
#define fwrite write_file
#define ferror error_file
#define fclose close_file
#define remove remove_file
''' + (ROOT / 'src/file_output.h').read_text() + SOURCE[START:END] + r'''
int main(int argc,char**argv) {
    strcpy(full,argv[1]);strcpy(panels[1].path,argv[2]);strcpy(selected.name,"TEST.BNY");
    fault=atoi(argv[3]);cleanup_bad=atoi(argv[4]);binary2_entry(NULL);
    printf("%s\nremoves=%d\n",note,removes);
    return 0;
}
'''


def record(name, data, more=False):
    h = bytearray(128)
    h[:3] = b'\x0aGL'
    h[4] = 6
    h[20:23] = len(data).to_bytes(3, 'little')
    name = name.encode('ascii')
    h[23] = len(name)
    h[24:24 + len(name)] = name
    h[127] = int(more)
    return bytes(h) + data + bytes((-len(data)) % 128)


class Binary2Safety(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory(prefix='b2-build-', dir='/tmp')
        p = Path(cls.build.name)
        (p/'test.c').write_text(C)
        cls.exe = p/'test'
        subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas',
                        str(p/'test.c'), '-o', str(cls.exe)], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='b2-', dir='/tmp')
        self.addCleanup(self.tmp.cleanup)
        self.p = Path(self.tmp.name)
        self.src = self.p/'ARCHIVE'
        self.dst = self.p/'OUT'
        self.dst.mkdir()
        self.payload = b'data\r' * 103
        self.src.write_bytes(record('DATA', self.payload))

    def run_extract(self, fault=0, cleanup=False):
        before = self.src.read_bytes()
        out = subprocess.check_output([self.exe, self.src, self.dst,
                                       str(fault), str(int(cleanup))], text=True)
        self.assertEqual(self.src.read_bytes(), before)
        return out

    def test_each_record_moves_one_bar_over_copy_and_check(self):
        # Two records: the "n/m" says which, the bar runs once over the
        # write and the read-back (DOSGET's rule), never past its total.
        self.src.write_bytes(record('ONE', b'1' * 1100, more=True) + record('TWO', b'2' * 300))
        run = subprocess.run([self.exe, self.src, self.dst, '0', '0'], text=True,
                             capture_output=True, check=True)
        self.assertIn('2 file(s) extracted', run.stdout)
        bars = [l.split()[1:] for l in run.stderr.splitlines()]
        self.assertEqual(bars, [['1/2', 'ONE', str(d), '2200'] for d in (0, 512, 1024, 1100, 1356, 1612, 1868, 2124)]
                         + [['2/2', 'TWO', str(d), '600'] for d in (0, 300, 556)])

    def test_complete_records_and_padding(self):
        for size in (0, 1, 127, 128, 512, 1024):
            with self.subTest(size=size):
                self.src.write_bytes(record('DATA', b'A'*size))
                self.assertIn('1 file(s) extracted', self.run_extract())
                self.assertEqual((self.dst/'DATA').read_bytes(), b'A'*size)
                (self.dst/'DATA').unlink()

    def test_truncated_header_data_and_padding_never_report_success(self):
        whole = self.src.read_bytes()
        for length in (0, 127, 128, 129, 128+512, len(whole)-1):
            with self.subTest(length=length):
                self.src.write_bytes(whole[:length])
                self.assertIn('Extract failed', self.run_extract())
                self.assertFalse((self.dst/'DATA').exists())

    def test_io_faults_cleanup_only_owned_output(self):
        for fault in (1, 2, 3, 4, 5, 6, 10, 11):
            with self.subTest(fault=fault):
                out = self.run_extract(fault)
                self.assertIn('failed', out)
                self.assertFalse((self.dst/'DATA').exists())
                self.assertIn('removes=0' if fault==1 else 'removes=1', out)

    def test_failed_cleanup_names_retained_file_and_retry_preserves_bytes(self):
        for fault in (2, 3, 4, 5, 6, 10, 11):
            with self.subTest(fault=fault):
                self.assertIn('Cleanup failed: DATA retained', self.run_extract(fault, True))
                target = self.dst/'DATA'
                expected = b'' if fault in (2,3,4) else self.payload[:256] if fault==5 else self.payload[:512] if fault==10 else self.payload
                self.assertEqual(target.read_bytes(), expected)
                self.assertIn('Create failed', self.run_extract())
                self.assertEqual(target.read_bytes(), expected)
                target.unlink()

    def test_existing_file_and_late_collision_are_preserved(self):
        target = self.dst/'DATA'
        target.write_bytes(b'original')
        self.assertIn('removes=0', self.run_extract())
        self.assertEqual(target.read_bytes(), b'original')
        target.unlink()
        self.assertIn('removes=0', self.run_extract(9))
        self.assertEqual(target.read_bytes(), b'arrival')

    def test_missing_or_invalid_next_header_keeps_completed_record(self):
        first = record('DATA', self.payload, more=True)
        for tail in (b'', b'X'*128):
            self.src.write_bytes(first+tail)
            out = self.run_extract()
            self.assertNotIn('file(s) extracted', out)
            self.assertEqual((self.dst/'DATA').read_bytes(), self.payload)
            self.assertIn('removes=0', out)
            (self.dst/'DATA').unlink()

    def test_readback_refuses_a_wrong_byte_or_an_unreadable_output(self):
        for fault in (12, 13):
            with self.subTest(fault=fault):
                out = self.run_extract(fault)
                self.assertIn('failed', out)
                self.assertFalse((self.dst/'DATA').exists())
                self.assertIn('removes=1', out)
        self.assertIn('reads back different', self.run_extract(13))

    def test_archive_close_failure_is_reported_without_deleting_complete_output(self):
        out = self.run_extract(7)
        self.assertIn('Extract failed', out)
        self.assertIn('removes=0', out)
        self.assertEqual((self.dst/'DATA').read_bytes(), self.payload)

    def test_second_record_failure_does_not_remove_first(self):
        self.src.write_bytes(record('FIRST', self.payload, True) + record('LAST', b'end')[:-1])
        self.assertIn('Extract failed', self.run_extract())
        self.assertEqual((self.dst/'FIRST').read_bytes(), self.payload)
        self.assertFalse((self.dst/'LAST').exists())

    def test_folder_records_are_skipped_not_extracted_as_files(self):
        def folder(name, data=b'', more=True, filetype=0x0F, storage=0x0D):
            r = bytearray(record(name, data, more))
            r[4], r[7] = filetype, storage
            return bytes(r)
        self.src.write_bytes(folder('SUB') + record('SUB/DATA', self.payload, True)
                             + folder('SUB/DEEP', bytes(range(39))) + record('SUB/DEEP/END', b'end'))
        out = self.run_extract()
        self.assertIn('2 file(s) extracted, 2 folder(s) skipped', out)
        self.assertEqual(sorted(x.name for x in self.dst.iterdir()), ['DATA', 'END'])
        self.assertEqual((self.dst/'DATA').read_bytes(), self.payload)
        self.assertEqual((self.dst/'END').read_bytes(), b'end')
        for x in self.dst.iterdir():
            x.unlink()
        # Either mark alone is a folder: type $0F, or storage type $0D.
        for filetype, storage in ((0x0F, 1), (6, 0x0D)):
            with self.subTest(filetype=filetype, storage=storage):
                self.src.write_bytes(folder('DIR', b'x' * 600, True, filetype, storage) + record('LAST', b'end'))
                self.assertIn('1 file(s) extracted, 1 folder(s) skipped', self.run_extract())
                self.assertEqual(sorted(x.name for x in self.dst.iterdir()), ['LAST'])
                (self.dst/'LAST').unlink()
        # A folder record cut short (data or padding) is a failure, never success.
        whole = folder('DIR', bytes(200)) + record('LAST', b'end')
        for length in (128 + 100, 128 + 200 + 10):
            with self.subTest(length=length):
                self.src.write_bytes(whole[:length])
                out = self.run_extract()
                self.assertIn('Extract failed', out)
                self.assertIn('removes=0', out)
                self.assertEqual(list(self.dst.iterdir()), [])

    def test_sanitized_name_collision_keeps_first_record(self):
        self.src.write_bytes(record('A-B', b'first', True) + record('A?B', b'second'))
        self.assertIn('Create failed', self.run_extract())
        self.assertEqual((self.dst/'A.B').read_bytes(), b'first')


if __name__ == '__main__':
    unittest.main()
