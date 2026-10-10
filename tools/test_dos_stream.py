"""Production prototype C, real-driver READ_BLOCK callbacks and image I/O.

Read-only disposable DOS disks, expected bytes from an independent fixture.
No write/delete/format services exist in this harness.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from mini33_fixture import make_disk, offset
from take1_ref import DosImage
from test_six_plugins import PREFIX

HARNESS = PREFIX + r'''
#include <stdarg.h>
static unsigned char buffer[512];
static const char* source_path;
static const char* keys;
static unsigned int fault,reads,opens,closes;
static unsigned char ioerr,shown;
static int ferr(FILE* f){return ioerr || ferror(f);}
#define ferror ferr
#include "src/plugins/dosview.c"
#undef ferror
static int print(const char* fmt,...){int r;va_list ap;va_start(ap,fmt);r=vprintf(fmt,ap);va_end(ap);return r;}
static void put(char c){putchar(c);}
static void xy(unsigned char x,unsigned char y){(void)x;if(!x && y)putchar('\n');}
static void clear(void){}
static void message(const char* s){printf("\nMSG %s\n",s);}
static char key(void){char c=*keys;if(c)++keys;return c=='E'||!c?27:c=='N'?' ':c;}
void host_lores(const unsigned char* p){
 unsigned char row;unsigned int at;unsigned char page[1024];
 memset(page,0xa5,sizeof page);++shown;
 for(row=0;row<24;++row){at=(unsigned int)(row&7)*128+(unsigned int)(row>>3)*40;memcpy(page+at,p+at,40);}
 puts("LORES");fwrite(page,1,1024,stdout);
}
void host_hgr(const unsigned char* p,unsigned int n){++shown;puts("HGR");fwrite(p,1,n,stdout);}
/* sim65 has no lseek. Read/discard supplies the backend positioning
 * callback there; the production stream has no dependency on FILE layout. */
static int skip_(FILE* f,unsigned long n){
 unsigned char discard[256];unsigned int m;
 while(n){m=n>256?256:(unsigned int)n;if(fread(discard,1,m,f)!=m)return -1;n-=m;}return 0;
}
static int part(unsigned long at,unsigned char* p){
 FILE* f=fopen(source_path,"rb");int r;
 if(!f)return 0;
#ifdef __CC65__
 r=skip_(f,at);
#else
 r=fseek(f,(long)at,SEEK_SET);
#endif
 r=!r && fread(p,1,256,f)==256 && !ferror(f);
 if(fclose(f))r=0;return r;
}
static unsigned char mli(unsigned char cmd,void* ptr){
 static const unsigned char order[16]={0,14,13,12,11,10,9,8,7,6,5,4,3,2,1,15};
 unsigned char* p=ptr;unsigned int b;unsigned char h,s,t;
 if(cmd!=0x80 || p[0]!=3 || p[1]!=0xe0)abort();
 ++reads;if(fault==reads)return 0x27;
 b=p[4]|((unsigned int)p[5]<<8);t=b/8;if(t>=35)abort();
 for(h=0;h<2;++h){s=order[(b&7)*2+h];if(!part(((unsigned long)t*16+s)*256,buffer+h*256))return 0x27;}
 return 0;
}
static FILE* opn(const char* p,const char* m){
 ++opens;if(strcmp(m,"rb"))abort();return fault==1001?NULL:fopen(p,m);
}
static size_t read_(void* p,size_t z,size_t n,FILE* f){
 ++reads;if(fault==reads){ioerr=1;return 0;}
 n=fread(p,z,n,f);if(fault==1004)ioerr=1;return n;
}
static int seek_(FILE* f,long at,int origin){
 if(fault==1003)return -1;if(origin!=SEEK_SET || at<0)abort();
#ifdef __CC65__
 if(fclose(f))return -1;dv_file=fopen(source_path,"rb");if(!dv_file)return -1;
 return skip_(dv_file,(unsigned long)at);
#else
 return fseek(f,at,origin);
#endif
}
static int close_(FILE* f){++closes;return fclose(f)||fault==1002?EOF:0;}
int main(int argc,char** argv){
 static struct A2fcApi api;static struct Panel panels[2];static struct Entry entry;
 static unsigned char active;static char note[80],sel[80];int c,ok;
 source_path=argv[1];fault=atoi(argv[3]);keys=argv[8];
 strcpy(entry.name,argv[4]);entry.mdate=strtoul(argv[5],0,10);entry.type=atoi(argv[6]);entry.size=strtoul(argv[7],0,10);
 strcpy(panels[0].path,source_path);panels[0].fs=FS_DOS33;panels[0].dir_key=0xe0;
 if(atoi(argv[2]))panels[0].img_len=strlen(source_path);
 api.panels=panels;api.active=&active;api.selected=&entry;api.copy_buf=buffer;api.note=note;api.reselect=sel;
 api.mli=mli;api.fopen=opn;api.fread=read_;api.fseek=seek_;api.fclose=close_;
 api.strcpy=strcpy;api.cprintf=print;api.cputc=put;api.gotoxy=xy;api.clrscr=clear;api.message=message;api.wait_key=key;
 if(!strncmp(argv[9],"view",4)&&argv[9][4])api.arg=argv[9][4]=='R'?KEY_RETURN:argv[9][4];
 if(strcmp(argv[9],"stream")){plugin_entry(&api);ok=!note[0];}
 else {
  A=&api;ok=dv_open(panels)&&ds_open(&entry);
  if(ok && argc>10)ok=ds_seek(strtoul(argv[10],0,10));
  if(ok)while((c=ds_get())>=0)putchar(c);
  if(ds_bad)ok=0;if(!dv_close())ok=0;
 }
 fprintf(stderr,"%d %u %u %u %u %s\n",ok,reads,opens,closes,shown,note);return 0;
}
'''


class Streams(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='direct-dos-', dir='/tmp')
        cls.p = Path(cls.tmp.name)
        (cls.p / 'test.c').write_text(HARNESS)
        cls.exe = cls.p / 'host'
        subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-I', str(ROOT),
                        str(cls.p / 'test.c'), '-o', str(cls.exe)], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_disk(self, disk, name='TEXT', typ=4, image=0, fault=0, at=None,
                 keys='', mode='stream', exe=None, size=1, key=None, good=True):
        src = self.p / ('DISK.2MG' if image == 2 else 'DISK.DSK')
        physical = disk
        if image == 2:
            head = bytearray(64);head[:4] = b'2IMG'
            head[24:28] = (64).to_bytes(4, 'little');head[28:32] = len(disk).to_bytes(4, 'little')
            disk = bytes(head) + disk
        src.write_bytes(disk)
        if key is None:
            t, s = DosImage(physical).find(name.encode())
            key = t*256+s
        args = [str(src), str(int(bool(image))), str(fault), name, str(key), str(typ), str(size), keys, mode]
        if at is not None:
            args.append(str(at))
        command = [str(self.exe)] if exe is None else ['sim65', str(exe)]
        r = subprocess.run(command + args, check=True, capture_output=True, timeout=45)
        self.assertEqual(src.read_bytes(), disk)
        fields = r.stderr.decode().split(maxsplit=5)
        self.assertEqual(int(fields[0]), int(good), r.stderr)
        return r.stdout, [int(x) for x in fields[:5]], fields[5] if len(fields)>5 else ''

    def test_physical_image_and_container_have_exact_bytes_and_stale_sizes(self):
        payload = bytes(range(256))*4+b'END'
        for kind, typ, prefix in ((0, 4, b''), (4, 6, b'\0 '+len(payload).to_bytes(2, 'little')),
                                  (1, 0xFA, len(payload).to_bytes(2, 'little')),
                                  (2, 0xFC, len(payload).to_bytes(2, 'little'))):
            raw = prefix+payload
            disk = make_disk([('TEXT', kind, raw)])
            expected = payload if prefix else raw+bytes((-len(raw))%256)
            for image in (0, 1, 2):
                for size in (0, 1, 0xffffff):
                    out, _, _ = self.run_disk(disk, typ=typ, image=image, size=size)
                    self.assertEqual(out, expected)

    def test_multiple_lists_and_seek_across_sector_boundaries(self):
        payload = bytes(range(256))*130
        disk = make_disk([('TEXT', 4, b'\0 '+len(payload).to_bytes(2, 'little')+payload)])
        for at in (0, 1, 251, 252, 253, 255, 256, 257, 122*256-4, len(payload)):
            for image in (0, 1):
                out, _, _ = self.run_disk(disk, typ=6, image=image, at=at)
                self.assertEqual(out, payload[at:])
        self.run_disk(disk, typ=6, at=len(payload)+1, good=False)

    def test_sparse_holes_have_zero_bytes(self):
        disk = bytearray(make_disk([('TEXT', 0, b'A'*256+b'B'*256+b'C'*256)]))
        t, s = DosImage(disk).find(b'TEXT');base=offset(t,s)
        disk[base+14:base+16] = b'\0\0'
        for image in (0, 1):
            out, _, _ = self.run_disk(bytes(disk), image=image)
            self.assertEqual(out, b'A'*256+bytes(256)+b'C'*256)

    def test_malformed_catalog_lists_identity_and_length(self):
        original = make_disk([('TEXT', 4, b'\0 \x05\0HELLO')])
        t, s = DosImage(original).find(b'TEXT');ts=offset(t,s)
        dt, ds = original[ts+12:ts+14];data=offset(dt,ds)
        cases = [(offset(17,0)+0x34, b'\x28'), (offset(17,15)+1, b'\x11\x0f'),
                 (ts+1, bytes([t,s])), (ts+5, b'\x01\0'),
                 (ts+12, b'\x23\0'), (ts+12, b'\0\x01'),
                 (ts+12, b'\x11\x0f'), (ts+14, original[ts+12:ts+14]),
                 (data+2, b'\xff\xff')]
        for at, value in cases:
            disk=bytearray(original);disk[at:at+len(value)]=value
            for image in (0, 1):
                self.run_disk(bytes(disk), typ=6, image=image, key=t*256+s, good=False)
        self.run_disk(original, name='WRONG', typ=6, key=t*256+s, good=False)
        self.run_disk(original, typ=4, key=t*256+s, good=False)
        for kind in (8,16,32,64):
            other=make_disk([('TEXT',kind,b'HELLO')])
            for image in (0,1,2):
                out,_,_=self.run_disk(other,typ=0,image=image)
                self.assertEqual(out,b'HELLO'+bytes(251))
        unsupported=make_disk([('TEXT',3,b'HELLO')])
        for image in (0,1,2):self.run_disk(unsupported,typ=0,image=image,good=False)

    def test_read_open_seek_close_errors_are_not_eof(self):
        payload=bytes(range(256))*6
        disk=make_disk([('TEXT',4,b'\0 '+len(payload).to_bytes(2,'little')+payload)])
        _, counts, _ = self.run_disk(disk, typ=6)
        for fault in range(1, counts[1]+1):
            self.run_disk(disk, typ=6, fault=fault, good=False)
        _, counts, _ = self.run_disk(disk, typ=6, image=1)
        for fault in (*range(1,counts[1]+1),1001,1002,1003,1004):
            self.run_disk(disk, typ=6, image=1, fault=fault, good=False)

    def test_text_hex_and_lores_frontends(self):
        text=b'FIRST\r'*22+b'SECOND\r'
        disk=make_disk([('TEXT',0,text)])
        for image in (0,1):
            out, _, _ = self.run_disk(disk, image=image, mode='view', keys='TNBE')
            self.assertIn(b'FIRST',out);self.assertIn(b'SECOND',out)
            out, _, _ = self.run_disk(disk, image=image, mode='view', keys='HE')
            self.assertIn(b'46 49 52 53 54 0D',out)
        picture=bytes(range(256))*4
        disk=make_disk([('TEXT',4,b'\0\x04\0\x04'+picture)])
        for image in (0,1,2):
            out, counts, _ = self.run_disk(disk, typ=6, image=image, mode='view', keys='IE')
            self.assertEqual(counts[4],1)
            shown=out.split(b'LORES\n')[1][:1024]
            expected=bytearray(b'\xa5'*1024)
            for row in range(24):
                at=(row&7)*128+(row>>3)*40;expected[at:at+40]=picture[at:at+40]
            self.assertEqual(shown,expected)
        _, counts, _ = self.run_disk(disk, typ=6, image=1, fault=1002, mode='view', keys='I', good=False)
        self.assertEqual(counts[4],0)

    def test_direct_keys_and_return_dispatch(self):
        text=make_disk([('TEXT',0,b'DIRECT TEXT\r')])
        binary=make_disk([('TEXT',4,b'\0 \x04\0ABCD')])
        picture=make_disk([('TEXT',4,b'\0\x04\0\x04'+bytes(1024))])
        for image in (0,1,2):
            for command in ('T','R'):
                out,_,_=self.run_disk(text,image=image,mode='view'+command,keys='E')
                self.assertIn(b'DIRECT TEXT',out)
            for command in ('H','R'):
                out,_,_=self.run_disk(binary,typ=6,image=image,mode='view'+command,keys='E')
                self.assertIn(b'000000: 41 42 43 44',out)
            for command in ('I','R'):
                _,counts,_=self.run_disk(picture,typ=6,image=image,mode='view'+command,keys='E')
                self.assertEqual(counts[4],1)

    def test_hgr_exact_bytes_short_page_and_all_io_failures(self):
        for length in (8184,8192):
            picture=bytes((i*17+i//128)&255 for i in range(length))
            for load in (0x2000,0x4000):
                disk=make_disk([('TEXT',4,load.to_bytes(2,'little')+length.to_bytes(2,'little')+picture)])
                for image in (0,1,2):
                    for command in ('I','R'):
                        out,counts,_=self.run_disk(disk,typ=6,image=image,mode='view'+command,keys='E')
                        self.assertEqual(counts[4],1)
                        self.assertEqual(out.split(b'HGR\n')[1][:8192],picture+bytes(8192-length))
                    for fault in (*range(1,counts[1]+1), *((1002,1003,1004) if image else ())):
                        _,failed,_=self.run_disk(disk,typ=6,image=image,fault=fault,mode='viewI',keys='E',good=False)
                        self.assertEqual(failed[4],0)

    def test_native_cc65_streams_on_both_cpus(self):
        if not shutil.which('cl65') or not shutil.which('sim65'):
            self.skipTest('cc65/sim65 unavailable')
        target_path=Path(subprocess.check_output(['cl65','--print-target-path'],text=True).strip())
        payload=bytes(range(256))*2+b'END'
        disk=make_disk([('TEXT',4,b'\0 '+len(payload).to_bytes(2,'little')+payload)])
        for cpu,target in (('6502','sim6502'),('65c02','sim65c02')):
            cfg=(target_path.parent/'cfg'/(target+'.cfg')).read_text()
            config=self.p/(target+'.cfg');config.write_text(cfg.replace('\n    CODE:', '\n    OVLHDR: load = MAIN, type = ro;\n    CODE:',1))
            exe=self.p/target
            subprocess.run(['cl65','-t',target,'--cpu',cpu,'-O','-Cl','-C',str(config),
                            '-I',str(ROOT),'-o',str(exe),str(self.p/'test.c')],check=True,capture_output=True)
            for image in (0,1,2):
                out, _, _ = self.run_disk(disk,typ=6,image=image,exe=exe)
                self.assertEqual(out,payload)
                self.run_disk(disk,typ=6,image=image,exe=exe,fault=3,good=False)
                out,_,_=self.run_disk(disk,typ=6,image=image,exe=exe,mode='viewR',keys='E')
                self.assertIn(b'000000: 00 01 02 03',out)


if __name__=='__main__':
    unittest.main()
