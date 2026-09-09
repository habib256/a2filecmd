"""Run actual overlay C routines against damaged images and failed writes."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_volinfo import fixture, entry, allocated, ptr
from prodos_read import Image
ROOT=Path(__file__).resolve().parents[1]
PREFIX='''#define __fastcall__
#define PLUGIN_HOST
#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#undef memcpy
#undef memset
#undef strcpy
#undef sprintf
struct A2fcApi;
'''
UNDELETE=PREFIX+r'''
#include "src/plugins/undelete.c"
static FILE* diskfile;
static unsigned char mock(unsigned char cmd,void* p) {
    struct Block* b=p;if(cmd!=0x80)abort();
    if(fseek(diskfile,(long)b->block*512,SEEK_SET))return 0x27;
    return fread(b->buffer,1,512,diskfile)==512?0:0x27;
}
int main(int argc,char** argv) {
    unsigned char scratch[512];
    a.memcpy=memcpy;a.memset=memset;a.mli=mock;buf=scratch;
    diskfile=fopen(argv[1],"rb");fseek(diskfile,1024,SEEK_SET);fread(buf,1,512,diskfile);
    total=rd16(buf+41);bitmap=rd16(buf+39);memcpy(e,buf+43,39);
    printf("%u\n",valid());fclose(diskfile);return 0;
}
'''
MKIMAGE=PREFIX+r'''
#include "src/plugins/mkimage.c"
int main(int argc,char** argv) {
    unsigned char scratch[512];FILE* f=fopen(argv[1],"wb");
    a.memcpy=memcpy;a.memset=memset;a.strlen=strlen;buf=scratch;
    strcpy(name,"EMPTY");blocks=atoi(argv[2]);maps=(blocks+4095U)/4096;
    for(b=0;b<blocks;++b){makeblock();fwrite(buf,1,512,f);}fclose(f);return 0;
}
'''
SYNC=PREFIX+r'''
#include "src/plugins/sync.c"
static unsigned int mode;
static char oldpath[80],newpath[80];
static unsigned char mock(unsigned char cmd,void* p) {
    FILE* f;unsigned char* pp;
    if(cmd==0xC0){pp=((struct Create*)p)->path;memcpy(oldpath,pp+1,pp[0]);oldpath[pp[0]]=0;
        f=fopen(oldpath,"wx");if(!f)return 0x47;fclose(f);return 0;}
    if(cmd==0xC4){pp=((struct Info*)p)->path;memcpy(oldpath,pp+1,pp[0]);oldpath[pp[0]]=0;
        f=fopen(oldpath,"rb");if(!f)return 0x46;fclose(f);return 0;}
    if(cmd==0xC2){pp=((struct Rename*)p)->old;memcpy(oldpath,pp+1,pp[0]);oldpath[pp[0]]=0;
        pp=((struct Rename*)p)->newpath;memcpy(newpath,pp+1,pp[0]);newpath[pp[0]]=0;
        if(mode==2 && strstr(oldpath,"A2FC.SYNC"))return 0x27;
        return rename(oldpath,newpath)?0x27:0;}
    if(cmd==0xC3)return mode==4?0x27:0;
    abort();
}
static size_t write_fail(const void* p,size_t s,size_t n,FILE* f) {
    return mode==1?0:fwrite(p,s,n,f);
}
int main(int argc,char** argv) {
    unsigned char scratch[512];char msg[80];
    a.strlen=strlen;a.strcpy=strcpy;a.memcpy=memcpy;a.memset=memset;a.mli=mock;
    a.fopen=fopen;a.fclose=fclose;a.fread=fread;a.fwrite=write_fail;a.remove=remove;
    a.note=msg;buf=scratch;
    strcpy(sdir,argv[1]);strcpy(ddir,argv[2]);join(source,sdir,"DATA");join(target,ddir,"DATA");
    if(!newer((30<<9)|33,0,(26<<9)|33,0) || newer((99<<9)|33,0,(0<<9)|33,0) ||
       !newer((26<<9)|33,0x0D00,(26<<9)|33,0x0C00))abort();
    mode=atoi(argv[3]);cancelled=mode==3;size=1600;meta.type=6;meta.aux=0;meta.access=0xE3;
    printf("%u\n",copy_file(1));return 0;
}
'''

RESCUE=PREFIX+r'''
#include "src/plugins/rescue.c"
static unsigned int attempts,failures;
static unsigned char mock(unsigned char cmd,void* p) {
    struct Block* b=p;if(cmd!=0x80)abort();++attempts;
    if(attempts<=failures)return 0x27;
    memset(b->buffer,0x5A,512);return 0;
}
int main(int argc,char** argv) {
    unsigned char scratch[512],r;
    buf=scratch;a.mli=mock;a.memset=memset;disk=1;unit=0x60;
    memset(buf,0xA5,512);failures=atoi(argv[1]);cancelled=argc>2;
    r=read_chunk(27,2);
    printf("%u %u %u %u %u\n",r,attempts,retried,buf[0],buf[27]);return 0;
}
'''

class SixPlugins(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='six-',dir='/tmp');cls.root=Path(cls.temp.name)
        cls.exe={}
        for name,text in [('undelete',UNDELETE),('mkimage',MKIMAGE),('sync',SYNC),('rescue',RESCUE)]:
            source=cls.root/(name+'.c');source.write_text(text);exe=cls.root/name
            subprocess.run(['cc','-std=c11','-Wno-unknown-pragmas','-I',str(ROOT),str(source),'-o',str(exe)],check=True)
            cls.exe[name]=exe
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def candidate(self,d):
        path=self.root/'candidate.po';path.write_bytes(d)
        result=subprocess.check_output([str(self.exe['undelete']),str(path)],timeout=10).strip()==b'1'
        self.assertEqual(path.read_bytes(),d);return result
    def test_undelete_seedling(self):self.assertTrue(self.candidate(fixture(entries=[entry()])))
    def test_undelete_reused(self):
        d=fixture(entries=[entry()]);allocated(d,4);self.assertFalse(self.candidate(d))
    def test_undelete_sapling(self):
        d=fixture(entries=[entry(2,4,3,1024)]);ptr(d,4,0,5);ptr(d,4,1,6)
        self.assertTrue(self.candidate(d))
    def test_undelete_swapped_index_after_destroy(self):
        d=fixture(entries=[entry(2,4,3,1024)]);ptr(d,4,0,5);ptr(d,4,1,6)
        d[2048:2560]=d[2304:2560]+d[2048:2304]
        self.assertTrue(self.candidate(d))
    def test_undelete_destroy_partial_bitmap_is_refused(self):
        d=fixture(entries=[entry(2,4,3,1024)]);ptr(d,4,0,5);ptr(d,4,1,6)
        d[2048:2560]=d[2304:2560]+d[2048:2304]
        allocated(d,6)
        self.assertFalse(self.candidate(d))
    def test_undelete_destroy_mixed_index_order_is_refused(self):
        d=fixture(1000,[entry(3,4,5,131073)])
        ptr(d,4,0,5);ptr(d,4,1,7);ptr(d,5,0,6);ptr(d,7,0,8)
        # DESTROY stopped between child indexes: only the first is swapped.
        d[2560:3072]=d[2816:3072]+d[2560:2816]
        self.assertFalse(self.candidate(d))
    def test_undelete_ambiguous_index_order_is_refused(self):
        d=fixture(4000,[entry(2,4,2,513)]);ptr(d,4,0,5)
        # Both block 5 and byte-swapped block 1280 are free and plausible.
        self.assertFalse(self.candidate(d))
    def test_undelete_duplicate(self):
        d=fixture(entries=[entry(2,4,3,1024)]);ptr(d,4,0,5);ptr(d,4,1,5)
        self.assertFalse(self.candidate(d))
    def test_undelete_outside_volume(self):self.assertFalse(self.candidate(fixture(entries=[entry(key=280)])))
    def test_undelete_wrong_count(self):self.assertFalse(self.candidate(fixture(entries=[entry(blocks=2)])))
    def test_undelete_xl_last_block(self):self.assertTrue(self.candidate(fixture(65535,[entry(key=65534)])))
    def test_undelete_tree_sparse(self):
        d=fixture(1000,[entry(3,4,3,131073)]);ptr(d,4,0,5);ptr(d,5,0,6)
        self.assertTrue(self.candidate(d))
    def rescue(self,failures,cancel=False):
        args=[str(self.exe['rescue']),str(failures)]
        if cancel:args.append('cancel')
        return [int(x) for x in subprocess.check_output(args).split()]
    def test_rescue_first_read(self):self.assertEqual(self.rescue(0),[1,1,0,90,90])
    def test_rescue_retry_success(self):self.assertEqual(self.rescue(29),[1,30,1,90,90])
    def test_rescue_zero_fill_after_30_failures(self):self.assertEqual(self.rescue(30),[0,30,1,0,165])
    def test_rescue_cancel_does_not_read(self):self.assertEqual(self.rescue(30,True),[0,0,0,165,165])
    def test_mkimage_sizes(self):
        for size in (280,1600,4000,8000,16000,32767):
            with self.subTest(size=size):
                path=self.root/'empty.po';subprocess.run([str(self.exe['mkimage']),str(path),str(size)],check=True)
                im=Image(path.read_bytes());self.assertEqual(im.header()['blocks'],size)
                self.assertEqual(im.header()['name'],'EMPTY');self.assertEqual(im.entries(2),[])
                self.assertEqual(im.free_blocks(),size-6-(size+4095)//4096)
                bits=im.d[6*512:(6+(size+4095)//4096)*512]
                self.assertTrue(all(not(bits[b>>3]&(0x80>>(b&7))) for b in range(size,len(bits)*8)))
    def sync(self,mode,reserved=None):
        with tempfile.TemporaryDirectory(prefix='s-',dir='/tmp') as t:
            root=Path(t);s=root/'S';d=root/'D';s.mkdir();d.mkdir()
            original=b'original destination';replacement=bytes(range(200))*8
            (s/'DATA').write_bytes(replacement);(d/'DATA').write_bytes(original)
            if reserved:(d/reserved).write_bytes(b'preexisting')
            ok=subprocess.check_output([str(self.exe['sync']),str(s),str(d),str(mode)]).strip()==b'1'
            self.assertEqual((s/'DATA').read_bytes(),replacement)
            self.assertEqual((d/'DATA').read_bytes(),replacement if ok else original)
            if reserved:self.assertEqual((d/reserved).read_bytes(),b'preexisting')
            else:
                self.assertFalse((d/'A2FC.SYNC').exists())
                if mode==4:self.assertEqual((d/'A2FC.BAK').read_bytes(),original)
                else:self.assertFalse((d/'A2FC.BAK').exists())
            return ok
    def test_sync_verified_replace(self):self.assertTrue(self.sync(0))
    def test_sync_write_failure_keeps_original(self):self.assertFalse(self.sync(1))
    def test_sync_install_failure_rolls_back(self):self.assertFalse(self.sync(2))
    def test_sync_cancel_keeps_original(self):self.assertFalse(self.sync(3))
    def test_sync_metadata_failure_retains_original_backup(self):self.assertTrue(self.sync(4))
    def test_sync_preexisting_temp_is_preserved(self):self.assertFalse(self.sync(0,'A2FC.SYNC'))
    def test_sync_preexisting_backup_is_preserved(self):self.assertFalse(self.sync(0,'A2FC.BAK'))

if __name__=='__main__':unittest.main()
