"""Execute the resident loader with disposable code and failed stream I/O."""
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'src/a2fc.c').read_text()
loader = source[source.index('static unsigned char load_overlay('):source.index('\n#define overlay(name)')]
C = r'''
#include <stdio.h>
static void activity_begin(const char* text) {}
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
static unsigned char batch_snapshot,companion_unit,media_request;
static int mode,reads,closes,error,restored,draws,saved,opens,snaps;
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
static const char loading_tool[]="Loading tool...";
static void snapshot_entries(void){++snaps;}
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
 ok=load_overlay("DOSPUT",argc > 2 ? atoi(argv[2]) : 1);
 if(!mode && (snaps!=(argc > 2 && atoi(argv[2])==3 ? 0 : 1) || saved!=snaps))return 6;
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
 def test_an_empty_ram_disk_asks_nothing(self):
  # confirm_aux, as written in a2fc.c: no question when ram_empty() says
  # /RAM is on line and holds no file; otherwise the question, and a
  # refusal is obeyed.
  gate=source[source.index('static unsigned char media_aux_scope;'):source.index('/* A big overlay took the entry pool')]
  gate=gate.replace('#pragma rodata-name(push, "LC")','').replace('#pragma rodata-name(pop)','')
  code=r"""
#include <stdio.h>
#include <stdlib.h>
static int empty,answer,asked;
static unsigned char aux_dirty;
static unsigned char ram_empty(void){return empty;}
static unsigned char confirm(const char* q){(void)q;++asked;return answer;}
"""+gate+r"""
int main(int argc,char** argv){int r;
 empty=atoi(argv[1]);answer=atoi(argv[2]);media_aux_scope=atoi(argv[3]);
 r=confirm_aux();printf("%d %d %d %d\n",r,asked,media_aux_scope,aux_dirty);return 0;}
"""
  with tempfile.TemporaryDirectory(prefix='aux-gate-') as t:
   p=Path(t);(p/'g.c').write_text(code)
   subprocess.run(['cc','-std=c99',str(p/'g.c'),'-o',str(p/'g')],check=True)
   run=lambda *a:subprocess.check_output([str(p/'g')]+[str(x) for x in a],text=True).split()
   # The last figure is aux_dirty: set whenever leave is given, so that
   # Ctrl-Reset from inside the viewer rebuilds /RAM (crt0.s) instead of
   # leaving it on line over overwritten blocks; never on a refusal.
   self.assertEqual(run(1,0,0),['1','0','0','1'])   # empty /RAM: no question, granted
   self.assertEqual(run(1,0,1),['1','0','1','1'])
   self.assertEqual(run(0,0,0),['0','1','0','0'])   # files there: asked, refused
   self.assertEqual(run(0,1,1),['1','1','2','1'])   # asked, granted for the session
   self.assertEqual(run(0,0,2),['1','0','2','1'])   # already granted this session

 def test_failed_menu_cannot_replay_a_previous_command(self):
  dispatch=source[source.index("        case '!':"):source.index("        case 'i': case 'I':")]
  harness=r'''
#include <string.h>
static char input[17],note[80];static int walked;static void copy_or_move(unsigned char m){++walked;}
static int panels[2],active,mode,calls,moved;
#define pan_at(p) (&panels[p])   /* the resident helper: the same address */
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

 def test_plugins_wait_key_takes_no_click(self):
  """Bug hunt 2: the service table's wait_key was the main loop's, which
  hands a mouse click to click(): during DOS33W or CRC a click swapped the
  panels or landed the cursor and drew over copy_buf. The slot (frozen by
  tools/test_abi_freeze.py) now holds cgetc: keys only."""
  table=source[source.index('static struct A2fcApi api = {'):]
  table=table[:table.index('};')]
  names=[n.strip() for n in table.split('{',1)[1].replace('\n',' ').split(',')]
  self.assertEqual(names[names.index('report_error')+1],'cgetc')

 def test_menu_describes_every_overlay_the_loader_accepts(self):
  """Bug hunt 2 (bench/hunt2_menu.py): the ! menu wrote "(other A2FC
  build)" for every MEDIA_PLUGIN_MAGIC overlay (MUSIC, PURPLE...), which
  load_overlay runs from that very menu. The real description line of
  menu_entry, on the host, for the four signatures."""
  menu=source[source.index('void __fastcall__ menu_entry('):]
  line=next(l for l in menu.splitlines() if 'strcpy(m[i].desc, mn_stale)' in l)
  loader_ok=re.search(r'OVL->signature == a2fc_link_id \|\| \(any && \(([^)]*)\)\)', loader).group(1)
  harness=r'''
#include <string.h>
#define PLUGIN_MAGIC 0xA2FC
#define MEDIA_PLUGIN_MAGIC 0xA2FD
struct Overlay { unsigned int signature; };
static const char mn_stale[]="stale";
struct Item { char desc[16]; } m[1];
static unsigned int a2fc_link_id=0x4321;
int main(void){
 static const unsigned int sigs[4]={0x4321,PLUGIN_MAGIC,MEDIA_PLUGIN_MAGIC,0x1234};
 unsigned char i=0,k,len=80;struct Overlay h,*hdr=&h,o,*OVL=&o;unsigned char any=1;
 for(k=0;k<4;++k){
  strcpy(m[0].desc,"ok");h.signature=o.signature=sigs[k];
'''+line+r'''
  if((strcmp(m[0].desc,"stale")==0)!=!(OVL->signature==a2fc_link_id||(any&&('''+loader_ok+r''')))) return 1+k;
 }
 return 0;
}
'''
  with tempfile.TemporaryDirectory(prefix='overlay-menu-desc-') as d:
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
#define pan_at(p) (&panels[p])   /* the resident helper: the same address */
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

 def test_album_neighbour_gets_the_snapshot_but_keeps_the_tags(self):
  # API v5 (a2fc_plugin.h): a big overlay receives ENTRY_SNAPSHOT. On the
  # way to an album's neighbour (media_request) the tags stay as the
  # session saved them, but the snapshot is taken all the same (bug hunt 3:
  # both were skipped). BATCH keeps its own snapshot (batch_snapshot).
  main=r'''
int main(int argc,char** argv) {
 media_request=atoi(argv[1]);batch_snapshot=atoi(argv[2]);
 if(!load_overlay("DOSPUT",1))return 9;
 printf("%d %d\n",snaps,saved);return 0;
}
'''
  with tempfile.TemporaryDirectory(prefix='overlay-snap-') as d:
   p=Path(d);(p/'test.c').write_text(C+loader+main)
   subprocess.run(['cc','-std=c99',str(p/'test.c'),'-o',str(p/'test')],check=True,capture_output=True)
   run=lambda *a:subprocess.check_output([str(p/'test')]+[str(x) for x in a],text=True).split()
   self.assertEqual(run(0,0),['1','1'])      # a big overlay: tags saved, snapshot
   self.assertEqual(run(9,0),['1','0'])      # a neighbour (Right): snapshot, tags kept
   self.assertEqual(run(9,1),['0','0'])      # inside BATCH: its own snapshot

 def test_stream_failures_never_cache_code_and_restore_panels(self):
  with tempfile.TemporaryDirectory(prefix='overlay-load-') as d:
   p=Path(d);(p/'test.c').write_text(C+loader+MAIN)
   subprocess.run(['cc','-std=c99',str(p/'test.c'),'-o',str(p/'test')],check=True,capture_output=True)
   result=subprocess.run([str(p/'test'),'0','3'],capture_output=True)
   self.assertEqual(result.returncode,0,result.stderr)
   for mode in range(11):
    with self.subTest(mode=mode):
     result=subprocess.run([str(p/'test'),str(mode)],capture_output=True)
     self.assertEqual(result.returncode,0,result.stderr)

class MenuCapacity(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='menu-capacity-');cls.p=Path(cls.tmp.name)
  menu=source[source.index('static const char mn_catalog[]'):source.index('/* File operations')]
  menu=menu[:menu.rindex('/* ---------------------------------------------------------------------- */')]
  menu='\n'.join(l for l in menu.splitlines() if not l.startswith('#pragma'))
  menu=menu.replace('((struct MenuItem*)0x2C00)','((struct MenuItem*)(guarded+8))')
  prefix=r'''
#define __fastcall__
#define PLUGIN_HOST
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
struct A2fcApi;
#define Overlay ApiOverlay
#include "src/a2fc_plugin.h"
#undef Overlay
#ifndef __CC65__
#pragma pack(push,1)
#endif
struct Overlay {unsigned short signature;unsigned char flags;unsigned short entry;unsigned char reserved[3];char desc[66];};
#ifndef __CC65__
#pragma pack(pop)
#endif
static unsigned short a2fc_link_id=0x1234;
static unsigned char copy_buf[512],guarded[128*40+16];
static char input[81],note[81],other_full[81];static struct Entry dir_entry;
static unsigned int mode,at,total,keys;static const char *header_path,*catalog_path;
static const char* extra[]={"PURPLE","PSBORDER","PSFONT","SHAPES","RUN","MVMOVIE","DGMAGI","PCSVW"};
static void a2file_file(const char* n){strcpy(other_full,"/VOL/A2FILE/");strcat(other_full,n);}
static unsigned char companion_path(const char* n){(void)n;return 0;}
static unsigned char dir_open(const char* p){(void)p;at=0;return 1;}
static unsigned char dir_next(void){
 if(at>=total)return 0;dir_entry.type=6;
 if(at>=100 && at<108)sprintf(dir_entry.name,"%s.PLG",extra[at-100]);
 else sprintf(dir_entry.name,"T%03u.PLG",at);
 ++at;return 1;
}
static void dir_close(void){} static void activity_tick(void){}
static FILE* open_overlay(const char* n,unsigned char ask){(void)ask;if(!strcmp(n,"T005"))return NULL;return fopen(header_path,"rb");}
static FILE* menu_open(const char* p,const char* m){(void)p;if(strcmp(m,"rb"))abort();return mode==3?fopen(catalog_path,m):NULL;}
static void gotoxy(unsigned char x,unsigned char y){} static void revers(unsigned char n){}
static void clrscr(void){} static void cclearxy(unsigned char x,unsigned char y,unsigned char n){}
static void cputsxy(unsigned char x,unsigned char y,const char* s){}
static int cprintf(const char* s,...){return 0;} static void bar_begin(void){}
static void keys_bar(unsigned char x,const char* s){}
static char cgetc(void){if(mode==4){if(keys++<4)return KEY_DOWN;return KEY_RETURN;}return KEY_ESC;}
#define fopen menu_open
'''
  main=r'''
#undef fopen
int main(int argc,char**argv){
 unsigned int i,n,want;unsigned char found=0;struct MenuItem* m=MENU_ITEMS;
 mode=atoi(argv[3]);header_path=argv[1];catalog_path=argv[2];
 total=mode==2?140:mode==3?90:115;want=mode==2?128:mode==3?93:115;
 memset(guarded,0xA5,sizeof guarded);memset(m,0,128*40);
 menu_entry(NULL);
 n=0;for(i=0;i<8;++i){if(guarded[i]!=0xA5 || guarded[sizeof guarded-8+i]!=0xA5)return 1;n+=copy_buf[2*MENU_MAX+i];}
 if(n!=want || sizeof(struct MenuItem)!=40)return 2;
 for(i=0;i<n;++i){
  if(!memchr(m[i].name,0,12) || !memchr(m[i].desc,0,28))return 3;
  if(!strcmp(m[i].name,"IDV1"))return 4;
  if(!strcmp(m[i].name,"T005") && strcmp(m[i].desc,"(unreadable)"))return 5;
  if(!strcmp(m[i].name,"RUN"))found|=1;
  if(!strcmp(m[i].name,"PSFONT"))found|=2;
  if(!strcmp(m[i].name,"PURPLE"))found|=4;
 }
 if(found!=7 || (mode==4?strcmp(input,"RUN"):input[0]!=0))return 6;
 return 0;
}
'''
  (cls.p/'h.c').write_text(prefix+menu+main)
  header=bytes.fromhex('3412000100000000')+b'A long image reader description with intentionally nonzero padding'*2
  cls.header=cls.p/'header';cls.header.write_bytes(header)
  cls.catalog=cls.p/'catalog';cls.catalog.write_bytes(b''.join(name.encode().ljust(12,b'\0')+b'X'*65+b'\0' for name in ('IDV1','PURPLE','PSFONT','RUN')))
  exe=cls.p/'host';subprocess.run(['cc','-std=c99','-fsanitize=address,undefined','-I',str(ROOT),str(cls.p/'h.c'),'-o',str(exe)],check=True,capture_output=True)
  cls.commands=[[str(exe)]]
  if shutil.which('cl65') and shutil.which('sim65'):
   for cpu,target in (('6502','sim6502'),('65c02','sim65c02')):
    exe=cls.p/target
    subprocess.run(['cl65','-t',target,'--cpu',cpu,'-O','-Cl','-I',str(ROOT),str(cls.p/'h.c'),'-o',str(exe)],check=True,capture_output=True)
    cls.commands.append(['sim65',str(exe)])
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_complete_xl_menu_capacity_catalog_and_last_reader_selection(self):
  for cmd in self.commands:
   for mode in (1,2,3,4):
    with self.subTest(cmd=cmd,mode=mode):
     before=(self.header.read_bytes(),self.catalog.read_bytes())
     r=subprocess.run(cmd+[str(self.header),str(self.catalog),str(mode)],capture_output=True)
     self.assertEqual(r.returncode,0,r.stderr);self.assertEqual((self.header.read_bytes(),self.catalog.read_bytes()),before)
 def test_menu_memory_contract_keeps_guards_active(self):
  import check_layout
  self.assertEqual(check_layout.OVERLAYS['MENU'],0x2c00)
  self.assertIn('#define MENU_ITEMS ((struct MenuItem*)0x2C00)',source)
  self.assertEqual(0x2c00+128*40,0x4000)

if __name__=='__main__':unittest.main()
