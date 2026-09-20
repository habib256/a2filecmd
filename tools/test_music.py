"""Real MB1 loader C: malformed headers, read/close failures, no hardware writes."""
import subprocess
import shutil
import tempfile
import unittest
from pathlib import Path
from test_six_plugins import PREFIX,ROOT


def module():
    return b'MB1\0\0\0\x08\0'+bytes([0xA0,12,0x80,0,10,0x85,59,10,0xB3,31,10,0x95,0xF0,10,0xE0])

HARNESS=PREFIX+r'''
static int fault,started,stopped,reads;
static size_t rd(void* p,size_t s,size_t n,FILE* f){++reads;return fread(p,s,n,f);}
static int ferr(FILE* f){return fault==1 || ferror(f);}
static int cls(FILE* f){int r=fclose(f);return fault==2?EOF:r;}
static FILE* opn(const char* p,const char* m){return fault==3?NULL:fopen(p,m);}
unsigned char host_song[4096];
#define ferror ferr
#include "src/plugins/music.c"
#undef ferror
unsigned char mb_regs[28];
const unsigned int mb_notes[60]={977};
void __fastcall__ mb_hw_start(unsigned char slot){if(slot!=2)abort();started++;}
unsigned char mb_tick(void){return 1;}
void mb_output(void){}
void mb_silence(void){}
void mb_hw_stop(void){stopped++;}
static unsigned char mkey(unsigned char k){return k==27;}
static void info(const unsigned char* h){(void)h;}
static char key(void){return 0;}
static void cls_screen(void){}
static void puts_screen(const char* s){(void)s;}
int main(int argc,char**argv){
 static struct A2fcApi api;static struct Entry e;
 static unsigned char buf[512];static char note[80],sel[80];
 api.version=4;api.media_key=mkey;api.music_info=info;fault=atoi(argv[2]);api.arg=atoi(argv[3]);strcpy(e.name,"TEST.PT3");e.size=1;
 api.full=argv[1];api.selected=&e;api.note=note;api.reselect=sel;api.copy_buf=buf;
 api.fopen=opn;api.fread=rd;api.fclose=cls;api.strcpy=strcpy;api.cgetc=key;
 api.clrscr=cls_screen;api.cputs=puts_screen;
 plugin_entry(&api);printf("%d %d %s\n",started,stopped,note);return 0;
}
'''


class MUSIC(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='pt3-host-');cls.p=Path(cls.tmp.name)
        (cls.p/'test.c').write_text(HARNESS)
        cls.exe=cls.p/'test'
        subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-I',str(ROOT),str(cls.p/'test.c'),'-o',str(cls.exe)],check=True,capture_output=True)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def run_data(self,data,good=False,fault=0,card=2):
        p=self.p/'source';p.write_bytes(data)
        out=subprocess.check_output([str(self.exe),str(p),str(fault),str(card)],text=True,timeout=5)
        self.assertTrue(out.startswith('1 1 ' if good else '0 0 '),out)
        self.assertEqual(p.read_bytes(),data)
    def test_valid_module_ignores_stale_panel_size(self):self.run_data(module(),True)
    def test_io_errors_and_no_card(self):
        for fault in (1,2,3):self.run_data(module(),fault=fault)
        self.run_data(module(),card=0)
    def test_truncated_and_oversized(self):
        b=module()
        for n in range(len(b)):self.run_data(b[:n])
        self.run_data(b+bytes(4097-len(b)))
    def test_exact_capacity_and_all_voices(self):
        self.run_data(module()[:8]+bytes([1])*4087+bytes([0xE0]),True)
        for voice in range(6):
            self.run_data(module()[:8]+bytes([0xA0|voice,15,0x80|voice,59,1,0xB0|voice,31,1,0x90|voice,0xE0]),True)
    def test_packet_bounds(self):
        for tail in (b'\x80',b'\x86\0\xE0',b'\x80\x3c\xE0',b'\xA0\x10\xE0',b'\xB0\x20\xE0',b'\0\xE0',b'\xE0\1',b'\xC0\xE0'):
            self.run_data(module()[:8]+tail)



class CardProbe(unittest.TestCase):
    def test_real_probe_wakes_only_iic_and_still_rejects_absent_card(self):
        # sim65 has RAM rather than VIA timers at $Cn04: no card may be
        # reported. Execute the unmodified production assembly and observe
        # every byte of the card/ROM pages, on both CPU instruction sets.
        harness = r"""
#include <string.h>
unsigned char music_detect_card(void);
unsigned char a2fc_mouse;
static const unsigned char ids[][2] = {
 {0x06,0x00}, {0x06,0x00}, {0x06,0xE0}, {0x06,0xEA}, {0xEA,0xEA}, {0xEA,0x00}
};
int main(void) {
 unsigned i, j;
 for(i=0;i<sizeof(ids)/sizeof(ids[0]);++i) {
  memset((void*)0xC100,0xA5,0x700);
  if(i==0) *(volatile unsigned char*)0xC4FB=0xD6;
  a2fc_mouse=4;
  *(volatile unsigned char*)0xFBB3=ids[i][0];
  *(volatile unsigned char*)0xFBC0=ids[i][1];
  if(music_detect_card()!=0)return 1;
#ifdef A2FC_TEST_NOMOUSE
  if(a2fc_mouse!=4)return 3;
#else
  if(a2fc_mouse!=(i==1?0:4))return 3;
#endif
  for(j=0;j<0x700;++j) {
   unsigned char expected=(i<2 && j==0x303)?0:0xA5;
   if(i==0 && j==0x3FB)expected=0xD6;
   if(((volatile unsigned char*)0xC100)[j]!=expected)return 2;
  }
 }
 return 0;
}
"""
        with tempfile.TemporaryDirectory(prefix='mb-probe-') as tmp:
            root=Path(tmp)
            (root/'harness.c').write_text(harness)
            # Avoid compiler intermediates in the source tree.
            shutil.copyfile(ROOT/'src/mb_probe.s',root/'probe.s')
            for cpu,target in [('6502','sim6502'),('65c02','sim65c02')]:
                with self.subTest(cpu=cpu):
                    flags = ['--asm-define','A2_6502','-DA2FC_TEST_NOMOUSE'] if cpu=='6502' else []
                    subprocess.run(['cl65','-t',target,'--cpu',cpu,'-O',
                                    *flags,
                                    '-o',str(root/'probe'),str(root/'harness.c'),
                                    str(root/'probe.s')],check=True)
                    subprocess.run(['sim65',str(root/'probe')],check=True,timeout=20)

if __name__=='__main__':unittest.main()
