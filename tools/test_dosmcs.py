"""Production DOS MCS C: exact AY frames, read-only sources and I/O faults."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
import test_dos_stream as D
from mini33_fixture import make_disk,offset
from take1_ref import DosImage
import mcs_ref as M
import mcs_score_ref as S

ROOT=D.ROOT
HARNESS=D.HARNESS[:D.HARNESS.index('int main(int argc')]
HARNESS=HARNESS.replace('#include "src/plugins/dosview.c"',
                       'unsigned char host_song[2304];\n#include "src/plugins/dosmcs.c"')
HARNESS=HARNESS.replace("static int ferr(FILE* f)","int ferr(FILE* f)")
HARNESS=HARNESS.replace('dv_file=fopen(source_path,"rb");if(!dv_file)return -1;\n return skip_(dv_file,(unsigned long)at);',
                       'if(fopen(source_path,"rb")!=f)abort();\n return skip_(f,(unsigned long)at);')
HARNESS=HARNESS.replace("return c=='E'||!c?27:c=='N'?' ':c;",
                       "return c=='E'?27:c=='.'?0:c;")
HARNESS=HARNESS.replace('return fclose(f)||fault==1002?EOF:0;', 'return fclose(f)||fault==1002||fault==2000+closes?EOF:0;')
HARNESS=HARNESS.replace('return fault==1001?NULL:fopen(p,m);', 'return fault==1001||fault==2100+opens?NULL:fopen(p,m);')
HARNESS+=r'''
unsigned char mc_regs[28];
static unsigned int ticks,stopped;
static unsigned char capture;
void __fastcall__ mc_import(const struct A2fcApi*);
unsigned char __fastcall__ import_score(const struct A2fcApi*);
void __fastcall__ mc_play(const struct A2fcApi*);
void __fastcall__ plugin_entry(const struct A2fcApi* a){
 unsigned char stage=md_entrypoint(a);
 if(stage==2)stage=import_score(a);
 if(stage)mc_play(a);
}
void __fastcall__ mc_hw_start(unsigned char s){
 if(dv_file || s!=4 || opens!=closes)abort();
 if(capture)fwrite(host_song,1,2304,stdout);++shown;
}
unsigned char mc_tick(void){if(++ticks>200000)abort();return 1;}
void mc_output(void){if(!shown)abort();fwrite(mc_regs,1,28,stdout);}
void mc_silence(void){if(!shown)abort();}
void mc_hw_stop(void){if(!shown)abort();++stopped;}
static void text(const char* s){(void)s;}
int main(int argc,char** argv){
 static struct A2fcApi api;static struct Panel panels[2];static struct Entry entry;
 static unsigned char active;static char note[80],sel[80],context[81],fullpath[81];
 capture=!strcmp(argv[9],"score");source_path=argv[1];fault=atoi(argv[3]);keys=argv[8];
 strcpy(entry.name,argv[4]);entry.mdate=strtoul(argv[5],0,10);entry.type=atoi(argv[6]);entry.size=strtoul(argv[7],0,10);
 strcpy(panels[0].path,source_path);panels[0].fs=FS_DOS33;panels[0].dir_key=0xe0;
 if(atoi(argv[2]))panels[0].img_len=strlen(source_path);
 api.other_full=context;api.full=fullpath;api.panels=panels;api.active=&active;api.selected=&entry;api.copy_buf=buffer;api.note=note;api.reselect=sel;
 api.mli=mli;api.fopen=opn;api.fread=read_;api.fseek=seek_;api.fclose=close_;
 api.strcpy=strcpy;api.clrscr=clear;api.cputs=text;api.cgetc=key;api.arg=4;
 dv_file=(FILE*)1;plugin_entry(&api);if(shown!=stopped)abort();
 fprintf(stderr,"%d %u %u %u %u %s\n",!note[0],reads,opens,closes,shown,note);return 0;
}
'''


class DOSMCS(unittest.TestCase):
    run_disk=D.Streams.run_disk

    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='dosmcs-',dir='/tmp');cls.p=Path(cls.tmp.name)
        cls.h=cls.p/'test.c';cls.h.write_text(HARNESS);cls.exe=cls.p/'host'
        prefix=D.PREFIX+'extern int ferr(FILE*);\n#define ferror ferr\n'
        cls.units=[cls.h]
        for name,renames in (('mcsimport','#define md_entrypoint import_score\n#define md_player import_player\n#define md_cpu_tag import_cpu_tag\n#define md_api_offsets import_api_offsets\n'),('mcsplay','#define plugin_entry mc_play\n')):
            unit=cls.p/(name+'.c');unit.write_text(prefix+renames+'#define __plugin_header '+name+'_header\n#include "src/plugins/'+name+'.c"\n');cls.units.append(unit)
        subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-I',str(ROOT),
                        *map(str,cls.units),'-o',str(cls.exe)],check=True,capture_output=True)

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def disk(self,data=None):
        if data is None:data=M.fixture()
        return make_disk([('TEXT',4,b'\0\x10'+len(data).to_bytes(2,'little')+data)])

    def test_empty_selection_never_closes_unowned_file(self):
        self.run_disk(self.disk(),name='',key=0,typ=6,good=False)

    def test_exact_sound_and_stale_sizes_all_backends(self):
        data=M.fixture();expected=b''.join(M.frames(data))
        for image in (0,1,2):
            for size in (0,1,0xffffff):
                out,counts,_=self.run_disk(self.disk(data),typ=6,image=image,size=size)
                self.assertEqual(out,expected);self.assertEqual(counts[4],1)

    def test_every_read_open_seek_close_error_precedes_sound(self):
        disk=self.disk()
        for image in (0,1,2):
            _,counts,_=self.run_disk(disk,typ=6,image=image)
            faults=list(range(1,counts[1]+1))
            if image:faults+=[1001,1002,1003,1004]
            for fault in faults:
                out,counts,_=self.run_disk(disk,typ=6,image=image,fault=fault,good=False)
                self.assertEqual(out,b'');self.assertEqual(counts[4],0)

    def test_malformed_music_and_allocations_never_start_sound(self):
        data=bytearray(M.fixture())
        for at,value in ((0,255),(1,0),(1153,128)):
            bad=data.copy();bad[at]=value
            out,counts,_=self.run_disk(self.disk(bytes(bad)),typ=6,good=False)
            self.assertEqual(out,b'');self.assertEqual(counts[4],0)
        for n in (0,255,2303,2305):
            self.run_disk(self.disk(bytes(n)),typ=6,good=False)
        disk=bytearray(self.disk());t,s=DosImage(disk).find(b'TEXT');ts=offset(t,s)
        for at,value in ((ts+1,bytes((t,s))),(ts+5,b'\1\0'),
                         (ts+14,disk[ts+12:ts+14]),(ts+12,b'\0\1'),
                         (ts+12,b'\x23\0'),(offset(17,0)+0x34,b'\x24')):
            bad=disk.copy();bad[at:at+len(value)]=value
            for image in (0,1):self.run_disk(bytes(bad),typ=6,image=image,good=False)
        # Physical allocations beyond the ten-sector budget are refused,
        # even if a cached/header length says a short export fits.
        large=make_disk([('TEXT',4,b'\0\x10\0\x09'+M.fixture()+bytes(512))])
        self.run_disk(large,typ=6,good=False)
        self.run_disk(self.disk(),typ=4,good=False)
        self.run_disk(self.disk(),name='WRONG',typ=6,key=t*256+s,good=False)

    def test_controls_match_the_existing_sequencer(self):
        data=M.fixture();disk=self.disk(data)
        for keys,tempo in (('+',3),('-',5),('E',4)):
            out,_,_=self.run_disk(disk,typ=6,keys=keys)
            self.assertEqual(out,b''.join(M.frames(data,tempo)) if keys!='E' else b''.join(M.frames(data))[:28])
        baseline,_,_=self.run_disk(disk,typ=6)
        paused,_,_=self.run_disk(disk,typ=6,keys='P...P')
        self.assertEqual(paused,baseline[:28]+baseline)

    def test_real_reference_exports_when_available(self):
        disk=Path('/tmp/a2fc-mcs-player/dsk/mcs-player.dsk')
        if not disk.exists():self.skipTest('private reference disk unavailable')
        raw=disk.read_bytes();catalog=DosImage(raw)
        for name,data in M.disk_exports(disk):
            t,s=catalog.find(name.encode('ascii'))
            normalized=''.join(c if 'A'<=c<='Z' or '0'<=c<='9' else '.' for c in name.upper()[:15])
            if not 'A'<=normalized[0]<='Z':normalized='X'+normalized[1:]
            out,_,_=self.run_disk(raw,name=normalized,typ=6,key=t*256+s)
            self.assertEqual(out,b''.join(M.frames(data)),name)

    def pair_disk(self,main=None,obj=None,name='SCORE',missing=False):
        if main is None:main,obj=S.fixture()
        files=[(name,4,b'\0A'+len(main).to_bytes(2,'little')+main)]
        if not missing:files.append((name+'.OBJ',4,b'\0t'+len(obj).to_bytes(2,'little')+obj))
        return make_disk(files)

    def check_score(self,disk,main,obj,selected='SCORE',image=0,exe=None):
        t,s=DosImage(disk).find(selected.encode())
        normalized=''.join(c if c.isalnum() else '.' for c in selected.upper()[:15])
        out,counts,_=self.run_disk(disk,name=normalized,key=t*256+s,typ=6,image=image,mode='score',exe=exe)
        expected=S.score(main,obj)
        self.assertEqual(out[:2304],expected)
        self.assertEqual(out[2304:],b''.join(M.frames(expected)))
        return counts

    def test_paired_scores_full_names_both_selections_all_backends(self):
        main,obj=S.fixture()
        for name in ('SCORE','A LONG NAME WITH SPACES'):
            disk=self.pair_disk(main,obj,name)
            for image in (0,1,2):
                for selected in (name,name+'.OBJ'):
                    self.check_score(disk,main,obj,selected,image)

    def test_paired_every_read_open_close_error_before_audio(self):
        main,obj=S.fixture();disk=self.pair_disk(main,obj)
        for image in (0,1,2):
            counts=self.check_score(disk,main,obj,image=image)
            faults=list(range(1,counts[1]+1))
            if image:faults += [1003,1004,2001,2002,2101,2102]
            for fault in faults:
                out,c,_=self.run_disk(disk,name='SCORE',typ=6,image=image,mode='score',fault=fault,good=False)
                self.assertEqual(out,b'');self.assertEqual(c[4],0)

    def test_paired_malformed_missing_duplicate_alias_and_truncation(self):
        main,obj=S.fixture()
        self.run_disk(self.pair_disk(main,obj,missing=True),name='SCORE',typ=6,good=False)
        for n in (0,4,255,256,len(main)-1):
            self.run_disk(self.pair_disk(main[:n],obj),name='SCORE',typ=6,good=False)
        for n in (0,4,len(obj)-1):
            self.run_disk(self.pair_disk(main,obj[:n]),name='SCORE',typ=6,good=False)
        for where in (118,119,120,121,122,123,124,125,126,256+8):
            bad=bytearray(main);bad[where]=255
            self.run_disk(self.pair_disk(bad,obj),name='SCORE',typ=6,good=False)
        disk=self.pair_disk(main,obj)
        self.run_disk(self.pair_disk(main+b'X',obj),name='SCORE',typ=6,good=False)
        self.run_disk(self.pair_disk(main,obj+b'X'),name='SCORE',typ=6,good=False)
        duplicate=make_disk([('SCORE',4,b'\0A'+len(main).to_bytes(2,'little')+main),
                            ('SCORE.OBJ',4,b'\0t'+len(obj).to_bytes(2,'little')+obj),
                            ('SCORE.OBJ',4,b'\0t'+len(obj).to_bytes(2,'little')+obj)])
        self.run_disk(duplicate,name='SCORE',typ=6,good=False)
        # Cross-file allocation aliasing must be refused before decoding.
        t,s=DosImage(disk).find(b'SCORE');u,v=DosImage(disk).find(b'SCORE.OBJ')
        bad=bytearray(disk);a,b=offset(t,s),offset(u,v)
        bad[b+12:b+14]=bad[a+12:a+14]
        self.run_disk(bytes(bad),name='SCORE',typ=6,good=False)

    def test_original_editor_scores_directly_from_private_disk(self):
        disk=Path('/tmp/a2fc-mcs-player/dsk/Music Construction Set.dsk')
        if not disk.exists():self.skipTest('private reference disk unavailable')
        raw=disk.read_bytes();catalog=DosImage(raw)
        for name in (b'YANKEE DOODLE',b'RACKET',b'ALLEGRO',b'SCALES',b'DIXIE',
                     b'DAISY',b'BUGGY',b'RHYTHM',b'PAT THE HAT'):
            main=catalog.read_file(*catalog.find(name));obj=catalog.read_file(*catalog.find(name+b'.OBJ'))
            for selected in (name,name+b'.OBJ'):
                self.check_score(raw,main,obj,selected.decode())

    def test_real_cc65_c_on_both_processors(self):
        if not shutil.which('cl65') or not shutil.which('sim65'):self.skipTest('cc65 unavailable')
        target_path=Path(subprocess.check_output(['cl65','--print-target-path'],text=True).strip())
        disk=self.disk()
        for cpu,target in (('6502','sim6502'),('65c02','sim65c02')):
            cfg=(target_path.parent/'cfg'/(target+'.cfg')).read_text()
            config=self.p/(cpu+'.cfg');config.write_text(cfg.replace('\n    CODE:','\n    OVLHDR: load = MAIN, type = ro;\n    CODE:',1))
            exe=self.p/cpu
            subprocess.run(['cl65','-t',target,'--cpu',cpu,'-O','-Cl','-C',str(config),
                            '-I',str(ROOT),'-o',str(exe),*map(str,self.units)],check=True,capture_output=True)
            for image in (0,1,2):
                out,_,_=self.run_disk(disk,typ=6,image=image,exe=exe)
                self.assertEqual(out,b''.join(M.frames(M.fixture())))
                main,obj=S.fixture();self.check_score(self.pair_disk(main,obj),main,obj,image=image,exe=exe)
                self.check_score(self.pair_disk(main,obj),main,obj,selected='SCORE.OBJ',image=image,exe=exe)
                for fault in (1,5,12):self.run_disk(disk,typ=6,image=image,exe=exe,fault=fault,good=False)
                if image:self.run_disk(disk,typ=6,image=image,exe=exe,fault=1002,good=False)


if __name__=='__main__':unittest.main()
