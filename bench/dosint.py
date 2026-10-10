#!/usr/bin/env python3
"""Native direct Integer BASIC listing on disposable read-only DOS media."""
import re
import sys
import tempfile
from pathlib import Path
from xplug import boot_hd,menu_run,RET,ESC,ok_all
from pom2 import ROOT
sys.path.insert(0,str(ROOT/'tools'))
from mini33_fixture import make_disk
from test_dosint import program


def main():
    data=program(70);bad=bytes((5,10,0,0x61,0))
    raw=make_disk([('SCRIPT',0x81,len(data).to_bytes(2,'little')+data),
                   ('BAD',1,len(bad).to_bytes(2,'little')+bad)])
    head=bytearray(64);head[:4]=b'2IMG';head[24:28]=(64).to_bytes(4,'little');head[28:32]=len(raw).to_bytes(4,'little')
    files={'WORK/DIRECT.DSK#060000':raw,'WORK/DIRECT.2MG#060000':bytes(head)+raw}
    with tempfile.TemporaryDirectory(prefix='dosint-native-') as tmp:
        tmp=Path(tmp);floppy=tmp/'SOURCE.DSK';floppy.write_bytes(raw);floppy.chmod(0o444)
        with boot_hd(tmp,files,port=6950,plugins=['dosint'],floppy2=floppy) as (p,s):
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
                s.select('SCRIPT',panel);menu_run(s,p,'DOSINT')
                s.wait(lambda:s.rows()[0].startswith('10 PRINT') and 'page 1' in s.rows()[22],'Integer BASIC first page',30)
                s.ok(backend+': first page detokenized',s.rows()[0].startswith('10 PRINT "LINE 1 123"'))
                s.key(b' ');s.wait(lambda:'page 2' in s.rows()[22],'second page',20)
                s.ok(backend+': next page at line boundary',s.rows()[0].startswith('230 PRINT'))
                s.key(b'B');s.wait(lambda:'page 1' in s.rows()[22],'previous page',20)
                s.ok(backend+': previous page restores listing',s.rows()[0].startswith('10 PRINT'))
                s.key(b' ');s.key(b'R');s.wait(lambda:'page 1' in s.rows()[22],'restart listing',20)
                s.ok(backend+': restart',s.rows()[0].startswith('10 PRINT'))
                s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'panels after BASIC',30);p.stable()
                s.select('BAD',panel);menu_run(s,p,'DOSINT')
                s.wait(lambda:s.has('(malformed)'),'bad line status',20)
                s.key(ESC);s.wait(lambda:s.has('Program ends in the middle'),'bad line reported',30)
                s.ok(backend+': malformed line refused',s.has('Program ends in the middle'))
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
    return ok_all(s,'direct DOS Integer BASIC')


if __name__=='__main__':raise SystemExit(main())
