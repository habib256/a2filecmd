"""Run actual batch manifest code: failures, fixed names, cancellation, marks."""
import subprocess
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
C=r'''
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <sys/stat.h>
#include <assert.h>
#define __fastcall__
#define PATH_LEN 64
#define NAME_LEN 17
#define MAX_ENTRIES 140
struct Entry{char name[17];unsigned char type,access;unsigned int aux,blocks;unsigned long size;unsigned int mdate;};
struct Panel{char path[64];unsigned char count,fs,tags[18];};
struct A2fcApi{unsigned char arg;};
struct MoveBatch{char list[64],source[64],target[64],reason[80];unsigned char count,index,owned,ready;};
static struct MoveBatch state;
#define MB (&state)
static struct Entry entries[140],selected;
#define BATCH_ENTRIES entries
static struct Panel panels[2];
static unsigned char active,copy_buf[512],gfi[18],_filetype,_oserror;
static unsigned int _auxtype;
static char note[80],full[81];
static const char* fault;
static int reads,phase;
static int eq(const char*s){return !strcmp(fault,s);}
static unsigned char tagged(const struct Panel*p,unsigned char i){return !!(p->tags[i>>3]&(1<<(i&7)));}
static void set_tag(struct Panel*p,unsigned char i,unsigned char yes){if(yes)p->tags[i>>3]|=1<<(i&7);}
static unsigned char is_dir(const struct Entry*e){return e->type==15;}
static unsigned char target_check(void){return strcmp(panels[0].path,panels[1].path)!=0;}
static void too_long(void){strcpy(note,"Path too long.");}
static void keep_tags(unsigned char n){(void)n;}
static unsigned char confirm(const char*s){assert(strlen(s)<80);return !eq("cancel");}
static unsigned char push_name(char*p,const char*n){if(strlen(p)+strlen(n)+1>=64)return 0;strcat(p,"/");strcat(p,n);return 1;}
static unsigned char build_full(char*p,const struct Panel*pan,const struct Entry*e){strcpy(p,pan->path);return push_name(p,e->name);}
static unsigned char file_info(const char*p){struct stat st;if(eq("stat")||stat(p,&st))return 0;gfi[7]=1;gfi[3]=eq("locked")?1:0xC3;gfi[4]=4;gfi[5]=gfi[6]=0;return 1;}
static FILE* bfopen(const char*p,const char*m){phase=!strcmp(m,"wb")?0:++reads;return fopen(p,m);}
static size_t bfread(void*p,size_t z,size_t n,FILE*f){if((phase==1&&eq("verify_read"))||(phase>1&&eq("read_record")))return 0;return fread(p,z,n,f);}
static int bferror(FILE*f){return (phase==1&&eq("verify_read"))||(phase>1&&eq("read_record"))||ferror(f);}
static int bfclose(FILE*f){int r=fclose(f);if((phase==0&&eq("write_close"))||(phase==1&&eq("verify_close"))||(phase>1&&eq("read_close")))return EOF;return r;}
static size_t bfwrite(const void*p,size_t z,size_t n,FILE*f){return fwrite(p,z,eq("write")?n/2:n,f);}
static int bfseek(FILE*f,long p,int whence){if(eq("seek"))return -1;return fseek(f,p,whence);}
static int bopen(const char*p,int flags){assert((flags&(O_CREAT|O_EXCL))==(O_CREAT|O_EXCL));if(eq("create"))return -1;return open(p,flags,0600);}
static int bremove(const char*p){if(eq("remove"))return -1;return remove(p);}
#define fopen bfopen
#define fread bfread
#define fwrite bfwrite
#define fclose bfclose
#define ferror bferror
#define fseek bfseek
#define open bopen
#define remove bremove
#include "src/batch.h"
#undef fopen
#undef fread
#undef fwrite
#undef fclose
#undef ferror
#undef fseek
#undef open
#undef remove
int main(int argc,char**argv){
 struct A2fcApi api;unsigned int i,n;char dst[81];FILE*f;
 fault=argv[3];active=argc>4?atoi(argv[4]):0;
 strcpy(panels[active].path,argv[1]);strcpy(panels[!active].path,argv[2]);panels[active].count=3;
 for(i=0;i<3;++i){entries[i].name[0]='A'+i;entries[i].type=4;entries[i].access=0xC3;entries[i].size=4;}
 set_tag(&panels[active],0,1);set_tag(&panels[active],2,1);
 api.arg='W';batch_entry(&api);
 if(MB->ready){
  if(eq("corrupt")){f=fopen(MB->list,"r+b");fputc('B',f);fclose(f);}
  if(eq("truncate")){f=fopen(MB->list,"wb");fclose(f);}
  for(i=0;i<MB->count;++i){
   api.arg='R';batch_entry(&api);
   if(!MB->ready){strcpy(MB->reason,note);break;}
   strcpy(dst,MB->target);push_name(dst,selected.name);
   assert(!strcmp(selected.name,i?"C":"A"));
   assert(!rename(full,dst));++MB->index;
   if(eq("partial")){strcpy(MB->reason,"Cancelled");break;}
  }
  /* Rebuild the active snapshot just like the real core after MOVE. */
  n=0;for(i=0;i<3;++i){char p[81];strcpy(p,panels[active].path);strcat(p,"/");p[strlen(p)+1]=0;p[strlen(p)]='A'+i;
   if(!access(p,F_OK)){memset(&entries[n],0,sizeof entries[n]);entries[n].name[0]='A'+i;entries[n].type=4;++n;}}
  panels[active].count=n;api.arg='F';batch_entry(&api);
 }
 printf("%u|%u|%s|",MB->index,MB->owned,note);
 for(i=0;i<panels[active].count;++i)if(tagged(&panels[active],i))printf("%s,",entries[i].name);
 puts("");return 0;
}
'''
class Batch(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='bq-',dir='/tmp');cls.root=Path(cls.tmp.name)
  c=cls.root/'test.c';c.write_text(C);cls.exe=cls.root/'test'
  subprocess.run(['cc','-std=c99','-I',str(ROOT),str(c),'-o',str(cls.exe)],check=True)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def run_case(self,fault='',collision=False,active=0):
  d=Path(tempfile.mkdtemp(prefix='q-',dir=self.root));src=d/'s';dst=d/'d';src.mkdir();dst.mkdir()
  for n in 'ABC':(src/n).write_bytes((n*4).encode())
  if collision:(dst/'A2MOVE.LST').write_bytes(b'personal bytes')
  out=subprocess.check_output([self.exe,src,dst,fault,str(active)],text=True)
  return out,{p.name:p.read_bytes() for p in src.iterdir()},{p.name:p.read_bytes() for p in dst.iterdir()}
 def test_only_marked_names_both_panels(self):
  for active in (0,1):
   out,src,dst=self.run_case(active=active);self.assertTrue(out.startswith('2|0|'),out)
   self.assertEqual(src,{'B':b'BBBB'});self.assertEqual(dst,{'A':b'AAAA','C':b'CCCC'})
 def test_cancel_and_collision_preserve_all(self):
  for f,c in [('cancel',False),('',True)]:
   out,src,dst=self.run_case(f,c);self.assertTrue(out.startswith('0|0|'))
   self.assertEqual(src,{n:(n*4).encode() for n in 'ABC'})
   self.assertEqual(dst,{'A2MOVE.LST':b'personal bytes'} if c else {})
 def test_failures_before_first_move(self):
  for f in ('create','write','write_close','verify_read','verify_close','read_record','read_close','seek','stat','locked','corrupt','truncate'):
   with self.subTest(f=f):
    out,src,dst=self.run_case(f);self.assertTrue(out.startswith('0|'),out)
    self.assertEqual(src,{n:(n*4).encode() for n in 'ABC'})
    self.assertFalse({'A','B','C'}&dst.keys())
 def test_partial_restores_pending_marks_by_name(self):
  out,src,dst=self.run_case('partial');self.assertTrue(out.rstrip().endswith('|C,'),out)
  self.assertEqual(src,{'B':b'BBBB','C':b'CCCC'});self.assertEqual(dst,{'A':b'AAAA'})
 def test_cleanup_failure_keeps_owned_manifest(self):
  out,src,dst=self.run_case('remove');self.assertTrue(out.startswith('2|1|'),out)
  self.assertIn('A2MOVE.LST',dst);self.assertEqual(src,{'B':b'BBBB'})
if __name__=='__main__':unittest.main()
