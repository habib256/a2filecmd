"""Execute the shipped NuFX C driver on disposable files with I/O faults.

Only the Apple II AUX transport and assembly decoder are substituted. Stored
threads exercise the whole parser and file lifecycle; raw LZW blocks exercise
the C window/refill/write paths. bench/shk.py executes the actual decoder.
"""
import struct
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from mkshk import crc16  # noqa: E402
SOURCE = (ROOT/'src/a2fc.c').read_text()
START = SOURCE.index('static const char us_extract_failed[]')
END = SOURCE.index('#pragma rodata-name (pop)', START)
DRIVER = SOURCE[START:END].replace('unsigned long', 'uint32_t')
DRIVER = DRIVER.replace('unsigned int w[2]', 'uint16_t w[2]')
DRIVER = DRIVER.replace('#define US ((struct UsState*)0x3E00)',
                        'static struct UsState state;\n#define US (&state)')
DRIVER = DRIVER.replace('(unsigned int)copy_buf', '(uintptr_t)copy_buf')
DRIVER = DRIVER.replace('(unsigned)copy_buf', '(uintptr_t)copy_buf')
DRIVER = DRIVER.replace('*(volatile unsigned char*)0xC056 = 0;', '(void)0;')
C = r'''
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#define __fastcall__
#define PATH_LEN 64
struct A2fcApi { int unused; };
struct Entry { char name[17]; };
struct Panel { char path[64]; unsigned char count,fs; };
static struct Panel panels[2];
static struct Entry selected;
static unsigned char active,copy_buf[512],_filetype,progress_abort;
static unsigned int _auxtype,progress_total,progress_done;
static char full[81],other_full[81],note[80],reselect[17];
static int fault,cleanup_bad,removes,reads,read_at,read_error,write_error;
static int opens,writes,progress_calls,cancel_at,decoder_calls,init_fmt;
static unsigned char aux[65536],cmpbuf[512];
#define US_CMP cmpbuf
static unsigned int devadr[16];
#define US_DEVADR devadr
static char dstroot[81];
/* "/RAMDISK" names the host output directory: a volume called like /RAM
 * that is not the /RAM driver. */
static const char* mapped(const char* p){
    static char b[256];
    if(!strncmp(p,"/RAMDISK",8)){snprintf(b,sizeof b,"%s%s",dstroot,p+8);return b;}
    return p;
}
/* ON_LINE for every unit: the archive's volume in unit $60, the output's in
 * unit $50 when it is another volume. */
static unsigned char mli_call(unsigned char cmd,void* parms){
    const char* vols[2];unsigned char units[2]={0x60,0x50},*out=copy_buf;int i,len;
    if(cmd!=0xC5||((unsigned char*)parms)[1])abort();
    if(fault==31)return 0x27;
    memset(copy_buf,0,256);
    vols[0]=full;vols[1]=panels[1].path;
    for(i=0;i<2;++i){
        const char* v=vols[i]+1,*sl=strchr(v,'/');
        len=sl?(int)(sl-v):(int)strlen(v);
        if(i==1&&!strncmp(full+1,v,len)&&(full[len+1]=='/'||!full[len+1]))break;
        out[0]=units[i]|len;memcpy(out+1,v,len);out+=16;
    }
    return 0;
}
static FILE *archive,*output;
static int output_open;
static int is_dir(struct Entry* e){return 0;}
static void too_long(void){strcpy(note,"Path too long");}
static void report_error(const char* s){strcpy(note,s);}
static unsigned char ram_format(void){return 0;}
static void progress_bar(const char* s,uint32_t n,uint32_t total){++progress_calls;}
static unsigned char abort_key(void){
    if(cancel_at && progress_calls>=cancel_at)progress_abort=1;
    return progress_abort;
}
static void aux_copy(uintptr_t main_addr,unsigned int addr,unsigned char to_aux){
    if(main_addr<0x2000)return; /* native core staging; no host decoder bytes */
    if(addr+512>sizeof aux)abort();
    if(to_aux)memcpy(aux+addr,(void*)main_addr,512);
    else memcpy((void*)main_addr,aux+addr,512);
}
void us_init(unsigned int fmt){init_fmt=fmt&255;}
unsigned int us_chunk(unsigned int addr){
    unsigned int header=init_fmt==2?3:2;
    ++decoder_calls;
    if(fault==16)return 0;
    if(fault==17)return 8193;
    /* Raw, uncompressed 4096-byte chunks in an LZW container. memmove, not
     * memcpy: on a truncated thread us_fill hands the decoder a window
     * holding less than one whole block, so the source runs into OUTBUF at
     * $8000 -- which is what the 6502 core reads there too, and what the
     * caller then rejects on `used > win_len - win_pos`. */
    if(addr+header+4096>sizeof aux)abort();
    memmove(aux+0x8000,aux+addr+header,4096);
    return header+4096;
}
static int reserve(const char* p,int flags){
    if(flags!=(O_WRONLY|O_CREAT|O_EXCL))abort();
    ++opens;
    if(fault==1)return -1;
    if(fault==9){FILE* f=fopen(p,"wx");if(!f)abort();fputs("arrival",f);fclose(f);}
    return open(mapped(p),flags,0600);
}
static int close_reserved(int fd){int r=close(fd);return fault==2?-1:r;}
static FILE* open_file(const char* p,const char* mode){
    FILE* f;
    if(!strcmp(mode,"wb") && fault==2)abort();
    if(!strcmp(mode,"wb") && fault==3)return NULL;
    if(!strcmp(mode,"rb") && strcmp(p,full)==0){archive=fopen(p,mode);return archive;}
    if(!strcmp(mode,"rb") && fault==20)return NULL;   /* the closed output cannot be reopened */
    f=fopen(mapped(p),mode);
    output=f;output_open=f!=NULL;
    return f;
}
static size_t read_file(void* p,size_t s,size_t n,FILE* f){
    size_t got;
    ++reads;
    if(reads==read_at && fault==4){read_error=1;return 0;}
    if(fault==21 && f==output && n>1)n-=1;              /* the readback comes up short */
    got=fread(p,s,n,f);
    if(reads==read_at && fault==12)read_error=1;
    return got;
}
static int error_file(FILE* f){
    return ferror(f) || (f==archive?read_error:write_error);
}
static size_t write_file(const void* p,size_t s,size_t n,FILE* f){
    ++writes;
    if(fault==5)return fwrite(p,s,n/2,f);
    if(fault==13)write_error=1;
    if(fault==19 && n>8){unsigned char c[4096];memcpy(c,p,n);c[7]^=1;return fwrite(c,s,n,f);}   /* a byte lands wrong: only the readback can see it */
    return fwrite(p,s,n,f);
}
static int close_file(FILE* f){
    int is_output=output_open && f==output;
    int r=fclose(f);
    if(is_output)output_open=0;
    return fault==18 || (fault==6 && is_output) || (fault==7 && !is_output)?-1:r;
}
static int remove_file(const char* p){++removes;return cleanup_bad?-1:remove(mapped(p));}
static int seek_file(FILE* f,long o,int w){if(fault==22)return -1;return fseek(f,o,w);}
#define open reserve
#define close close_reserved
#define fopen open_file
#define fread read_file
#define fwrite write_file
#define ferror error_file
#define fclose close_file
#define remove remove_file
#define fseek seek_file
''' + (ROOT/'src/file_output.h').read_text() + DRIVER + r'''
int main(int argc,char** argv){
    strcpy(full,argv[1]);strcpy(panels[0].path,"/SOURCE");
    fault=atoi(argv[3]);
    strcpy(dstroot,argv[2]);
    strcpy(panels[1].path,fault==30||fault==32?"/RAMDISK":argv[2]);panels[0].count=1;
    if(fault==30)devadr[5]=0xFF00;      /* the output volume is the /RAM driver's, whatever its name */
    if(fault==33)devadr[6]=0xFF00;      /* the archive's volume is */
    strcpy(selected.name,"ARCHIVE.SHK");cleanup_bad=atoi(argv[4]);read_at=atoi(argv[5]);cancel_at=atoi(argv[6]);
    /* Scratch is not zero-initialized on Apple II overlay entry. */
    memset(&state,0xA5,sizeof state);
    unshrink_entry(NULL);
    if(output_open)abort();
    printf("%s\nremoves=%d opens=%d writes=%d reads=%d decoded=%d\n",note,removes,opens,writes,reads,decoder_calls);
    return 0;
}
'''


def thread(data, klass=2, fmt=0, kind=0, eof=None, ceof=None, crc=0):
    return (struct.pack('<HHHHII', klass, fmt, kind, crc,
                        len(data) if eof is None else eof,
                        len(data) if ceof is None else ceof), data)


def record(name, data=b'', extra=(), fmt=0, eof=None, ceof=None, kind=0, auxtype=0, version=0, crc=0):
    name = name.encode()
    threads = [thread(name, klass=3), *extra,
               thread(data, fmt=fmt, eof=eof, ceof=ceof, kind=kind, crc=crc)]
    header = bytearray(60)
    header[:4] = bytes.fromhex('4E F5 46 D8')
    header[8] = version
    struct.pack_into('<H', header, 6, 60)
    struct.pack_into('<H', header, 10, len(threads))
    header[16] = ord('/')
    header[22] = 6
    struct.pack_into('<H', header, 26, auxtype)
    return bytes(header) + b''.join(h for h, _ in threads) + b''.join(d for _, d in threads)


def archive(*records):
    header = bytearray(48)
    header[:6] = bytes.fromhex('4E F5 46 E9 6C E5')
    struct.pack_into('<I', header, 8, len(records))
    return bytes(header) + b''.join(records)


class UnshrinkSafety(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory(prefix='us-build-', dir='/tmp')
        p = Path(cls.build.name)
        (p/'test.c').write_text(C)
        cls.exe = p/'test'
        run = subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas',
                              '-fsanitize=address,undefined', str(p/'test.c'),
                              '-o', str(cls.exe)], capture_output=True, text=True)
        if run.returncode:
            raise RuntimeError(run.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='us-', dir='/tmp')
        self.addCleanup(self.tmp.cleanup)
        self.p = Path(self.tmp.name)
        self.src = self.p/'ARCHIVE'
        self.dst = self.p/'OUT'
        self.dst.mkdir()
        self.payload = b'data\r'*103
        self.src.write_bytes(archive(record('DATA', self.payload)))

    def run_extract(self, fault=0, cleanup=False, read_at=6, cancel_at=0):
        before = self.src.read_bytes()
        out = subprocess.check_output([self.exe, self.src, self.dst, str(fault),
                                       str(int(cleanup)), str(read_at), str(cancel_at)],
                                      text=True, timeout=5)
        self.assertEqual(self.src.read_bytes(), before)
        return out

    def test_complete_stored_and_binary2_wrapped_records(self):
        for size in (0, 1, 511, 512, 513, 8192):
            data = archive(record('DATA', b'A'*size))
            if size & 1:
                data = b'\x0aGL'+bytes(125)+data
            self.src.write_bytes(data)
            self.assertIn('1 file(s) extracted', self.run_extract())
            self.assertEqual((self.dst/'DATA').read_bytes(), b'A'*size)
            (self.dst/'DATA').unlink()

    def test_reservation_read_write_and_close_faults(self):
        for fault in (1, 2, 3, 4, 5, 6, 12, 13):
            with self.subTest(fault=fault):
                out = self.run_extract(fault)
                self.assertIn('failed', out)
                self.assertFalse((self.dst/'DATA').exists())
                self.assertIn('removes=0' if fault==1 else 'removes=1', out)

    def test_cleanup_failure_and_retry_preserve_exact_bytes(self):
        for fault in (2, 3, 4, 5, 6, 12, 13, 18):
            with self.subTest(fault=fault):
                self.assertIn('Cleanup failed: DATA retained', self.run_extract(fault, True))
                expected = b'' if fault in (2, 3, 4, 12) else self.payload[:256] if fault==5 else self.payload
                self.assertEqual((self.dst/'DATA').read_bytes(), expected)
                self.assertIn('Create failed', self.run_extract())
                self.assertEqual((self.dst/'DATA').read_bytes(), expected)
                (self.dst/'DATA').unlink()

    def test_existing_and_late_name_collisions(self):
        (self.dst/'DATA').write_bytes(b'original')
        self.assertIn('removes=0', self.run_extract())
        self.assertEqual((self.dst/'DATA').read_bytes(), b'original')
        (self.dst/'DATA').unlink()
        self.assertIn('removes=0', self.run_extract(9))
        self.assertEqual((self.dst/'DATA').read_bytes(), b'arrival')

    def test_cancellation_cleanup_and_retained_partial_retry(self):
        for at in (1, 2):
            for cleanup in (False, True):
                out = self.run_extract(cleanup=cleanup, cancel_at=at)
                self.assertIn('Cleanup failed' if cleanup else 'cancelled', out)
                target = self.dst/'DATA'
                if cleanup:
                    expected = self.payload[:512] if at==2 else b''
                    self.assertEqual(target.read_bytes(), expected)
                    self.assertIn('Create failed', self.run_extract())
                    self.assertEqual(target.read_bytes(), expected)
                    target.unlink()
                else:
                    self.assertFalse(target.exists())

    def test_readback_catches_wrong_byte_failed_reopen_short_read_and_failed_seek(self):
        for fault in (19, 20, 21, 22):
            with self.subTest(fault=fault):
                out = self.run_extract(fault)
                self.assertIn('DATA reads back different', out)
                self.assertIn('removes=1', out)
                self.assertFalse((self.dst/'DATA').exists())
        # every second-pass read failing (archive or output) removes the file;
        # the last one-byte read is the end-of-file check, where 0 is the answer
        for at in (8, 9, 10, 11):
            with self.subTest(read_at=at):
                self.assertIn('reads back different', self.run_extract(4, read_at=at))
                self.assertFalse((self.dst/'DATA').exists())
        # a failed cleanup retains the complete bytes as written, wrong byte included
        out = self.run_extract(19, cleanup=True)
        self.assertIn('Cleanup failed: DATA retained', out)
        written = (self.dst/'DATA').read_bytes()
        self.assertEqual(len(written), len(self.payload))
        self.assertNotEqual(written, self.payload)
        self.assertIn('Create failed', self.run_extract())
        self.assertEqual((self.dst/'DATA').read_bytes(), written)

    def test_archive_close_failure_keeps_completed_outputs(self):
        self.assertIn('Extract failed', self.run_extract(7))
        self.assertEqual((self.dst/'DATA').read_bytes(), self.payload)

    def test_verified_file_survives_unreadable_padding_and_retry_refuses_it(self):
        self.src.write_bytes(archive(record('DATA', self.payload+b'PAD', eof=len(self.payload))))
        for cleanup in (False, True):
            out = self.run_extract(4, cleanup=cleanup, read_at=13)
            self.assertIn('DATA extracted; Corrupt archive.', out)
            self.assertIn('removes=0', out)
            self.assertEqual((self.dst/'DATA').read_bytes(), self.payload)
            if not cleanup:
                (self.dst/'DATA').unlink()
        # truncated inside the padding: the same
        self.src.write_bytes(archive(record('DATA', self.payload+b'PAD', eof=len(self.payload)))[:-1])
        self.assertIn('Create failed', self.run_extract())
        (self.dst/'DATA').unlink()
        self.assertIn('DATA extracted; Corrupt archive.', self.run_extract())
        self.assertEqual((self.dst/'DATA').read_bytes(), self.payload)
        self.assertIn('Create failed', self.run_extract())
        self.assertEqual((self.dst/'DATA').read_bytes(), self.payload)

    def test_disk_member_uses_block_count_and_po_suffix(self):
        data = bytes(range(256))*4
        self.src.write_bytes(archive(record('LONGDISKIMAGENAME', data, kind=1, auxtype=2, eof=0)))
        self.assertIn('1 file(s) extracted', self.run_extract())
        target = self.dst/('LONGDISKIMAGENAME'[:12]+'.PO')
        self.assertEqual(target.read_bytes(), data)
        target.unlink()
        self.src.write_bytes(archive(record('SHORT', b'abc', kind=1, auxtype=2, eof=0)))
        self.assertIn('Extract failed', self.run_extract())
        self.assertEqual(list(self.dst.iterdir()), [])

    def test_truncated_headers_data_and_padding(self):
        whole = archive(record('DATA', self.payload+b'PAD', eof=len(self.payload)))
        for length in (0, 47, 48, 55, 107, 139, 143, 145, len(whole)-4):
            self.src.write_bytes(whole[:length])
            self.assertNotIn('file(s) extracted', self.run_extract())
            self.assertFalse((self.dst/'DATA').exists())

    def test_declared_stored_length_cannot_consume_following_record(self):
        self.src.write_bytes(archive(record('DATA', b'abc', eof=20), record('NEXT', b'next')))
        self.assertIn('Extract failed', self.run_extract())
        self.assertEqual(list(self.dst.iterdir()), [])

    def test_skipped_thread_truncation_error_and_no_next_file(self):
        for klass,fmt in ((0,0),(2,1)):
            extra = thread(b'comment', klass=klass, fmt=fmt)
            self.src.write_bytes(archive(record('DATA', self.payload, extra=[extra])))
            self.assertNotIn('file(s) extracted', self.run_extract(4))
            self.assertEqual(list(self.dst.iterdir()), [])
        # No data thread: a final skipped thread must really exist through EOF.
        data = archive(record('DATA', b'', extra=[thread(b'abc', klass=0, ceof=999)]))
        self.src.write_bytes(data)
        self.assertNotIn('file(s) extracted', self.run_extract())
        self.assertEqual(list(self.dst.iterdir()), [])

    def test_complete_skipped_threads_and_unsupported_diagnostic(self):
        for klass,fmt in ((0,0),(2,1)):
            self.src.write_bytes(archive(record('DATA', self.payload,
                                                extra=[thread(b'comment', klass=klass, fmt=fmt)])))
            out = self.run_extract()
            self.assertIn('Unsupported compression' if klass==2 else '1 file(s) extracted', out)
            self.assertEqual((self.dst/'DATA').read_bytes(), self.payload)
            (self.dst/'DATA').unlink()

    def test_full_count_read_errors_in_every_parser_phase(self):
        # archive reads: header, record, attributes, threads, name, data (2) and
        # the second pass over the data (2); 9, 11 and 12 read the output back
        for call in (1, 2, 3, 4, 5, 6, 7, 8, 10):
            self.assertNotIn('file(s) extracted', self.run_extract(12, read_at=call))
            self.assertEqual(list(self.dst.iterdir()), [])

    def test_completed_record_survives_later_failure_and_name_collision(self):
        for last in (record('LAST', b'end')[:-1], record('FIRST', b'replacement')):
            self.src.write_bytes(archive(record('FIRST', self.payload), last))
            self.assertNotIn('file(s) extracted', self.run_extract())
            self.assertEqual((self.dst/'FIRST').read_bytes(), self.payload)
            self.assertFalse((self.dst/'LAST').exists())
            (self.dst/'FIRST').unlink()

    def test_short_attributes_cannot_reuse_stale_header_fields(self):
        data = bytearray(self.src.read_bytes())
        for size in (8, 16, 31, 33, 257):
            struct.pack_into('<H', data, 54, size)
            self.src.write_bytes(data)
            self.assertIn('Corrupt archive', self.run_extract())
            self.assertEqual(list(self.dst.iterdir()), [])

    def test_long_name_is_saved_before_skipping_its_tail(self):
        self.src.write_bytes(archive(record('LONGNAME'+'Z'*505, self.payload)))
        self.assertIn('1 file(s) extracted', self.run_extract())
        self.assertEqual((self.dst/('LONGNAME'+'Z'*7)).read_bytes(), self.payload)

    def test_lzw_window_refill_and_output_errors(self):
        payload = bytes(range(256))*49
        for fmt in (2, 3):
            crc = 0
            for offset in range(0,len(payload),4096):
                crc = crc16(payload[offset:offset+4096].ljust(4096,b'\0'), crc)
            stream = (struct.pack('<H', crc) if fmt==2 else b'') + b'\xfe\xdb'
            for offset in range(0,len(payload),4096):
                stream += b'\0\x10' + (b'\0' if fmt==2 else b'')
                stream += payload[offset:offset+4096].ljust(4096,b'\0')
            stream += b'\0'
            self.src.write_bytes(archive(record('DATA', stream, fmt=fmt, eof=len(payload))))
            self.assertIn('1 file(s) extracted', self.run_extract())
            self.assertEqual((self.dst/'DATA').read_bytes(), payload)
            (self.dst/'DATA').unlink()
            for fault in (5, 6, 13, 16, 17, 19, 21):
                self.assertIn('Extract failed', self.run_extract(fault))
                self.assertFalse((self.dst/'DATA').exists())

    @staticmethod
    def raw_lzw(payload, fmt, crc=None):
        """An LZW container of raw chunks the host stand-in decoder copies."""
        if crc is None:
            crc = 0
            for offset in range(0, len(payload), 4096):
                crc = crc16(payload[offset:offset+4096].ljust(4096, b'\0'), crc)
        stream = (struct.pack('<H', crc) if fmt == 2 else b'') + b'\xfe\xdb'
        for offset in range(0, len(payload), 4096):
            stream += b'\0\x10' + (b'\0' if fmt == 2 else b'')
            stream += payload[offset:offset+4096].ljust(4096, b'\0')
        return stream + b'\0'

    def test_lzw1_stream_crc_covers_padded_chunks(self):
        payload = bytes(range(256))*20 + b'tail'
        good = self.raw_lzw(payload, 2)
        self.src.write_bytes(archive(record('DATA', good, fmt=2, eof=len(payload))))
        self.assertIn('1 file(s) extracted', self.run_extract())
        self.assertEqual((self.dst/'DATA').read_bytes(), payload)
        (self.dst/'DATA').unlink()
        # one bit of the padding of the last chunk: the file bytes are the same
        bad = bytearray(good)
        bad[-2] ^= 1
        for stream in (bytes(bad), self.raw_lzw(payload, 2, crc=crc16(payload) ^ 0x8000)):
            self.src.write_bytes(archive(record('DATA', stream, fmt=2, eof=len(payload))))
            out = self.run_extract()
            self.assertIn('CRC error: DATA not extracted.', out)
            self.assertIn('removes=1', out)
            self.assertFalse((self.dst/'DATA').exists())
        # a failed cleanup names the retained file
        self.assertIn('Cleanup failed: DATA retained', self.run_extract(cleanup=True))

    def test_thread_crc_of_version_3_records(self):
        payload = bytes(range(256))*20 + b'tail'
        right = crc16(payload, 0xFFFF)
        cases = ((dict(data=payload), 0), (dict(data=self.raw_lzw(payload, 3), fmt=3), 3),
                 (dict(data=self.raw_lzw(payload, 2), fmt=2), 2))
        for kwargs, fmt in cases:
            with self.subTest(fmt=fmt):
                self.src.write_bytes(archive(record('DATA', eof=len(payload), version=3, crc=right, **kwargs)))
                self.assertIn('1 file(s) extracted', self.run_extract())
                self.assertEqual((self.dst/'DATA').read_bytes(), payload)
                (self.dst/'DATA').unlink()
                self.src.write_bytes(archive(record('DATA', eof=len(payload), version=3, crc=right ^ 1, **kwargs)))
                self.assertIn('CRC error: DATA not extracted.', self.run_extract())
                self.assertFalse((self.dst/'DATA').exists())
                # before version 3 the field is not a CRC
                self.src.write_bytes(archive(record('DATA', eof=len(payload), version=2, crc=right ^ 1, **kwargs)))
                self.assertIn('1 file(s) extracted', self.run_extract())
                (self.dst/'DATA').unlink()
        # a disk image: the CRC covers blocks * 512
        disk = bytes(range(256))*4
        self.src.write_bytes(archive(record('DISK', disk, kind=1, auxtype=2, eof=0, version=3, crc=crc16(disk, 0xFFFF))))
        self.assertIn('1 file(s) extracted', self.run_extract())
        self.assertEqual((self.dst/'DISK.PO').read_bytes(), disk)

    def test_ram_disk_is_known_by_its_driver_not_its_name(self):
        for fault in (30, 31, 33):       # output on the /RAM driver, no ON_LINE, archive on it
            with self.subTest(fault=fault):
                out = self.run_extract(fault)
                self.assertIn('/RAM shares AUX', out)
                self.assertIn('opens=0', out)
                self.assertIn('reads=0', out)
                self.assertEqual(list(self.dst.iterdir()), [])
        out = self.run_extract(32)       # a volume merely named /RAMDISK
        self.assertIn('1 file(s) extracted', out)
        self.assertEqual((self.dst/'DATA').read_bytes(), self.payload)

    def test_lzw_header_and_chunk_lengths_are_bounded(self):
        for fmt in (2, 3):
            for stream in (b'', b'\xfe', b'\0'*8):
                self.src.write_bytes(archive(record('DATA', stream, fmt=fmt, eof=1)))
                self.assertIn('Extract failed', self.run_extract())
                self.assertFalse((self.dst/'DATA').exists())


if __name__ == '__main__':
    unittest.main()
