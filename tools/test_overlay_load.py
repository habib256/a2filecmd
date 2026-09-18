"""Execute the resident loader with disposable code and failed stream I/O."""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'src/a2fc.c').read_text()
loader = source[source.index('static unsigned char load_overlay('):source.index('\n#define overlay(name)')]
C = r'''
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#define OVERLAY_BIG 1
#define OVERLAY_AUX 2
#define OVERLAY_SMALL 1280
#define OVERLAY_LARGE 9472
#define PLUGIN_MAGIC 0x1234
#define MEDIA_PLUGIN_MAGIC 0x5678
struct Overlay { uint16_t signature; unsigned char flags, rest[5]; };
static unsigned char window[OVERLAY_LARGE],copy_buf[512];
#define OVERLAY_WINDOW window
#define OVL ((struct Overlay*)window)
static uint16_t a2fc_link_id=0xABCD;
static char overlay_loaded[17],other_full[81],full[81],cfg_path[81],question[81];static unsigned char in_overlay;
static unsigned char batch_snapshot,companion_unit;
static int mode,reads,closes,error,restored,draws,saved,opens;
static FILE* open_overlay(const char* name,int ask) {
 FILE* f=tmpfile();unsigned i,n=mode==5?8:mode==6?OVERLAY_LARGE+1:mode==8?OVERLAY_SMALL:mode==9?OVERLAY_LARGE:2000;
 unsigned char header[8]={0xCD,0xAB,OVERLAY_BIG,0,0,0,0,0};
 if(mode==8 || mode==10)header[2]=0;
 ++opens;fwrite(header,1,8,f);for(i=8;i<n;++i)fputc(0xA5,f);rewind(f);return f;
}
static size_t read_code(void* p,size_t size,size_t n,FILE* f) {
 size_t got;++reads;
 if(mode==2 && reads==2)n=1400;
 got=fread(p,size,n,f);
 if((mode==1 && reads==1)||((mode==2||mode==3)&&reads==2)||(mode==7 && reads==3))error=1;
 return got;
}
static int close_code(FILE* f){++closes;fclose(f);return mode==4?-1:0;}
static int confirm_aux(void){return 1;}
static void snapshot_entries(void){}
static void keep_tags(int save){saved+=save?1:-1;}
static int read_panel(int p){++restored;memset(window+1280,0xEE,100);return 1;}
static void draw_all(void){++draws;}
static void reread_both(void){read_panel(0);read_panel(1);keep_tags(0);draw_all();}
static void open_row22(void){}
static int exists(const char* p){return 1;}
static int disk_question(const char* p){return 0;}
static void clear_row(int y){}
static void gotoxy(int x,int y){}
#define cprintf(...) ((void)0)
#define fread read_code
#define fclose close_code
#define ferror(f) error
'''
MAIN = r'''
int main(int argc,char** argv) {
 int ok;mode=atoi(argv[1]);memset(window,0xEE,sizeof window);
 ok=load_overlay("DOSPUT",1);
 if(!mode || mode==8 || mode==9) {
  if(!ok || strcmp(overlay_loaded,"DOSPUT") || closes!=1)return 1;
  if(!load_overlay("DOSPUT",1) || opens!=1)return 2;
 } else {
  if(ok || overlay_loaded[0] || closes!=1)return 3;
  if(mode!=1 && mode!=10 && (restored!=2 || draws!=1 || saved || window[1280]!=0xEE))return 4;
  if((mode==1 || mode==10) && (saved || restored || window[1280]!=0xEE))return 5;
 }
 return 0;
}
'''

class OverlayLoad(unittest.TestCase):
 def test_failed_menu_cannot_replay_a_previous_command(self):
  dispatch=source[source.index("        case '!':"):source.index("        case 'i': case 'I':")]
  harness=r'''
#include <string.h>
static char input[17],note[80];static int walked;static void copy_or_move(unsigned char m){++walked;}
static int panels[2],active,mode,calls,moved;
static int tag_count(int* p){return 1;}
static void move_marked(void){++moved;}
static void overlay_run(const char* name,int arg){
 ++calls;
 if(!strcmp(name,"MENU") && mode)strcpy(input,mode==1?"CRC":"MOVE");
}
static void dispatch(void){switch('!'){
'''+dispatch+r'''
}}
int main(void){
 for(mode=0;mode<3;++mode){
  strcpy(input,"MOVE");calls=moved=0;dispatch();
  if(calls!=(mode==1?2:1) || moved!=(mode==2))return 1;
 }
 return 0;
}
'''
  with tempfile.TemporaryDirectory(prefix='overlay-menu-') as d:
   p=Path(d);(p/'test.c').write_text(harness)
   subprocess.run(['cc','-std=c99',str(p/'test.c'),'-o',str(p/'test')],check=True,capture_output=True)
   self.assertEqual(subprocess.run([str(p/'test')]).returncode,0)

 def test_snapshot_preserves_overlapping_entry_tables(self):
  snapshot=source[source.index('static void snapshot_entries(void)'):source.index('static unsigned char load_overlay(')]
  c=r'''
#include <string.h>
#include <stdlib.h>
struct Entry {unsigned char bytes[29];};
struct Panel {struct Entry* e;unsigned char count;};
static unsigned char ram[8192],active;
static struct Panel panels[2];
#define ENTRY_SNAPSHOT ((struct Entry*)(ram+4096))
'''+snapshot+r'''
int main(void){unsigned side,n,k;unsigned char original[4060];
 for(side=0;side<2;++side)for(n=0;n<=140;++n){
  for(k=0;k<sizeof ram;++k)ram[k]=k*13+k/29;
  active=side;panels[side].e=(struct Entry*)(ram+side*4060);panels[side].count=n;
  memcpy(original,panels[side].e,n*29);snapshot_entries();
  if(memcmp(original,ENTRY_SNAPSHOT,n*29))return 1;
 }return 0;}
'''
  with tempfile.TemporaryDirectory(prefix='entry-snapshot-') as d:
   p=Path(d);(p/'test.c').write_text(c)
   subprocess.run(['cc','-std=c99','-fsanitize=address,undefined',str(p/'test.c'),'-o',str(p/'test')],check=True,capture_output=True)
   subprocess.run([str(p/'test')],check=True)

 def test_stream_failures_never_cache_code_and_restore_panels(self):
  with tempfile.TemporaryDirectory(prefix='overlay-load-') as d:
   p=Path(d);(p/'test.c').write_text(C+loader+MAIN)
   subprocess.run(['cc','-std=c99',str(p/'test.c'),'-o',str(p/'test')],check=True,capture_output=True)
   for mode in range(11):
    with self.subTest(mode=mode):
     result=subprocess.run([str(p/'test'),str(mode)],capture_output=True)
     self.assertEqual(result.returncode,0,result.stderr)

if __name__=='__main__':unittest.main()
