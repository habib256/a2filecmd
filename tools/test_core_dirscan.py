"""Core recursive operations must distinguish incomplete directories from EOF."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_file_safety import SOURCE, section

HARNESS = r'''
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <unistd.h>
#include <fcntl.h>
static unsigned char copy_buf[512];
static int fail_close;
static int checked_close(int fd) {int r=close(fd);return fail_close?-1:r;}
#define close checked_close
static int dir_fd=-1;
static FILE* img_f;
static unsigned char dir_img,dir_error,dir_index,dir_per_block,dir_entry_len;
static unsigned int dir_block_key;
static int valid_chain;
static unsigned char tree_room=1;
static unsigned char tree_stack_ok(void){return tree_room;}
struct DirEntry {char name[17]; unsigned char type,access;unsigned int key,blocks,aux,mdate;unsigned long size;};
static struct DirEntry dir_entry;
struct Mini {char name[16];unsigned char type;unsigned int aux;};
#define POOL_SIZE 213
static struct Mini pool[POOL_SIZE];
static unsigned char img_read_block(unsigned int b,unsigned char* buf) {
 memset(buf,0,512);
 if(valid_chain){buf[0]=b-1;buf[2]=b==3?4:0;}else{buf[0]=2;buf[2]=3;}
 return 1;
}
''' + section('static unsigned char dir_open(const char* path)\n{', '/* ---------------------------------------------------------------------- */\n/* Display') + section('static unsigned char list_dir(const char* path,', '/* Appends "/name"') + r'''
int main(int argc,char**argv) {
    unsigned char n=0,ok;fail_close=argc>2;if(argc>2 && !strcmp(argv[2],"stack-low"))tree_room=0;ok=list_dir(argv[1],0,&n);
    printf("%u %u %u\n",ok,n,dir_error);return 0;
}
'''

PANEL = r'''
#define WINDOW 139
#define MAX_ENTRIES 140
#define ROWS 18
struct Entry {char name[17];unsigned char type,access;unsigned int aux,blocks,mdate;unsigned long size;};
struct Panel {char path[81];unsigned char fs,count,more,cursor,top,tags[18];unsigned int first;struct Entry*e;};
static struct Panel panels[2];static struct Entry entries[140];
static unsigned char read_image_panel(struct Panel*p){return 0;}
static void read_volumes(struct Panel*p){p->count=0;}
static void volume_space(struct Panel*p){}
static void sort_entries(struct Panel*p){}
static struct Entry* add_entry(struct Panel*p,const char*n,unsigned char t){struct Entry*e=&p->e[p->count++];strcpy(e->name,n);e->type=t;return e;}
''' + section('static unsigned char read_panel(unsigned char p)\n{','static void set_cursor(')
HARNESS=HARNESS.replace('int main(int argc,char**argv) {',PANEL+'''int main(int argc,char**argv) {
    if(argc>2 && !strcmp(argv[2],"cycle")) {
        valid_chain=argc>3;dir_img=1;dir_block_key=2;dir_index=13;dir_per_block=13;dir_entry_len=39;
        copy_buf[2]=3;
        printf("%u ",dir_next());printf("%u\\n",dir_error);return 0;
    }
    if(argc>2 && !strcmp(argv[2],"panel")) {
        unsigned char ok;panels[0].e=entries;strcpy(panels[0].path,argv[1]);fail_close=argc>3;
        ok=read_panel(0);printf("%u %u %u\\n",ok,panels[0].count,dir_error);return 0;
    }
''')

class CoreDirscan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='core-dir-');cls.p=Path(cls.tmp.name)
        (cls.p/'test.c').write_text(HARNESS);cls.exe=cls.p/'test'
        subprocess.run(['cc','-std=c99',str(cls.p/'test.c'),'-o',str(cls.exe)],check=True,capture_output=True)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def scan(self,length,linked,name=None,close_error=False,panel=False):
        d=bytearray(length);d[4]=0xF1;d[35:37]=bytes([39,13]);d[2:4]=linked.to_bytes(2,'little')
        d[43:45]=b'\x11A';d[59]=6
        if name is not None:
            d[43]=0x10|len(name);d[44:44+len(name)]=name
        f=self.p/'dir';f.write_bytes(d)
        result=subprocess.check_output([self.exe,f]+(['panel'] if panel else [])+(['close-error'] if close_error else []),text=True)
        self.assertEqual(f.read_bytes(),d)
        return list(map(int,result.split()))
    def test_malformed_names_cannot_redirect_file_operations(self):
        for name in (b'',b'..',b'A/B',b'A:B',b'A\x00B',b'1BAD'):
            with self.subTest(name=name):self.assertEqual(self.scan(512,0,name),[0,0,1])

    def test_close_error_is_not_a_complete_directory(self):
        self.assertEqual(self.scan(512,0,close_error=True),[0,1,1])

    def test_panel_refuses_incomplete_read_and_close(self):
        self.assertEqual(self.scan(512,3,panel=True),[0,0,1])
        self.assertEqual(self.scan(512,0,panel=True,close_error=True),[0,0,1])
        self.assertEqual(self.scan(512,0,panel=True),[1,2,0])

    def test_image_cycle_backlink_is_rejected(self):
        result=subprocess.check_output([self.exe,'unused','cycle'],text=True,timeout=3)
        self.assertEqual(result.split(),['0','1'])

    def test_image_valid_backward_links_are_accepted(self):
        result=subprocess.check_output([self.exe,'unused','cycle','valid'],text=True,timeout=3)
        self.assertEqual(result.split(),['0','0'])

    def test_low_stack_refuses_before_opening_a_directory(self):
        result=subprocess.check_output([self.exe,'unused','stack-low'],text=True,timeout=3)
        self.assertEqual(result.split(),['0','0','0'])

    def test_normal_end(self):self.assertEqual(self.scan(512,0),[1,1,0])
    def test_missing_next_block(self):self.assertEqual(self.scan(512,3),[0,1,1])
    def test_partial_next_block(self):self.assertEqual(self.scan(768,3),[0,1,1])
    def test_complete_next_block(self):self.assertEqual(self.scan(1024,3),[1,1,0])
if __name__=='__main__':unittest.main()
