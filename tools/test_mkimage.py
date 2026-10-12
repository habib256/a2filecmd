"""Execute MKIMAGE's entry point on disposable files with injected I/O faults."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from test_six_plugins import PREFIX, ROOT

C = PREFIX + r'''
static int stream_error(FILE*);
#define ferror stream_error
#include "src/plugins/mkimage.c"
#undef ferror
static int fault, writes, closes, verifying, keys, removes, creates, opens;
static FILE* errored;
static const char* host;
static char format;
static char size_key;
static int cancel_write;
static int stream_error(FILE* f){return f==errored || ferror(f);}
static unsigned char mli_(unsigned char cmd,void* p){
 struct Create* c=p;FILE* f;
 if(cmd!=0xC0 || c->type!=6 || c->aux || c->storage!=1)abort();
 ++creates;if(fault==22 || fault==24)cancelled=1;
 if(fault==1)return 0x48;
 f=fopen(host,"wx");if(!f)return 0x47;fclose(f);return 0;
}
static FILE* open_(const char* p,const char* m){
 (void)p;verifying=!strcmp(m,"rb");
 ++opens;if(fault==23 || fault==25)cancelled=1;
 if(fault==2 || (fault==8 && verifying))return NULL;
 return fopen(host,m);
}
static size_t write_(const void* p,size_t z,size_t n,FILE* f){
 unsigned char damaged[512];++writes;
 if(fault>=26 && fault<=29 && writes==cancel_write){cancelled=1;if(fault==27 || fault==29)errored=f;}
 if(fault==3)return fwrite(p,z,n/2,f);
 if(fault==4 || fault==14)errored=f;
 if((fault==5 && n==512 && writes==(format=='2'?4:3)) || (fault==6 && n==64)){
  memcpy(damaged,p,n);damaged[n-1]^=1;return fwrite(damaged,z,n,f);
 }
 return fwrite(p,z,n,f);
}
static size_t read_(void* p,size_t z,size_t n,FILE* f){
 if(fault==17 && n==1)cancelled=1;
 if(fault==9 && n>1)return fread(p,z,n-1,f);
 if(fault==10 && n==1){errored=f;return 0;}
 if(fault==11 && n>1)errored=f;
 return fread(p,z,n,f);
}
static int close_(FILE* f){
 int r;++closes;
 if(fault==7 && !verifying)fputc('X',f);
 r=fclose(f);if(f==errored)errored=NULL;
 if(verifying && fault>=18 && fault<=20)cancelled=1;
 return (fault==12 && closes==1) || ((fault==13 || fault==20) && closes==2)?-1:r;
}
static int remove_(const char* p){(void)p;++removes;return fault==14 || fault==19 || fault==24 || fault==25 || fault==28 || fault==29?-1:remove(host);}
static char key_(void){return keys++? size_key:format;}
static unsigned char prompt_(const char* l,const char* i,unsigned char h){(void)l;(void)i;(void)h;strcpy(a.input,"EMPTY");if(fault==21)cancelled=1;return 1;}
static void message_(const char* p){(void)p;}
static void progress_(const char* p,unsigned long n,unsigned long total){
 (void)p;(void)n;(void)total;if(fault==15 && !verifying)cancelled=1;if(fault==16 && verifying)cancelled=1;
}
int main(int argc,char** argv){
 static struct A2fcApi api;static struct Panel panels[2];static unsigned char active, scratch[512],type;
 static unsigned int aux;static char full[64],input[17],note[80];
 host=argv[1];fault=atoi(argv[2]);format=argv[3][0];size_key=argv[4][0];strcpy(panels[0].path,"/OUT");
 cancel_write=argc>5?atoi(argv[5]):1;
 api.panels=panels;api.active=&active;api.copy_buf=scratch;api.full=full;api.input=input;api.note=note;
 api.filetype=&type;api.auxtype=&aux;api.memcpy=memcpy;api.memset=memset;api.strcpy=strcpy;
 api.strlen=strlen;api.sprintf=sprintf;api.mli=mli_;api.fopen=open_;api.fwrite=write_;api.fread=read_;
 api.fclose=close_;api.remove=remove_;api.cgetc=key_;api.prompt=prompt_;api.message=message_;api.progress_bar=progress_;
 plugin_entry(&api);fprintf(stderr,"STATE %d %d %d %d\n",creates,opens,writes,closes);printf("%d|%s\n",removes,note);return 0;
}
'''


class Mkimage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='mkimage-test-')
        cls.root = Path(cls.tmp.name)
        source = cls.root/'test.c'
        source.write_text(C)
        cls.exe = cls.root/'test'
        subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-I',str(ROOT),
                        str(source),'-o',str(cls.exe)],check=True,capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_case(self, fault=0, fmt='P', existing=None, size='1', cancel_write=1):
        with tempfile.TemporaryDirectory(dir=self.root) as directory:
            path = Path(directory)/'image'
            if existing is not None:path.write_bytes(existing)
            result = subprocess.run([self.exe,path,str(fault),fmt,size,str(cancel_write)],text=True,capture_output=True,check=True)
            self.state=list(map(int,result.stderr.split()[1:]))
            out=result.stdout.strip()
            return out, path.read_bytes() if path.exists() else None

    def test_success_po_and_2mg_have_valid_headers_and_bitmap(self):
        for fmt,base in (('P',0),('2',64)):
            with self.subTest(fmt=fmt):
                out,data = self.run_case(fmt=fmt)
                self.assertIn('Created EMPTY: 280 blocks',out)
                self.assertEqual(len(data),base+280*512)
                if base:
                    self.assertEqual(data[:8],b'2IMGA2FC')
                    self.assertEqual(int.from_bytes(data[28:32],'little'),280*512)
                header=data[base+1024:base+1536]
                self.assertEqual(header[4:10],b'\xf5EMPTY')
                self.assertEqual(int.from_bytes(header[41:43],'little'),280)
                bitmap=data[base+6*512:base+7*512]
                for block in range(4096):
                    self.assertEqual(bool(bitmap[block//8] & (0x80>>(block&7))),7<=block<280)

    def test_large_images_verify_multiple_bitmaps_and_last_block(self):
        for size,blocks in (('4',8000),('6',32767)):
            for fmt,base in (('P',0),('2',64)):
                with self.subTest(size=size,fmt=fmt):
                    out,data=self.run_case(fmt=fmt,size=size)
                    self.assertIn('Created EMPTY',out)
                    self.assertEqual(len(data),base+blocks*512)
                    self.assertEqual(data[-512:],bytes(512))
                    maps=(blocks+4095)//4096
                    bitmap=data[base+6*512:base+(6+maps)*512]
                    for block in range(maps*4096):
                        self.assertEqual(bool(bitmap[block//8] & (0x80>>(block&7))),6+maps<=block<blocks)

    def test_stream_errors_corruption_and_cancel_never_claim_success(self):
        for fmt in ('P','2'):
            for fault in (2,3,4,5,7,8,9,10,11,12,13,15,16):
                with self.subTest(fmt=fmt,fault=fault):
                    out,data=self.run_case(fault,fmt)
                    self.assertNotIn('Created',out)
                    self.assertIsNone(data)
            out,data=self.run_case(6,'2')
            self.assertNotIn('Created',out);self.assertIsNone(data)

    def test_failed_create_and_collision_never_remove_existing_bytes(self):
        for fmt in ('P','2'):
            for fault in (0,1):
                out,data=self.run_case(fault,fmt,b'personal bytes')
                self.assertTrue(out.startswith('0|'),out)
                self.assertEqual(data,b'personal bytes')
            out,data=self.run_case(1,fmt)
            self.assertTrue(out.startswith('0|'),out);self.assertIsNone(data)

    def test_failed_cleanup_retains_owned_bytes_and_blocks_retry(self):
        for fmt in ('P','2'):
            out,data=self.run_case(14,fmt)
            self.assertIn('Cleanup failed',out);self.assertNotIn('Created',out)
            self.assertIsNotNone(data)
            retry,kept=self.run_case(0,fmt,data)
            self.assertTrue(retry.startswith('0|'),retry);self.assertEqual(kept,data)

    def test_cancel_before_initial_write_preserves_existing_files(self):
        for fmt in ('P','2'):
            for size in ('1','2','3','4','5','6'):
                for fault in range(21,26):
                    for existing in (None,b'personal bytes'):
                        with self.subTest(fmt=fmt,size=size,fault=fault,existing=existing):
                            out,data=self.run_case(fault,fmt,existing,size)
                            self.assertNotIn('Created',out)
                            if fault==21:
                                self.assertEqual(self.state,[0,0,0,0])
                                self.assertTrue(out.startswith('0|'),out)
                                self.assertEqual(data,existing)
                            elif existing is not None:
                                self.assertEqual(self.state,[1,0,0,0])
                                self.assertTrue(out.startswith('0|'),out)
                                self.assertEqual(data,existing)
                            else:
                                self.assertEqual(self.state,[1,1,0,1])
                                self.assertTrue(out.startswith('1|'),out)
                                self.assertEqual(data,b'' if fault in (24,25) else None)
                                if fault in (24,25):self.assertIn('Cleanup failed',out)

    def test_cancel_during_write_stops_before_any_further_block(self):
        for size,blocks in zip('123456',(280,1600,4000,8000,16000,32767)):
            for fmt in ('P','2'):
                _,expected=self.run_case(fmt=fmt,size=size)
                header=64 if fmt=='2' else 0
                for target in (1,2,32,33,blocks+int(bool(header))):
                    prefix=expected[:header+(target-1)*512] if header else expected[:target*512]
                    for fault in range(26,30):
                        with self.subTest(size=size,fmt=fmt,target=target,fault=fault):
                            out,data=self.run_case(fault,fmt,size=size,cancel_write=target)
                            self.assertNotIn('Created',out)
                            self.assertTrue(out.startswith('1|'),out)
                            self.assertEqual(self.state,[1,1,target,1],out)
                            if fault>=28:
                                self.assertIn('Cleanup failed',out)
                                self.assertEqual(data,prefix)
                                retry,kept=self.run_case(fmt=fmt,size=size,existing=data)
                                self.assertTrue(retry.startswith('0|'),retry)
                                self.assertEqual(self.state,[1,0,0,0])
                                self.assertEqual(kept,prefix)
                            else:self.assertIsNone(data)

    def test_cancel_at_final_read_or_close_refuses_success(self):
        for fmt in ('P','2'):
            for size in ('1','2'):
                _, expected = self.run_case(fmt=fmt,size=size)
                for fault in (17,18,19,20):
                    with self.subTest(fmt=fmt,size=size,fault=fault):
                        out,data=self.run_case(fault,fmt,size=size)
                        self.assertNotIn('Created',out)
                        self.assertTrue(out.startswith('1|'),out)
                        if fault==19:
                            self.assertIn('Cleanup failed',out)
                            self.assertEqual(data,expected)
                            retry,kept=self.run_case(0,fmt,data,size)
                            self.assertTrue(retry.startswith('0|'),retry)
                            self.assertEqual(kept,expected)
                        else:
                            self.assertIsNone(data)
                        collision,kept=self.run_case(fault,fmt,b'personal bytes',size)
                        self.assertTrue(collision.startswith('0|'),collision)
                        self.assertEqual(kept,b'personal bytes')


if __name__=='__main__':unittest.main()
