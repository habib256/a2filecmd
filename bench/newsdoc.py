#!/usr/bin/env python3
"""Automatic Newsroom readers on protected Disk II and DOS image sources."""
import random,sys,tempfile
from pathlib import Path
from xplug import boot_hd,menu_run,RET,ESC,ok_all
from pom2 import ROOT
sys.path.insert(0,str(ROOT/'tools'))
from mini33_fixture import make_disk
from test_newsdoc import panel,page
from newsroom_ref import make,page as picture_page

def main():
 pn=panel(b'RECOVERED NEWSROOM TEXT\rSecond line\x7f');pg=page();ph=make(random.Random(77),35,80,history=b'\xff'*40)
 entries=[('PN.PANEL',4,b'\0@'+len(pn).to_bytes(2,'little')+pn),('PG.PAGE',4,b'\xa5\x98'+len(pg).to_bytes(2,'little')+pg),('PH.PHOTO',4,b'\0@'+len(ph).to_bytes(2,'little')+ph)]
 raw=make_disk(entries);head=bytearray(64);head[:4]=b'2IMG';head[24:28]=(64).to_bytes(4,'little');head[28:32]=len(raw).to_bytes(4,'little')
 files={'WORK/DIRECT.DSK#060000':raw,'WORK/DIRECT.2MG#060000':bytes(head)+raw,'WORK/PN.PANEL#064000':pn,'WORK/PG.PAGE#0698A5':pg}
 with tempfile.TemporaryDirectory(prefix='news-native-') as tmp:
  tmp=Path(tmp);floppy=tmp/'SOURCE.DSK';floppy.write_bytes(raw);floppy.chmod(0o444)
  with boot_hd(tmp,files,port=6980,plugins=['newspan','newspage','dosnews','dosview'],floppy2=floppy) as (p,s):
   hd=Path(p.hdv);before=hd.read_bytes()
   s.key(b'/');s.select('/WORKHD');s.key(RET);s.select('WORK');s.key(RET);p.stable()
   aux=p.peek(0x1000,0xb000,'aux');floor=s.sym['__HIMEM__']-s.sym['__STACKSIZE__'];p.poke(floor,b'\xa5'*8)
   for name,expected in (('PN.PANEL','RECOVERED NEWSROOM TEXT'),('PG.PAGE','BN.BANNER')):
    s.select(name);s.key(RET);s.wait(lambda:s.has(expected) and s.has('End - press'),'ProDOS automatic '+name,30)
    s.ok('ProDOS: automatic '+name,s.has(expected));s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'ProDOS panels',30)
   s.key(b'\t');s.key(b'/');p.stable()
   for _ in range(15):
    if 'DOS 3.3 disk' in s.line(41):break
    s.key(b'\x0a')
   s.key(RET);s.wait(lambda:s.has('PN.PANEL') and '/DOS 3.3' in s.rows()[0],'DOS catalog',60)
   for backend in ('Disk II','DSK','2IMG'):
    column=40 if backend=='Disk II' else 0
    for name,expected in (('PN.PANEL','RECOVERED NEWSROOM TEXT'),('PG.PAGE','BN.BANNER')):
     s.select(name,column);menu_run(s,p,'IDENT');s.wait(lambda:s.has('Newsroom '),'IDENT description',30)
     s.ok(backend+': IDENT '+name,s.has('Newsroom text panel' if name.startswith('PN') else 'Newsroom page layout'))
     for key in (RET,b'I'):
      s.select(name,column);s.key(key);s.wait(lambda:s.has(expected) and s.has('End - press'),'automatic '+name,30)
      s.ok(backend+': '+repr(key)+' decodes '+name,s.has(expected));s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'panels',30)
    for key in (RET,b'I'):
     s.select('PH.PHOTO',column);s.key(key);s.wait(lambda:p.peek(0x2000,8192)==picture_page(ph),'Newsroom bitmap',30)
     s.ok(backend+': photo all pixels exact',p.peek(0x2000,8192)==picture_page(ph));s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'photo panels',30)
    s.ok(backend+': AUX unchanged',p.peek(0x1000,0xb000,'aux')==aux)
    if backend=='Disk II':p.eject(1);s.key(b'\t');s.select('DIRECT.DSK');s.key(RET)
    elif backend=='DSK':s.key(ESC);s.wait(lambda:s.has('DIRECT.2MG'),'image parent',30);s.select('DIRECT.2MG');s.key(RET)
    if backend!='2IMG':s.wait(lambda:s.has('PN.PANEL'),'next DOS source',30);p.stable()
   s.ok('stack floor unchanged',p.peek(floor,8)==b'\xa5'*8);p.sync_disks()
  s.ok('ProDOS volume unchanged',hd.read_bytes()==before);s.ok('DOS source unchanged',floppy.read_bytes()==raw)
 return ok_all(s,'automatic Newsroom readers')
if __name__=='__main__':raise SystemExit(main())
