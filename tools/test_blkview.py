"""Run BLKVIEW's actual search/extraction code against normalized disk data."""
import subprocess,tempfile,unittest
from pathlib import Path
from test_six_plugins import PREFIX,ROOT
from po22mg import to_2mg
from po2dsk import to_dsk
HARNESS=PREFIX+r'''
#define ferror mock_error
static FILE* errored;
static int mock_error(FILE* f){return f==errored;}
#include "src/plugins/blkview.c"
static long reject;
static unsigned int reads;
static unsigned char writefail;
static size_t read_data(void* p,size_t s,size_t n,FILE* f) {
    if(reject>=0 && ftell(f)>=reject)return 0;
    if(reject<=-2 && ++reads==-reject-1)errored=f; /* full count, flagged source */
    return fread(p,s,n,f);
}
static size_t write_data(const void* p,size_t s,size_t n,FILE* f) {
    if(writefail==1 && ftell(f)>=512)return 0;
    if(writefail>=2 && ftell(f)==(writefail-2)*512L)errored=f;
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
OPEN=PREFIX+r'''
#include "src/plugins/blkview.c"
static struct DirEntry entry;
static const char* host_path;
static unsigned char listed,device_error;
static unsigned char dir_open(const char* p){(void)p;listed=0;return 1;}
static unsigned char dir_next(void){return !listed++;}
static unsigned char dir_close(void){return 0;}
static FILE* open_image(const char* p,const char* m){(void)p;return fopen(host_path,m);}
static unsigned char read_device(unsigned char cmd,void* p){
    struct Block* b=p;unsigned int i;
    if(cmd!=0x80 || b->unit!=0x60 || b->block!=1)abort();
    if(device_error)return 0x27;
    for(i=0;i<512;++i)b->buffer[i]=(unsigned char)(i*3+7);
    return 0;
}
int main(int argc,char** argv){
    static unsigned char scratch[512];FILE* f;unsigned char ok;unsigned int i;
    (void)argc;buf=scratch;host_path=argv[1];
    a.fread=fread;a.fopen=open_image;a.fseek=fseek;a.fclose=fclose;
    a.strcpy=strcpy;a.strcmp=strcmp;a.strlen=strlen;
    a.dir_open=dir_open;a.dir_next=dir_next;a.dir_close=(void (*)(void))dir_close;a.dir_entry=&entry;
    if(!strcmp(argv[2],"device") || !strcmp(argv[2],"device-error")){
        source.unit=0x60;source.blocks=8;source.file=NULL;
        device_error=!strcmp(argv[2],"device-error");a.mli=read_device;
    }else{
        strcpy(entry.name,argv[2]);sprintf(source.path,"/V/%s",argv[2]);
        f=fopen(host_path,"rb");fseek(f,0,SEEK_END);entry.size=ftell(f);fclose(f);
        if(!image_open(&source)){puts("0");return 0;}
    }
    ok=checked_read(&source,1,buf);printf("%u ",ok);
    if(ok)for(i=0;i<512;++i)printf("%02x",buf[i]);
    puts("");source_close(&source);return 0;
}
'''
# extract()'s guard for a device source: the destination volume must be on
# line on another unit. argv: the ON_LINE layout -- "other" (D at $70),
# "same" (D at $60, the source's unit), "twin" (D at $70 and at $E0),
# "none" (no D).
GUARD=PREFIX+r'''
#include "src/plugins/blkview.c"
static const char* layout;static char said[256];
static unsigned char mli(unsigned char cmd,void* p) {
    struct Online* o=p;if(cmd!=0xC5)abort();
    memset(o->buffer,0,256);o->buffer[0]=0x61;o->buffer[1]='S';
    if(!strcmp(layout,"other")||!strcmp(layout,"twin")){o->buffer[16]=0x71;o->buffer[17]='D';}
    if(!strcmp(layout,"same")){o->buffer[16]=0x61;o->buffer[17]='D';}
    if(!strcmp(layout,"twin")){o->buffer[32]=0xE1;o->buffer[33]='D';}
    return 0;
}
static void msg(const char* s){strcat(said,s);strcat(said,"|");}
static char key(void){return 27;}
static unsigned char ask(const char* q,const char* d,unsigned char n){(void)d;(void)n;msg(q);return 0;}
int main(int argc,char** argv) {
    static struct Panel panels[2];static unsigned char scratch[512];static char note[80];
    (void)argc;layout=argv[1];
    a.mli=mli;a.message=msg;a.cgetc=key;a.prompt=ask;a.note=note;a.sprintf=sprintf;buf=scratch;
    other=panels+1;strcpy(other->path,"/D/OUT");source.unit=0x60;
    extract();puts(said);return 0;
}
'''
ENTRY=PREFIX+r'''
#include "src/plugins/blkview.c"
static struct DirEntry entry;
static const char *image_path,*output_path;
static FILE* image_file;
static unsigned char listed,close_error,key_step,source_close_error,extract_requested;
static unsigned int opens,reads,prompts,creates,source_closes,device_reads;
static char input[20],notes[80],messages[400];
static unsigned char dir_open(const char* p){(void)p;listed=0;return 1;}
static unsigned char dir_next(void){return !listed++;}
static unsigned char dir_close(void){return close_error;}
static FILE* open_file(const char* p,const char* m){
    ++opens;
    if(!strcmp(p,"/OUT/EXTRACT"))return fopen(output_path,m);
    image_file=fopen(image_path,m);return image_file;
}
static int close_file(FILE* f){
    int failed=0,r;
    if(f==image_file){++source_closes;image_file=NULL;failed=source_close_error;}
    r=fclose(f);return failed?EOF:r;
}
static size_t read_file(void* p,size_t s,size_t n,FILE* f){++reads;return fread(p,s,n,f);}
static unsigned char mli(unsigned char cmd,void* p){
    FILE* f;
    if(cmd==0xC5){
        struct Online* o=p;memset(o->buffer,0,256);o->buffer[0]=0x66;
        memcpy(o->buffer+1,"SOURCE",6);return 0;
    }
    if(cmd==0x80){
        struct Block* b=p;unsigned int i;if(b->unit!=0x60)abort();++device_reads;
        for(i=0;i<512;++i)b->buffer[i]=(unsigned char)(i*7+b->block*2);
        if(b->block==2){b->buffer[4]=0xF6;b->buffer[41]=8;b->buffer[42]=0;}
        return 0;
    }
    if(cmd!=0xC0)abort();++creates;
    f=fopen(output_path,"wbx");if(!f)return 0x47;
    return fclose(f)?0x27:0;
}
static unsigned char prompt(const char* q,const char* d,unsigned char n){
    (void)q;(void)d;(void)n;strcpy(input,++prompts==1?"0001":"EXTRACT");return 1;
}
static char key(void){return key_step++ || !extract_requested?KEY_ESC:'X';}
static void message(const char* s){strcat(messages,s);strcat(messages,"\n");}
static int print(const char* f,...){(void)f;return 0;}
static void puts_(const char* s){(void)s;}
static void putc_(char c){(void)c;}
static void xy(unsigned char x,unsigned char y){(void)x;(void)y;}
static void cls(void){}
int main(int argc,char** argv){
    static struct A2fcApi api;static struct Panel panels[2];static struct Entry selected;
    static unsigned char active,scratch[512],filetype;static unsigned int auxtype;
    static char full[PATH_LEN],other_full[PATH_LEN];FILE* f;
    (void)argc;image_path=argv[1];output_path=argv[2];close_error=atoi(argv[4]);
    source_close_error=argc>5?atoi(argv[5]):0;extract_requested=argc>6?atoi(argv[6]):1;
    strcpy(entry.name,argv[3]);strcpy(selected.name,argv[3]);
    f=fopen(image_path,"rb");fseek(f,0,SEEK_END);entry.size=ftell(f);fclose(f);
    strcpy(panels[0].path,"/SOURCE");strcpy(panels[1].path,"/OUT");
    sprintf(full,"/SOURCE/%s",argv[3]);
    api.panels=panels;api.active=&active;api.selected=&selected;api.full=full;
    api.other_full=other_full;api.copy_buf=scratch;api.note=notes;api.input=input;
    api.filetype=&filetype;api.auxtype=&auxtype;
    api.memcpy=memcpy;api.strcpy=strcpy;api.strcmp=strcmp;api.strlen=strlen;api.sprintf=sprintf;
    api.fopen=open_file;api.fread=read_file;api.fwrite=fwrite;api.fseek=fseek;api.fclose=close_file;
    api.dir_open=dir_open;api.dir_next=dir_next;api.dir_close=(void (*)(void))dir_close;api.dir_entry=&entry;
    api.mli=mli;api.prompt=prompt;api.message=message;api.cgetc=key;
    api.cprintf=print;api.cputs=puts_;api.cputc=putc_;api.gotoxy=xy;api.clrscr=cls;
    plugin_entry(&api);
    fprintf(stderr,"%u %u %u %u %u\n",opens,reads,prompts,creates,source_closes);
    fprintf(stderr,"DEVICE %u\n",device_reads);
    printf("%s\n%s",notes,messages);return 0;
}
'''

class ImageMetadata(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='blkview-metadata-');cls.p=Path(cls.tmp.name)
        (cls.p/'entry.c').write_text(ENTRY);cls.exe=cls.p/'entry'
        subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-I',str(ROOT),str(cls.p/'entry.c'),'-o',str(cls.exe)],check=True,capture_output=True)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def run_entry(self,name,wrap,error,existing=False,source_close_error=0,extract=True):
        data=bytes((i*7+i//256)&255 for i in range(4096))
        path=self.p/name;original=wrap(data);path.write_bytes(original)
        output=self.p/'EXTRACT';sentinel=b'Existing output must survive.'
        if output.exists():output.unlink()
        if existing:output.write_bytes(sentinel)
        keep=self.p/'KEEP';keep.write_bytes(sentinel)
        run=subprocess.run([str(self.exe),str(path),str(output),name,str(error),
                            str(source_close_error),str(int(extract))],text=True,capture_output=True,check=True)
        self.assertEqual(path.read_bytes(),original)
        self.assertEqual(keep.read_bytes(),sentinel)
        if existing:self.assertEqual(output.read_bytes(),sentinel)
        lines=run.stderr.splitlines();self.device_reads=int(lines[1].split()[1])
        return run.stdout,tuple(map(int,lines[0].split())),output,data
    def test_metadata_close_error_prevents_open_and_extraction(self):
        for name,wrap in (('VOL.PO',bytes),('VOL.DSK',to_dsk),('VOL.2MG',to_2mg)):
            for error in (1,27):
                for existing in (False,True):
                    with self.subTest(name=name,error=error,existing=existing):
                        note,state,output,data=self.run_entry(name,wrap,error,existing)
                        self.assertEqual(state,(0,0,0,0,0))
                        self.assertIn('Invalid or unreadable image.',note)
                        if not existing:self.assertFalse(output.exists())
    def test_successful_metadata_close_still_allows_normalized_extraction(self):
        for name,wrap in (('VOL.PO',bytes),('VOL.DSK',to_dsk),('VOL.2MG',to_2mg)):
            with self.subTest(name=name):
                note,state,output,data=self.run_entry(name,wrap,0)
                self.assertIn('Blocks extracted to other panel.',note)
                self.assertEqual(state[2:],(2,1,1))
                self.assertEqual(output.read_bytes(),data[:512])

    def test_final_image_close_error_is_reported_and_preserves_outputs(self):
        for name,wrap in (('VOL.PO',bytes),('VOL.DSK',to_dsk),('VOL.2MG',to_2mg)):
            for extract,existing in ((False,False),(True,False),(True,True)):
                with self.subTest(name=name,extract=extract,existing=existing):
                    note,state,output,data=self.run_entry(
                        name,wrap,0,existing,source_close_error=1,extract=extract)
                    self.assertEqual(note.splitlines()[0],'BLKVIEW: source close failed.')
                    self.assertEqual(state[-1],1)
                    if extract and not existing:
                        self.assertEqual(output.read_bytes(),data[:512])
                    elif not existing:
                        self.assertFalse(output.exists())

    def test_device_session_has_no_source_file_to_close(self):
        note,state,output,data=self.run_entry('device',bytes,0,source_close_error=1,extract=False)
        self.assertEqual(note,'\n')
        self.assertEqual(state,(0,0,0,0,0))
        self.assertEqual(self.device_reads,2)
        self.assertFalse(output.exists())

class ExtractGuard(unittest.TestCase):
    """Before: the guard was source.unit==unit_of(destination); unit_of
    answering 0 (two volumes named /D on line, so ProDOS may write the copy
    onto either, the source included) let the extraction go on. Now 0 is
    a refusal too."""
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='blkview-guard-');cls.p=Path(cls.tmp.name)
        (cls.p/'guard.c').write_text(GUARD);cls.exe=cls.p/'guard'
        subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-I',str(ROOT),str(cls.p/'guard.c'),'-o',str(cls.exe)],check=True,capture_output=True)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def said(self,layout):return subprocess.check_output([str(self.exe),layout],text=True).strip()
    def test_another_unit_goes_on_to_the_count(self):
        self.assertEqual(self.said('other'),'Block count (4 hex digits, max 7FFF)|')
    def test_the_source_unit_two_names_or_none_are_refused(self):
        for layout in ('same','twin','none'):
            with self.subTest(layout=layout):
                self.assertEqual(self.said(layout),'Choose another destination volume.|')
class Blkview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='blkview-');cls.p=Path(cls.tmp.name)
        (cls.p/'test.c').write_text(HARNESS);cls.exe=cls.p/'test'
        subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-I',str(ROOT),str(cls.p/'test.c'),'-o',str(cls.exe)],check=True,capture_output=True)
        (cls.p/'open.c').write_text(OPEN);cls.open_exe=cls.p/'open'
        subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-I',str(ROOT),str(cls.p/'open.c'),'-o',str(cls.open_exe)],check=True,capture_output=True)
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
    def test_single_image_open_preserves_normalized_reads(self):
        data=b''.join(bytes([s])*256 for s in range(16));path=self.p/'opened-image'
        for name,wrap in (('VOL.PO',bytes),('VOL.DSK',to_dsk),('VOL.2MG',to_2mg)):
            with self.subTest(name=name):
                encoded=wrap(data);path.write_bytes(encoded)
                result=subprocess.check_output([self.open_exe,str(path),name],text=True).split()
                self.assertEqual(result[0],'1')
                self.assertEqual(bytes.fromhex(result[1]),data[512:1024])
                self.assertEqual(path.read_bytes(),encoded)
    def test_device_reads_use_mli_status_without_a_file_stream(self):
        for mode in ('device','device-error'):
            with self.subTest(mode=mode):
                result=subprocess.check_output([self.open_exe,'unused',mode],text=True).split()
                self.assertEqual(result[0],'1' if mode=='device' else '0')
                if mode=='device':
                    self.assertEqual(bytes.fromhex(result[1]),bytes((i*3+7)&255 for i in range(512)))
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
    def test_full_count_source_error_stops_search(self):
        data=bytearray(4096);data[2048:2052]=bytes.fromhex('DEADBEEF')
        for kind in (0,1,2):
            for at in (1,2,3):
                with self.subTest(kind=kind,at=at):
                    self.assertEqual(self.search(data,kind=kind,reject=-at-1)[0],2)
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
    def test_full_count_write_error_stops_extraction(self):
        d=b''.join(bytes([b])*512 for b in range(8));out=self.p/'out'
        for kind in (0,1,2):
            for at in range(3):
                with self.subTest(kind=kind,block=at):
                    self.assertEqual(self.run_data(d,kind,['extract',1,3,at+2,out]),[1])
                    self.assertEqual(out.read_bytes(),d[512:(at+2)*512])
    def test_full_count_source_error_stops_extraction_before_flagged_block(self):
        data=b''.join(bytes([b])*512 for b in range(8));out=self.p/'out'
        for kind in (0,1,2):
            for at in (1,2,3):
                with self.subTest(kind=kind,at=at):
                    self.assertEqual(self.run_data(data,kind,['extract',0,3,0,out],reject=-at-1),[2])
                    copied=(at-1)//(2 if kind==1 else 1)
                    self.assertEqual(out.read_bytes(),data[:copied*512])
    def test_cancel_extract(self):
        out=self.p/'out';self.assertEqual(self.run_data(bytes(1024),0,['extract',0,2,0,out],cancel=1),[3]);self.assertEqual(out.read_bytes(),b'')
if __name__=='__main__':unittest.main()
