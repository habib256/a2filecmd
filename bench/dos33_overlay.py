#!/usr/bin/env python3
"""A DOS 3.3 catalog read from under running overlay code (HELP, the sort
hosted by TEXT) is deferred and settled: the catalog is back on screen and
the image is untouched. Disposable images only."""
import tempfile,sys
from pathlib import Path
from xplug import boot_hd,RET,ESC,ok_all,ROOT
sys.path.insert(0,str(ROOT/'tools'))
import mkdos33

def main():
 dos=mkdos33.build([('HELLO',2,b'\x00'*300),('NOTES',0,b'A NOTE\r'+b'\x00'*100),('PICTURE',4,b'\x00\x20\x00\x08'+b'\x55'*2048)])
 files={'WORK/DEMO.DSK':bytes(dos),'WORK/KEEP#040000':b'preserve this file\r'}
 with tempfile.TemporaryDirectory(prefix='dos33-overlay-') as t:
  with boot_hd(Path(t),files,port=6907) as(p,s):
   original=Path(p.hdv).read_bytes()
   s.key(b'/');s.select('/WORKHD');s.key(RET);s.select('WORK');s.key(RET);p.stable()
   s.select('DEMO.DSK');s.key(RET)
   catalog=lambda:s.has('HELLO') and s.has('NOTES') and s.has('PICTURE')
   s.wait(catalog,'the DOS 3.3 catalog is read through DOS33.PLG',60);p.stable()
   s.ok('the image path shows as the panel',s.has('DEMO.DSK'))
   # HELP rereads both panels from inside its overlay: the DOS read waits.
   s.key(b'?');s.wait(lambda:not s.has('NOTES'),'the help page covers the panels',30)
   s.key(b' ');s.wait(catalog,'the DOS 3.3 catalog is back after help',60);p.stable()
   # S (sort, hosted by TEXT) rereads the panel from inside its overlay too.
   for i in range(3):
    s.key(b'S');s.wait(catalog,'the DOS 3.3 catalog survives sort %d'%(i+1),60);p.stable()
   s.select('NOTES');s.ok('the cursor still lands on a DOS entry',s.line().startswith('NOTES'))
   s.key(ESC);s.wait(lambda:s.has('DEMO.DSK') and not s.has('PICTURE'),'Escape leaves the image',60);p.stable()
   s.ok('leaving the image restores the directory and its selection',s.line().startswith('DEMO.DSK'))
   s.key(RET);s.wait(catalog,'the image reopens',60);p.stable()
  s.ok('DOS panel browsing preserves all disk bytes',Path(p.hdv).read_bytes()==original)
 return ok_all(s,'dos33 overlay')
if __name__=='__main__':raise SystemExit(main())
