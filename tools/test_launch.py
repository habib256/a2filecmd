"""Execute RUN's actual launcher with failed I/O and clobbered shared buffers."""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
C = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#define PATH_LEN 64
#define NAME_LEN 17
struct Entry { char name[16]; unsigned char type; unsigned int aux; unsigned long size; unsigned int mdate; };
struct Panel { char path[64]; unsigned char fs, count; struct Entry e[64]; unsigned char tags[64]; unsigned char img_len; unsigned int dir_key; };
enum { FS_PRODOS, FS_IMG, FS_DOS33 };
static struct Panel panels[2];
static unsigned char tagged(const struct Panel* p, unsigned char i) { return p->tags[i]; }
/* As in memory: the entry snapshot at $3000 and LaunchState at $3400 over it. */
static unsigned char mem[0x1000];
#define ENTRY_SNAPSHOT ((struct Entry*)mem)
#define pan_at(p) (&panels[p])   /* the resident helper: the same address */
static unsigned char active, gfi[18], _oserror, copy_buf[512];
static char full[64],other_full[64],cfg_path[64],question[128],note[128];
static const char cfg_rb[]="rb";
struct ConfigState { char reserved[402]; };
#define LAUNCH_STATE ((struct LaunchState*)(mem + 0x400))
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
/* display.s's classification, tested there under sim65: 8 is a movie. */
static unsigned char named_kind(const struct Entry*e){return e->type==6&&e->aux==0x8400?8:0;}
#include "src/launch.h"
int main(int argc,char**argv){
 struct Entry e;root=argv[1];fault=atoi(argv[2]);
 strcpy(panels[0].path,argv[4]);strcpy(cfg_path,argc>8?argv[8]:"/BOOT/A2FILE/A2FILE.CFG");
 /* argv[9]: the panel's entries, NAME:SIZE:MARK;... */
 if(argc>9){char*t=argv[9],*end;unsigned long z;int m;
  while(*t&&panels[0].count<64){struct Entry*x=&panels[0].e[panels[0].count];end=strchr(t,';');if(end)*end=0;
   if(sscanf(t,"%15[^:]:%lu:%d",x->name,&z,&m)!=3)return 99;x->size=z;
   /* the snapshot is what RUN may trust; the table is garbage under it */
   ENTRY_SNAPSHOT[panels[0].count]=*x;memset(x,0xA5,sizeof*x);x->name[15]=0;panels[0].tags[panels[0].count++]=m;
   if(!end)break;t=end+1;}}
 strcpy(e.name,getenv("T1_NAME")?getenv("T1_NAME"):"PROGRAM");e.type=atoi(argv[3]);e.size=1;
 /* A Take 1 movie's panel: its file system, image path length, unit, T/S. */
 if(getenv("T1_FS")){panels[0].fs=atoi(getenv("T1_FS"));panels[0].img_len=atoi(getenv("T1_IMGLEN"));
  panels[0].dir_key=atoi(getenv("T1_KEY"));e.mdate=atoi(getenv("T1_MDATE"));}
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
    def run_case(self, fault=0, kind=250, path='/SOURCE/WORK', data=None, disk_aux=0x2000, panel_aux=0x2000, disk_type=None, cfg=None, panel=None, env=None):
        if data is None:data=bytes.fromhex('4c0020eeee4100')+bytes(93)
        for name in ('BASIC.SYSTEM','INTBASIC.SYSTEM','PROGRAM','FANTA.SYSTEM','TAKE1.SYSTEM'):(self.root/name).write_bytes(data)
        args=[str(self.exe),str(self.root),str(fault),str(kind),path,str(disk_aux),str(panel_aux)]
        if disk_type is not None or cfg is not None:args.append(str(kind if disk_type is None else disk_type))
        if cfg is not None or panel is not None:args.append(cfg or '/BOOT/A2FILE/A2FILE.CFG')
        if panel is not None:args.append(panel)
        import os
        out=subprocess.check_output(args,text=True,env=dict(os.environ,**(env or {}))).strip().split('|')
        for name in ('BASIC.SYSTEM','INTBASIC.SYSTEM','PROGRAM','FANTA.SYSTEM','TAKE1.SYSTEM'):self.assertEqual((self.root/name).read_bytes(),data)
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

    def test_fantavision_movie_plays_in_fanta_system_from_a2fc_home(self):
        # The movie's full path goes to FANTA.SYSTEM (an interpreter, from
        # A2FC's own A2FILE directory); the prefix is A2FC's directory, where
        # the player finds A2FILE.SYSTEM to come back. No question asked.
        out=self.run_case(kind=6,path='/SOURCE/WORK',panel_aux=0x8400,disk_type=255,cfg='/TOOLS/A2FILE/A2FILE.CFG')
        self.assertEqual(out,['1','/TOOLS/A2FILE/FANTA.SYSTEM','/SOURCE/WORK/PROGRAM','0','1','/TOOLS',str(0x2000)])
        # An invalid player, a failed lookup or prefix, an unknown home: never
        # launched. (Faults 5 and 13 refuse the first question, which a movie
        # never asks: its only one is the configuration warning.)
        self.assertEqual(self.run_case(kind=6,panel_aux=0x8400,disk_type=255,cfg='/TOOLS/A2FILE/A2FILE.CFG',data=bytes(100))[0],'0')
        for fault in (1,2,4,7,8,11,12):
            with self.subTest(fault=fault):
                self.assertEqual(self.run_case(fault=fault,kind=6,panel_aux=0x8400,disk_type=255,cfg='/TOOLS/A2FILE/A2FILE.CFG')[0],'0')
        self.assertEqual(self.run_case(kind=6,panel_aux=0x8400,disk_type=255,cfg='A2FILE.CFG')[0],'0')
        # A path too long for the interpreter's buffer is refused, not cut.
        self.assertEqual(self.run_case(kind=6,path='/SOURCE/'+'A'*15+'/'+'B'*15,panel_aux=0x8400,disk_type=255,cfg='/TOOLS/A2FILE/A2FILE.CFG')[0],'0')

    def test_fantavision_backdrop_is_the_one_marked_hi_res_page(self):
        movie=dict(kind=6,path='/SOURCE/WORK',panel_aux=0x8400,disk_type=255,cfg='/TOOLS/A2FILE/A2FILE.CFG')
        out=self.run_case(panel='PROGRAM:4000:0;PARADIES:8192:1;NOTE:100:1',**movie)
        self.assertEqual(out[:3],['1','/TOOLS/A2FILE/FANTA.SYSTEM','/SOURCE/WORK/PROGRAM,PARADIES'])
        # an 8,184-byte save counts; a marked text does not
        self.assertEqual(self.run_case(panel='PIC:8184:1',**movie)[2],'/SOURCE/WORK/PROGRAM,PIC')
        self.assertEqual(self.run_case(panel='NOTE:100:1;PIC:8192:0',**movie)[2],'/SOURCE/WORK/PROGRAM')
        # Bug hunt 2: the viewers' page_size also takes "nearly a page"
        # (8,185-8,199, 16,376-16,391); FANTA.SYSTEM's read takes 8,192 or
        # 8,184 only, and named such a file to a player that refused it.
        for size in (8183, 8185, 8191, 8194, 8199, 16384, 16380):
            with self.subTest(size=size):
                self.assertEqual(self.run_case(panel='PIC:%d:1' % size,**movie)[2],'/SOURCE/WORK/PROGRAM')
        self.assertEqual(self.run_case(panel='A:8191:1;B:8192:1',**movie)[2],'/SOURCE/WORK/PROGRAM,B')
        # two marked pictures: which one? Nothing is launched.
        self.assertEqual(self.run_case(panel='A:8192:1;B:8192:1',**movie)[0],'0')
        # the name would pass the thunk's 46 characters: refused, never cut
        long=dict(movie,path='/SOURCE/'+'A'*15+'/'+'B'*11)   # 35 + '/PROGRAM' = 43
        self.assertEqual(self.run_case(panel='PIC:8192:0',**long)[0],'1')
        self.assertEqual(self.run_case(panel='PICTURE:8192:1',**long)[0],'0')
        # 60 entries: the 51st lies where LaunchState overwrites the snapshot.
        many=';'.join('F%02d:100:0' % i for i in range(50))+';DECOR:8192:1;'+';'.join('G%02d:100:0' % i for i in range(9))
        self.assertEqual(self.run_case(panel=many,**movie)[2],'/SOURCE/WORK/PROGRAM,DECOR')

    def test_take1_movie_commands(self):
        # A Take 1 movie MV.x goes to TAKE1.SYSTEM from A2FC's home, with the
        # command of docs/TAKE1-FORMAT.md: the extracted file's full path...
        home=dict(kind=6,disk_type=255,cfg='/TOOLS/A2FILE/A2FILE.CFG')
        out=self.run_case(path='/SOURCE/WORK',panel_aux=0x8029,env={'T1_NAME':'MV.SHUTTLE.DISC'},**home)
        self.assertEqual(out,['1','/TOOLS/A2FILE/TAKE1.SYSTEM','/SOURCE/WORK/MV.SHUTTLE.DISC','0','1','/TOOLS',str(0x2000)])
        # ...a DOS 3.3 image and the T/S of the movie's first list...
        dos={'T1_NAME':'MV.SHUTTLE.DISC','T1_FS':'2','T1_IMGLEN':'16','T1_KEY':'0','T1_MDATE':str(0x1203)}
        out=self.run_case(path='/DISKS/TAKE1.DSK',panel_aux=0,env=dos,**home)
        self.assertEqual(out[:3],['1','/TOOLS/A2FILE/TAKE1.SYSTEM','/DISKS/TAKE1.DSK,1203'])
        # ...or a real DOS 3.3 disk by its ProDOS unit.
        out=self.run_case(path='/DOS 3.3',panel_aux=0,env=dict(dos,T1_IMGLEN='0',T1_KEY=str(0x60),T1_MDATE=str(0x0A0F)),**home)
        self.assertEqual(out[:3],['1','/TOOLS/A2FILE/TAKE1.SYSTEM','%60,0A0F'])
        # An image path past 41 characters would pass the thunk's 46: refused.
        longimg='/'+'A'*15+'/'+'B'*15+'/'+'C'*10      # 43 characters
        self.assertEqual(self.run_case(path=longimg,panel_aux=0,env=dict(dos,T1_IMGLEN=str(len(longimg))),**home)[0],'0')
        # Inside a ProDOS image: nowhere TAKE1.SYSTEM can read from.
        self.assertEqual(self.run_case(path='/DISKS/X.PO',panel_aux=0x8029,env=dict(dos,T1_FS='1'),**home)[0],'0')
        # A player that fails its checks, or an unknown home: never launched.
        self.assertEqual(self.run_case(path='/SOURCE/WORK',panel_aux=0x8029,env={'T1_NAME':'MV.X'},data=bytes(100),**home)[0],'0')
        self.assertEqual(self.run_case(kind=6,disk_type=255,cfg='A2FILE.CFG',panel_aux=0x8029,env={'T1_NAME':'MV.X'})[0],'0')
        # Not a movie: another aux type, or another name, takes the old way.
        self.assertNotEqual(self.run_case(path='/SOURCE/WORK',panel_aux=0x8000,env={'T1_NAME':'MV.X'},**home)[1],'/TOOLS/A2FILE/TAKE1.SYSTEM')
        self.assertNotEqual(self.run_case(path='/SOURCE/WORK',panel_aux=0x8029,env={'T1_NAME':'SN.X'},**home)[1],'/TOOLS/A2FILE/TAKE1.SYSTEM')

if __name__=='__main__':unittest.main()
