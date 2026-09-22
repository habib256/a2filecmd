"""Run the actual DOSGET C extraction against disposable files and I/O faults."""
import subprocess
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
s=(ROOT/'src/a2fc.c').read_text()
a=s.index('static const char d3_target[]');b=s.index('#pragma static-locals (pop)',a)
DRIVER=s[a:b]
TYPE=s[s.index('static unsigned char dos33_type('):s.index('/* Fills the panel from the DOS 3.3 catalog')]
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
struct Entry {char name[17];unsigned char type;unsigned int mdate,blocks;};
struct Panel {char path[512];unsigned char fs,count,cursor,img_len;unsigned int dir_key;};
static struct Panel panels[2];
static struct Entry entries[2];
#define ENTRY_SNAPSHOT entries
static unsigned char scratch[244],seen[70],cmp[256],copy_buf[512],active,dos_unit,_filetype;
#define DOS_TSBUF scratch
#define DOS_SEEN seen
#define DOS_CMP cmp
static unsigned int _auxtype,a2fc_ops;
static FILE *img_f,*output;
static unsigned char sectors[560][256];
static char other_full[1024],note[80];
static int fault,reads,removes,writes,io_error,source_close,alltags,keys;
static int img_open(const char* p){img_f=tmpfile();return img_f!=NULL;}
static void message(const char* p){strcpy(note,p);}
static int is_up(const struct Entry* e){return e->name[0]=='.';}
static int tag_calls;
static int tag_count(const struct Panel* p){if(++tag_calls>1)abort();return alltags;}
static int tagged(const struct Panel* p,unsigned i){return alltags;}
static int build_full(char* p,const struct Panel* pan,const struct Entry* e){sprintf(p,"%s/%s",pan->path,e->name);return 1;}
/* The progress bar the extraction shows: never backwards, never past its
 * total, and at least once a file -- a Disk II read is slow enough that a
 * silent screen reads as a hang. */
static unsigned long bar_done,bar_total;static int bar_calls,bar_bad;
static unsigned int progress_done,progress_total;   /* the "n/m" of the bar: files */
static void progress_bar(const char* n,unsigned long done,unsigned long total){
 if(!n||!*n||!total||done>total||(bar_calls&&total==bar_total&&done<bar_done))bar_bad=1;
 bar_done=done;bar_total=total;++bar_calls;}
static int kbhit(void){return fault==10;}
static int cgetc(void){return ++keys==2?27:0;}
static int dos_read_sector(unsigned t,unsigned s){
 ++reads;if(t>=35||s>=16)abort();
 if(fault==4&&reads==3)return 0;
 memcpy(copy_buf,sectors[t*16+s],256);return 1;
}
static int reserve(const char* p,int flags){if(fault==1)return -1;return open(p,flags,0600);}
static int close_reserved(int fd){int r=close(fd);return fault==2?-1:r;}
static int opens;
static FILE* open_file(const char* p,const char* mode){++opens;if(fault==3)return NULL;if(fault==15&&!strcmp(mode,"rb"))return NULL;output=fopen(p,mode);return output;}
static size_t write_file(const void* p,size_t s,size_t n,FILE* f){++writes;if(fault==5)n/=2;if(fault==6)io_error=1;
 if(fault==14&&writes==2){unsigned char c[256];memcpy(c,p,n);c[7]^=1;return fwrite(c,s,n,f);}   /* a byte lands wrong: only the readback can see it */
 return fwrite(p,s,n,f);}
static size_t read_file(void* p,size_t s,size_t n,FILE* f){if(fault==16&&n>1)return 0;return fread(p,s,n,f);}
static int error_file(FILE* f){return io_error||ferror(f);}
static int close_file(FILE* f){int src=f==img_f,r=fclose(f);return (src?fault==9:fault==7)?-1:r;}
static int remove_file(const char* p){++removes;return fault==8?-1:remove(p);}
#define open reserve
#define close close_reserved
#define fopen open_file
#define fwrite write_file
#define fread read_file
#define ferror error_file
#define fclose close_file
#define remove remove_file
'''+(ROOT/'src/file_output.h').read_text()+TYPE+DRIVER+r'''
int main(int argc,char** argv){
 unsigned i,len=atoi(argv[3]),skip,type=atoi(argv[2]);fault=atoi(argv[4]);
 if(argc>5){printf("%u\n",dos33_type(atoi(argv[5])));return 0;}
 strcpy(panels[1].path,argv[1]);strcpy(panels[0].path,"X");panels[0].img_len=1;panels[0].count=1;
 strcpy(entries[0].name,"OUTPUT");entries[0].type=type;entries[0].mdate=0x0100;
 entries[0].blocks=9;                /* the catalog's count: one T/S list, eight data */
 skip=type==6?4:type>=250?2:0;
 for(i=0;i<8;++i){sectors[16][12+i*2]=2;sectors[16][13+i*2]=i;}
 for(i=0;i<2048;++i)sectors[32+i/256][i%256]=(i-skip)*17+3;
 if(skip==4){sectors[32][0]=0x34;sectors[32][1]=0x12;}
 if(skip){sectors[32][skip-2]=len;sectors[32][skip-1]=len>>8;}
 if(fault==8)sectors[16][16]=35; /* fail after writing first two sectors; cleanup fails */
 if(fault==11)sectors[16][16]=0; /* premature EOF */
 if(fault==12){sectors[16][14]=2;sectors[16][15]=0;} /* duplicate sector */
 if(fault==13){sectors[16][1]=1;sectors[16][2]=0;} /* TS cycle */
 if(fault==20){sectors[16][14]=0;sectors[16][15]=0;} /* a hole between data sectors */
 if(fault==21)for(i=6;i<8;++i){sectors[16][12+i*2]=0;sectors[16][13+i*2]=0;} /* trailing holes */
 if(fault==22){for(i=2;i<8;++i){sectors[16][12+i*2]=0;sectors[16][13+i*2]=0;}
  sectors[16][1]=1;sectors[16][2]=5;sectors[21][12]=2;sectors[21][13]=2;} /* data again in the next T/S list */
 if(fault==23){sectors[16][12]=0;sectors[16][13]=0;} /* the first sector is a hole */
 dos_extract();
 printf("%u %u %u %d %d %d %d %s\n",a2fc_ops,_filetype,_auxtype,removes,writes,
        bar_calls,bar_bad,note);return 0;
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
 def test_the_extraction_shows_progress(self):
  """A Disk II read is slow; a screen that says nothing reads as a hang."""
  for typ in (4,6,252):
   with self.subTest(typ=typ):
    out,_=self.run_case(typ,600)
    calls,bad=out.split()[5],out.split()[6]
    self.assertEqual(bad,'0',out)        # never backwards, never past the total
    self.assertGreater(int(calls),1,out) # and more than once over the file

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
 def test_readback_catches_a_wrong_byte_a_failed_reopen_and_a_short_read(self):
  for fault in (14,15,16):
   with self.subTest(fault=fault):
    out,data=self.run_case(fault=fault);self.assertTrue(out.startswith('0 '),out);self.assertIsNone(data)
 def test_source_close_error_keeps_completed_output_but_reports_failure(self):
  out,data=self.run_case(fault=9);self.assertIn('Extract failed',out);self.assertEqual(len(data),600)
 def test_cycle_is_rejected_before_reusing_sectors(self):
  out,data=self.run_case(4,fault=13);self.assertTrue(out.startswith('0 '),out);self.assertIsNone(data)
 def test_sparse_text_holes_are_zero_sectors_and_trailing_holes_end_the_file(self):
  pat=bytes((i*17+3)&255 for i in range(2048))
  out,data=self.run_case(4,fault=20);self.assertTrue(out.startswith('1 4 0 '),out)
  self.assertEqual(data,pat[:256]+bytes(256)+pat[512:])
  out,data=self.run_case(4,fault=21);self.assertTrue(out.startswith('1 4 0 '),out);self.assertEqual(data,pat[:1536])
  out,data=self.run_case(4,fault=22);self.assertTrue(out.startswith('1 4 0 '),out)
  self.assertEqual(data,pat[:512]+bytes(120*256)+pat[512:768])
 def test_a_sized_file_cannot_start_with_a_hole(self):
  for typ in (6,250,252):
   out,data=self.run_case(typ,fault=23);self.assertTrue(out.startswith('0 '),out);self.assertIsNone(data)
 def test_dos_types_without_a_bin_header_keep_every_byte(self):
  types={0:4,1:250,2:252,4:6,0x84:6,8:0,0x10:0,0x20:0,0x40:0,0x88:0}
  for dos,prodos in types.items():
   with self.subTest(dos=dos):
    out=subprocess.check_output([str(self.exe),'.','0','0','0',str(dos)],text=True)
    self.assertEqual(int(out),prodos)
  out,data=self.run_case(0,600);self.assertTrue(out.startswith('1 0 0 '),out)
  self.assertEqual(data,bytes((i*17+3)&255 for i in range(2048)))
if __name__=='__main__':unittest.main()
