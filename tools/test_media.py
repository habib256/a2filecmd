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
static struct Entry entries[140],all[300],selected;
static unsigned int total;static int failure;
static char full[81],album[2][17],output[1024];
static unsigned char tags[18];
static void cputs(const char*s){strcat(output,s);}
static void cputc(char c){size_t n=strlen(output);output[n]=c;output[n+1]=0;}
static void clrscr(void){output[0]=0;}
static char cgetc(void){return 27;}
static unsigned char overlay(const char*n){return 1;}
static unsigned char is_dir(const struct Entry*e){return e->type==15;}
static void keep_tags(unsigned char save){memcpy(save?tags:panels[0].tags,save?panels[0].tags:tags,18);}
static unsigned char read_panel(unsigned char p){
 unsigned int i;struct Panel*pan=&panels[p];
 if((failure==1 && pan->first==139) || (failure==2 && !pan->first))return 0;
 if(failure==3 && !pan->first)total=1;
 pan->count=0;memset(pan->tags,0,18);
 for(i=pan->first;i<total && pan->count<WINDOW;++i)entries[pan->count++]=all[i];
 pan->more=i<total;return 1;
}
static unsigned char build_full(char*out,const struct Panel*p,const struct Entry*e){strcpy(out,e->name);return 1;}
#include "src/media.h"
static const char* file_viewer(const struct Entry*e,unsigned char pic){
 const char*p=strrchr(e->name,'.');return p && !strcmp(p,".MB")?media_names[0]:media_names[1];
}
int main(int argc,char**argv){
 unsigned int i;unsigned char h[99];
 panels[0].e=entries;strcpy(panels[0].path,"/TEST");
 if(atoi(argv[1])==1){
  total=4;strcpy(all[0].name,"A.MB");strcpy(all[1].name,"B.PT3");strcpy(all[2].name,"C.MB");strcpy(all[3].name,"D.MB");
  read_panel(0);panels[0].cursor=2;panels[0].tags[0]=5;media_prepare(1);
  if(strcmp(album[0],"A.MB")||strcmp(album[1],"D.MB")||panels[0].cursor!=2||panels[0].tags[0]!=5)return 1;
  if(!media_key(KEY_LEFT)||media_request!=KEY_LEFT)return 2;
  panels[0].cursor=0;media_prepare(1);if(media_key(KEY_LEFT)||media_request)return 3;
 }else if(atoi(argv[1])==2){
  total=300;for(i=0;i<300;++i)sprintf(all[i].name,"F%03u.PT3",i);
  strcpy(all[0].name,"A.MB");strcpy(all[299].name,"Z.MB");read_panel(0);panels[0].cursor=0;media_prepare(1);
  if(strcmp(album[1],"Z.MB")||media_first[1]!=278||panels[0].first||panels[0].cursor)return 4;
  failure=1;if(media_prepare(1))return 5;
  failure=0;panels[0].first=0;read_panel(0);
  failure=2;if(media_prepare(1))return 12;
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
C=C.replace('int main(int argc,char**argv){', '''static void select_name(struct Panel*p,const char*n){unsigned char i;p->cursor=p->top=0;for(i=0;i<p->count;++i)if(!strcmp(p->e[i].name,n)){p->cursor=i;break;}}
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
 def test_neighbours_boundaries_and_marks(self):subprocess.run([str(self.exe),'1'],check=True)
 def test_window_crossing_and_read_failure(self):subprocess.run([str(self.exe),'2'],check=True)
 def test_parent_search_across_windows_and_errors(self):subprocess.run([str(self.exe),'4'],check=True)
 def test_shrunk_directory_cannot_restore_invalid_cursor(self):subprocess.run([str(self.exe),'5'],check=True)
 def test_credits_fixed_fields_and_controls(self):subprocess.run([str(self.exe),'3'],check=True)
if __name__=='__main__':unittest.main()
