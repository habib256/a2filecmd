"""Execute RUN's actual launcher with failed I/O and clobbered shared buffers."""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
C = r'''
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#define PATH_LEN 64
struct Entry { char name[16]; unsigned char type; unsigned int aux; unsigned long size; };
static struct { char path[64]; unsigned char fs; } panels[2];
#define pan_at(p) (&panels[p])   /* the resident helper: the same address */
static unsigned char active, gfi[18], _oserror, copy_buf[512];
static char full[64],other_full[64],cfg_path[64],question[128],note[128];
static const char cfg_rb[]="rb";
struct ConfigState { char reserved[402]; };
static unsigned char scratch[128];
#define LAUNCH_STATE ((struct LaunchState*)scratch)
static unsigned int chain_addr, chain_size, launches, asks, saves, prompts;
static char command[64],runtime[64],prefix[64];
static const char* root;
static int fault, disk_type, disk_aux;
static unsigned char is_dir(const struct Entry* e){return e->type==15;}
static void message(const char*s){strcpy(note,s);}
static void report_error(const char*s){strcpy(note,s);}
static void too_long(void){strcpy(note,"long");}
static void clrscr(void){}
static unsigned char build_full(char*p,const void*pan,const struct Entry*e){
 (void)pan;if(strlen(panels[0].path)+strlen(e->name)+1>=64)return 0;
 sprintf(p,"%s/%s",panels[0].path,e->name);return 1;
}
static FILE* open_path(const char*p,const char*m){
 char host[512];sprintf(host,"%s/%s",root,strrchr(p,'/')+1);return fopen(host,m);
}
static unsigned char file_info(const char*p){
 FILE*f;if(fault==1){_oserror=0x27;return 0;}
 if(strncmp(p,"/TOOLS/",7)){_oserror=0x46;return 0;}
 f=open_path(p,"rb");if(!f){_oserror=0x46;return 0;}fclose(f);
 gfi[3]=fault==2?0:0xC3;gfi[4]=fault==3?6:strstr(p,"PROGRAM")?disk_type:255;gfi[7]=fault==4?5:1;
 gfi[5]=disk_aux&255;gfi[6]=disk_aux>>8;return 1;
}
static unsigned char companion_path(const char*s){strcpy(other_full,"/TOOLS");strcat(other_full,s);return 1;}
static unsigned char ask_disk(const char*s){(void)s;++asks;return 0;}
static unsigned char confirm(const char*s){(void)s;++prompts;return fault!=5 && !(fault==13 && prompts==2);}
static unsigned char save_config(void){++saves;memset(full,'X',63);full[63]=0;strcpy(other_full,"/WRONG");return fault!=6 && fault!=13;}
static int change_dir(const char*p){strcpy(prefix,p);return fault==7?-1:0;}
static void chain_command(const char*s){strcpy(command,s);}
static void chain_load(const char*s){strcpy(runtime,s);++launches;}
static int seek_file(FILE*f,long n,int w){return fault==8?-1:fseek(f,n,w);}
static long tell_file(FILE*f){return fault==9?-1:ftell(f);}
static size_t read_file(void*p,size_t s,size_t n,FILE*f){return fault==10?0:fread(p,s,n,f);}
static int error_file(FILE*f){return fault==11?1:ferror(f);}
static int close_file(FILE*f){int r=fclose(f);return fault==12?-1:r;}
#define fopen open_path
#define fseek seek_file
#define ftell tell_file
#define fread read_file
#define ferror error_file
#define fclose close_file
#define chdir change_dir
#include "src/launch.h"
int main(int argc,char**argv){
 struct Entry e;root=argv[1];fault=atoi(argv[2]);
 strcpy(panels[0].path,argv[4]);strcpy(cfg_path,"/BOOT/A2FILE/A2FILE.CFG");
 strcpy(e.name,"PROGRAM");e.type=atoi(argv[3]);e.size=1;
 /* The file on disk (aux, type) may differ from the panel's stale entry. */
 disk_aux=argc>5?atoi(argv[5]):0x2000;e.aux=argc>6?atoi(argv[6]):0x2000;disk_type=argc>7?atoi(argv[7]):e.type;
 strcpy(command,"OLD.COMMAND");run_selected(&e);
 printf("%u|%s|%s|%u|%u|%s|%u\n",launches,runtime,command,asks,saves,prefix,chain_addr);
 return 0;
}
'''

class Launch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='a2fc-launch-')
        cls.root=Path(cls.tmp.name)
        (cls.root/'test.c').write_text(C)
        cls.exe=cls.root/'test'
        subprocess.run(['cc','-std=c99','-I',str(ROOT),str(cls.root/'test.c'),'-o',str(cls.exe)],check=True)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def run_case(self, fault=0, kind=250, path='/SOURCE/WORK', data=None, disk_aux=0x2000, panel_aux=0x2000, disk_type=None):
        if data is None:data=bytes.fromhex('4c0020eeee4100')+bytes(93)
        for name in ('BASIC.SYSTEM','INTBASIC.SYSTEM','PROGRAM'):(self.root/name).write_bytes(data)
        args=[str(self.exe),str(self.root),str(fault),str(kind),path,str(disk_aux),str(panel_aux)]
        if disk_type is not None:args.append(str(disk_type))
        out=subprocess.check_output(args,text=True).strip().split('|')
        for name in ('BASIC.SYSTEM','INTBASIC.SYSTEM','PROGRAM'):self.assertEqual((self.root/name).read_bytes(),data)
        return out
    def test_both_runtimes_keep_paths_across_config_save(self):
        for kind,name in ((250,'INTBASIC.SYSTEM'),(252,'BASIC.SYSTEM')):
            out=self.run_case(kind=kind)
            self.assertEqual(out[:3],['1','/TOOLS/'+name,'/SOURCE/WORK/PROGRAM'])
            self.assertEqual(out[3:],['0','1','/SOURCE/WORK',str(0x2000)])
    def test_binary_loads_at_the_aux_type_on_disk_not_the_panel_copy(self):
        # A stale panel address never reaches chain_addr: the file's own one does.
        out=self.run_case(kind=6,path='/TOOLS',disk_aux=0x2000,panel_aux=0x0300)
        self.assertEqual((out[0],out[6]),('1',str(0x2000)))
        out=self.run_case(kind=6,path='/TOOLS',disk_aux=0x4000,panel_aux=0x2000)
        self.assertEqual((out[0],out[6]),('1',str(0x4000)))
        # The panel said a valid address; the file now says an invalid one.
        self.assertEqual(self.run_case(kind=6,path='/TOOLS',disk_aux=0x0300,panel_aux=0x2000)[0],'0')
        # The panel's type is stale too: the file on disk decides.
        for kind,disk_type in ((6,255),(255,6),(255,4)):
            with self.subTest(kind=kind,disk_type=disk_type):
                self.assertEqual(self.run_case(kind=kind,path='/TOOLS',disk_type=disk_type)[0],'0')
        self.assertEqual(self.run_case(kind=255,path='/TOOLS')[0],'1')
    def test_long_path_uses_filename_and_source_prefix(self):
        path='/SOURCE/'+('A'*14+'/')*3
        out=self.run_case(path=path.rstrip('/'))
        self.assertEqual(out[0],'1');self.assertEqual(out[2],'PROGRAM');self.assertEqual(out[5],path.rstrip('/'))
    def test_errors_and_cancel_never_launch(self):
        for fault in (1,2,3,4,5,7,8,9,10,11,12,13):
            with self.subTest(fault=fault):self.assertEqual(self.run_case(fault=fault)[0],'0')
        self.assertEqual(self.run_case(fault=1)[3:5],['0','0'])
    def test_invalid_interpreter_header_and_size(self):
        for data in (b'',bytes(100),bytes.fromhex('4c0020eeee1000')+bytes(93),bytes.fromhex('4c0020eeee4100')+bytes(0x9B00)):
            self.assertEqual(self.run_case(data=data)[0],'0')
    def test_default_runtime_command_is_replaced(self):
        data=bytearray(bytes.fromhex('4c0020eeee4100')+bytes(93))
        data[6:14]=b'\x07STARTUP'
        self.assertEqual(self.run_case(data=bytes(data))[0],'1')
    def test_binary_launch_clears_old_interpreter_command(self):
        out=self.run_case(kind=6,path='/TOOLS')
        self.assertEqual(out[:3],['1','/TOOLS/PROGRAM',''])
        self.assertEqual(self.run_case(kind=6,path='/TOOLS',data=bytes(0x9B01))[0],'0')

if __name__=='__main__':unittest.main()
