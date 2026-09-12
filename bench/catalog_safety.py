#!/usr/bin/env python3
"""Reject malformed ProDOS/DOS catalog chains, on disposable images only."""
import tempfile,sys
from pathlib import Path
from xplug import boot_hd,RET,ESC,ok_all,ROOT
sys.path.insert(0,str(ROOT/'tools'))
import mkdos33

def main():
 # One valid ProDOS header, followed by an empty self-linked block.
 po=bytearray(64*512);po[2*512+2]=3;po[2*512+4]=0xF4;po[1029:1033]=b'TEST'
 po[1024+35:1024+37]=bytes([39,13]);po[1536]=2;po[1538]=3
 dos=bytearray(mkdos33.build([]));c=mkdos33.off(17,15)
 dos[c+1:c+3]=bytes([17,15])
 for i in range(7):dos[c+11+i*35]=255
 bad_sector=bytearray(dos);bad_sector[c+2]=255
 files={'WORK/CYCLE.PO':bytes(po),'WORK/CYCLE.DSK':bytes(dos),'WORK/BADSEC.DSK':bytes(bad_sector),'WORK/KEEP#040000':b'preserve this file\r'}
 with tempfile.TemporaryDirectory(prefix='catalog-native-') as t:
  with boot_hd(Path(t),files,port=6903) as(p,s):
   original=Path(p.hdv).read_bytes()
   s.key(b'/');s.select('/WORKHD');s.key(RET);s.select('WORK');s.key(RET);p.stable()
   aux=p.peek(0x1000,0xB000,'aux')
   for name in ['CYCLE.PO','CYCLE.DSK','BADSEC.DSK']:
    s.select(name);s.key(RET)
    s.wait(lambda:s.has('Not a ProDOS disk image'),name+' refused',60);p.stable()
    s.ok(name+' rejected and selection restored',s.line().startswith(name+' '))
   s.ok('catalog inspection preserves AUX',p.peek(0x1000,0xB000,'aux')==aux)
  s.ok('catalog inspection preserves all disk bytes',Path(p.hdv).read_bytes()==original)
 return ok_all(s,'catalog safety')
if __name__=='__main__':raise SystemExit(main())
