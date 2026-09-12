"""Execute native catalog readers with failed I/O and malformed disk links."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_file_safety import section
ROOT=Path(__file__).resolve().parents[1]
C=r'''
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#define __fastcall__
#include "src/a2fc_plugin.h"
#define MAX_ENTRIES 140
static unsigned char copy_buf[512],dos_unit,DOS_TS[16];
static FILE* img_f;static long img_base;
static unsigned int seeks,reads,mlis;static int seek_bad,scenario;
static unsigned char mli_call(unsigned char c,unsigned char*p){++mlis;return 0;}
static int fake_seek(FILE*f,long n,int w){++seeks;return seek_bad;}
static size_t fake_read(void*p,size_t s,size_t n,FILE*f){++reads;memset(p,0,s*n);return n;}
#define fseek fake_seek
#define fread fake_read
''' + section('static unsigned char dos_read_sector(', '/* A real DOS 3.3 volume?') + r'''
#undef fseek
#undef fread
static unsigned char dos_vtoc_ok(void){memset(copy_buf,0,512);copy_buf[1]=17;copy_buf[2]=1;return 1;}
static unsigned char catalog_read(unsigned char t,unsigned char s){
 if(++reads>561)exit(9);
 if(scenario==3)return 0;
 memset(copy_buf,0,512);copy_buf[1]=17;copy_buf[2]=1;
 /* An entirely deleted sector in a cyclic chain must terminate. */
 for(unsigned int i=0;i<7;++i)copy_buf[11+i*35]=255;
 return 1;
}
static unsigned char dos33_type(unsigned char t){return 6;}
static struct Entry entries[MAX_ENTRIES];
static struct Entry* add_entry(struct Panel*p,const char*n,unsigned char t){return &entries[p->count++];}
#define dos_read_sector catalog_read
''' + section('static unsigned char read_dos33_panel(', '/* Fills the panel from an image or a real disk') + r'''
#undef dos_read_sector
int main(int argc,char**argv){
 scenario=atoi(argv[1]);
 if(scenario==1){seek_bad=1;if(dos_read_sector(17,1)||reads)return 1;}
 if(scenario==2){dos_unit=0;if(dos_read_sector(35,0)||dos_read_sector(17,16)||seeks||reads)return 2;
 dos_unit=1;if(dos_read_sector(35,0)||dos_read_sector(17,255)||mlis)return 3;}
 if(scenario>=3){struct Panel p;memset(&p,0,sizeof p);if(read_dos33_panel(&p))return 4;}
 return 0;
}
'''
class CatalogSafety(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='catalog-safety-');p=Path(cls.tmp.name);cls.exe=p/'test'
  (p/'test.c').write_text(C)
  subprocess.run(['cc','-std=c99','-Wno-pointer-to-int-cast','-I',str(ROOT),str(p/'test.c'),'-o',str(cls.exe)],check=True,capture_output=True)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def run_case(self,n):subprocess.run([str(self.exe),str(n)],check=True,timeout=3)
 def test_failed_seek_never_reads_wrong_sector(self):self.run_case(1)
 def test_invalid_track_sector_never_accesses_disk_or_table(self):self.run_case(2)
 def test_catalog_read_failure_is_not_success(self):self.run_case(3)
 def test_deleted_catalog_cycle_terminates(self):self.run_case(4)
if __name__=='__main__':unittest.main()
