"""Decode with the actual overlay; assemble the output with ca65 as an oracle."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_six_plugins import PREFIX, ROOT

HARNESS = PREFIX + r'''
#include "src/plugins/disasm.c"
static int seekfail;
static int seek_(FILE* f,long o,int w) { return seekfail ? -1 : fseek(f,o,w); }
static void clear_(void) {}
static void xy_(unsigned char x,unsigned char y) {}
int main(int argc,char** argv) {
    unsigned char data[512],n,i;
    struct Entry entry;
    a.sprintf=sprintf;a.strcpy=strcpy;a.strlen=strlen;
    cpu=atoi(argv[1]);
    if(!strcmp(argv[2],"page")) {
        a.clrscr=clear_;a.cprintf=printf;a.cputs=(void(*)(const char*))puts;a.gotoxy=xy_;
        a.fseek=seek_;a.fread=fread;a.selected=&entry;strcpy(entry.name,"TEST");buf=data;
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
        cls.tmp=tempfile.TemporaryDirectory(prefix='disasm-');cls.p=Path(cls.tmp.name)
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

if __name__=='__main__': unittest.main()
