#!/usr/bin/env python3
"""A DOS 3.3 catalog or a ProDOS image directory read from under running
overlay code (HELP, the sort hosted by TEXT) is deferred and settled: the
catalog is back on screen and the image is untouched. Disposable images only."""
import subprocess,tempfile,sys
from pathlib import Path
from xplug import boot_hd,RET,ESC,ok_all,ROOT
sys.path.insert(0,str(ROOT/'tools'))
import mkdos33

def tiny_po(tmp):
 stage=tmp/'tiny';(stage/'INSIDE').mkdir(parents=True)
 (stage/'INSIDE/DEEP.TXT').write_bytes(b'deep inside the image\r')
 (stage/'HELLO.TXT').write_bytes(b'hello from inside a disk image\r'*20)
 (stage/'ZEBRA.TXT').write_bytes(b'last by name\r')
 out=tmp/'TINY.PO'
 subprocess.run([sys.executable,str(ROOT/'tools/mkvolume.py'),str(stage),str(out),'--volume','TINY','--blocks','64'],check=True,capture_output=True)
 return out.read_bytes()

def main():
 dos=mkdos33.build([('HELLO',2,b'\x00'*300),('NOTES',0,b'A NOTE\r'+b'\x00'*100),('PICTURE',4,b'\x00\x20\x00\x08'+b'\x55'*2048)])
 with tempfile.TemporaryDirectory(prefix='catalog-overlay-') as t:
  files={'WORK/DEMO.DSK':bytes(dos),'WORK/TINY.PO':tiny_po(Path(t)),'WORK/KEEP#040000':b'preserve this file\r'}
  with boot_hd(Path(t),files,port=6907) as(p,s):
   original=Path(p.hdv).read_bytes()
   s.key(b'/');s.select('/WORKHD');s.key(RET);s.select('WORK');s.key(RET);p.stable()
   s.select('DEMO.DSK');s.key(RET)
   catalog=lambda:s.has('HELLO') and s.has('NOTES') and s.has('PICTURE')
   s.wait(catalog,'the DOS 3.3 catalog is read through CATALOG.PLG',60);p.stable()
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
   s.key(ESC);s.wait(lambda:s.has('DEMO.DSK') and not s.has('PICTURE'),'back to WORK',60);p.stable()
   # A ProDOS image opened as a folder: the same overlay walks its directories.
   s.select('TINY.PO');s.key(RET)
   root=lambda:s.has('HELLO ') and s.has('ZEBRA ') and s.has('INSIDE/')
   s.wait(root,'the image root is read through CATALOG.PLG',60);p.stable()
   s.key(b'?');s.wait(lambda:not s.has('ZEBRA '),'help covers the image panel',30)
   s.key(b' ');s.wait(root,'the image root is back after help',60);p.stable()
   s.key(b'S');s.wait(root,'the image root survives sort',60);p.stable()
   s.select('INSIDE');s.key(RET);s.wait(lambda:s.has('DEEP ') and s.has('..'),'a subdirectory of the image',60);p.stable()
   s.key(b'?');s.wait(lambda:not s.has('DEEP '),'help covers the subdirectory',30)
   s.key(b' ');s.wait(lambda:s.has('DEEP '),'the subdirectory is back after help',60);p.stable()
   s.key(ESC);s.wait(root,'Escape returns to the image root',60);p.stable()
   s.ok('the cursor lands on the directory left',s.line().startswith('INSIDE'))
   s.key(ESC);s.wait(lambda:s.has('TINY.PO') and not s.has('ZEBRA '),'Escape leaves the ProDOS image',60);p.stable()
   s.ok('the directory shows the image file again',s.line().startswith('TINY.PO'))
  s.ok('DOS and image panel browsing preserve all disk bytes',Path(p.hdv).read_bytes()==original)
 return ok_all(s,'catalog overlay')
if __name__=='__main__':raise SystemExit(main())
