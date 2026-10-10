#!/usr/bin/env python3
"""MAIN-only word processors: real documents, paging, IDENT and both CPUs.
Uses only disposable images. Sources and AUX above text pages must survive.
"""
import os
import sys
import tempfile
from pathlib import Path
from xplug import boot_hd, menu_run, RET, ESC, ok_all
from pom2 import ROOT
sys.path.insert(0,str(ROOT/'tools'))
from prodos_read import Image


def main():
    corpus=Path(os.environ.get('A2FC_WORDPRO_CORPUS','/tmp/a2fc-wordpro-corpus'))/'extracted'
    samples={
        'OLDMS':('MULTISCR',(corpus/'Multiscribe disk 2__PHOENIX').read_bytes(),'THE LEGEND OF THE PHOENIX',4),
        'NEWMS':('MULTISCR',(corpus/'MultiScribe Data Disk__FONT.SAMPLES').read_bytes(),'These are the type-fonts',11),
        'WRITER':('APPLEWR',b'.lm2\r.rm30\r.pm+3\rApple Writer first paragraph\r'*24,'Apple Writer first',4),
        'REALAW':('APPLEWR',(corpus/'APPLE_WRITER_DOS33__ENCOMIUM1').read_bytes(),'What makes Apple Writer',4),
    }
    files={'WORK/'+name+'#%02X0000'%typ:data for name,(_,data,_,typ) in samples.items()}
    files['WORK/BADMS#040000']=samples['OLDMS'][1][:40]
    files['WORK/WRITER.DSK#060000']=__import__('mkdos33').build([('LETTER',0,bytes(c|128 for c in b'.lm2\r.rm30\rHello DOS Writer\r')+b'\0')])
    with tempfile.TemporaryDirectory(prefix='worddocs-native-') as tmp:
        with boot_hd(Path(tmp),files,port=6921,plugins=['multiscr','applewr']) as (p,s):
            s.key(b'/');s.select('/WORKHD');s.key(RET);s.select('WORK');s.key(RET);p.stable()
            before=p.peek(0x1000,0xb000,'aux');floor=s.sym['__HIMEM__']-s.sym['__STACKSIZE__'];p.poke(floor,b'\xa5'*8)
            for name,(plugin,_,expected,_) in samples.items():
                s.select(name);s.key(RET)
                s.wait(lambda:s.has(expected),name+' automatic display',30);s.ok(name+' decoded automatically',True)
                if name=='WRITER':s.key(b' ');s.wait(lambda:s.has(expected),'Writer second page',10);s.ok('Writer paging',True)
                s.key(ESC);s.wait(lambda:s.has('Type  Aux'),name+' exit',30);p.stable()
            s.select('BADMS');menu_run(s,p,'MULTISCR');s.wait(lambda:s.has('Malformed MultiScribe'),'bad style rejected',30);s.ok('Malformed rejected',True)
            s.select('WRITER.DSK');s.key(RET);s.wait(lambda:s.has('LETTER'),'DOS image mounted',30)
            s.select('LETTER');s.key(RET);s.wait(lambda:s.has('Hello DOS Writer'),'DOS Writer decoded',30);s.ok('DOS Writer automatic',True)
            s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'DOS Writer exit',30);p.stable()
            s.ok('AUX preserved',p.peek(0x1000,0xb000,'aux')==before)
            s.ok('Stack floor preserved',p.peek(floor,8)==b'\xa5'*8)
            disk=Image((Path(tmp)/'WORKHD.hdv').read_bytes())
            directory=next(e for e in disk.entries(2) if e[1:5]==b'WORK');key=int.from_bytes(directory[17:19],'little')
            actual={e[1:1+(e[0]&15)].decode():disk.read(e) for e in disk.entries(key)}
            s.ok('All sources preserved',all(actual[n]==data for n,(_,data,_,_) in samples.items()))
    return ok_all(s,'worddocs')


if __name__=='__main__':raise SystemExit(main())
