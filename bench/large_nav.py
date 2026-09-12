#!/usr/bin/env python3
"""Parent selection and media navigation across 139-entry windows; disposable HDV."""
import tempfile
from pathlib import Path
from xplug import boot_hd,RET,ESC,TAB,ok_all

def find(s,p,name,x=0):
 for _ in range(24):
  rows=s.rows()
  target=next((i for i in range(2,20) if rows[i][x:x+17].startswith(name+'/') or rows[i][x:x+17].startswith(name+' ')),None)
  if target is not None:
   delta=target-s.cursor_row(x)
   for _ in range(abs(delta)):s.key(b'\x0a' if delta>0 else b'\x0b')
   return
  s.key(b'>');p.stable()
 raise AssertionError('missing '+name+'\n'+'\n'.join(s.rows()))

def main():
 mb=b'MB1\0\0\0\x08\0'+bytes([0x80,24])+bytes([127])*30+bytes([0xE0])
 files={'BIG/A.MB#061000':mb,'BIG/Z.MB#061000':mb}
 for i in range(300):
  path=f'BIG/F{i:03}' + ('/KEEP#040000' if i%2==0 else '#040000')
  files[path]=b'original data'
 files['BIG/F250/SUB/LEAF#040000']=b'nested data'
 with tempfile.TemporaryDirectory(prefix='large-nav-') as t:
  with boot_hd(Path(t),files,port=6902,blocks=4000) as(p,s):
   original=Path(p.hdv).read_bytes()
   s.key(b'/');s.select('/WORKHD');s.key(RET);s.select('BIG');s.key(RET);p.stable()
   before=p.peek(0x1000,0xB000,'aux')
   find(s,p,'F250');s.key(RET);s.wait(lambda:s.rows()[0].startswith('/WORKHD/BIG/F250'),'child')
   s.select('SUB');s.key(RET);s.key(ESC);p.stable();s.ok('nested ESC restores SUB',s.line().startswith('SUB/'))
   s.key(ESC);p.stable();s.ok('ESC finds child beyond first window',s.line().startswith('F250/'))
   s.key(RET);s.select('..');s.key(RET);p.stable();s.ok('Return on .. restores child',s.line().startswith('F250/'))
   s.key(TAB);s.key(b'/');s.select('/WORKHD',40);s.key(RET);s.select('BIG',40);s.key(RET);p.stable()
   find(s,p,'F280',40);s.key(RET);s.key(ESC);p.stable();s.ok('right panel ESC restores child',s.line(40).startswith('F280/'))
   s.key(TAB);p.stable();s.key(ESC)
   s.wait(lambda:s.rows()[0][:38].strip()=='/WORKHD','left parent');p.stable()
   s.select('BIG');s.key(RET)
   s.wait(lambda:s.rows()[0][:38].strip()=='/WORKHD/BIG','left BIG');p.stable()
   # BIG was freshly opened: select its first file from '..'. Wait for
   # the actual cursor before sending Return; redraw can outlast key().
   p.rq('/speed',{'preset':'1x'})
   s.key(b'\x0a')
   s.wait(lambda:s.line().startswith('A.MB '),'first tune cursor',15)
   s.key(RET)
   s.wait(lambda:s.has('MB1 - A.MB'),'first tune');s.key(bytes([21]));s.wait(lambda:s.has('MB1 - Z.MB'),'next across windows',120)
   s.ok('media next crosses two windows',True);s.key(bytes([8]));s.wait(lambda:s.has('MB1 - A.MB'),'previous across windows',120)
   s.ok('media previous crosses two windows',True);s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'panels after music',60);p.stable();s.ok('media returns to original entry',s.line().startswith('A.MB '))
   s.ok('navigation preserves AUX',p.peek(0x1000,0xB000,'aux')==before)
  s.ok('navigation performs no file writes',Path(p.hdv).read_bytes()==original)
 return ok_all(s,'large navigation')
if __name__=='__main__':raise SystemExit(main())
