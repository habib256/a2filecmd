"""Real C entry points, malformed input and I/O failures; native render oracles."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_six_plugins import PREFIX, ROOT


def row(y):
    return (y & 7)*1024 + ((y >> 3) & 7)*128 + (y >> 6)*40


def font_page(data):
    flag,last,height=data[:3]; count=last+1; cols=1+(flag==128)
    assert flag in (0,128) and 0<count<=128 and 0<height<=22
    assert len(data)==3+count+height*cols*count
    widths=data[3:3+count]; assert max(widths)<=cols*7
    out=bytearray(8192)
    for g in range(count):
        for y in range(height):
            for x in range(widths[g]):
                bit=data[3+count+(y*cols+x//7)*count+g] & (1<<(x%7))
                if bit: out[row((g//16)*(height+2)+y)+4+(g%16)*2+x//7] |= bit
    return bytes(out)


def clip_page(data):
    assert len(data) in (572,576)
    out=bytearray(8192)
    for y in range(156):
        for x in range(176):
            if not data[(y//3)*11+(x//2)//8] & (128 >> ((x//2)%8)):
                px=x+52; out[row(y+18)+px//7]|=1<<(px%7)
    return bytes(out)


def lz_page(data):
    assert data[0]==0x66
    out=bytearray(); at=1
    while True:
        token=data[at]; at+=1; n=token>>4
        if n==15: n+=data[at]; at+=1
        assert at+n<=len(data)
        out+=data[at:at+n]; at+=n
        n=token&15
        if n==15:
            ext=data[at]; at+=1
            if ext==254: break
            if ext==253: continue
            n+=ext
        off=int.from_bytes(data[at:at+2],'little'); at+=2
        assert off<len(out)
        for i in range(n+4): out.append(out[off+i])
        assert len(out)<=8192
    assert at==len(data) and len(out)<=8192
    return bytes(out).ljust(8192,b'\0')


HARNESS=PREFIX+r'''
unsigned char host_page[8192];
static int fault,shown,calls;
static size_t rd(void* p,size_t s,size_t n,FILE* f) {
 ++calls;
 if(fault==1 && calls==2)return 0;
 return fread(p,s,n,f);
}
static int ferr(FILE* f) { return fault==2 || (fault==1 && calls>=2) || ferror(f); }
static int cls(FILE* f) { int r=fclose(f);return fault==3?EOF:r; }
static FILE* opn(const char* p,const char* m) {return fault==4?NULL:fopen(p,m);}
#define ferror ferr
#include "src/plugins/PLUGIN.c"
#undef ferror
void hv_clear(void){memset(host_page,0,8192);}
void hv_show(void){shown=1;}
unsigned char* hv_row(unsigned char y) {
 if(y>=192)abort();
 return host_page+(y&7)*1024+((y>>3)&7)*128+(y>>6)*40;
}
HELPERS
static char key(void){return 27;}
int main(int argc,char**argv) {
 static struct A2fcApi api;static struct Entry e;
 static unsigned char buf[512];static char note[80],sel[80];
 fault=atoi(argv[2]);e.type=atoi(argv[3]);strcpy(e.name,"SOURCE");
 api.full=argv[1];api.selected=&e;api.note=note;api.reselect=sel;
 api.copy_buf=buf;api.fopen=opn;api.fread=rd;api.fclose=cls;
 api.version=4;api.strcpy=strcpy;api.wait_key=key;api.media_wait=key;
 memset(host_page,0xa5,8192);plugin_entry(&api);
 fwrite(host_page,1,8192,stdout);
 return shown?0:2;
}
'''
FONT=r'''
void __fastcall__ font_draw(unsigned char* b){
 unsigned int g,w;
 for(g=0;g<fn;++g){w=b[g]>fc*7?b[g]-fc*7:0;if(w>7)w=7;
 hv_row((g/16)*(fh+2)+fr)[4+(g%16)*2+fc]=b[128+g]&((1<<w)-1);}
}
'''
PS=r'''
void __fastcall__ ps_draw(unsigned char* b){
 unsigned int x,y,px;
 for(y=0;y<3;++y)for(x=0;x<176;++x)
 if(!(b[x/16]&(128>>((x/2)%8)))){
 px=52+x;hv_row(py+y)[px/7]|=1<<(px%7);}
}
'''


class SampleMedia(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='a2fc-media-');cls.root=Path(cls.tmp.name);cls.exes={}
        for n,helper in [('fontview',FONT),('printshop',PS),('lz4fh','')]:
            src=cls.root/(n+'.c');src.write_text(HARNESS.replace('plugins/PLUGIN.c','plugins/'+n+'.c').replace('HELPERS',helper))
            exe=cls.root/n
            subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-I',str(ROOT),str(src),'-o',str(exe)],check=True,capture_output=True)
            cls.exes[n]=exe

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def run_file(self,name,data,good=True,fault=0,expected=None):
        p=self.root/'input';p.write_bytes(data)
        r=subprocess.run([str(self.exes[name]),str(p),str(fault),str(7 if name=='fontview' else 6)],capture_output=True,timeout=5)
        self.assertEqual(r.returncode,0 if good else 2,r.stderr)
        self.assertEqual(p.read_bytes(),data)
        if expected is not None:self.assertEqual(r.stdout,expected)

    def fixtures(self):
        font=bytes([128,127,16])+bytes([14]*128)+bytes((i*31)&127 for i in range(4096))
        clip=bytes((i*37)&255 for i in range(572))
        lz=b'\x66\x40ABCD\x00\x00\x0f\xfe'
        return [('fontview',font,font_page),('printshop',clip,clip_page),('lz4fh',lz,lz_page)]

    def test_valid_pixels(self):
        for name,data,oracle in self.fixtures():self.run_file(name,data,expected=oracle(data))
        self.run_file('printshop',bytes(576),expected=clip_page(bytes(576)))

    def test_io_failures_never_display(self):
        for name,data,_ in self.fixtures():
            for fault in (1,2,3,4):self.run_file(name,data,False,fault)

    def test_truncations_and_trailing_data(self):
        for name,data,_ in self.fixtures():
            for n in (0,1,2,3,len(data)//2,len(data)-1):self.run_file(name,data[:n],False)
            self.run_file(name,data+b'X',False)

    def test_font_bounds(self):
        for head in (b'\x01\x7f\x08',b'\0\xff\x08',b'\0\x80\x08',b'\0\x7f\0',b'\0\x7f\x17'):
            self.run_file('fontview',head+bytes(5000),False)
        self.run_file('fontview',b'\0\x7f\x08'+bytes([8])*128+bytes(1024),False)

    def test_lz_bad_matches_and_overflow(self):
        for data in (b'\x66\0\0\0',b'\x66\x10A\x01\0',b'\x66\x0f\xff\0\0',b'\x66\xf0\xff'):
            self.run_file('lz4fh',data,False)
        self.run_file('lz4fh',b'\x66\x1fA\xfc\0\0'+b'\x0f\xfc\0\0'*32+b'\x0f\xfe',False)


if __name__=='__main__':unittest.main()
