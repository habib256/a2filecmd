"""Run the actual DOSGET C extraction against disposable files and I/O faults."""
import subprocess
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
s=(ROOT/'src/a2fc.c').read_text()
a=s.index('static const char d3_target[]');b=s.index('#pragma static-locals (pop)',a)
DRIVER=s[a:b]
C=r'''
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#define __fastcall__
#define KEY_ESC 27
struct A2fcApi {int unused;};
struct Entry {char name[17];unsigned char type;unsigned int mdate;};
struct Panel {char path[512];unsigned char fs,count,cursor,img_len;unsigned int dir_key;};
static struct Panel panels[2];
static struct Entry entries[2];
#define ENTRY_SNAPSHOT entries
static unsigned char scratch[244],seen[70],copy_buf[512],active,dos_unit,_filetype;
#define DOS_TSBUF scratch
#define DOS_SEEN seen
static unsigned int _auxtype,a2fc_ops;
static FILE *img_f,*output;
static unsigned char sectors[560][256];
static char other_full[1024],note[80];
static int fault,reads,removes,writes,io_error,source_close,alltags,keys;
static int img_open(const char* p){img_f=tmpfile();return img_f!=NULL;}
static void message(const char* p){strcpy(note,p);}
static int is_up(const struct Entry* e){return e->name[0]=='.';}
static int tag_count(const struct Panel* p){return alltags;}
static int tagged(const struct Panel* p,unsigned i){return alltags;}
static int build_full(char* p,const struct Panel* pan,const struct Entry* e){sprintf(p,"%s/%s",pan->path,e->name);return 1;}
static int kbhit(void){return fault==10;}
static int cgetc(void){return ++keys==2?27:0;}
static int dos_read_sector(unsigned t,unsigned s){
 ++reads;if(t>=35||s>=16)abort();
 if(fault==4&&reads==3)return 0;
 memcpy(copy_buf,sectors[t*16+s],256);return 1;
}
static int reserve(const char* p,int flags){if(fault==1)return -1;return open(p,flags,0600);}
static int close_reserved(int fd){int r=close(fd);return fault==2?-1:r;}
static FILE* open_file(const char* p,const char* mode){if(fault==3)return NULL;output=fopen(p,mode);return output;}
static size_t write_file(const void* p,size_t s,size_t n,FILE* f){++writes;if(fault==5)n/=2;if(fault==6)io_error=1;return fwrite(p,s,n,f);}
static int error_file(FILE* f){return io_error||ferror(f);}
static int close_file(FILE* f){int src=f==img_f,r=fclose(f);return (src?fault==9:fault==7)?-1:r;}
static int remove_file(const char* p){++removes;return fault==8?-1:remove(p);}
#define open reserve
#define close close_reserved
#define fopen open_file
#define fwrite write_file
#define ferror error_file
#define fclose close_file
#define remove remove_file
'''+(ROOT/'src/file_output.h').read_text()+DRIVER+r'''
int main(int argc,char** argv){
 unsigned i,len=atoi(argv[3]),skip,type=atoi(argv[2]);fault=atoi(argv[4]);
 strcpy(panels[1].path,argv[1]);strcpy(panels[0].path,"X");panels[0].img_len=1;panels[0].count=1;
 strcpy(entries[0].name,"OUTPUT");entries[0].type=type;entries[0].mdate=0x0100;
 skip=type==6?4:type>=250?2:0;
 for(i=0;i<8;++i){sectors[16][12+i*2]=2;sectors[16][13+i*2]=i;}
 for(i=0;i<2048;++i)sectors[32+i/256][i%256]=(i-skip)*17+3;
 if(skip==4){sectors[32][0]=0x34;sectors[32][1]=0x12;}
 if(skip){sectors[32][skip-2]=len;sectors[32][skip-1]=len>>8;}
 if(fault==8)sectors[16][16]=35; /* fail after writing first two sectors; cleanup fails */
 if(fault==11)sectors[16][16]=0; /* premature EOF */
 if(fault==12){sectors[16][14]=2;sectors[16][15]=0;} /* duplicate sector */
 if(fault==13){sectors[16][1]=1;sectors[16][2]=0;} /* TS cycle */
 dos_extract();
 printf("%u %u %u %d %d %s\n",a2fc_ops,_filetype,_auxtype,removes,writes,note);return 0;
}
'''
class DosExtract(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='dos-extract-');cls.root=Path(cls.tmp.name)
  p=cls.root/'test.c';p.write_text(C);cls.exe=cls.root/'test'
  r=subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-fsanitize=address,undefined',str(p),'-o',str(cls.exe)],capture_output=True,text=True)
  if r.returncode:raise RuntimeError(r.stderr)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def run_case(self,typ=6,length=600,fault=0,existing=None):
  with tempfile.TemporaryDirectory(dir=self.root) as d:
   p=Path(d)/'OUTPUT'
   if existing is not None:p.write_bytes(existing)
   out=subprocess.check_output([str(self.exe),d,str(typ),str(length),str(fault)],text=True)
   return out,p.read_bytes() if p.exists() else None
 def test_exact_lengths_and_load_addresses(self):
  for typ in (6,250,252):
   for n in (0,1,252,253,254,255,256,600,2044):
    with self.subTest(typ=typ,n=n):
     out,data=self.run_case(typ,n)
     self.assertTrue(out.startswith(f'1 {typ} {4660 if typ==6 else 2049 if typ==252 else 0} '),out)
     self.assertEqual(data,bytes((i*17+3)&255 for i in range(n)))
 def test_text_preserves_sector_bytes(self):
  out,data=self.run_case(4);self.assertTrue(out.startswith('1 4 0 '));self.assertEqual(len(data),2048)
 def test_failures_never_leave_unverified_output(self):
  for fault in (1,2,3,4,5,6,7,10,11,12):
   with self.subTest(fault=fault):
    out,data=self.run_case(fault=fault);self.assertTrue(out.startswith('0 '),out);self.assertIsNone(data)
 def test_existing_file_is_never_opened_or_removed(self):
  out,data=self.run_case(existing=b'KEEP\x00ALL');self.assertEqual(data,b'KEEP\x00ALL');self.assertIn(' 0 0 ',out)
 def test_failed_cleanup_reports_and_retains_exact_partial_bytes(self):
  out,data=self.run_case(fault=8);self.assertIn('Cleanup failed',out)
  self.assertEqual(data,bytes((i*17+3)&255 for i in range(508)))
  out,again=self.run_case(existing=data);self.assertEqual(again,data)
 def test_source_close_error_keeps_completed_output_but_reports_failure(self):
  out,data=self.run_case(fault=9);self.assertIn('Extract failed',out);self.assertEqual(len(data),600)
 def test_cycle_is_rejected_before_reusing_sectors(self):
  out,data=self.run_case(4,fault=13);self.assertTrue(out.startswith('0 '),out);self.assertIsNone(data)
if __name__=='__main__':unittest.main()
