"""Run real DISKIMG reservation, transfer and finalization on disposable files."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_file_safety import section
ROOT=Path(__file__).resolve().parents[1]
C=r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#define SIDE_DEVICE 0
#define SIDE_PO 1
#define SIDE_DSK 2
struct Side {unsigned char kind,unit;FILE* f;unsigned long base;};
static struct {struct Side src,dst;unsigned char output_owned,checking,parms[6];unsigned int checkblock;} state;
#define DI (&state)
static unsigned char imageblock[512];
#define DI_BLOCK imageblock
static char full[256],note[100],reselect[17],input[100];
static int mode,cleanup_bad,removes,closed,opened;
static FILE* output;
static unsigned char mli_call(unsigned char c,void*p){abort();return 1;}
static int reserve(const char* p,int flags) {
 if(flags!=(O_WRONLY|O_CREAT|O_EXCL))abort();
 if(mode==1)return -1;
 return open(p,flags,0600);
}
static int close_reserved(int fd){int r=close(fd);return mode==2?-1:r;}
static FILE* open_output(const char* p,const char* m) {
 ++opened;if(mode==2)abort();if(mode==3)return NULL;
 output=fopen(p,m);return output;
}
static int close_stream(FILE* f){int r=fclose(f);++closed;return mode==5 || mode==8?-1:r;}
static int discard(const char* p){++removes;return cleanup_bad?-1:remove(p);}
static size_t write_data(const void* p,size_t s,size_t n,FILE*f){return fwrite(p,s,mode==4?n/2:n,f);}
static int seek_stream(FILE*f,long o,int w){return mode==6?-1:fseek(f,o,w);}
#define open reserve
#define close close_reserved
#define fopen open_output
#define fclose close_stream
#define remove discard
#define fwrite write_data
#define fseek seek_stream
'''+(ROOT/'src/file_output.h').read_text()+section('static const char S_TITLEFMT[]','#define DI_BLOCK')+section('static const unsigned char DSK_SECTORS','/* "slot s drive d"')+section('static unsigned char di_xfer(', '/* Staging block i:')+section('static const char* di_error(', 'void __fastcall__ diskimg_entry(')+r'''
#undef fopen
#undef fclose
int main(int argc,char**argv){
 unsigned char r=0;unsigned int i;
 mode=atoi(argv[2]);cleanup_bad=atoi(argv[3]);strcpy(full,argv[1]);strcpy(reselect,"IMAGE.PO");
 DI->src.f=DI->dst.f=NULL;DI->output_owned=0;
 /* Start with a success message as the real entry does before final closes. */
 strcpy(note,"Saved");
 if(mode==8){DI->src.f=fopen(full,"rb");if(!DI->src.f)abort();}
 else {
  DI->dst.kind=argc>4?SIDE_DSK:SIDE_PO;
  if(!di_new_image())r=0x27;
  else if(mode==7)r=0xFF;
  else{for(i=0;i<512;++i)imageblock[i]=i;r=di_xfer(&DI->dst,0,1);}
 }
 di_finish(r);
 if(DI->src.f || DI->dst.f)abort();
 printf("%d %d %d %s\n",removes,opened,closed,note);return 0;
}
'''
class DiskOutput(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='di-output-');p=Path(cls.tmp.name);cls.exe=p/'test'
  (p/'test.c').write_text(C)
  result=subprocess.run(['cc','-std=c99',str(p/'test.c'),'-o',str(cls.exe)],capture_output=True,text=True)
  if result.returncode:raise RuntimeError(result.stderr)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def setUp(self):
  self.case=tempfile.TemporaryDirectory(prefix='di-out-',dir='/tmp');self.addCleanup(self.case.cleanup)
  self.target=Path(self.case.name)/'IMAGE.PO'
 def run_op(self,mode=0,cleanup=False,dsk=False):
  return subprocess.check_output([self.exe,self.target,str(mode),str(int(cleanup))]+(['DSK'] if dsk else []),text=True)
 def test_successful_po_and_dsk_close_before_success(self):
  self.assertIn('0 1 1 Saved',self.run_op())
  self.assertEqual(self.target.read_bytes(),bytes(range(256))*2)
  self.target.unlink()
  self.assertIn('Saved',self.run_op(dsk=True))
  content=self.target.read_bytes();self.assertEqual(len(content),15*256)
  self.assertEqual(content[:256],bytes(range(256)));self.assertEqual(content[14*256:],bytes(range(256)))
 def test_failed_operations_clean_only_owned_output(self):
  for mode in (1,2,3,4,5,6,7):
   with self.subTest(mode=mode):
    out=self.run_op(mode);self.assertIn('Failed:',out);self.assertFalse(self.target.exists())
    self.assertEqual(int(out.split()[0]),0 if mode==1 else 1)
 def test_cleanup_failure_keeps_bytes_and_names_file(self):
  for mode in (2,3,4,5,6,7):
   with self.subTest(mode=mode):
    out=self.run_op(mode,True);self.assertIn('Cleanup failed: IMAGE.PO retained.',out)
    expected=bytes(range(256))*(2 if mode==5 else 1) if mode in (4,5) else b''
    self.assertEqual(self.target.read_bytes(),expected)
    self.assertIn('Failed:',self.run_op())
    self.assertEqual(self.target.read_bytes(),expected)
    self.target.unlink()
 def test_existing_image_is_neither_opened_nor_deleted(self):
  self.target.write_bytes(b'existing image')
  self.assertIn('0 0 0 Failed:',self.run_op())
  self.assertEqual(self.target.read_bytes(),b'existing image')
 def test_source_close_failure_preserves_read_only_source(self):
  self.target.write_bytes(b'source image')
  self.assertIn('0 0 1 Failed:',self.run_op(8))
  self.assertEqual(self.target.read_bytes(),b'source image')
if __name__=='__main__':unittest.main()
