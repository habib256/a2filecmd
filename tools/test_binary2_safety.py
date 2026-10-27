"""Run the real Binary II extractor on disposable files with I/O faults.

Both native compilers also run the extractor against bounded memory streams:
full-count errors, failed EOF probes hiding extra data, cleanup failures and
unchanged archive bytes. A canary surrounds the real 64-byte summary buffer.
"""
import subprocess
import os
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
#define pan_at(p) (&panels[p])   /* the resident helper: the same address */
static struct Entry selected;
static unsigned char active, copy_buf[512], _filetype;
static unsigned int _auxtype;
static char full[64], other_full[64], note[100];
static struct {char text[64];unsigned char guard[8];} question_region;
#define question question_region.text
static int fault, cleanup_bad, read_calls, failed_read, output_open, removes;
static FILE *archive, *output;
static FILE* output_error;
static unsigned char output_reading, output_selected;
static unsigned long output_size;
static unsigned int output_reads, output_writes;
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
    else {
        const char* leaf=strrchr(p,'/');
        output=f;output_open=f!=NULL;output_reading=!strcmp(mode,"rb");
        output_selected=fault>=14 && leaf && !strcmp(leaf+1,"DATA");
        if(!output_reading)output_size=0;
    }
    return f;
}
static size_t read_file(void* p,size_t s,size_t n,FILE* f) {
    size_t got;
    ++read_calls;
    if((fault==4 && read_calls==2) || (fault==10 && read_calls==3) || (fault==11 && read_calls==4)) {
        failed_read=1;return 0;
    }
    if(f==output && output_reading && output_selected) {
        ++output_reads;
        /* A failed EOF probe is not proof that no unread bytes remain. */
        if((fault==16 || fault==17) && n==1 && (unsigned long)ftell(f)==output_size) {
            output_error=f;return 0;
        }
    }
    got=fread(p,s,n,f);
    if(f==output && output_reading && output_selected && fault==15)output_error=f;
    return got;
}
static int error_file(FILE* f) { return failed_read || f==output_error || ferror(f); }
static size_t write_file(const void* p,size_t s,size_t n,FILE* f) {
    size_t got;
    if(fault==5)return fwrite(p,s,n/2,f);
    if(fault==13){unsigned char c[512];memcpy(c,p,n);c[3]^=1;return fwrite(c,s,n,f);}   /* a wrong byte on the medium */
    got=fwrite(p,s,n,f);
    if(f==output)output_size+=s*got;
    if(f==output && output_selected) {
        ++output_writes;
        if(fault==14)output_error=f;
    }
    return got;
}
static int close_file(FILE* f) {
    int is_output=output_open && f==output;
    if(is_output && output_selected && !output_reading && fault==17)fwrite("EXTRA",1,5,f);
    if(f==output_error)output_error=NULL;
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
''' + '#define HOST_CREATE_FAULT (fault==2)\n#include "' + str(ROOT / 'tools/host_reserve.h') + '"\n' + (ROOT / 'src/file_output.h').read_text() + SOURCE[START:END] + r'''
int main(int argc,char**argv) {
    unsigned char i;
    strcpy(full,argv[1]);strcpy(panels[1].path,argv[2]);strcpy(selected.name,"TEST.BNY");
    fault=atoi(argv[3]);cleanup_bad=atoi(argv[4]);
    memset(question_region.guard,0xA5,sizeof question_region.guard);
    if(fault==18){sprintf(question,b2_done,65535U,65535U);strcpy(note,question);}
    else binary2_entry(NULL);
    for(i=0;i<sizeof question_region.guard;++i)if(question_region.guard[i]!=0xA5)return 86;
    printf("%s\nremoves=%d\noutwrites=%u outreads=%u\n",note,removes,output_writes,output_reads);
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
                # fault 2: a failed CREATE (once a failed close of the reservation)
                # creates nothing, so nothing is removed
                self.assertIn('removes=0' if fault in (1, 2) else 'removes=1', out)

    def test_failed_cleanup_names_retained_file_and_retry_preserves_bytes(self):
        for fault in (3, 4, 5, 6, 10, 11):     # 2, a failed CREATE, leaves nothing
            with self.subTest(fault=fault):
                self.assertIn('Cleanup failed: DATA retained', self.run_extract(fault, True))
                target = self.dst/'DATA'
                expected = b'' if fault in (3,4) else self.payload[:256] if fault==5 else self.payload[:512] if fault==10 else self.payload
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

    def test_output_stream_errors_never_commit_a_record(self):
        keep=self.dst/'KEEP';keep.write_bytes(b'unrelated bytes')
        for fault in (14,15,16,17):
            for size in ((1,256,512,515,1024) if fault<16 else (0,1,256,512,515,1024)):
                for cleanup in (False,True):
                    with self.subTest(fault=fault,size=size,cleanup=cleanup):
                        for name in ('FIRST','DATA','LAST'):(self.dst/name).unlink(missing_ok=True)
                        payload=bytes(i&255 for i in range(size))
                        self.src.write_bytes(record('FIRST',b'completed',True)+record('DATA',payload,True)
                                             +record('LAST',b'must not be extracted'))
                        out=self.run_extract(fault,cleanup)
                        self.assertNotIn('file(s) extracted',out)
                        self.assertIn('removes=1',out)
                        expected={'FIRST':b'completed','KEEP':b'unrelated bytes'}
                        if cleanup:
                            self.assertIn('Cleanup failed: DATA retained',out)
                            expected['DATA']=(payload[:512] if fault==14 else payload)+(b'EXTRA' if fault==17 else b'')
                        else:self.assertIn('failed',out)
                        self.assertEqual({p.name:p.read_bytes() for p in self.dst.iterdir()},expected)
                        if fault==14:self.assertIn('outwrites=1 outreads=0',out)
                        if fault==15:self.assertIn('outreads=1',out)
                        for name in ('FIRST','DATA'):(self.dst/name).unlink(missing_ok=True)

    def test_summary_fits_the_real_64_byte_buffer_at_counter_limits(self):
        out=self.run_extract(18)
        self.assertLess(len(out.splitlines()[0]),64)
        self.assertIn('65535 file(s) extracted, 65535 skipped',out)
        self.assertIn('removes=0',out)
        self.assertEqual(list(self.dst.iterdir()),[])

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
        self.assertIn('2 file(s) extracted, 2 skipped (dir/phantom/squeezed)', out)
        self.assertEqual(sorted(x.name for x in self.dst.iterdir()), ['DATA', 'END'])
        self.assertEqual((self.dst/'DATA').read_bytes(), self.payload)
        self.assertEqual((self.dst/'END').read_bytes(), b'end')
        for x in self.dst.iterdir():
            x.unlink()
        # Either mark alone is a folder: type $0F, or storage type $0D.
        for filetype, storage in ((0x0F, 1), (6, 0x0D)):
            with self.subTest(filetype=filetype, storage=storage):
                self.src.write_bytes(folder('DIR', b'x' * 600, True, filetype, storage) + record('LAST', b'end'))
                self.assertIn('1 file(s) extracted, 1 skipped (dir/phantom/squeezed)', self.run_extract())
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

    def test_phantom_and_squeezed_records_are_skipped(self):
        """Bug hunt 2 (tools/hunt2/probe_binary2_phantom.py): a phantom record
        (+$7C non-zero, which the Binary II specification says an unpacker
        must not save) was extracted as PHANTOM, 21 bytes of comment, and a
        squeezed record (+$7D bit 7) as SQUEEZED, its Huffman stream written
        as plain data: "4 file(s) extracted". Both are skipped and counted,
        the files around them extracted intact."""
        def rec(name, data, more, **at):
            r = bytearray(record(name, data, more))
            for off, v in at.items():
                r[int(off[1:], 16)] = v
            return bytes(r)
        self.src.write_bytes(rec('REAL', b'real\r' * 10, True)
                             + rec('PHANTOM', b'phantom comment block', True, x7C=1)
                             + rec('SQUEEZED', b'\x76\xff' + b'?' * 300, True, x7D=0x80)
                             + rec('LAST', b'end', False))
        out = self.run_extract()
        self.assertIn('2 file(s) extracted, 2 skipped (dir/phantom/squeezed)', out)
        self.assertEqual(sorted(x.name for x in self.dst.iterdir()), ['LAST', 'REAL'])
        self.assertEqual((self.dst/'REAL').read_bytes(), b'real\r' * 10)
        self.assertEqual((self.dst/'LAST').read_bytes(), b'end')
        for x in self.dst.iterdir():
            x.unlink()
        # a skipped record cut short is still a failure, never a success
        self.src.write_bytes(rec('PHANTOM', b'x' * 300, True, x7C=1)[:128 + 100])
        self.assertIn('Extract failed', self.run_extract())
        self.assertEqual(list(self.dst.iterdir()), [])

    def test_sanitized_name_collision_keeps_first_record(self):
        self.src.write_bytes(record('A-B', b'first', True) + record('A?B', b'second'))
        self.assertIn('Create failed', self.run_extract())
        self.assertEqual((self.dst/'A.B').read_bytes(), b'first')


NATIVE = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define A2FC_BIG_BINARY2
#define PATH_LEN 64
#define OUTPUT_RESERVED 1
struct A2fcApi {unsigned char unused;};
struct Entry {char name[17];};
struct Panel {char path[64];unsigned char fs;};
static struct Panel panels[2];
#define pan_at(p) (&panels[p])
static struct Entry selected;
static unsigned char active,copy_buf[512],_filetype;
static unsigned int _auxtype,progress_done,progress_total;
static char full[]="S/ARCHIVE",other_full[64],note[100];
static struct {char text[64];unsigned char guard[8];} question_region;
#define question question_region.text
static unsigned char input[768],snapshot[768],data[1024];
struct Stream {unsigned int pos,len;unsigned char error,writing,open;};
static struct Stream archive_stream,target_stream;
static unsigned char fault,cleanup_bad,created,removes;
static unsigned int expected,reads,writes;
static int is_dir(struct Entry* e){return 0;}
static void report_error(const char* s){strcpy(note,s);}
static unsigned char reserve_output(const char* p){if(created)return 0;created=1;return 1;}
static void progress_bar(const char* s,unsigned long d,unsigned long t){}
static FILE* m_open(const char* path,const char* mode){
    struct Stream* f;
    if(!strcmp(path,full))f=&archive_stream;
    else {if(!created)return NULL;f=&target_stream;}
    f->pos=f->error=0;f->writing=*mode=='w';f->open=1;
    if(f->writing)f->len=0;
    return (FILE*)f;
}
static size_t m_read(void* p,size_t size,size_t n,FILE* file){
    struct Stream* f=(struct Stream*)file;
    unsigned char* bytes=f==&archive_stream?input:data;
    if(size!=1 || !f->open)exit(9);
    if(f==&target_stream){
        ++reads;
        if((fault==3 || fault==4) && f->pos==expected){f->error=1;return 0;}
    }
    if(f->error)return 0;
    if(n>f->len-f->pos)n=f->len-f->pos;
    memcpy(p,bytes+f->pos,n);f->pos+=n;
    /* The final complete verification read may also report an error. */
    if(f==&target_stream && fault==2 && f->pos==expected)f->error=1;
    return n;
}
static size_t m_write(const void* p,size_t size,size_t n,FILE* file){
    struct Stream* f=(struct Stream*)file;
    if(size!=1 || f!=&target_stream || !f->open || n>sizeof data-f->pos)exit(9);
    ++writes;if(f->error)return 0;
    memcpy(data+f->pos,p,n);f->pos+=n;f->len=f->pos;
    /* Error on the last full-count write, before a successful close. */
    if(fault==1 && f->len==515)f->error=1;
    return n;
}
static int m_error(FILE* file){return ((struct Stream*)file)->error;}
static int m_close(FILE* file){
    struct Stream* f=(struct Stream*)file;
    if(!f->open)exit(9);
    if(f==&target_stream && f->writing){
        expected=f->len;
        if(fault==4){memcpy(data+f->len,"EXTRA",5);f->len+=5;}
    }
    f->open=0;return 0;
}
static long m_tell(FILE* file){return ((struct Stream*)file)->pos;}
static int m_seek(FILE* file,long off,int whence){
    struct Stream* f=(struct Stream*)file;
    if(whence!=SEEK_SET || off<0 || off>f->len)return -1;
    f->pos=(unsigned int)off;return 0;
}
static int m_remove(const char* path){++removes;if(cleanup_bad)return -1;created=0;return 0;}
#define fopen m_open
#define fread m_read
#define fwrite m_write
#define ferror m_error
#define fclose m_close
#define ftell m_tell
#define fseek m_seek
#define remove m_remove
#pragma static-locals(push,off)
''' + SOURCE[START:END] + r'''
#pragma static-locals(pop)
int main(int argc,char** argv){
    unsigned int i;
    fault=atoi(argv[1]);cleanup_bad=atoi(argv[2]);
    memset(question_region.guard,0xA5,sizeof question_region.guard);
    if(fault==5){
        sprintf(question,b2_done,65535U,65535U);
        if(strlen(question)>=64)return 8;
    } else {
        strcpy(panels[1].path,"D");strcpy(selected.name,"TEST.BNY");
        input[0]=0x0A;input[1]='G';input[2]='L';input[4]=6;
        input[20]=3;input[21]=2;input[23]=4;memcpy(input+24,"DATA",4);
        for(i=0;i<515;++i)input[128+i]=(unsigned char)(i*17);
        memcpy(snapshot,input,sizeof input);archive_stream.len=sizeof input;
        binary2_entry(NULL);
        if(memcmp(input,snapshot,sizeof input) || archive_stream.open || target_stream.open)return 1;
        if(!fault){
            if(!strstr(note,"1 file(s) extracted") || !created || removes || target_stream.len!=515)return 2;
        } else {
            if(strstr(note,"file(s) extracted") || removes!=1 || created!=cleanup_bad)return 3;
            if(!strstr(note,cleanup_bad?"Cleanup failed":"failed"))return 4;
            if(fault==1 && (writes!=2 || reads))return 5;
            if(fault==2 && reads!=3)return 6;
        }
        if(created && (memcmp(data,input+128,515) || target_stream.len!=(fault==4?520:515) ||
                       (fault==4 && memcmp(data+515,"EXTRA",5))))return 7;
    }
    for(i=0;i<sizeof question_region.guard;++i)if(question_region.guard[i]!=0xA5)return 10;
    return 0;
}
'''


class Binary2Native(unittest.TestCase):
    def test_real_extractor_on_both_processors(self):
        from test_wipe import toolchains
        chains=toolchains()
        if not chains:self.skipTest('no cc65 toolchain')
        with tempfile.TemporaryDirectory(prefix='binary2-native-') as tmp:
            p=Path(tmp);source=p/'h.c';source.write_text(NATIVE)
            for cpu,cl65,sim65,extra,_ in chains:
                env={**os.environ,**extra};exe=p/cpu
                subprocess.run([cl65,'-t',cpu,'-O','-Oirs','-Cl','--codesize','100',
                                '-o',str(exe),str(source)],env=env,check=True,capture_output=True)
                for fault in range(6):
                    for cleanup in (0,1):
                        with self.subTest(cpu=cpu,fault=fault,cleanup=cleanup):
                            run=subprocess.run([sim65,str(exe),str(fault),str(cleanup)],
                                               env=env,capture_output=True,timeout=30)
                            self.assertEqual(run.returncode,0,(cpu,fault,cleanup,run.stdout,run.stderr))


if __name__ == '__main__':
    unittest.main()
