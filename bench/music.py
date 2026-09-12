#!/usr/bin/env python3
"""Foreground MB1, disposable media, MAIN/AUX and real AY output."""
import tempfile,time,re
from pathlib import Path
from xplug import boot_hd,RET,ESC,ok_all
from pom2 import BUILD
from pt3 import ay_snapshot
from mkdemo import fanfare

def main():
 raw=fanfare();files={'WORK/SONG.MB#061000':raw,'WORK/BAD.MB#061000':raw[:-1]}
 addr=int(re.search(r'al ([0-9A-Fa-f]{6}) \._mb_regs',(BUILD/'music.lbl').read_text())[1],16)
 with tempfile.TemporaryDirectory(prefix='mb-native-') as t:
  with boot_hd(Path(t),files,port=6895) as(p,s):
   s.key(b'/');s.select('/WORKHD');s.key(RET);s.select('WORK');s.key(RET);p.stable()
   aux=p.peek(0x1000,0xB000,'aux');floor=s.sym['__HIMEM__']-s.sym['__STACKSIZE__'];p.poke(floor,b'\xA5'*8)
   p.rq('/speed',{'preset':'1x'});s.select('SONG.MB');s.key(RET)
   s.wait(lambda:s.has('MB1 - SONG.MB'),'MB foreground')
   time.sleep(1.2);s.ok('audible AY output',any(ay_snapshot(p,'MB')[8:11]))
   s.key(b'P');p.stable();paused=p.peek(addr,28);time.sleep(.2)
   s.ok('pause freezes decoder',p.peek(addr,28)==paused)
   ay=ay_snapshot(p,'paused');s.ok('pause silences hardware',ay[7]&63==63 and not any(ay[8:11]))
   s.key(b'P');s.wait(lambda:p.peek(addr,28)!=paused,'resume',5);s.ok('resume advances',True)
   s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'MB exit');p.stable()
   s.ok('ESC silences hardware',not any(ay_snapshot(p,'exit')[8:11]))
   s.select('SONG.MB');s.key(RET);s.wait(lambda:s.has('MB1 - SONG.MB'),'reopen');p.rq('/speed',{'preset':'max'})
   s.wait(lambda:s.has('Type  Aux'),'MB natural end');s.ok('natural end returns',True)
   s.select('BAD.MB');s.key(RET);s.wait(lambda:s.has('Bad/large MB1'),'bad MB rejected');s.ok('malformed MB safe return',s.has('Type  Aux'))
   s.ok('AUX unchanged',p.peek(0x1000,0xB000,'aux')==aux)
   s.ok('stack floor unchanged',p.peek(floor,8)==b'\xA5'*8)
 return ok_all(s,'music')
if __name__=='__main__':raise SystemExit(main())
