#!/usr/bin/env python3
"""DISASM display, CPU selection, navigation, errors and stack under POM2."""
import os
import tempfile
import urllib.request
from pathlib import Path
from pom2 import BUILD, Pom2, Session
from xplug import stage_hd, menu_run, RET, ESC, ok_all


def main():
    code=bytes.fromhex('A9428D00C0D0F980FE6434')+b'\xEA'*160+bytes.fromhex('4C34')
    with tempfile.TemporaryDirectory(prefix='a2fc-disasm-') as tmp:
        hd=stage_hd(Path(tmp),{'WORK/CODE#062000':code,
            'WORK/EMPTY#060000':b'', 'WORK/SYSTEM#FF0000':bytes.fromhex('4C032060'),
            'WORK/LARGE#06FFFF':b'\xEA'*65537+bytes.fromhex('A942'),
            'WORK/NOTE.TXT':b'text'},plugins=['disasm'])
        original=hd.read_bytes()
        with Pom2(hd,port=6848+int(os.environ.get('A2FC_PORT_OFFSET','0'))) as p:
            s=Session(p);s.boot();s.select('WORK');s.key(RET);p.stable()
            stack=p.peek(0x80,2);floor=s.sym['__HIMEM__']-s.sym['__STACKSIZE__'];p.poke(floor,b'\xA5'*8)
            s.select('CODE');menu_run(s,p,'DISASM')
            s.wait(lambda:s.has('DISASM -'),'disassembler');p.stable()
            cpu='6502' if BUILD.name=='build-6502' else '65C02'
            s.ok('CPU defaults to build family',s.has('DISASM - '+cpu+' -'))
            s.ok('BIN load address and operands',s.has('Load $2000') and s.has('LDA #$42') and s.has('STA $C000') and s.has('BNE $2000'),'\n'.join(s.rows()))
            first=s.rows()[2:21]
            s.key(b'N');p.stable();s.ok('next page advances',s.rows()[2:21]!=first)
            s.key(b'P');p.stable();s.ok('previous restores instruction boundaries',s.rows()[2:21]==first)
            s.key(b'N');p.stable();second=s.rows()[2:21]
            s.key(b'N');s.key(b'N');s.key(b'P');s.key(b'P');p.stable()
            s.ok('multiple previous pages remain exact',s.rows()[2:21]==second)
            s.key(b'P');p.stable()
            if cpu=='65C02':s.key(b'C');p.stable()
            s.ok('6502 leaves CMOS opcode as data',s.has('.BYTE $80'))
            s.key(b'C');p.stable();s.ok('CMOS decodes BRA and STZ',s.has('BRA $2007') and s.has('STZ $34'))
            capture=os.environ.get('A2FC_CAPTURE')
            if capture:
                with urllib.request.urlopen(p.base+'/screen.ppm') as response:
                    Path(capture).write_bytes(response.read())
            s.key(b'L');s.wait(lambda:s.has('Load address'),'load');s.type('4000');s.key(RET);p.stable()
            s.ok('load override relocates branches',s.has('Load $4000') and s.has('BNE $4000'))
            s.key(b'G');s.wait(lambda:s.has('File offset'),'offset');s.type(f'{len(code)-2:06X}');s.key(RET);p.stable()
            s.ok('truncated tail is data, clean EOF',s.has('.BYTE $4C') and s.has('.BYTE $34') and s.has('End of file.'))
            tail=s.rows()[2:21];s.key(b'N');p.stable();s.ok('next at EOF stays put',s.rows()[2:21]==tail)
            s.key(b'G');s.wait(lambda:s.has('File offset'),'invalid offset');s.type('FFFFFF');s.key(RET)
            s.wait(lambda:s.has('Offset outside file'),'invalid refused');s.key(RET);p.stable()
            s.ok('invalid offset keeps page',s.rows()[2:21]==tail)
            s.key(b'R');p.stable();s.ok('restart returns to byte zero',s.has('000000  4000'))
            s.key(ESC);p.stable()
            s.select('EMPTY');menu_run(s,p,'DISASM');s.ok('empty BIN reports EOF',s.has('End of file.'));s.key(ESC);p.stable()
            s.select('SYSTEM');menu_run(s,p,'DISASM');s.ok('SYS starts at 2000',s.has('Load $2000') and s.has('JMP $2003'));s.key(ESC);p.stable()
            s.select('LARGE');menu_run(s,p,'DISASM');s.key(b'G');s.wait(lambda:s.has('File offset'),'large offset')
            s.type('010001');s.key(RET);p.stable()
            s.ok('24-bit offset and 16-bit address wrap',s.has('010001  0000') and s.has('LDA #$42'));s.key(ESC);p.stable()
            s.select('NOTE');menu_run(s,p,'DISASM');s.ok('non-code selection refused',s.has('Select a BIN or SYS'))
            s.ok('stack restored and budget respected',p.peek(0x80,2)==stack and p.peek(floor,8)==b'\xA5'*8)
        s.ok('source volume unchanged',hd.read_bytes()==original)
        return ok_all(s,'disasm')

if __name__=='__main__':raise SystemExit(main())
