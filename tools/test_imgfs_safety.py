"""Run the actual IMGFS C extraction against disposable files and I/O faults.

Only the image block reader and the ProDOS calls are substituted: the
seedling/sapling walk, the reservation, the two passes and the cleanup
decisions are the shipped code.
"""
import subprocess
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
s=(ROOT/'src/a2fc.c').read_text()
a=s.index('static const char im_target[]');b=s.index('#pragma static-locals (pop)',a)
DRIVER=s[a:b]
C=r'''
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#define __fastcall__
struct A2fcApi {int unused;};
struct Entry {char name[17];unsigned char type;unsigned int aux,mdate;unsigned long size;};
struct Panel {char path[512];unsigned char fs,count,cursor,img_len,tags[4];unsigned int dir_key;};
static struct Panel panels[2];
#define pan_at(p) (&panels[p])   /* the resident helper: the same address */
static struct Entry entries[4];
#define ENTRY_SNAPSHOT entries
static unsigned char idxbuf[512],cmp[512],copy_buf[512],active,_filetype;
#define IM_IDX idxbuf
#define IM_CMP cmp
static unsigned int _auxtype,a2fc_ops,progress_total,progress_done;
static FILE *img_f,*output;
static unsigned char blocks[300][512];
static char other_full[1024],note[80];
static int fault,reads,removes,writes,io_error,progress_calls,opens;
static int img_open(const char* p){img_f=tmpfile();return img_f!=NULL;}
static int is_up(const struct Entry* e){return e->name[0]=='.';}
static int is_dir(const struct Entry* e){return e->type==0x0F;}
static int tag_calls;
static int tag_count(const struct Panel* p){if(++tag_calls>1)abort();return p->tags[0]+p->tags[1]+p->tags[2]+p->tags[3];}
static int tagged(const struct Panel* p,unsigned i){return p->tags[i];}
static int build_full(char* p,const struct Panel* pan,const struct Entry* e){if(fault==17)return 0;sprintf(p,"%s/%s",pan->path,e->name);return 1;}
static void progress_bar(const char* s,unsigned long n,unsigned long total){++progress_calls;}
static int img_read_block(unsigned block,unsigned char* buf){
 if(block>=300)abort();if(block!=290)++reads;   /* the directory (290) is not counted */
 if((fault==4||fault==8)&&reads==3)return 0;        /* 8: and the cleanup fails too */
 if(fault==18&&reads>3)return 0;              /* the second pass cannot read the image */
 memcpy(buf,blocks[block],512);return 1;
}
static int reserve(const char* p,int flags){++opens;if(fault==1)return -1;return open(p,flags,0600);}
static int close_reserved(int fd){int r=close(fd);return fault==2?-1:r;}
static FILE* open_file(const char* p,const char* mode){if(fault==3&&!strcmp(mode,"wb"))return NULL;if(fault==15&&!strcmp(mode,"rb"))return NULL;output=fopen(p,mode);return output;}
static size_t write_file(const void* p,size_t s,size_t n,FILE* f){++writes;if(fault==5)n/=2;if(fault==6)io_error=1;
 if(fault==14&&writes==2){unsigned char c[512];memcpy(c,p,n);c[7]^=1;return fwrite(c,s,n,f);}   /* a byte lands wrong: only the readback can see it */
 return fwrite(p,s,n,f);}
static size_t read_file(void* p,size_t s,size_t n,FILE* f){if(fault==16&&n>1)n-=1;return fread(p,s,n,f);}
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
'''+(ROOT/'src/file_output.h').read_text()+DRIVER+r'''
int main(int argc,char** argv){
 unsigned i,n=atoi(argv[2]),k;unsigned long size=strtoul(argv[3],0,10);fault=atoi(argv[4]);int hole=atoi(argv[5]),storage=argc>6?atoi(argv[6]):0;
 strcpy(panels[1].path,argv[1]);strcpy(panels[0].path,"/X/IMG.PO/DIR");panels[0].img_len=9;panels[0].count=n;
 for(i=0;i<n;++i){sprintf(entries[i].name,"OUT%u",i);entries[i].type=4;entries[i].aux=0x1234+i;entries[i].size=size;entries[i].mdate=2+i;
  if(n>1)panels[0].tags[i]=1;}
 if(n>2){strcpy(entries[1].name,"SUBDIR");entries[1].type=0x0F;}   /* a tagged directory is skipped */
 /* file f: key block 2+f; seedling data there, else an index block there and data in 20+f*64+k */
 panels[0].dir_key=290;blocks[290][4]=0xF1;      /* the directory: its header, then one entry per file */
 for(i=0;i<n;++i){unsigned char* d=blocks[290]+4+(i+1)*0x27;unsigned long eof=size+(storage==8);
  d[0]=((storage&&storage!=8)?storage:size<=512?1:size<=131072?2:3)<<4|4;memcpy(d+1,entries[i].name,4);
  d[0x11]=entries[i].mdate;d[0x12]=entries[i].mdate>>8;d[0x15]=eof;d[0x16]=eof>>8;d[0x17]=eof>>16;
  if(storage==9)d[0]=0;}                     /* 9: no entry (deleted since the snapshot) */
 for(i=0;i<n&&size<=131072;++i){          /* a tree file has no blocks to prepare: it is refused */
  unsigned long need=(size+511)>>9;
  if(storage==1)for(k=0;k<512;++k)blocks[2+i][k]=(k*17+3)&255;
  else if(size<=512)for(k=0;k<size;++k)blocks[2+i][k]=(k*17+3)&255;
  else for(k=0;k<need;++k){unsigned blk=20+i*64+k,j;
   if(hole&&k==1)blk=0;
   blocks[2+i][k]=blk&255;blocks[2+i][256+k]=blk>>8;
   if(blk)for(j=0;j<512;++j)blocks[blk][j]=((k*512+j)*17+3)&255;}
 }
 note[0]=0;
 extract_targets();
 printf("%u %u %u %d %d %d %s\n",a2fc_ops,_filetype,_auxtype,removes,writes,opens,note);return 0;
}
'''
def expected(size,hole=0):
    data=bytes((i*17+3)&255 for i in range(size))
    if hole and size>512:data=data[:512]+bytes(min(512,size-512))+data[1024:]
    return data
class ImgfsExtract(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='imgfs-extract-');cls.root=Path(cls.tmp.name)
  p=cls.root/'test.c';p.write_text(C);cls.exe=cls.root/'test'
  r=subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-fsanitize=address,undefined',str(p),'-o',str(cls.exe)],capture_output=True,text=True)
  if r.returncode:raise RuntimeError(r.stderr)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def run_case(self,size=600,fault=0,files=1,hole=0,existing=None,storage=0):
  with tempfile.TemporaryDirectory(dir=self.root) as d:
   p=Path(d)/'OUT0'
   if existing is not None:p.write_bytes(existing)
   out=subprocess.check_output([str(self.exe),d,str(files),str(size),str(fault),str(hole),str(storage)],text=True)
   return out,p.read_bytes() if p.exists() else None,{q.name:q.read_bytes() for q in Path(d).iterdir()}
 def test_exact_bytes_seedling_sapling_and_holes(self):
  for n in (0,1,511,512,513,1024,1025,5000,131072):
   with self.subTest(n=n):
    out,data,_=self.run_case(n)
    self.assertTrue(out.startswith('1 4 4660 0 '),out);self.assertEqual(data,expected(n))
    self.assertIn('1 file extracted.',out)
  out,data,_=self.run_case(2000,hole=1);self.assertEqual(data,expected(2000,1))
 def test_tree_file_is_refused_before_any_reservation(self):
  out,data,_=self.run_case(131073);self.assertIsNone(data);self.assertTrue(out.startswith('0 0 0 0 0 0 '),out)
  self.assertIn('0 files extracted, 1 not supported (tree/fork).',out)
 def test_failures_never_leave_unverified_output(self):
  for fault in (1,2,3,4,5,6,7,17):
   with self.subTest(fault=fault):
    out,data,_=self.run_case(fault=fault);self.assertTrue(out.startswith('0 '),out);self.assertIsNone(data)
    self.assertIn('Extract failed; 0 complete.',out)
 def test_existing_file_is_never_opened_or_removed(self):
  out,data,_=self.run_case(existing=b'KEEP\x00ALL');self.assertEqual(data,b'KEEP\x00ALL');self.assertIn(' 0 0 1 ',out)
 def test_failed_cleanup_reports_and_retains_exact_partial_bytes(self):
  out,data,_=self.run_case(fault=8);self.assertIn('Cleanup failed: OUT0 retained',out)
  self.assertEqual(data,expected(600)[:512])
  out,again,_=self.run_case(existing=data);self.assertEqual(again,data)
 def test_readback_catches_a_wrong_byte_a_failed_reopen_a_short_read_and_a_lost_image(self):
  for fault in (14,15,16,18):
   with self.subTest(fault=fault):
    out,data,_=self.run_case(fault=fault);self.assertTrue(out.startswith('0 '),out);self.assertIsNone(data)
 def test_image_close_error_keeps_verified_output_but_reports_failure(self):
  out,data,_=self.run_case(fault=9);self.assertIn('Extract failed; 1 complete.',out);self.assertEqual(data,expected(600))
 def test_tagged_batch_skips_directories_and_keeps_completed_files_on_failure(self):
  out,_,files=self.run_case(files=3)
  self.assertIn('2 files extracted.',out);self.assertEqual(files,{'OUT0':expected(600),'OUT2':expected(600)})
  out,_,files=self.run_case(files=3,fault=18)   # the first readback fails: nothing kept, batch stopped
  self.assertIn('Extract failed; 0 complete.',out);self.assertEqual(files,{})
  out,_,files=self.run_case(files=3,fault=9)
  self.assertEqual(sorted(files),['OUT0','OUT2'])
 def test_storage_type_comes_from_the_directory_entry(self):
  # a sparse seedling: its key block is data, never an index; zeros follow
  for n in (513,1000,5000):
   with self.subTest(n=n):
    out,data,_=self.run_case(n,storage=1);self.assertIn('1 file extracted.',out)
    self.assertEqual(data,expected(512)+bytes(n-512))
  for st in (3,5):                         # tree or forked below 128K: refused, nothing reserved
   with self.subTest(storage=st):
    out,data,_=self.run_case(600,storage=st);self.assertIsNone(data);self.assertTrue(out.startswith('0 0 0 0 0 0 '),out)
    self.assertIn('1 not supported (tree/fork).',out)
  for st in (8,9):                         # stale size or entry gone: no guess, no output
   with self.subTest(storage=st):
    out,data,_=self.run_case(600,storage=st);self.assertIsNone(data);self.assertIn('Extract failed; 0 complete.',out)
    self.assertIn(' 0 0 0 ',out)
if __name__=='__main__':unittest.main()
