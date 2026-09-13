"""Real Electric Duet loader C: record validation, read/close failures, both outputs."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_six_plugins import PREFIX,ROOT
import mkdemo

HARNESS=PREFIX+r'''
static int fault,started,stopped,reads,speaker_notes,ay_writes;
static unsigned char ay_log[4096][2];
static size_t rd(void* p,size_t s,size_t n,FILE* f){++reads;return fread(p,s,n,f);}
static int ferr(FILE* f){return fault==1 || ferror(f);}
static int cls(FILE* f){int r=fclose(f);return fault==2?EOF:r;}
static FILE* opn(const char* p,const char* m){return fault==3?NULL:fopen(p,m);}
unsigned char host_song[7168];
#define ferror ferr
#include "src/plugins/duet.c"
#undef ferror
unsigned char* ed_pos;
unsigned char ed_lsr[2];
void __fastcall__ ed_pulse(unsigned char n){ed_lsr[0]=n<2?0x4A:0xEA;ed_lsr[1]=n<1?0x4A:0xEA;}
/* The speaker player's reading of the stream: records until the terminator. */
unsigned char ed_speaker(void){
 for(;;){
  unsigned char c=ed_pos[0];
  if(!c)return 0;
  if(c>1)++speaker_notes;
  ed_pos+=3;
 }
}
void __fastcall__ ay_start(unsigned char slot){if(slot!=4)abort();started++;}
unsigned char ay_tick(void){return 1;}
void __fastcall__ ay_write(unsigned int rv){if(!started)abort();if(ay_writes<4096){ay_log[ay_writes][0]=rv>>8;ay_log[ay_writes][1]=rv;}++ay_writes;}
void ay_silence(void){if(!started)abort();}
void ay_stop(void){if(!started)abort();stopped++;}
static unsigned char mkey_(unsigned char k){return k==27;}
static char key(void){return 0;}
static void cls_screen(void){}
static void puts_screen(const char* s){(void)s;}
int main(int argc,char**argv){
 static struct A2fcApi api;static struct Entry e;
 static unsigned char buf[512];static char note[80],sel[80];
 int i;
 api.version=4;api.media_key=mkey_;fault=atoi(argv[2]);api.arg=atoi(argv[3]);strcpy(e.name,"TEST.ED");e.size=1;
 api.full=argv[1];api.selected=&e;api.note=note;api.reselect=sel;api.copy_buf=buf;
 api.fopen=opn;api.fread=rd;api.fclose=cls;api.strcpy=strcpy;api.cgetc=key;
 api.clrscr=cls_screen;api.cputs=puts_screen;
 plugin_entry(&api);printf("%d %d %d %d %s\n",started,stopped,speaker_notes,ay_writes,note);
 if(argc>4)printf("lsr %d %d\n",ed_lsr[0],ed_lsr[1]);
 for(i=0;i<ay_writes && i<4096;++i)printf("%d %d\n",ay_log[i][0],ay_log[i][1]);
 return 0;
}
'''


def song():
    return mkdemo.duet()


class DUET(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='duet-host-');cls.p=Path(cls.tmp.name)
        (cls.p/'test.c').write_text(HARNESS)
        cls.exe=cls.p/'test'
        subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-I',str(ROOT),str(cls.p/'test.c'),'-o',str(cls.exe)],check=True,capture_output=True)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def run_data(self,data,good=False,fault=0,card=0):
        p=self.p/'source';p.write_bytes(data)
        out=subprocess.check_output([str(self.exe),str(p),str(fault),str(card)],text=True,timeout=5)
        first,_,rest=out.partition('\n')
        started,stopped,notes,writes=[int(x) for x in first.split()[:4]]
        self.assertEqual(p.read_bytes(),data)
        if not good:
            self.assertEqual((started,stopped,notes,writes),(0,0,0,0),out)
            self.assertIn('Bad/large Electric Duet or I/O.' if fault!=3 else 'Cannot open the song.',first)
        else:
            self.assertEqual((started,stopped),(1,1) if card else (0,0),out)
        writes=[tuple(int(x) for x in line.split()) for line in rest.splitlines()]
        return notes,writes
    def records(self,data):
        out=[];p=0
        while p+3<=len(data) and data[p]:
            out.append(tuple(data[p:p+3]));p+=3
        return out
    def test_demo_song_plays_every_note_on_the_speaker(self):
        notes,writes=self.run_data(song(),True)
        self.assertEqual(notes,sum(1 for r in self.records(song()) if r[0]>1))
        self.assertEqual(writes,[])
    def test_mockingboard_periods_follow_the_speaker_loop(self):
        data=song();notes,writes=self.run_data(data,True,card=4)
        self.assertEqual(notes,0)
        expected=[(7,0x3C)]   # the mixer: tones A and B, no noise
        for d,p1,p2 in self.records(data):
            if d==1:continue
            for v,p in enumerate((p1,p2)):
                period=(p<<2)+(p>>1)+(p>>4)
                expected+=[(8+v,15 if p else 0),(v*2,period&255),(v*2+1,period>>8)]
        self.assertEqual(writes,expected)
    def test_io_errors_and_absent_card(self):
        for fault in (1,2,3):self.run_data(song(),fault=fault)
        self.run_data(song(),True,card=0)
    def test_every_truncation_is_refused_and_trailing_bytes_are_ignored(self):
        b=song()
        for n in range(len(b)):self.run_data(b[:n])
        notes,_=self.run_data(b+b'\x10\x20\x30',True)
        self.assertEqual(notes,sum(1 for r in self.records(b) if r[0]>1))
        self.run_data(b+bytes(7169-len(b)))
        self.run_data(b+bytes(7168-len(b)),True)
    def test_a_song_needs_a_note_and_a_complete_terminator(self):
        self.run_data(b'\x01\x02\x02\x00\x00\x00')
        self.run_data(b'\x00\x00\x00')
        self.run_data(b'\x10\x20\x30\x00')
        self.run_data(b'\x10\x20\x30\x00\x00')
        self.run_data(bytes([0x10,0x20,0x30])*2389+b'\x00\x00\x00',True)
        notes,writes=self.run_data(b'\x02\x00\x00\x00\x00\x00',True,card=4)
        self.assertEqual(writes,[(7,0x3C),(8,0),(0,0),(1,0),(9,0),(2,0),(3,0)])
    def test_voice_records_are_skipped(self):
        notes,writes=self.run_data(b'\x01\x03\x04\x10\xFF\x01\x01\x02\x02\x00\x00\x00',True,card=4)
        self.assertEqual(writes,[(7,0x3C),(8,15),(0,(0x3FC+127+15)&255),(1,(0x3FC+127+15)>>8),(9,15),(2,4),(3,0)])
        notes,writes=self.run_data(b'\x01\x03\x04\x10\xFF\x01\x01\x02\x02\x00\x00\x00',True)
        self.assertEqual(notes,1)
    def test_default_pulse_is_an_eighth(self):
        self.run_data(song(),True)
        # ed_lsr is written before playback: one shift kept, one turned into NOP
        out=subprocess.check_output([str(self.exe),str(self.p/'source'),'0','0','lsr'],text=True)
        self.assertIn('lsr 74 234',out)


if __name__=='__main__':unittest.main()
