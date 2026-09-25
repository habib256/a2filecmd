#!/usr/bin/env python3
"""C from ProDOS to a real Disk II DOS 3.3 disk, using disposable media only."""
import os
import shutil
import sys
import tempfile
from pathlib import Path
from pom2 import Pom2,Session,ROOT,BUILD
from xplug import ok_all
sys.path.insert(0,str(ROOT/'tools'))
from mini33_fixture import make_disk,read_files
from prodos_read import Image

def main():
 with tempfile.TemporaryDirectory(prefix='doswrite-ui-') as d:
  d=Path(d);hd=d/'test.hdv';target=d/'dos.dsk'
  cpu='6502' if BUILD.name=='build-6502' else '65C02'
  original=(BUILD/'A2FILECMD-XL.hdv').read_bytes()
  hd.write_bytes(original)
  im=Image(original);vol=im.header()['name']
  def find(path):   # DEMO is sorted by kind (tools/stage_demo.py)
   key=2
   for part in path.split('/'):
    e=next(e for e in im.entries(key) if e[1:1+(e[0]&15)].decode()==part);key=int.from_bytes(e[17:19],'little')
   return e
  hello=find('DEMO/PROGRAMS/HELLO');payload=im.read(hello)
  before=make_disk([('KEEP',0x80,b'old text\r'*50)])
  target.write_bytes(before)
  dos_slot=os.environ.get('A2FC_DOS_SLOT','6')
  with Pom2(hd,floppy2=target,port=6896,exe=os.environ.get('POM2','/tmp/a2fc-dos-host')) as p:
   s=Session(p);s.boot()
   guard_start=s.sym['__ONCE_RUN__'];guard_end=s.sym['__HIMEM__']-s.sym['__STACKSIZE__']
   guard=bytes([0xEE])*(guard_end-guard_start);p.poke(guard_start,guard)
   def into(*names):
    for name in names:s.select(name);s.key(b'\r');p.stable()
   into('DEMO','PROGRAMS');s.select('HELLO')
   s.key(b'\t');s.key(b'/');p.stable()
   for _ in range(15):
    if 'DOS 3.3 disk' in s.line(41):break
    s.key(b'\x0a')
   s.key(b'\r');s.wait(lambda:s.has('KEEP') and '/DOS 3.3' in s.rows()[0],'initial DOS catalog');p.stable()
   # Returning to volumes must clear DOS mode; catalog entries must never
   # be rendered as volume names, and the DOS disk must reopen repeatedly.
   for _ in range(3):
    s.key(b'/');s.wait(lambda:s.has('[Volumes]'),'return to volumes');p.stable()
    s.ok('DOS -> volumes keeps physical DOS classification',s.has('DOS 3.3 disk'),'\n'.join(s.rows()) if not s.has('DOS 3.3 disk') else '')
    for _ in range(15):
     if 'DOS 3.3 disk' in s.line(41):break
     s.key(b'\x0a')
    s.key(b'\r');s.wait(lambda:s.has('KEEP') and '/DOS 3.3' in s.rows()[0],'reopen DOS catalog');p.stable()
    s.ok('DOS disk reopens after volume refresh',s.has('KEEP'))
   s.key(b'\t');s.key(b'C')
   s.wait(lambda:s.has('Copy HELLO to DOS 3.3 S'+dos_slot+',D2?'),'DOS copy confirmation',60)
   s.ok('No write before confirmation',target.read_bytes()==before)
   s.key(b'N');p.stable()
   s.ok('Refusal preserves DOS disk',target.read_bytes()==before)
   s.key(b'C');s.wait(lambda:s.has('Copy HELLO to DOS 3.3 S'+dos_slot+',D2?'),'second confirmation',60)
   aux=p.peek(0x1000,0xB000,'aux')
   s.key(b'Y');s.wait(lambda:s.has('Copied to DOS 3.3; source kept.'),'verified physical copy',120)
   s.ok('AUX RAM disk storage preserved',aux==p.peek(0x1000,0xB000,'aux'))
   s.key(b'C');s.wait(lambda:s.has('Copy refused:'),'collision refused',60)
   for path,name in ((('..','PICTURES'),'HGR.RLE'),(('..',),'README')):
    into(*path);s.select(name);s.key(b'C')
    s.wait(lambda:s.has('Copy '+name+' to DOS 3.3 S'+dos_slot+',D2?'),'copy '+name,60)
    s.key(b'Y');s.wait(lambda:s.has('Copied to DOS 3.3; source kept.'),'verified '+name,120)
   into('PICTURES','ALBUM');s.select('TIGER')
   s.key(b'C');s.wait(lambda:s.has('Copy TIGER to DOS 3.3 S'+dos_slot+',D2?'),'TIGER confirmation',60)
   s.key(b'Y');s.wait(lambda:s.has('Copied to DOS 3.3; source kept.'),'verified TIGER copy',120)
   into('..','..','DOCUMENTS')
   p.eject(1)
   saved=target.read_bytes();target.chmod(0o444);p.insert(1,str(target))
   s.select('SAMPLE');s.key(b'C')
   s.wait(lambda:s.has('DOS 3.3 disk is write-protected.'),'physical write protection',60)
   p.eject(1)
   s.ok('Write-protected disk preserved',target.read_bytes()==saved)
   target.chmod(0o644)
   s.ok('192-byte C stack guard preserved',p.peek(guard_start,len(guard))==guard)
  result=read_files(target.read_bytes())
  s.ok('Existing DOS file preserved',result['KEEP']==read_files(before)['KEEP'])
  expected=len(payload).to_bytes(2,'little')+payload
  s.ok('Applesoft program and DOS length prefix exact',result['HELLO']['type']==2 and result['HELLO']['data']==expected+bytes((-len(expected))%256))
  for name,kind in (('HGR.RLE',4),('README',0)):
   e=find({'HGR.RLE':'DEMO/PICTURES/HGR.RLE','README':'DEMO/README'}[name])
   expected=im.read(e)
   if kind==4:expected=e[31:33]+len(expected).to_bytes(2,'little')+expected
   s.ok(name+' has exact DOS type, prefix and payload',result[name]['type']==kind and result[name]['data']==expected+bytes((-len(expected))%256))
  tiger=find('DEMO/PICTURES/ALBUM/TIGER')
  payload=im.read(tiger);expected=tiger[31:33]+len(payload).to_bytes(2,'little')+payload
  s.ok('Screenshot case: TIGER BIN $2000, 8192 bytes exact',len(payload)==8192 and result['TIGER']['data']==expected+bytes((-len(expected))%256))
  s.ok('Source volume preserved',hd.read_bytes()==original)
  return ok_all(s,'DOSWRITE C to physical DOS disk')
if __name__=='__main__':sys.exit(main())
