"""Production FONTRIX C: glyph bits, actual EOF, all pointers and I/O faults."""
import random
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_six_plugins import PREFIX, ROOT

HARNESS = PREFIX + r'''
static int fault,opens,reads,closes,ioerr;
static int ferr(FILE* f){return ioerr || ferror(f);}
#define ferror ferr
#include "src/plugins/fontrix.c"
#undef ferror
static char screen[24][80];
static unsigned char xx,yy;
static const char* keys;
static void clear(void){memset(screen,' ',sizeof screen);}
static void xy(unsigned char x,unsigned char y){xx=x;yy=y;}
static void put(char c){if(xx>=80 || yy<1 || yy>20)abort();screen[yy][xx++]=c;}
static int print(const char* fmt,...){return 0;}
static void message(const char* s){(void)s;}
static char key(void){
 unsigned char i;char k=*keys;
 puts("PAGE");for(i=1;i<21;++i){fwrite(screen[i],1,80,stdout);putchar('\n');}
 if(k)++keys;return k=='N'?21:k=='B'?8:27;
}
static FILE* opn(const char* p,const char* m){
 ++opens;ioerr=0;if(strcmp(m,"rb"))abort();return fault==1?NULL:fopen(p,m);
}
static size_t read_(void* p,size_t z,size_t n,FILE* f){
 ++reads;if(fault==2 || (fault==5 && opens>=2)){ioerr=1;return 0;}
 return fread(p,z,n,f);
}
static int close_(FILE* f){++closes;return fclose(f) || fault==3 || (fault==6 && opens>=2)?EOF:0;}
static int seek_(FILE* f,long n,int whence){
 if(fault==4)return -1;
#ifdef __CC65__
 /* sim65 has no lseek: this callback emulates a fresh file's SEEK_SET. */
 if(whence!=SEEK_SET || n<0)abort();
 while(n--){if(fgetc(f)==EOF)return -1;}return 0;
#else
 return fseek(f,n,whence);
#endif
}
int main(int argc,char**argv){
 static struct A2fcApi api;static struct Entry e;static unsigned char buf[512];
 static char note[80],reselect[80];fault=atoi(argv[2]);keys=argv[3];
 strcpy(e.name,"SET.TEST");e.type=6;e.aux=0x6400;e.size=atoi(argv[4]);
 api.full=argv[1];api.selected=&e;api.copy_buf=buf;api.note=note;api.reselect=reselect;
 api.fopen=opn;api.fread=read_;api.fclose=close_;api.fseek=seek_;api.strcpy=strcpy;
 api.clrscr=clear;api.cprintf=print;api.message=message;api.gotoxy=xy;api.cputc=put;api.wait_key=key;
 plugin_entry(&api);fprintf(stderr,"%s\n",note);return 0;
}
'''


def fixture(first=65, height=9, widths=(1, 2, 4), inverted=False):
    rng = random.Random(6400)
    head = bytearray(384)
    head[16:21] = bytes([len(widths), first, 1, max(widths)*8, height])
    head[24:27] = bytes.fromhex('6f084d' if inverted else '90f7b2')
    body = bytearray()
    for i, width in enumerate(widths):
        p = 32 + 2*(first+i-32)
        head[p:p+2] = (384+len(body)).to_bytes(2, 'little')
        body.extend(rng.randbytes(width * height))
    p = 32 + 2*(first+len(widths)-32)
    head[p:p+2] = (384+len(body)).to_bytes(2, 'little')
    return bytes(head+body)


def preview(data, char):
    h = data[20]
    p = 32+2*(char-32)
    begin, end = int.from_bytes(data[p:p+2], 'little'), int.from_bytes(data[p+2:p+4], 'little')
    width = (end-begin)//h
    scale = 1 if h<=20 else 2
    rows = []
    for y in range(20):
        line = [' '] * 80
        if y*scale<h:
            for x in range(width*8):
                ink = any(data[begin+r*width+x//8] & (1 << (x%8))
                          for r in range(y*scale, min(h, (y+1)*scale)))
                line[8+x*2:10+x*2] = '**' if ink else '  '
        rows.append(''.join(line))
    return rows


class Fontrix(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='fontrix-')
        cls.p = Path(cls.tmp.name)
        (cls.p/'h.c').write_text(HARNESS)
        cls.exe = cls.p/'test'
        subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-I',str(ROOT),
                        str(cls.p/'h.c'),'-o',str(cls.exe)],check=True,capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def view(self,data,keys='',fault=0,size=1,good=True):
        src=self.p/'source';src.write_bytes(data)
        r=subprocess.run([str(self.exe),str(src),str(fault),keys,str(size)],
                         check=True,capture_output=True,text=True,timeout=10)
        self.assertEqual(src.read_bytes(),data)
        if good:self.assertEqual(r.stderr,'\n')
        else:self.assertNotEqual(r.stderr,'\n');self.assertEqual(r.stdout,'')
        return [chunk.splitlines() for chunk in r.stdout.split('PAGE\n')[1:]]

    def test_every_glyph_and_bits_in_both_signatures(self):
        for h in (1,9,20,21,31,32):
            for inverted in (False,True):
                data=fixture(height=h,inverted=inverted)
                self.assertEqual(self.view(data,'NN'),[preview(data,c)for c in range(65,68)])

    def test_previous_glyph_and_navigation_bounds(self):
        data=fixture()
        self.assertEqual(self.view(data,'BNNB'),[preview(data,c)for c in (65,65,66,67,66)])

    def test_all_pointers_are_checked_before_first_preview(self):
        data=fixture()
        for value in (0,383,65535):
            b=bytearray(data);p=32+2*(67-32);b[p:p+2]=value.to_bytes(2,'little')
            self.view(bytes(b),good=False)
        for off,value in ((16,0),(16,95),(17,32),(17,127),(18,2),(20,0),(20,33),(24,0)):
            b=bytearray(data);b[off]=value;self.view(bytes(b),good=False)
        # Last pointer correct but glyph width exceeds four bytes.
        self.view(fixture(widths=(1,2,5)),good=False)

    def test_actual_eof_and_stale_sizes(self):
        data=fixture()
        for n in range(len(data)):
            self.view(data[:n],good=False)
        for size in (0,1,65000):self.view(data,size=size)
        self.view(data+bytes(20481-len(data)),good=False)

    def test_read_seek_and_close_errors_show_nothing(self):
        for fault in range(1,7):self.view(fixture(),fault=fault,good=False)

    def test_cc65_on_both_processors(self):
        if not shutil.which('cl65') or not shutil.which('sim65'):
            self.skipTest('cc65/sim65 unavailable')
        target_path=Path(subprocess.check_output(['cl65','--print-target-path'],text=True).strip())
        for cpu,target in (('6502','sim6502'),('65c02','sim65c02')):
            cfg=(target_path.parent/'cfg'/(target+'.cfg')).read_text()
            config=self.p/(target+'.cfg')
            config.write_text(cfg.replace('\n    CODE:','\n    OVLHDR: load = MAIN, type = ro;\n    CODE:',1))
            exe=self.p/target
            subprocess.run(['cl65','-t',target,'--cpu',cpu,'-O','-Cl','-C',str(config),
                            '-I',str(ROOT),'-o',str(exe),str(self.p/'h.c')],check=True,capture_output=True)
            for height in (9,32):
                src=self.p/'native-source';data=fixture(height=height);src.write_bytes(data)
                for fault in (0,2,3,4,5,6):
                    args=[str(src),str(fault),'NN','0']
                    expected=subprocess.run([str(self.exe)]+args,check=True,capture_output=True)
                    actual=subprocess.run(['sim65',str(exe)]+args,check=True,capture_output=True,timeout=20)
                    self.assertEqual(actual.stdout,expected.stdout)
                    self.assertEqual(actual.stderr,expected.stderr)
                    self.assertEqual(src.read_bytes(),data)

    def test_real_fontpaks_when_available(self):
        from legacy_corpus import dos_files
        root=Path.home()/'.cache/a2fc/asimov_corpus/raw/images'
        found=0
        for disk in root.rglob('*Fontrix*.dsk'):
            for name,kind,aux,data in dos_files(disk.read_bytes()):
                if name.startswith('SET.') and aux==0x6400:
                    found+=1
                    with self.subTest(font=name):
                        pages=self.view(data,'N'*(data[16]-1))
                        self.assertEqual(pages,[preview(data,c)for c in range(data[17],data[17]+data[16])])
        if not found:self.skipTest('real fontpaks unavailable')


if __name__=='__main__':unittest.main()
