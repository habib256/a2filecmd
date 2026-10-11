"""Decode with the actual overlay; assemble the output with ca65 as an oracle."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_six_plugins import PREFIX, ROOT

HARNESS = PREFIX + r'''
static int error_(FILE*);
#define ferror error_
#include "src/plugins/disasm.c"
#undef ferror
static FILE* errored;
static int error_(FILE* f){return f==errored || ferror(f);}
static int seekfail;
static int writes,writefail,cancelafter;
static int closefault,creates;
static FILE* output;
static char export_path[80],export_name[16]="OUT.TXT";
static unsigned char prompt_(const char* p,const char* d,unsigned char n){strcpy(a.input,"OUT.TXT");return 1;}
static unsigned char create_(unsigned char cmd,void* q){
    struct Create* c=q;char path[80];FILE* f;
    if(cmd!=0xC0)abort();++creates;
    memcpy(path,c->path+1,c->path[0]);path[c->path[0]]=0;
    f=fopen(path,"wx");if(!f)return 0x47;fclose(f);return 0;
}
static int close_(FILE* f){
    int r=fclose(f);
    if(f==output){if(closefault>=2)cancelled=1;if(closefault==1 || closefault==3)return EOF;}
    return r;
}
static FILE* open_(const char* p,const char* m){output=fopen(p,m);return output;}
static char key_(void){return 0;}
static void message_(const char* p){}
static long readfail;
static int seek_(FILE* f,long o,int w) {
    if(readfail==-4 && o==(long)size && w==SEEK_SET)return -1;
    return seekfail==1 ? -1 : fseek(f,o,w);
}
static size_t read_(void* p,size_t s,size_t n,FILE* f) {
    if(readfail==-2 || seekfail==2)errored=f;
    if(n==1 && ftell(f)==(long)size && readfail==-3){errored=f;return 0;}
    if(n==1 && ftell(f)==(long)size && readfail==-5)cancelled=1;
    return readfail>=0 && ftell(f)>=readfail ? 0 : fread(p,s,n,f);
}
static size_t write_(const void* p,size_t s,size_t n,FILE* f) {
    ++writes;
    if(cancelafter && writes>=cancelafter)cancelled=1;
    if(writefail>0 && writes>=writefail)return 0;
    if(writefail==-2 || (writefail==-3 && writes>=4))errored=f;
    return fwrite(p,s,n,f);
}
static void clear_(void) {}
static void bar_(const char* p,unsigned long d,unsigned long t) { fprintf(stderr,"BAR %s %lu %lu\n",p,d,t); }
static void xy_(unsigned char x,unsigned char y) {}
int main(int argc,char** argv) {
    unsigned char data[512],n,i;
    struct Entry entry;
    a.sprintf=sprintf;a.strcpy=strcpy;a.strlen=strlen;
    cpu=atoi(argv[1]);
    if(!strcmp(argv[2],"export") || !strcmp(argv[2],"ui-export")) {
        FILE* out;
        a.fseek=seek_;a.fread=read_;a.fwrite=write_;a.full="/SOURCE/CODE";buf=data;
        a.progress_bar=bar_;a.input="OUT.TXT";
        file=fopen(argv[3],"rb");size=strtoul(argv[4],0,10);offset=strtoul(argv[5],0,10);
        origin=strtoul(argv[6],0,16);readfail=atol(argv[7]);writefail=atoi(argv[8]);cancelafter=atoi(argv[9]);
        if(!strcmp(argv[2],"ui-export")) {
            struct Panel destination;char directory[80];
            unsigned char filetype;unsigned int auxtype;
            strcpy(directory,argv[10]);*strrchr(directory,'/')=0;
            memset(&destination,0,sizeof destination);strcpy(destination.path,directory);other=&destination;
            a.input=export_name;a.other_full=export_path;a.memcpy=memcpy;
            a.filetype=&filetype;a.auxtype=&auxtype;
            a.prompt=prompt_;a.mli=create_;a.fopen=open_;a.fclose=close_;
            a.message=message_;a.cgetc=key_;a.gotoxy=xy_;a.cprintf=printf;
            closefault=atoi(argv[11]);export();fclose(file);
            printf("\nUI %s\nCREATES %d\n",export_status?export_status:"none",creates);return 0;
        }
        out=fopen(argv[10],"wb");n=export_text(out);fclose(out);fclose(file);
        printf("%u %lu\n",n,offset);return 0;
    }
    if(!strcmp(argv[2],"page")) {
        a.clrscr=clear_;a.cprintf=printf;a.cputs=(void(*)(const char*))puts;a.gotoxy=xy_;
        a.fseek=seek_;a.fread=read_;readfail=-1;a.selected=&entry;strcpy(entry.name,"TEST");buf=data;
        file=fopen(argv[3],"rb");size=strtoul(argv[4],0,10);offset=strtoul(argv[5],0,10);
        origin=strtoul(argv[6],0,16);seekfail=atoi(argv[7]);render();
        printf("RESULT %lu %u\n",following,failed);fclose(file);return 0;
    }
    n=strlen(argv[3])/2;
    for(i=0;i<n;++i) { char b[3]={argv[3][i*2],argv[3][i*2+1],0};data[i]=strtoul(b,0,16); }
    n=decode(data,n,strtoul(argv[2],0,16));printf("%u %s\n",n,instruction);return 0;
}
'''

class Disasm(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='disasm-',dir='/tmp');cls.p=Path(cls.tmp.name)
        (cls.p/'test.c').write_text(HARNESS);cls.exe=cls.p/'test'
        subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-I',str(ROOT),str(cls.p/'test.c'),'-o',str(cls.exe)],check=True,capture_output=True)
    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()
    def decode(self,data,cpu=0,pc=0x4000):
        n,text=subprocess.check_output([self.exe,str(cpu),f'{pc:X}',data.hex()],text=True).strip().split(' ',1)
        return int(n),text
    def page(self,data,size=None,offset=0,origin=0x2000,seekfail=0):
        path=self.p/'input';path.write_bytes(data)
        result=subprocess.check_output([self.exe,'0','page',path,str(len(data) if size is None else size),str(offset),f'{origin:X}',str(seekfail)],text=True)
        self.assertEqual(path.read_bytes(),data)
        return result
    def export(self,data,offset=0,cpu=1,origin=0x2000,readfail=-1,writefail=0,cancelafter=0,size=None):
        path=self.p/'source';out=self.p/'export';path.write_bytes(data)
        args=[self.exe,str(cpu),'export',path,str(len(data) if size is None else size),str(offset),f'{origin:X}',str(readfail),str(writefail),str(cancelafter),out]
        run=subprocess.run(args,capture_output=True,text=True,check=True)
        status,position=map(int,run.stdout.split())
        self.assertEqual(position,offset);self.assertEqual(path.read_bytes(),data)
        self.bars=[tuple(map(int,l.split()[2:])) for l in run.stderr.splitlines() if l.startswith('BAR OUT.TXT ')]
        return status,out.read_bytes()
    def test_every_opcode_roundtrips_through_assembler(self):
        self.assertIsNotNone(shutil.which('ca65'))
        for cpu,count in ((0,151),(1,212)):
            source=['.setcpu "65C02"' if cpu else '.setcpu "6502"'];expected=bytearray();legal=0
            for op in range(256):
                data=bytes((op,0x34,0x12));n,text=self.decode(data,cpu)
                legal+=not text.startswith('.BYTE')
                # cc65 2.19 has no W65C02 mode. Check the two WDC-only names
                # explicitly; all other output is assembled, including bit ops.
                if cpu and op in (0xCB,0xDB):
                    self.assertEqual((n,text),(1,'WAI' if op==0xCB else 'STP'))
                    continue
                source+=['.org $4000',text];expected+=data[:n]
            self.assertEqual(legal,count)
            (self.p/'round.s').write_text('\n'.join(source)+'\n')
            (self.p/'link.cfg').write_text('MEMORY { M: start=$0000, size=$10000, file=%O; } SEGMENTS { CODE: load=M; }')
            subprocess.run(['ca65',str(self.p/'round.s'),'-o',str(self.p/'round.o')],check=True,capture_output=True)
            subprocess.run(['ld65','-C',str(self.p/'link.cfg'),str(self.p/'round.o'),'-o',str(self.p/'round.bin')],check=True,capture_output=True)
            self.assertEqual((self.p/'round.bin').read_bytes(),expected)
    def test_cmos_is_explicit(self):
        self.assertEqual(self.decode(bytes.fromhex('8034')),(1,'.BYTE $80'))
        self.assertEqual(self.decode(bytes.fromhex('8034'),1),(2,'BRA $4036'))
        self.assertEqual(self.decode(bytes.fromhex('1234'),1),(2,'ORA ($34)'))
    def test_relative_wrap_and_signed_offsets(self):
        for pc,delta,target in ((0,0x80,0xFF82),(0xFFFF,0,1),(0x4000,0xFE,0x4000)):
            self.assertEqual(self.decode(bytes((0xD0,delta)),pc=pc),(2,f'BNE ${target:04X}'))
        self.assertEqual(self.decode(bytes.fromhex('FF3480'),1,0),(3,'BBS7 $34,$FF83'))
    def test_truncated_and_reserved_bytes(self):
        for cpu in (0,1):
            for data in (b'\x4C',b'\x4C\x34',b'\xA9',b'\x03'):
                self.assertEqual(self.decode(data,cpu),(1,f'.BYTE ${data[0]:02X}'))
    def test_page_stops_on_instruction_boundary(self):
        text=self.page(bytes.fromhex('A9124C3412')*20)
        self.assertIn('RESULT 47 0',text)
        self.assertNotIn('.BYTE',text)
    def test_empty_and_truncated_eof(self):
        self.assertIn('End of file.',self.page(b''))
        text=self.page(bytes.fromhex('EA4C34'))
        self.assertIn('.BYTE $4C',text);self.assertIn('RESULT 3 0',text)
    def test_short_read_and_seek_error(self):
        for data,seekfail in ((b'\xEA',0),(b'\xEA'*100,1)):
            text=self.page(data,size=100,seekfail=seekfail)
            self.assertIn('Read error: incomplete page.',text);self.assertNotIn('End of file.',text)
    def test_large_offset_and_wrapped_address(self):
        text=self.page(bytes(0x10001)+bytes.fromhex('A942'),offset=0x10001,origin=0xFFFF)
        self.assertIn('010001  0000  A9 42',text);self.assertIn('LDA #$42',text)
    def test_export_exact_bytes_across_pages_and_eof(self):
        data=bytes.fromhex('A9428D00C080F9')*100+bytes.fromhex('4C34')
        for cpu in (0,1):
            status,text=self.export(data,offset=2,cpu=cpu,origin=0xFFFF)
            self.assertEqual(status,0);self.assertTrue(text.endswith(b'; END DISASM\r\n'))
            self.assertIn(b'OFFSET $000002',text)
            rebuilt=bytearray();pos=2
            for row in text.decode().splitlines():
                if row.startswith(';'):continue
                self.assertEqual(int(row[:6],16),pos)
                self.assertEqual(int(row[8:12],16),(0xFFFF+pos)&65535)
                raw=bytes.fromhex(row[14:23]);rebuilt+=raw;pos+=len(raw)
            self.assertEqual(rebuilt,data[2:])
            if cpu:self.assertIn(b'.BYTE $4C\r\n',text)
    def test_export_moves_the_bar(self):
        # One sprintf and one write per line: minutes for a big BIN at 1 MHz.
        data=bytes.fromhex('A9428D00C0')*400
        status,text=self.export(data,offset=5)
        self.assertEqual(status,0)
        done=[d for d,t in self.bars]
        self.assertEqual({t for d,t in self.bars},{len(data)-5})
        self.assertEqual(done[0],0);self.assertEqual(done,sorted(done))
        self.assertGreaterEqual(len(done),(len(data)-5)//(19*5))
        self.assertLess(done[-1],len(data)-5)
    def test_export_uses_selected_cpu_and_origin(self):
        for cpu,instruction in ((0,b'.BYTE $80'),(1,b'BRA $4000')):
            status,text=self.export(bytes.fromhex('80FE'),cpu=cpu,origin=0x4000)
            self.assertEqual(status,0);self.assertIn(instruction,text)
    def test_export_failures_leave_partial_without_end_marker(self):
        for kw,expected in (({'readfail':60},2),({'writefail':4},1),({'cancelafter':4},3),({'size':1000},2)):
            with self.subTest(kw=kw):
                status,text=self.export(b'\xEA'*200,**kw)
                self.assertEqual(status,expected);self.assertNotIn(b'END DISASM',text)
                self.assertTrue(text.startswith(b'; DISASM /SOURCE/CODE\r\n'))
    def test_stale_small_size_never_announces_a_complete_export(self):
        for cpu in (0,1):
            for cached in (0,1,57,200):
                for extra in (1,16):
                    for offset in (0,cached):
                        with self.subTest(cpu=cpu,cached=cached,extra=extra,offset=offset):
                            status,text=self.export(b'\xEA'*(cached+extra),cpu=cpu,
                                                    size=cached,offset=offset)
                            self.assertEqual(status,2)
                            self.assertNotIn(b'END DISASM',text)
                            rows=[row for row in text.splitlines() if not row.startswith(b';')]
                            self.assertEqual(len(rows),cached-offset)

    def test_final_source_probe_errors_and_cancel_keep_export_incomplete(self):
        for cpu in (0,1):
            for size in (0,1,57,200):
                data=b'\xEA'*size
                status,healthy=self.export(data,cpu=cpu)
                self.assertEqual(status,0)
                for readfail in (-3,-4,-5):
                    with self.subTest(cpu=cpu,size=size,readfail=readfail):
                        status,text=self.export(data,cpu=cpu,readfail=readfail)
                        self.assertEqual(status,3 if readfail==-5 else 2)
                        self.assertEqual(text,healthy.removesuffix(b'; END DISASM\r\n'))

    def test_source_growth_in_export_interface_preserves_existing_files(self):
        for cpu in (0,1):
            for cached in (0,1,57,200):
                data=b'\xEA'*(cached+1)
                status,healthy=self.export(data[:cached],cpu=cpu)
                self.assertEqual(status,0)
                for collision in (False,True):
                    with self.subTest(cpu=cpu,cached=cached,collision=collision):
                        with tempfile.TemporaryDirectory(prefix='ui-',dir=self.p) as tmp:
                            case=Path(tmp);source=case/'SOURCE';target=case/'OUT.TXT'
                            source.write_bytes(data);(case/'KEEP').write_bytes(b'old')
                            if collision:target.write_bytes(b'previous export')
                            args=[self.exe,str(cpu),'ui-export',source,str(cached),'0','2000',
                                  '-1','0','0',target,'0']
                            run=subprocess.run(args,text=True,capture_output=True,check=True)
                            self.assertEqual(source.read_bytes(),data)
                            self.assertEqual((case/'KEEP').read_bytes(),b'old')
                            self.assertEqual(target.read_bytes(),b'previous export' if collision else
                                             healthy.removesuffix(b'; END DISASM\r\n'))
                            self.assertIn('UI '+('none' if collision else
                                                 'Export incomplete; partial file kept.'),run.stdout)
                            self.assertEqual({p.name for p in case.iterdir()},{'SOURCE','OUT.TXT','KEEP'})

    def test_export_empty_file(self):
        status,text=self.export(b'')
        self.assertEqual(status,0);self.assertTrue(text.endswith(b'; END DISASM\r\n'))

    def test_cancel_on_final_export_write_refuses_success(self):
        for cpu in (0,1):
            for size in (0,1,57,200):
                with self.subTest(cpu=cpu,size=size):
                    data=b'\xEA'*size
                    status,healthy=self.export(data,cpu=cpu)
                    self.assertEqual(status,0)
                    status,text=self.export(data,cpu=cpu,cancelafter=size+3)
                    self.assertEqual(status,3)
                    self.assertEqual(text,healthy)

    def test_export_close_faults_and_collisions_preserve_bytes(self):
        for cpu in (0,1):
            for size in (0,1,57,200):
                data=b'\xEA'*size
                status,healthy=self.export(data,cpu=cpu)
                self.assertEqual(status,0)
                for closefault in (0,1,2,3,4):
                    with self.subTest(cpu=cpu,size=size,closefault=closefault):
                        with tempfile.TemporaryDirectory(prefix='ui-',dir=self.p) as tmp:
                            case=Path(tmp);source=case/'SOURCE';target=case/'OUT.TXT'
                            source.write_bytes(data);(case/'KEEP').write_bytes(b'old')
                            if closefault==4:target.write_bytes(b'previous export')
                            args=[self.exe,str(cpu),'ui-export',source,str(size),'0','2000',
                                  '-1','0','0',target,str(closefault)]
                            run=subprocess.run(args,text=True,capture_output=True,check=True)
                            self.assertEqual(source.read_bytes(),data)
                            self.assertEqual((case/'KEEP').read_bytes(),b'old')
                            self.assertEqual(target.read_bytes(),b'previous export' if closefault==4 else healthy)
                            expected=('none' if closefault==4 else
                                      'Export cancelled; partial file kept.' if closefault>=2 else
                                      'Export incomplete; partial file kept.' if closefault==1 else
                                      'Disassembly exported to other panel.')
                            self.assertIn('UI '+expected,run.stdout)
                            self.assertEqual({p.name for p in case.iterdir()},{'SOURCE','OUT.TXT','KEEP'})
    def test_full_read_count_with_stream_error_is_an_incomplete_page(self):
        text=self.page(b'\xEA'*100,seekfail=2)
        self.assertIn('Read error: incomplete page.',text)
        self.assertIn('RESULT 19 1',text)
        self.assertNotIn('End of file.',text)
    def test_full_io_counts_with_errors_never_complete_export(self):
        for cpu in (0,1):
            for kwargs,status in (({'readfail':-2},2),({'writefail':-2},1),({'writefail':-3},1)):
                with self.subTest(cpu=cpu,kwargs=kwargs):
                    result,text=self.export(b'\xEA'*200,cpu=cpu,**kwargs)
                    self.assertEqual(result,status)
                    self.assertNotIn(b'END DISASM',text)
                    self.assertTrue(text.startswith(b'; DISASM /SOURCE/CODE\r\n'))

if __name__=='__main__': unittest.main()
