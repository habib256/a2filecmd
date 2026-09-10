"""Run BLKVIEW's actual search/extraction code against normalized disk data."""
import subprocess,tempfile,unittest
from pathlib import Path
from test_six_plugins import PREFIX,ROOT
HARNESS=PREFIX+r'''
#include "src/plugins/blkview.c"
static long reject;
static unsigned char writefail;
static size_t read_data(void* p,size_t s,size_t n,FILE* f) {
    if(reject>=0 && ftell(f)>=reject)return 0;
    return fread(p,s,n,f);
}
static size_t write_data(const void* p,size_t s,size_t n,FILE* f) {
    if(writefail && ftell(f)>=512)return 0;
    return fwrite(p,s,n,f);
}
int main(int argc,char**argv) {
    unsigned char scratch[512],r,i;FILE* out;
    a.fread=read_data;a.fwrite=write_data;a.fseek=fseek;buf=scratch;
    source.file=fopen(argv[1],"rb");source.blocks=atoi(argv[2]);source.kind=atoi(argv[3]);
    source.base=source.kind==2?64:0;reject=atol(argv[4]);cancelled=atoi(argv[5]);
    if(!strcmp(argv[6],"search")) {
        for(i=0;i<4;++i)pattern[i]=number(argv[7]+i*2,2);
        r=search_bytes(strtoul(argv[8],0,10));
        printf("%u %u %u %lu\n",r,found_block,found_offset,next_search);
    } else {
        block=atoi(argv[7]);writefail=atoi(argv[9]);out=fopen(argv[10],"wb");
        r=extract_blocks(out,atoi(argv[8]));fclose(out);printf("%u\n",r);
    }
    fclose(source.file);
}
'''
class Blkview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='blkview-');cls.p=Path(cls.tmp.name)
        (cls.p/'test.c').write_text(HARNESS);cls.exe=cls.p/'test'
        subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-I',str(ROOT),str(cls.p/'test.c'),'-o',str(cls.exe)],check=True,capture_output=True)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def run_data(self,data,kind,args,reject=-1,cancel=0):
        blocks=len(data)//512
        if kind==1:
            sectors=[0,14,13,12,11,10,9,8,7,6,5,4,3,2,1,15];encoded=bytearray(len(data))
            for t in range(len(data)//4096):
                for s in range(16):encoded[t*4096+sectors[s]*256:t*4096+(sectors[s]+1)*256]=data[t*4096+s*256:t*4096+(s+1)*256]
        else:encoded=(bytes(64) if kind==2 else b'')+data
        path=self.p/'image';path.write_bytes(encoded)
        result=subprocess.check_output([self.exe,str(path),str(blocks),str(kind),str(reject),str(cancel),*map(str,args)],text=True)
        self.assertEqual(path.read_bytes(),encoded)
        return list(map(int,result.split()))
    def search(self,data,start=0,kind=0,reject=-1,cancel=0,pattern='DEADBEEF'):
        return self.run_data(data,kind,['search',pattern,start],reject,cancel)
    def test_boundaries_and_formats(self):
        for kind in (0,1,2):
            for off in (0,255,256,509,510,511,512,4092):
                with self.subTest(kind=kind,off=off):
                    d=bytearray(4096);d[off:off+4]=bytes.fromhex('DEADBEEF')
                    self.assertEqual(self.search(d,kind=kind),[1,off//512,off%512,off+1])
    def test_overlapping_occurrences(self):
        d=bytearray(1024);d[510:515]=b'AAAAA'
        self.assertEqual(self.search(d,pattern='41414141'),[1,0,510,511])
        self.assertEqual(self.search(d,511,pattern='41414141'),[1,0,511,512])
        self.assertEqual(self.search(d,512,pattern='41414141')[0],0)
    def test_short_tail_cannot_match_zero_padding(self):self.assertEqual(self.search(bytes(1024),1021,pattern='00000000')[0],0)
    def test_last_block_of_largest_volume(self):
        d=bytearray(65535*512);d[-4:]=bytes.fromhex('DEADBEEF');start=len(d)-512
        self.assertEqual(self.search(d,start),[1,65534,508,len(d)-3])
    def test_exhausted_has_no_wrap(self):self.assertEqual(self.search(bytes(1024),1024)[0],0)
    def test_read_error_is_not_no_match(self):self.assertEqual(self.search(bytes(1024),reject=512)[0],2)
    def test_cancel(self):self.assertEqual(self.search(bytes(1024),cancel=1)[0],3)
    def test_extract_normalizes_all_formats(self):
        d=bytes(range(256))*16;out=self.p/'out'
        for kind in (0,1,2):
            self.assertEqual(self.run_data(d,kind,['extract',2,3,0,out]),[0])
            self.assertEqual(out.read_bytes(),d[1024:2560])
    def test_partial_read_and_write_errors(self):
        d=bytes(range(256))*8;out=self.p/'out'
        for reject,writefail,expected in ((512,0,2),(-1,1,1)):
            self.assertEqual(self.run_data(d,0,['extract',0,3,writefail,out],reject),[expected])
            self.assertEqual(out.read_bytes(),d[:512])
    def test_cancel_extract(self):
        out=self.p/'out';self.assertEqual(self.run_data(bytes(1024),0,['extract',0,2,0,out],cancel=1),[3]);self.assertEqual(out.read_bytes(),b'')
if __name__=='__main__':unittest.main()
