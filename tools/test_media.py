"""Execute the shared media coordinator/credit renderer against directory windows."""
import subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
C=r'''
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#define __fastcall__
#include "src/a2fc_plugin.h"
#define WINDOW 139
static struct Panel panels[2];static unsigned char active;
#define pan_at(p) (&panels[p])   /* the resident helper: the same address */
static struct Entry entries[140],all[300],selected;
static unsigned int total;static int failure;
static char full[81],album[2][17],output[1024];
static unsigned char tags[18];
static void cputs(const char*s){strcat(output,s);}
static void cputc(char c){size_t n=strlen(output);output[n]=c;output[n+1]=0;}
static void clrscr(void){output[0]=0;}
static void prepare_text(void){}
static char cgetc(void){return 27;}
static unsigned char overlay(const char*n){return 1;}
static unsigned char is_dir(const struct Entry*e){return e->type==15;}
static void keep_tags(unsigned char save){memcpy(save?tags:panels[0].tags,save?panels[0].tags:tags,18);}
static unsigned char read_panel(unsigned char p){
 unsigned int i;struct Panel*pan=&panels[p];
 if((failure==1 && pan->first==139) || (failure==2 && !pan->first))return 0;
 if(failure==3 && !pan->first)total=1;
 /* dir_open failed: read_panel has fallen back to the volume list. */
 if(failure==6 && pan->first==139){pan->path[0]=0;pan->first=0;pan->count=0;memset(pan->tags,0,18);return 0;}
 pan->count=0;memset(pan->tags,0,18);
 for(i=pan->first;i<total && pan->count<WINDOW;++i)entries[pan->count++]=all[i];
 pan->more=i<total;return 1;
}
static unsigned char build_full(char*out,const struct Panel*p,const struct Entry*e){strcpy(out,e->name);return 1;}
static unsigned int ticks;static void activity_tick(void){++ticks;}
static unsigned char media_request;   /* a2fc.c declares it above load_overlay */
#include "src/media.h"
unsigned char slideshow;char slide_getc(void){return cgetc();}   /* display.s */
unsigned char file_viewer(const struct Entry*e,unsigned char pic){   /* open.s in the program */
 if(failure==4 && !strcmp(e->name,"BAD.MB"))return V_ERROR;
 if(strstr(e->name,".FOTO"))return V_PURPLE;
 const char*p=strrchr(e->name,'.');return p && !strcmp(p,".MB")?V_MUSIC:V_PT3;
}
int main(int argc,char**argv){
 unsigned int i;unsigned char h[99];
 panels[0].e=entries;strcpy(panels[0].path,"/TEST");
 if(atoi(argv[1])==1){
  total=4;strcpy(all[0].name,"A.MB");strcpy(all[1].name,"B.PT3");strcpy(all[2].name,"C.MB");strcpy(all[3].name,"D.MB");
  read_panel(0);panels[0].cursor=2;panels[0].tags[0]=5;media_prepare(1);
  if(strcmp(album[0],"A.MB")||strcmp(album[1],"D.MB")||panels[0].cursor!=2||panels[0].tags[0]!=5)return 1;
  if(!media_key(KEY_LEFT)||media_request!=KEY_LEFT)return 2;
  /* overlay_run clears the arrow once the neighbour's viewer is loaded
   * (media_prepare no longer does: it tells a session's first pass) */
  media_request=0;panels[0].cursor=0;media_prepare(1);if(media_key(KEY_LEFT)||media_request)return 3;
 }else if(atoi(argv[1])==2){
  total=300;for(i=0;i<300;++i)sprintf(all[i].name,"F%03u.PT3",i);
  strcpy(all[0].name,"A.MB");strcpy(all[299].name,"Z.MB");read_panel(0);panels[0].cursor=0;media_prepare(1);
  if(strcmp(album[1],"Z.MB")||media_first[1]!=278||panels[0].first||panels[0].cursor)return 4;
  /* 299 neighbours opened one by one: the activity cell turns for each */
  if(ticks<299)return 30;
  /* A failed read in the next window puts the panel back as it was:
   * window, cursor, scroll and marks. */
  panels[0].cursor=5;panels[0].top=2;panels[0].tags[0]=0x21;
  failure=1;if(media_prepare(1))return 5;
  if(panels[0].first||panels[0].cursor!=5||panels[0].top!=2||panels[0].tags[0]!=0x21)return 20;
  /* ...unless the panel fell back to the volume list: no marks put back there. */
  failure=0;panels[0].first=0;read_panel(0);panels[0].cursor=5;panels[0].tags[0]=0x21;
  failure=6;if(media_prepare(1)||panels[0].path[0]||panels[0].tags[0])return 21;
  strcpy(panels[0].path,"/TEST");
  failure=0;panels[0].first=0;read_panel(0);
  failure=2;if(media_prepare(1))return 12;
 }else if(atoi(argv[1])==9){
  /* Right goes round: from the last one, the first; the panel stays put. */
  total=4;strcpy(all[0].name,"A.MB");strcpy(all[1].name,"B.PT3");strcpy(all[2].name,"C.MB");strcpy(all[3].name,"D.MB");
  read_panel(0);panels[0].cursor=3;panels[0].tags[0]=9;
  if(!media_prepare(1)||strcmp(album[0],"C.MB")||strcmp(album[1],"A.MB")||media_first[1])return 31;
  if(panels[0].cursor!=3||panels[0].first||panels[0].tags[0]!=9)return 32;
  /* Alone in its folder, a file is its own neighbour: a slideshow shows
   * it again, nothing else. */
  total=3;strcpy(all[0].name,"A.PT3");strcpy(all[1].name,"B.MB");strcpy(all[2].name,"C.PT3");
  read_panel(0);panels[0].cursor=1;
  if(!media_prepare(1)||album[0][0]||strcmp(album[1],"B.MB"))return 33;
  /* A cursor on a file of another kind, none of its own: the ring is
   * walked once, and nothing is found. */
  total=2;strcpy(all[0].name,"A.PT3");strcpy(all[1].name,"B.PT3");
  read_panel(0);panels[0].cursor=0;ticks=0;
  if(!media_prepare(1)||album[0][0]||album[1][0]||ticks!=3)return 34;
 }else if(atoi(argv[1])==10){
  /* Across windows: from the last window back to the first. */
  total=300;for(i=0;i<300;++i)sprintf(all[i].name,"F%03u.PT3",i);
  strcpy(all[5].name,"A.MB");strcpy(all[299].name,"Z.MB");
  panels[0].first=278;read_panel(0);panels[0].cursor=21;panels[0].top=4;panels[0].tags[2]=0x40;
  if(!media_prepare(1)||strcmp(album[1],"A.MB")||media_first[1]||strcmp(album[0],"A.MB"))return 35;
  if(panels[0].first!=278||panels[0].cursor!=21||panels[0].top!=4||panels[0].tags[2]!=0x40)return 36;
  /* A failed read on the way round: no neighbour is claimed, and the
   * panel is put back as it was. */
  failure=2;panels[0].first=278;
  if(media_prepare(1)||album[1][0]||panels[0].first!=278||panels[0].cursor!=21||panels[0].tags[2]!=0x40)return 37;
 }else if(atoi(argv[1])==11){
  /* Bug hunt 2 (bench/probe_album_window_tags.py): on the way to a neighbour
   * in another window (media_request holds the arrow), media_prepare saved
   * the tags again -- an empty set under the other window's fingerprint --
   * and Left back to the first window found none to give back. The save of
   * the session's first pass stands. */
  total=4;strcpy(all[0].name,"A.MB");strcpy(all[1].name,"B.PT3");strcpy(all[2].name,"C.MB");strcpy(all[3].name,"D.MB");
  read_panel(0);panels[0].cursor=2;panels[0].tags[0]=5;media_request=0;
  if(!media_prepare(1)||tags[0]!=5)return 40;
  media_request=KEY_RIGHT;memset(panels[0].tags,0,18);panels[0].cursor=3;
  if(!media_prepare(1)||tags[0]!=5)return 41;      /* not re-saved over the session's bits */
  media_request=0;memset(panels[0].tags,0,18);panels[0].tags[0]=2;
  if(!media_prepare(1)||tags[0]!=2)return 42;      /* a new session saves again */
 }else if(atoi(argv[1])==7){
  total=4;strcpy(all[0].name,"A.MB");strcpy(all[1].name,"BAD.MB");strcpy(all[2].name,"C.MB");
  read_panel(0);panels[0].cursor=0;failure=4;
  if(!media_prepare(V_MUSIC)||album[1][0]||panels[0].cursor)return 16;
 }else if(atoi(argv[1])==8){
  total=6;for(i=0;i<6;++i)sprintf(all[i].name,"%c.FOTO%u",'A'+i/2,i%2+1);
  read_panel(0);panels[0].cursor=3;
  if(!media_prepare(V_PURPLE)||strcmp(album[0],"A.FOTO1")||strcmp(album[1],"C.FOTO1"))return 17;
  for(i=1;i<=MEDIA_COUNT;++i)if(media_type(media_names[i])!=i)return 18;
  if(media_type("HEX")||media_type("UNKNOWN"))return 19;
 }else if(atoi(argv[1])==6){
  album[0][0]=album[1][0]=0;media_request=0;
  if(!media_key(0x9b)||media_request)return 14;
  strcpy(album[1],"NEXT");
  if(!media_key(KEY_RIGHT|128)||media_request!=KEY_RIGHT)return 15;
 }else{
  memset(h,0,sizeof h);strcpy(selected.name,"FILE.PT3");music_info(h);
  if(!strstr(output,"Title: FILE.PT3")||!strstr(output,"Not specified"))return 6;
  memset(h,' ',sizeof h);memcpy(h+30,"  Title",7);memcpy(h+66,"  Artist",8);h[74]=27;memcpy(h+75,"Name",4);
  music_info(h);if(!strstr(output,"Title: Title")||!strstr(output,"Artist Name")||!strstr(output,"Player: Vince Weaver"))return 7;
  for(i=0;output[i];++i)if(output[i]==27)return 8;
 }
 return 0;
}
'''
NAV=(ROOT/'src/a2fc.c').read_text()
NAV=NAV[NAV.index('static void nav_select('):NAV.index('static void go_up(')]
C=C.replace('int main(int argc,char**argv){', '''static unsigned char panel_stale,reselect_panel;static char reselect[17];
static void select_name(struct Panel*p,const char*n){unsigned char i;p->cursor=p->top=0;for(i=0;i<p->count;++i)if(!strcmp(p->e[i].name,n)){p->cursor=i;break;}}
static void open_path(struct Panel*p){p->first=p->cursor=p->top=0;read_panel(p-panels);}
'''+NAV+'int main(int argc,char**argv){')
C=C.replace(' }else{\n  memset(h', ''' }else if(atoi(argv[1])==5){
  total=300;for(i=0;i<300;++i)sprintf(all[i].name,"F%03u.PT3",i);
  strcpy(all[0].name,"A.MB");panels[0].first=139;read_panel(0);panels[0].cursor=50;
  failure=3;if(media_prepare(1))return 13;
 }else if(atoi(argv[1])==4){
  total=300;for(i=0;i<300;++i)sprintf(all[i].name,"F%03u",i);read_panel(0);nav_select(&panels[0],"F250");
  if(panels[0].first!=139||strcmp(entries[panels[0].cursor].name,"F250"))return 9;
  panels[0].first=0;read_panel(0);nav_select(&panels[0],"GONE");if(panels[0].first||panels[0].cursor)return 10;
  failure=1;nav_select(&panels[0],"F250");if(panels[0].first!=139)return 11;
 }else{
  memset(h''')
class Media(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='media-host-');p=Path(cls.tmp.name);(p/'test.c').write_text(C);cls.exe=p/'test'
  subprocess.run(['cc','-std=c99','-I',str(ROOT),str(p/'test.c'),'-o',str(cls.exe)],check=True,capture_output=True)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_right_goes_round_to_the_first(self):subprocess.run([str(self.exe),'9'],check=True)
 def test_round_across_windows_and_read_failure(self):subprocess.run([str(self.exe),'10'],check=True)
 def test_probe_error_does_not_skip_to_a_later_file(self):subprocess.run([str(self.exe),'7'],check=True)
 def test_purple_pairs_and_media_identity(self):subprocess.run([str(self.exe),'8'],check=True)
 def test_media_keys_with_open_apple_flag(self):subprocess.run([str(self.exe),'6'],check=True)
 def test_neighbours_boundaries_and_marks(self):subprocess.run([str(self.exe),'1'],check=True)
 def test_window_crossing_and_read_failure(self):subprocess.run([str(self.exe),'2'],check=True)
 def test_parent_search_across_windows_and_errors(self):subprocess.run([str(self.exe),'4'],check=True)
 def test_shrunk_directory_cannot_restore_invalid_cursor(self):subprocess.run([str(self.exe),'5'],check=True)
 def test_album_neighbour_keeps_session_tags(self):subprocess.run([str(self.exe),'11'],check=True)
 def test_credits_fixed_fields_and_controls(self):subprocess.run([str(self.exe),'3'],check=True)
if __name__=='__main__':unittest.main()
