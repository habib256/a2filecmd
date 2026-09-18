"""Execute the raw-image browsing loop with its entry tables overwritten.

Between two images the screen carries the name being loaded and nothing
else: the panels are read again (the image ate their table) but never
drawn, so an album never flashes them back. draw_all is called once, when
the album is left.
"""
import subprocess,tempfile,unittest
from pathlib import Path
from test_media_transition import base,ROOT
source=(ROOT/'src/a2fc.c').read_text()
start=source.index('static void view_image(void)\n{')
run=source[start:source.index('\n/* ---------------------------------------------------------------------- */',start)]
harness=r'''
static unsigned char aux_dirty,a2fc_view,img_kind,calls,mode,keys,draws;
static const char*ram_note;
#define IMG_NONE 0
#define IMG_HGR 1
#define IMG_HGRR 2
static const char*IMG_NAMES[]={"None","HGR","RLE"};
static unsigned long IMG_BYTES[]={0,8192,8192};
#define RAM_NOTE "RAM rebuilt"
static char input[81];
static void loading(const char*n){strcpy(output,n);}
static void show_hgr(void){}
static void switch_to_hgr(void){}
static unsigned char ram_format(void){return 0;}
static void too_long(void){abort();}
static void clear_row(unsigned char r){}
static void gotoxy(unsigned char x,unsigned char y){}
static void open_row22(void){}
#define cprintf(...) ((void)0)
static void set_cursor(struct Panel*p,unsigned char i){p->cursor=i;}
static unsigned char image_kind(const struct Entry*e){return strstr(e->name,".HGR")!=0;}
static unsigned char load_image(const struct Entry*e){
 ++calls;if(calls>2)abort();
 /* The neighbour is loaded with the panels never redrawn in between: the
  * screen carried its name and nothing else (the EXTASIE transition). */
 if(calls==2 && (strcmp(e->name,"B.HGR") || draws))abort();
 memset(entries,0xA5,sizeof entries);return IMG_HGR;
}
static void switch_to_text(void){
 if(calls==1 && keys==1){
  if(strcmp(output,"Loading B.HGR"))abort();
  if(mode==1)failure=2;
  if(mode==2)strcpy(all[2].name,"GONE.TXT");
 }
}
static void draw_all(void){
 ++draws;if(!mode && strcmp(entries[panels[0].cursor].name,"B.HGR"))abort();
}
static char next_key(void){++keys;return keys==1?(KEY_RIGHT|128):KEY_ESC;}
'''
main=r'''
int main(int argc,char**argv){
 mode=atoi(argv[1]);panels[0].e=entries;strcpy(panels[0].path,"/TEST");
 total=3;strcpy(all[0].name,"A.HGR");strcpy(all[1].name,"OTHER.TXT");strcpy(all[2].name,"B.HGR");
 read_panel(0);view_image();
 if(a2fc_view)return 1;
 if(calls!=(mode?1:2) || draws!=1)return 2;   /* one redraw, on the way out */
 return 0;
}
'''
class RawTransition(unittest.TestCase):
 def test_actual_loop_target_before_text_and_failed_rereads(self):
  with tempfile.TemporaryDirectory(prefix='raw-transition-') as d:
   p=Path(d)
   (p/'test.c').write_text(base+harness+'\n#define cgetc next_key\n'+run+main)
   r=subprocess.run(['cc','-std=c99','-I',str(ROOT),str(p/'test.c'),'-o',str(p/'test')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stderr)
   for mode in range(3):
    with self.subTest(mode=mode):
     r=subprocess.run([str(p/'test'),str(mode)],capture_output=True,text=True,timeout=5)
     self.assertEqual(r.returncode,0,r.stdout+r.stderr)
if __name__=='__main__':unittest.main()
