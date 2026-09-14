"""Execute overlay_run: target text precedes cleanup, panels are drawn once the
browsing ends, and a lo-res picture keeps graphics on while its neighbour loads."""
import subprocess, tempfile, unittest
from pathlib import Path
from test_media import C, ROOT
source=(ROOT/'src/a2fc.c').read_text()
run=source[source.index('static void overlay_run('):source.index('\n#pragma code-name (push, "LC")',source.index('static void overlay_run('))]
base=C[:C.index('int main(int argc,char**argv){')]
base=base.replace('#include "src/a2fc_plugin.h"','struct A2fcApi;\n#include "src/a2fc_plugin.h"')
base=base.replace('unsigned int i;struct Panel*pan=&panels[p];','unsigned int i;struct Panel*pan=&panels[p];if(p)return 1;')
base=base.replace('failure==1 && pan->first==139','failure==1 && pan->first==278')
base=base.replace('return p && !strcmp(p,".MB")?V_MUSIC:V_PT3;','return p && !strcmp(p,".GR")?V_DGR:p && !strcmp(p,".MB")?V_MUSIC:V_PT3;')
base=base.replace('static void prepare_text(void){}','static unsigned char routed;static void prepare_text(void){routed=1;}')
harness=r'''
static struct A2fcApi api;
static unsigned char media_aux_scope,batch_snapshot;
static char reselect[17],note[80],overlay_loaded[17];static unsigned char in_overlay;
static unsigned char mode,calls,draws,switches;
static const char* target;
const char msg_noentry[]="Missing entry";
static void entry(const struct A2fcApi* a){
 unsigned char key;
 ++calls;if(calls>2)abort();
 if(calls==2 && (strcmp(selected.name,target)||strcmp(full,target)))abort();
 strcpy(reselect,selected.name);strcpy(output,"OLD FILE");routed=0;
 key=calls==2 || mode==4?KEY_ESC:mode==6?KEY_LEFT:KEY_RIGHT;
 if(mode==5)album[1][0]=0;
 if(media_key(key) && key!=KEY_ESC && mode!=8){
  if(!routed || strncmp(output,"Loading ",8) || strcmp(output+8,target))abort();
 }else if(routed || strcmp(output,"OLD FILE"))abort();   /* lo-res: the text page is the picture */
 /* A real overlay owns the entry-table memory until it has returned. */
 memset(entries,0xA5,sizeof entries);
 if(mode==2)failure=1;
 if(mode==3)strcpy(all[299].name,"GONE.PT3");
}
static struct Overlay header;
#define OVL (&header)
static unsigned char load_overlay(const char* n,unsigned char any){
 header.flags=mode==7?0:OVERLAY_BIG;header.entry=entry;return 1;
}
static unsigned char prepare_audio(unsigned char a){return a;}
static void switch_to_text(void){
 ++switches;
 if(mode==8 && calls==1)abort();   /* graphics stay on until the neighbour is drawn */
 if(mode!=2 && mode!=3 && mode!=4 && mode!=5 && mode!=8){
  if(strcmp(reselect,target))abort();
  if(calls==1 && strcmp(output+8,target))abort();
 }
}
static void draw_all(void){
 ++draws;
 if(mode!=2 && mode!=3 && mode!=4 && mode!=5 && strcmp(entries[panels[0].cursor].name,target))abort();
}
static void message(const char* s){(void)s;}
'''
main=r'''
int main(int argc,char**argv){
 unsigned i;mode=atoi(argv[1]);
 panels[0].e=entries;strcpy(panels[0].path,"/TEST");
 total=(mode==0 || mode==7 || mode==8)?3:300;
 for(i=0;i<total;++i)sprintf(all[i].name,"F%03u.PT3",i);
 strcpy(all[0].name,mode==8?"A.GR":"A.MB");strcpy(all[total-1].name,mode==8?"B.GR":"B.MB");
 target=mode==6?"A.MB":mode==8?"B.GR":"B.MB";
 if(mode==6)panels[0].first=278;
 read_panel(0);if(mode==6)panels[0].cursor=21;
 overlay_run(mode==8?"DGRVIEW":"MUSIC",0);
 if(media_aux_scope)return 1;
 if(mode==2 || mode==3 || mode==4 || mode==5){if(calls!=1 || draws!=1 || switches!=1)return 2;}
 /* On the way to a neighbour nothing is drawn; a small overlay draws nothing
  * at the end either, and a lo-res viewer switches to text only at the end. */
 else if(calls!=2 || draws!=(mode==7?0:1) || switches!=(mode==7 || mode==8?1:2))return 3;
 return 0;
}
'''
class Transition(unittest.TestCase):
 def test_real_overlay_return_order_and_failures(self):
  with tempfile.TemporaryDirectory(prefix='media-transition-') as d:
   p=Path(d);(p/'test.c').write_text(base+harness+run+main)
   r=subprocess.run(['cc','-std=c99','-I',str(ROOT),str(p/'test.c'),'-o',str(p/'test')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stderr)
   for mode in range(9):
    with self.subTest(mode=mode):
     r=subprocess.run([str(p/'test'),str(mode)],capture_output=True,text=True,timeout=5)
     self.assertEqual(r.returncode,0,r.stdout+r.stderr)
if __name__=='__main__':unittest.main()
