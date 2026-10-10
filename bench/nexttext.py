#!/usr/bin/env python3
"""Magic Window/LISA v3 native previews on disposable images, both CPUs."""
import sys,tempfile
from pathlib import Path
from xplug import boot_hd,menu_run,RET,ESC,ok_all
from pom2 import ROOT
sys.path.insert(0,str(ROOT/'tools'))
from test_nexttext import real_files,lisa
from mkdos33 import build
from prodos_read import Image

def main():
    real=list(real_files())
    magic=next(d for r,n,t,a,d in real if n=='PRINTER TEST.MW')
    source=next(d for r,n,t,a,d in real if n=='LISA3.9')
    labels=['S%03d'%i for i in range(512)]
    many=lisa(b''.join(bytes((250+(i>>8),i&255)) for i in range(512))+b'\0',labels)
    specs={'MAGIC.MW':(magic,6,0x9481),'LISA.SRC':(source,250,0x1ffc),'SYMBOLS':(many,250,0x2000)}
    data={'WORK/'+n+'#%02X%04X'%(t,a):d for n,(d,t,a) in specs.items()}
    broken=lisa(b'\xfa\x00\0')
    data['WORK/BADLISA#FA2000']=broken
    dos=build([('TEST.MW',4,b'\x81\x94'+len(magic).to_bytes(2,'little')+magic)])
    data['WORK/MAGIC.DSK#060000']=dos
    with tempfile.TemporaryDirectory(prefix='nexttext-native-') as tmp:
        with boot_hd(Path(tmp),data,port=6941,plugins=['magwin','lisav3']) as (p,s):
            s.key(b'/');s.select('/WORKHD');s.key(RET);s.select('WORK');s.key(RET);p.stable()
            before=p.peek(0x1000,0xb000,'aux');floor=s.sym['__HIMEM__']-s.sym['__STACKSIZE__'];p.poke(floor,b'\xa5'*8)
            for n,expected in (('MAGIC.MW','^NPICA^N'),('LISA.SRC','DETOKEN'),('SYMBOLS','S000:')):
                s.select(n);s.key(RET);s.wait(lambda:s.has(expected),n+' decoded',30);s.ok(n+' automatic',True)
                if n=='SYMBOLS':
                    s.key(b' ');s.wait(lambda:s.has('S021:'),'symbol second page',15);s.ok('Symbols paging',True)
                    for page in range(2,14):
                        s.key(b' ');s.wait(lambda:s.has('S%03d:'%(21*page)),'symbol page',15)
                    s.ok('Second symbol bank',s.has('S273:'))
                s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'reader exit',30);p.stable()
            s.select('BADLISA');s.key(RET);s.wait(lambda:s.has('Malformed LISA v3'),'bad symbol refused',30);s.ok('Bad symbol refused before display',True)
            s.select('MAGIC.DSK');s.key(RET);s.wait(lambda:s.has('TEST.MW'),'DOS image mounted',30)
            s.select('TEST.MW');s.key(RET);s.wait(lambda:s.has('^NPICA^N'),'DOS Magic Window',30);s.ok('DOS Magic automatic',True)
            s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'DOS reader exit',30);p.stable()
            s.ok('AUX preserved',p.peek(0x1000,0xb000,'aux')==before)
            s.ok('Stack floor preserved',p.peek(floor,8)==b'\xa5'*8)
            disk=Image((Path(tmp)/'WORKHD.hdv').read_bytes());e=next(e for e in disk.entries(2) if e[1:5]==b'WORK');key=int.from_bytes(e[17:19],'little')
            actual={e[1:1+(e[0]&15)].decode():disk.read(e) for e in disk.entries(key)}
            s.ok('Source files preserved',all(actual[n]==d for n,(d,_,_) in specs.items()) and actual['MAGIC.DSK']==dos and actual['BADLISA']==broken)
    return ok_all(s,'nexttext')

if __name__=='__main__':raise SystemExit(main())
