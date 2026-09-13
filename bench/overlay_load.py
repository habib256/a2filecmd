#!/usr/bin/env python3
"""Reject oversized native code, restore panels and keep all disk bytes."""
import os
import tempfile
from pathlib import Path
from pom2 import Pom2, Session, BUILD
from xplug import stage_hd, ok_all

def main():
 with tempfile.TemporaryDirectory(prefix='overlay-load-ui-') as tmp:
  menu=(BUILD/'A2FILE.CODE.BIN.MENU').read_bytes()
  assert menu[2]&1
  hd=stage_hd(tmp,{'WORK/KEEP.TXT':b'preserve these bytes\r',
                  'A2FILE/MENU.PLG#061B00':menu+bytes(9473-len(menu))})
  original=hd.read_bytes()
  with Pom2(hd,port=6898+int(os.environ.get('A2FC_PORT_OFFSET','0')),
            exe=os.environ.get('POM2_DOS','/tmp/a2fc-dos-host')) as p:
   s=Session(p);s.boot();s.select('WORK');s.key(b'\r');p.stable()
   start=s.sym['__ONCE_RUN__'];end=s.sym['__HIMEM__']-s.sym['__STACKSIZE__']
   guard=bytes([0xEE])*(end-start);p.poke(start,guard)
   aux=p.peek(0x1000,0xB000,'aux')
   for attempt in range(2):
    s.key(b'!');s.wait(lambda:s.has('MENU.PLG is missing or stale'),'oversized code refused')
    p.stable();s.ok('Failed big load restores file names '+str(attempt),s.has('KEEP'))
   s.key(b'?');s.wait(lambda:not s.has('MENU.PLG is missing or stale'),'normal help loads')
   s.key(b'\x1b');p.stable();s.ok('Normal overlay returns to intact panels',s.has('KEEP'))
   s.ok('192-byte stack guard preserved',p.peek(start,len(guard))==guard)
   s.ok('AUX untouched',p.peek(0x1000,0xB000,'aux')==aux)
  s.ok('Entire disposable volume unchanged',hd.read_bytes()==original)
  return ok_all(s,'overlay load failure')

if __name__=='__main__':raise SystemExit(main())
