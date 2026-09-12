"""Real PT3 loader C: malformed headers, read/close failures, no hardware writes."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_six_plugins import PREFIX,ROOT


def module():
    b=bytearray(220);b[:13]=b'ProTracker 3.';b[13]=ord('3')
    b[99:105]=bytes([1,6,1,0,203,0]);b[201:203]=bytes([0,255])
    b[107:109]=(209).to_bytes(2,'little');b[169:171]=(215).to_bytes(2,'little')
    b[203:209]=(217).to_bytes(2,'little')*3
    b[209:215]=bytes([0,1,0,0,0,0]);b[215:217]=bytes([0,1])
    return bytes(b)

HARNESS=PREFIX+r'''
static int fault,started,stopped,reads,phase,misses,frame_calls,key_calls,opened,closed;
static unsigned char *original;
static unsigned char calls[2];
static const unsigned char lengths[4][2]={{3,5},{5,3},{4,5},{5,4}};
static unsigned char current;
static size_t rd(void* p,size_t s,size_t n,FILE* f){size_t r;++reads;r=fread(p,s,n,f);if(fault==8&&reads==1)return 0;if(fault==6&&phase)return r?r-1:0;return r;}
static int ferr(FILE* f){return fault==1 || ((fault==7||fault==15&&current)&&phase) || ferror(f);}
static int cls(FILE* f){int r=fclose(f);++closed;return fault==2?EOF:r;}
static int seekf(FILE*f,long n,int how){++misses;return (fault==9||fault==5&&phase)?-1:fseek(f,n,how);}
static FILE* opn(const char* p,const char* m){FILE*f=fault==3?NULL:fopen(p,m);if(f)++opened;return f;}
unsigned char host_song[512],host_cache[8][256],host_second[512],host_tables2[448];
#define ferror ferr
#include "src/plugins/pt3.c"
#undef ferror
unsigned int pt_end,pt_base;
unsigned char pt_chip,pt_dual,pt_running,pt_regs[14],pt_cache_pages[8]={0x3B,0x3C,0x3D,0x3E,0x3F,0,0,0};
void pt_swap(void){}
void __fastcall__ pt_play_tables(unsigned char*p){(void)p;}
void __fastcall__ pt_tables(unsigned char* p){memset(p,0xA5,448);}
unsigned char pt_init(void){return fault==4;}
unsigned char pt_frame(void){
 unsigned page,j,slot,want; ++frame_calls;
 if(pt_dual){
  if(fault>=16){if(calls[current]>=lengths[fault-16][current])abort();return ++calls[current]==lengths[fault-16][current]?2:0;}
  if(pt_end<202 || pt_base+(unsigned long)pt_end>file_length-16)abort();
  for(page=pt_base/256;page*256<pt_base+(unsigned long)pt_end;++page){
   slot=pt_page(page);if(!slot)return 1;for(j=0;j<CACHE_COUNT;++j)if(pt_cache_pages[j]==slot)break;slot=j;
   want=file_length-page*256;if(want>256)want=256;
   for(j=0;j<want;++j)if(CACHE(slot)[j]!=original[page*256+j])abort();
  }
  return 2;
 }
 for(page=2;page*256<n;++page){
  slot=pt_page(page);if(!slot)return 1;for(j=0;j<CACHE_COUNT;++j)if(pt_cache_pages[j]==slot)break;slot=j;
  want=n-page*256;if(want>256)want=256;
  for(j=0;j<want;++j)if(CACHE(slot)[j]!=original[page*256+j])abort();
 }
 if(n>512 && !pt_page(2))return 1; /* re-read an evicted page */
 if(pt_pages[0]!=HEADER_PAGE)abort();
 return 2;
}
void __fastcall__ pt_hw_start(unsigned char slot){if(slot!=2)abort();started++;phase=1;}
unsigned char pt_tick(void){return 1;}
void pt_output(void){}
void pt_silence(void){}
void pt_mute(void){}
void pt_hw_stop(void){stopped++;}
static unsigned char mkey(unsigned char k){return k==27||k==21;}
static void info(const unsigned char* h){if(memcmp(h,original,file_length<512?file_length:512))abort();}
static char key(void){if(!phase)return fault==14?27:0;++key_calls;if(fault==12)return 27;if(fault==13)return 21;if(fault==11&&(key_calls==1||key_calls==3))return 'P';return 0;}
static void cls_screen(void){}
static void puts_screen(const char* s){(void)s;}
int main(int argc,char**argv){
 static struct A2fcApi api;static struct Entry e;
 static unsigned char buf[512];static char note[80],sel[80];FILE*ref;unsigned i;
 original=malloc(65537);ref=fopen(argv[1],"rb");fread(original,1,65537,ref);fclose(ref);
 api.version=4;api.media_key=mkey;api.music_info=info;fault=atoi(argv[2]);api.arg=atoi(argv[3]);strcpy(e.name,"TEST.PT3");e.size=1;
 api.full=argv[1];api.selected=&e;api.note=note;api.reselect=sel;api.copy_buf=buf;
 api.fopen=opn;api.fread=rd;api.fclose=cls;api.fseek=seekf;api.strcpy=strcpy;api.cgetc=key;
 api.clrscr=cls_screen;api.cputs=puts_screen;
 plugin_entry(&api);
 if(closed!=opened)abort();
 if(fault>=16 && memcmp(calls,lengths[fault-16],2))abort();
 if(started){for(i=0;i<448;++i)if(buf[i]!=0xA5)abort();if(strcmp(sel,"TEST.PT3"))abort();}
 if(fault==11 && (frame_calls!=1||key_calls!=3))abort();
 if((fault==12||fault==13)&&frame_calls)abort();
 printf("%d %d %s\n",started,stopped,note);free(original);return 0;
}
'''



class PT3(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='pt3-host-');cls.p=Path(cls.tmp.name)
        (cls.p/'test.c').write_text(HARNESS)
        cls.exe=cls.p/'test'
        subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-I',str(ROOT),str(cls.p/'test.c'),'-o',str(cls.exe)],check=True,capture_output=True)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def run_data(self,data,good=False,fault=0,card=2,error=None):
        p=self.p/'source';p.write_bytes(data)
        out=subprocess.check_output([str(self.exe),str(p),str(fault),str(card)],text=True,timeout=5)
        self.assertTrue(out.startswith('1 1 ' if good else '0 0 '),out)
        self.assertEqual(p.read_bytes(),data)
        if error:self.assertIn(error,out)
    def test_valid_module_ignores_stale_panel_size(self):self.run_data(module(),True)
    def test_io_errors_and_no_card(self):
        for fault in (1,3,4):self.run_data(module(),fault=fault)
        self.run_data(module(),True,fault=2,error="close error")
        self.run_data(module(),card=0)
    def test_truncated_and_oversized(self):
        b=module()
        for n in (0,12,13,100,200,201,202,208):self.run_data(b[:n])
        self.run_data(b+bytes(65536-len(b)))
    def test_large_modules_cache_eviction_and_last_page(self):
        for size in (512,513,4608,4609,8192,32769,65535):
            b=module()+bytes(i%251 for i in range(size-len(module())))
            self.run_data(b,True)
    def test_stream_errors_and_pause_navigation(self):
        b=module()+bytes(8192-len(module()))
        for fault in (5,6,7):self.run_data(b,True,fault=fault,error='read/seek/close error')
        self.run_data(b,fault=8)
        self.run_data(b,fault=14)
        for fault in (11,12,13):self.run_data(b,True,fault=fault)
    def test_old_frequency_tables_are_accepted(self):
        for table in range(4):
            b=bytearray(module());b[99]=table;self.run_data(bytes(b),True)
    def test_turbosound_container_and_failures(self):
        first=module()+bytes(293);second=bytearray(module());second[13]=ord('7');second[99]=2
        footer=b'PT3!'+len(first).to_bytes(2,'little')+b'PT3!'+len(second).to_bytes(2,'little')+b'02TS'
        valid=first+second+footer
        self.run_data(valid,True)
        for fault in range(16,20):self.run_data(valid,True,fault=fault)
        self.run_data(valid,True,fault=15,error='read/seek/close error')
        self.run_data(valid,fault=9,error='read/seek/close error')
        for pos in (len(valid)-16,len(valid)-12,len(valid)-10,len(valid)-6,len(first),len(first)+99):
            bad=bytearray(valid);bad[pos]=255;self.run_data(bad)
        bad=bytearray(valid);bad[-6:-4]=bytes(2);self.run_data(bad)
    def test_header_and_order_bounds(self):
        for pos,value in ((0,0),(99,4),(100,0),(101,0),(101,255),(102,1),(103,255),(104,255),(201,1),(201,255),(202,0),(107,0),(169,0)):
            b=bytearray(module());b[pos]=value;self.run_data(bytes(b))


if __name__=='__main__':unittest.main()
