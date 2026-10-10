#!/usr/bin/env python3
"""LISA 8/16 native readers, automatic routing, errors and complete preservation."""
import sys,tempfile
from pathlib import Path
from xplug import boot_hd,menu_run,RET,ESC,ok_all
from pom2 import ROOT
sys.path.insert(0,str(ROOT/'tools'))
from test_lisa4 import real_lisa4,lisa4,big

def main():
    originals={n:(d,250,a) for n,a,d in real_lisa4()}
    if len(originals)!=2:raise RuntimeError('Two public LISA v4/v5 sources required')
    labels=['S%03d'%i for i in range(400)]
    many=lisa4(b''.join(b'\xfa'+i.to_bytes(2,'little') for i in range(400))+b'\0',labels)
    nums=lisa4(big(b'\x43\x33\0\xff\xff\xff\xff')+big(b'\x43\x35\x56\x34\x12')+b'\0')
    broken=lisa4(b'\xfa\xff\xff\0')
    specs={**originals,'SYMBOLS':(many,250,0x50e1),'NUMBERS':(nums,250,0x4000),'BADLISA':(broken,250,0x50e1)}
    data={'WORK/'+n+'#%02X%04X'%(t,a):d for n,(d,t,a) in specs.items()}
    with tempfile.TemporaryDirectory(prefix='lisa4-native-') as tmp:
        with boot_hd(Path(tmp),data,port=6944,plugins=['lisav4']) as (p,s):
            s.key(b'/');s.select('/WORKHD');s.key(RET);s.select('WORK');s.key(RET);p.stable()
            original=Path(p.hdv).read_bytes();aux=p.peek(0x1000,0xb000,'aux');floor=s.sym['__HIMEM__']-s.sym['__STACKSIZE__'];p.poke(floor,b'\xa5'*8)
            for n,label in (('DETOKEN.A','"detokenizer"'),('MNEMONICS.A','tables for token/detoken'),('SYMBOLS','S000'),('NUMBERS','4294967295')):
                s.select(n);s.key(RET);s.wait(lambda:s.has(label),n+' automatic',30);p.stable();s.ok(n+' automatic',True)
                if n in originals:
                    expected='sbt      "detokenizer"' if n=='DETOKEN.A' else 'sbt     "mnemonics"'
                    s.ok(n+' decoded first line',s.rows()[1].strip()==expected)
                if n=='SYMBOLS':
                    for page in range(1,14):
                        s.key(b' ');s.wait(lambda:s.has('S%03d'%(21*page)),'symbols page',15)
                    s.ok('16-bit symbol reference',s.has('S273'))
                if n=='NUMBERS':s.ok('24-bit hexadecimal number',s.has('$123456'))
                s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'reader exit',30);p.stable()
            s.select('BADLISA');s.key(RET);s.wait(lambda:s.has('Malformed LISA v4/v5'),'bad symbol refused',30);s.ok('Bad symbol refused',True)
            s.select('NUMBERS');menu_run(s,p,'LISAV4');s.wait(lambda:s.has('4294967295'),'manual invocation',30);s.ok('Manual reader',True)
            s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'manual exit',30);p.stable()
            s.ok('AUX preserved',p.peek(0x1000,0xb000,'aux')==aux)
            s.ok('Stack floor preserved',p.peek(floor,8)==b'\xa5'*8)
            p.sync_disks();s.ok('Whole source volume preserved',Path(p.hdv).read_bytes()==original)
    return ok_all(s,'lisa4')

if __name__=='__main__':raise SystemExit(main())
