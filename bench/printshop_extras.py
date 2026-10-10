#!/usr/bin/env python3
"""Read-only Print Shop BIN border/font previews, ProDOS and DOS, both CPUs."""
import os
import sys
import tempfile
from pathlib import Path
from xplug import boot_hd,menu_run,RET,ESC,ok_all
from pom2 import ROOT
sys.path.insert(0,str(ROOT/'tools'))
from corpus_read import files
from prodos_read import Image
from mkdos33 import build


def main():
    root=Path(os.environ.get('A2FC_PRINTSHOP_CORPUS','/tmp/a2fc-printshop-corpus'))/'images/productivity/graphics/printshop'
    _,bs=files((root/"Gordon's Print Shop Borders (Big Red Computer Club) (Side 1).dsk").read_bytes())
    _,fs=files((root/'Print Shop Compatible Fonts - Volume H89 (Big Red Computer Club) (Side 1).dsk').read_bytes())
    border=next(d for n,t,a,d in bs if n=='BORD.BRACKET.1')
    font=next(d for n,t,a,d in fs if n=='FONT.ALONDON')
    _,nb=files((root/"Gordon's Print Shop Borders (Big Red Computer Club) (Side 2).dsk").read_bytes())
    _,nf=files((root/'Print Shop Compatible Fonts - Volume H89 (Big Red Computer Club) (Side 2).dsk').read_bytes())
    border5=next(d for n,t,a,d in nb if n.rsplit('/',1)[-1]=='BORD.BRACKET.1')
    font5=next(d for n,t,a,d in nf if n.rsplit('/',1)[-1]=='FONT.ALONDON')
    specs={'BORD.BRACKET':border,'FONT.LONDON':font,'BORD.NEW':border5,'FONT.NEW':font5}
    data={'WORK/BORD.BRACKET#067800':border,'WORK/FONT.LONDON#065FF4':font,
          'WORK/BORD.NEW#F52000':border5,'WORK/FONT.NEW#F51000':font5,
          'WORK/PS.DSK#060000':build([('BORD.BRACKET',4,(0x7800).to_bytes(2,'little')+len(border).to_bytes(2,'little')+border),('FONT.LONDON',4,(0x5ff4).to_bytes(2,'little')+len(font).to_bytes(2,'little')+font)])}
    broken=bytearray(font);broken[12+177+58]=255;data['WORK/BADFONT#065FF4']=bytes(broken)
    with tempfile.TemporaryDirectory(prefix='ps-extra-native-') as tmp:
        tmp=Path(tmp)
        with boot_hd(tmp,data,port=6939,plugins=['psborder','psfont']) as (p,s):
            s.key(b'/');s.select('/WORKHD');s.key(RET);s.select('WORK');s.key(RET);p.stable()
            hd_before=Path(p.hdv).read_bytes();before=p.peek(0x1000,0xb000,'aux');floor=s.sym['__HIMEM__']-s.sym['__STACKSIZE__'];p.poke(floor,b'\xa5'*8)
            for dos in (False,True):
                if dos:s.select('PS.DSK');s.key(RET);s.wait(lambda:s.has('FONT.LONDON'),'DOS mounted',30)
                for name,label in (('BORD.BRACKET','Print Shop border'),('FONT.LONDON','Print Shop font')):
                    s.select(name);s.key(RET);s.wait(lambda:s.has(label),name+' automatic display',30);s.ok(name+(' DOS' if dos else ' ProDOS'),True)
                    if name=='FONT.LONDON':
                        s.key(b'\x15');s.wait(lambda:s.has('$22'),'next glyph',10)
                        for _ in range(20):s.key(b'\x0a',pause=0.04)
                        s.ok('Font vertical scrolling',s.has('rows') and not s.has('error'))
                    s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'reader exit',30);p.stable()
                if not dos:
                    for name,label in (('BORD.NEW','Print Shop border'),('FONT.NEW','Print Shop font')):
                        s.select(name);s.key(RET);s.wait(lambda:s.has(label),name+' F5 automatic display',30);s.ok(name+' F5',True)
                        if name=='FONT.NEW':
                            code=33
                            for _ in range(63):
                                code+=1
                                if code==64:code+=1
                                s.key(b'\x15');s.wait(lambda:s.has('$%02X'%code),'F5 glyph navigation',15)
                            s.ok('F5 lowercase navigation',s.has('$61') and not s.has('error'))
                        s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'F5 exit',30);p.stable()
                    s.select('BADFONT');menu_run(s,p,'PSFONT');s.wait(lambda:s.has('Malformed/unsupported'),'bad pointer refused',30);s.ok('Bad font refused',True)
            s.ok('AUX preserved',p.peek(0x1000,0xb000,'aux')==before)
            s.ok('Stack floor preserved',p.peek(floor,8)==b'\xa5'*8)
            p.sync_disks();s.ok('Whole source volume preserved',Path(p.hdv).read_bytes()==hd_before)
            disk=Image((tmp/'WORKHD.hdv').read_bytes());e=next(e for e in disk.entries(2) if e[1:5]==b'WORK');key=int.from_bytes(e[17:19],'little')
            actual={e[1:1+(e[0]&15)].decode():disk.read(e) for e in disk.entries(key)}
            s.ok('Sources preserved',all(actual[n]==d for n,d in specs.items()))
    return ok_all(s,'printshop_extras')

if __name__=='__main__':raise SystemExit(main())
