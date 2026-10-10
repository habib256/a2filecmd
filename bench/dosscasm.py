#!/usr/bin/env python3
"""Native direct S-C Assembler listing on disposable read-only DOS media."""
import re
import sys
import tempfile
from pathlib import Path
from xplug import boot_hd,menu_run,RET,ESC,ok_all
from pom2 import ROOT
sys.path.insert(0,str(ROOT/'tools'))
from mini33_fixture import make_disk
from test_dosscasm import program


def main():
    data=program(70);bad=bytes((5,10,0,0xc1,0))
    raw=make_disk([('SCRIPT',0x81,len(data).to_bytes(2,'little')+data),
                   ('BAD',1,len(bad).to_bytes(2,'little')+bad)])
    head=bytearray(64);head[:4]=b'2IMG';head[24:28]=(64).to_bytes(4,'little');head[28:32]=len(raw).to_bytes(4,'little')
    files={'WORK/DIRECT.DSK#060000':raw,'WORK/DIRECT.2MG#060000':bytes(head)+raw}
    with tempfile.TemporaryDirectory(prefix='dosscasm-native-') as tmp:
        tmp=Path(tmp);floppy=tmp/'SOURCE.DSK';floppy.write_bytes(raw);floppy.chmod(0o444)
        with boot_hd(tmp,files,port=6970,plugins=['scasm'],floppy2=floppy) as (p,s):
            hd=Path(p.hdv);before=hd.read_bytes()
            s.key(b'/');s.select('/WORKHD');s.key(RET);s.select('WORK');s.key(RET);p.stable()
            aux=p.peek(0x1000,0xb000,'aux');floor=s.sym['__HIMEM__']-s.sym['__STACKSIZE__'];p.poke(floor,b'\xa5'*8)
            s.key(b'\t');s.key(b'/');p.stable()
            for _ in range(15):
                if 'DOS 3.3 disk' in s.line(41):break
                s.key(b'\x0a')
            s.key(RET);s.wait(lambda:s.has('SCRIPT') and '/DOS 3.3' in s.rows()[0],'real DOS catalog',60)
            for backend in ('Disk II','DSK','2IMG'):
                panel=40 if backend=='Disk II' else 0
                s.select('SCRIPT',panel);menu_run(s,p,'SCASM')
                s.wait(lambda:s.rows()[1].startswith('0010') and s.has('Space/Down'),'S-C first page',30)
                s.ok(backend+': first page decoded',s.rows()[1].startswith('0010          LDA   #1'))
                s.key(b' ');s.wait(lambda:s.rows()[1].startswith('0220'),'second page',20)
                s.ok(backend+': next page at record boundary',s.rows()[1].startswith('0220          LDA'))
                s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'cancel to panels',30)
                s.ok(backend+': escape cancels listing',s.has('Type  Aux'))
                s.select('SCRIPT',panel);menu_run(s,p,'SCASM')
                s.wait(lambda:s.rows()[1].startswith('0010') and s.has('Space/Down'),'reopen source',30)
                for line in ('0220','0430','0640'):
                    s.key(b' ');s.wait(lambda:s.rows()[1].startswith(line),'next source page',20)
                s.wait(lambda:s.has('End - press'),'complete listing',20)
                s.ok(backend+': end after complete source',s.has('0700') and s.has('End - press'))
                s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'panels after listing',30);p.stable()
                s.select('BAD',panel);menu_run(s,p,'SCASM')
                s.wait(lambda:s.has('Malformed S-C Assembler'),'bad source refused before display',30)
                s.ok(backend+': malformed source refused',s.has('Malformed S-C Assembler'))
                s.ok(backend+': AUX storage unchanged',p.peek(0x1000,0xb000,'aux')==aux)
                if backend=='Disk II':
                    p.eject(1);s.ok('physical DOS source unchanged',floppy.read_bytes()==raw)
                    s.key(b'\t');s.select('DIRECT.DSK');s.key(RET)
                elif backend=='DSK':
                    s.key(ESC);s.wait(lambda:s.has('DIRECT.2MG'),'leave DOS image',30)
                    s.select('DIRECT.2MG');s.key(RET)
                if backend!='2IMG':s.wait(lambda:s.has('SCRIPT') and s.has('BAD'),'DOS image catalog',30);p.stable()
            s.ok('C-stack floor unchanged',p.peek(floor,8)==b'\xa5'*8);p.sync_disks()
        s.ok('complete ProDOS volume unchanged',hd.read_bytes()==before)
        s.ok('DOS source unchanged after shutdown',floppy.read_bytes()==raw)
    return ok_all(s,'direct DOS S-C Assembler')


if __name__=='__main__':raise SystemExit(main())
