#!/usr/bin/env python3
"""Compare actual A2FC C previews to Print Shop Companion original HGR.
Requires public original samples in A2FC_PRINTSHOP_CORPUS. Disposable disks
only; records results under /tmp, redistributes no original data or code.
Borders: 77 * 3 * 23 * 14 editable pixels. Fonts: 'A' in 36 fonts only.
"""
import os,sys,time,shutil,json,tempfile
from pathlib import Path
from xplug import stage_hd
from pom2 import Pom2,ROOT
sys.path.insert(0,str(ROOT/'tools'))
from corpus_read import files
from test_printshop_extras import PrintShop
root=Path(os.environ.get('A2FC_PRINTSHOP_CORPUS','/tmp/a2fc-printshop-corpus'))
output=Path('/tmp/a2fc-printshop-oracle');output.mkdir(exist_ok=True)

def borders():
 _,entries=files((root/"images/productivity/graphics/printshop/Gordon's Print Shop Borders (Big Red Computer Club) (Side 1).dsk").read_bytes())
 borders=[(n,d) for n,t,a,d in entries if n.startswith('BORD.') and t==6]
 PrintShop.setUpClass();test=PrintShop();results=[]
 try:
  with tempfile.TemporaryDirectory(prefix='ps-original-') as tmp:
   tmp=Path(tmp);hd=stage_hd(tmp);disk=tmp/'companion.dsk';shutil.copyfile(root/'images/productivity/graphics/printshop/PrintShop.Companion.dsk',disk)
   with Pom2(hd,floppy=disk,port=6937) as p:
    time.sleep(2);p.raw(b'\x0a');time.sleep(.15);p.raw(b'\r');time.sleep(2)
    for n,d in borders:
     p.poke(0x7800,d)
     for section in (b'1',b'2',b'3'):
      p.raw(section);time.sleep(.04);p.raw(b'H');time.sleep(.04);p.raw(b'H');time.sleep(.06)
     # The editor modifies only its in-memory copy. Double flip must preserve it.
     preserved=p.peek(0x7800,len(d))==d
     hgr=p.peek(0x2000,8192);rows,_,_=test.run_file('psborder',d,0x7800)
     differences=[]
     for k,(left,top) in enumerate(((35,45),(83,45),(35,89))):
      for y in range(14):
       yy=top+y*3;row=((yy&7)<<10)+((yy&56)<<4)+(yy>>6)*40
       for x in range(23):
        xx=left+2*x;ink=not bool(hgr[row+xx//7]&(1<<(xx%7)))
        actual=rows[y+3].ljust(80)[k*26+x]=='*'
        if ink!=actual:differences.append((k,x,y))
     results.append({'name':n,'pixels':3*23*14,'differences':len(differences),'preserved':preserved})
     print(n,len(differences),preserved,differences[:3],flush=True)
   (output/'borders.json').write_text(json.dumps(results,indent=2)+'\n')
 finally:PrintShop.tearDownClass()
 if len(results)!=77 or any(x['differences'] or not x['preserved'] for x in results):raise SystemExit(1)

def fonts():
 fonts=[]
 for diskpath in (root/'images').rglob('*Fonts*.dsk'):
  _,items=files(diskpath.read_bytes());fonts += [(n,d) for n,t,a,d in items if t==6 and a==0x5ff4 and n.startswith('FONT.')]
 PrintShop.setUpClass();test=PrintShop();results=[]
 try:
  with tempfile.TemporaryDirectory(prefix='ps-original-') as tmp:
   tmp=Path(tmp);hd=stage_hd(tmp);disk=tmp/'companion.dsk';shutil.copyfile(root/'images/productivity/graphics/printshop/PrintShop.Companion.dsk',disk)
   with Pom2(hd,floppy=disk,port=6938) as p:
    time.sleep(2);p.raw(b'\x0a\x0a');time.sleep(.15);p.raw(b'\r');time.sleep(2)
    for n,d in fonts:
     p.poke(0x5ff4,d);p.poke(0,bytes((len(d)&255,len(d)>>8)))
     p.raw(b'A');time.sleep(.2)
     preserved=p.peek(0x5ff4,len(d))==d
     hgr=p.peek(0x2000,8192);i=33;w=d[12+i]&127;h=min(d[12+59+i],38)
     # 31 Right presses skip the external '@' slot and reach 'A'.
     rows,_,_=test.run_file('psfont',d,0x5ff4,keys='R'*31)
     pixels=rows[-21:];extra=max(0,h-20)
     if extra:
      rows,_,_=test.run_file('psfont',d,0x5ff4,keys='R'*31+'D'*extra)
      pixels=pixels[:extra]+rows[-21:][:20]
     differences=[];scale=2 if w<=32 else 1
     for y in range(h):
      yy=38+y*3;row=((yy&7)<<10)+((yy&56)<<4)+(yy>>6)*40
      for x in range(w):
       xx=7+2*x;ink=not bool(hgr[row+xx//7]&(1<<(xx%7)))
       actual=pixels[y].ljust(80)[4+scale*x]=='*'
       if ink!=actual:differences.append((x,y))
     results.append({'name':n,'pixels':w*h,'differences':len(differences),'preserved':preserved})
     print(n,w,h,len(differences),preserved,differences[:3],flush=True)
   (output/'fonts.json').write_text(json.dumps(results,indent=2)+'\n')
 finally:PrintShop.tearDownClass()
 if len(results)!=36 or any(x['differences'] or not x['preserved'] for x in results):raise SystemExit(1)

if __name__=='__main__':
 os.chdir(ROOT)
 borders()
 fonts()
