#!/usr/bin/env python3
"""1.0 readers: actual overlays, pixels, AUX consent and preserved source HD."""
import os,sys,tempfile,time
from pathlib import Path
from xplug import boot_hd,RET,ESC,ok_all
from pom2 import ROOT
sys.path.insert(0,str(ROOT/'tools'))
from test_v1text import mouse,filer,SOURCE_ROOT
from test_v1media import movie,movie_navigation,pcs_pattern

def graphics_checks(p,s,name,expected,double=False,background=None):
 def pixels():
  main=p.peek(0x2000,8192)
  return p.peek(0x2000,8192,'aux')+main if double else main
 for key in (RET,b'I'):
  s.select(name);s.ram_occupied();aux=p.peek(0x1000,0xB000,'aux');s.key(key)
  s.wait(lambda:s.has('ALL /RAM files will be LOST'),'renamed '+name+' RAM warning',60)
  s.ok('Renamed '+name+' waits for consent '+repr(key),p.peek(0x1000,0xB000,'aux')==aux)
  s.key(b'N');p.stable();s.ok('Renamed '+name+' decline preserves RAM '+repr(key),p.peek(0x1000,0xB000,'aux')==aux)
  s.select(name);s.key(key);s.allow_aux()
  s.wait(lambda:pixels()==expected,'renamed '+name+' pixels',600)
  s.ok('Renamed '+name+' native pixels '+repr(key),True)
  if background is not None:
   staged=p.peek(0x4000,0x4000,'aux')
   for toggle,wanted,label in ((b'O',background,'background'),(b'O',expected,'objects'),(b'o',background,'lowercase background'),(b'o',expected,'lowercase objects')):
    s.key(toggle);s.wait(lambda:pixels()==wanted,name+' '+label,60)
    s.ok(name+' '+label+' pixels '+repr(key),True)
   s.ok(name+' toggles preserve both AUX views '+repr(key),p.peek(0x4000,0x4000,'aux')==staged)
  s.key(b'O' if double else ESC)  # DGMAGI keeps its any-key exit behavior.
  s.wait(lambda:s.has('Type  Aux'),'renamed '+name+' exit',60)
  s.ok('Renamed '+name+' rebuilds empty RAM '+repr(key),s.ram_files()==0)

def text_checks(p,s):
 for name,text in (('WP','Hello WordPerfect'),('MW','Hello MouseWrite'),('BS','Name: Hello'),('MP','R2C2 = -1.25')):
  s.select(name);s.key(RET);s.wait(lambda:s.has(text),name,60);s.ok(name+' automatic reader',True);s.key(ESC);s.wait(lambda:s.has('Type  Aux'),name+' exit',60)
 for version in (1,4,5):
  name='MWIMPORT'+str(version);expected='Hello MouseWrite V'+str(version)
  for key in (RET,b'I'):
   s.select(name);s.key(key);s.wait(lambda:s.has(expected),name+' automatic BIN import',60)
   s.ok(name+' BIN text '+repr(key),True);s.key(ESC);s.wait(lambda:s.has('Type  Aux'),name+' exit',60)
 for key in (RET,b'I'):
  s.select('BADMW');s.key(key);s.wait(lambda:s.has('Malformed MouseWrite'),'bad BIN row',60)
  s.ok('Truncated MouseWrite BIN rejected '+repr(key),True)
 s.select('MOVIE.MVM');s.key(RET);s.wait(lambda:p.peek(0x400,3)==b'\xff'*3,'Movie Maker first colour frame',60);s.ok('Movie Maker colour frame',True);s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'movie exit',60)

def multiplan_checks(p,s):
 for key in (RET,b'I'):
  s.select('MPIMPORT');s.key(key);s.wait(lambda:s.has('R2C2 = -1.25'),'Multiplan BIN values',60)
  s.ok('Multiplan BIN cached value/formula '+repr(key),s.has('R5C3 = 3 [formula tokens:'))
  s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'Multiplan BIN exit',60)
  s.select('BADMP');s.key(key);s.wait(lambda:s.has('Malformed Multiplan'),'bad BIN pool pointer',60)
  s.ok('Multiplan BIN bad pointer rejected '+repr(key),True)

def movie_import_checks(p,s):
 for key in (RET,b'I'):
  s.select('FILM');s.key(key);s.wait(lambda:p.peek(0x400,3)==b'\xff'*3,'Movie Maker aux-zero frame',60)
  s.ok('Movie Maker aux-zero frame '+repr(key),True);s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'film exit',60)
  s.select('BADFILM');s.key(key);s.wait(lambda:s.has('Unsupported/malformed MVM'),'Movie Maker malformed import',60)
  s.ok('Movie Maker truncated import refused '+repr(key),True)

def movie_navigation_checks(p,s,auto_only=False):
 def expected(dx,flip=0,background=0,actors=True):
  def pixel(x,y):
   x=39-x if flip&1 else x;y=47-y if flip&2 else y
   sx=x*7//2;bit=sx*2
   pair=((background>>(bit%7))&1)|(((background>>((bit+1)%7))&1)<<1)
   color=((0,6,9,15) if background&128 else (0,3,12,15))[pair]
   return 15 if actors and y*4<10 and dx<=sx<dx+10 else color
  return bytes(pixel(x,y*2)|(pixel(x,y*2+1)<<4) for y in range(24) for x in range(40))
 def displayed():
  page=p.peek(0x400,1024)
  return b''.join(page[(y&7)*128+(y>>3)*40:(y&7)*128+(y>>3)*40+40] for y in range(24))
 if auto_only:
  movie_auto_checks(p,s,expected,displayed);return
 s.select('NAVFILM');s.key(RET)
 for key,dx,label in ((None,0,'first'),(b'B',0,'previous at start'),(b' ',14,'next'),(b' ',28,'third'),(b'B',14,'previous'),(b'\x08',0,'left'),(b' ',14,'advance again'),(b'R',0,'restart'),(b'L',28,'last from first'),(b'l',28,'last at end'),(b'B',14,'previous after last'),(b'R',0,'restart after last')):
  if key:s.key(key)
  s.wait(lambda:displayed()==expected(dx),'Movie Maker navigation '+label,60);p.stable()
  s.ok('Movie Maker navigation '+label,displayed()==expected(dx))
 s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'navigation exit',60)
 s.select('LONGFILM');s.key(RET)
 for key,dx,label in ((None,0,'jump initial'),(b'+',70,'ten forward'),(b'+',84,'forward clamps at end'),
                      (b'-',14,'ten backward'),(b'-',0,'backward clamps at start'),(b'-',0,'backward at start'),
                      (b' ',7,'next after jump'),(b'+',77,'ten from second'),(b'B',70,'previous after jump'),(b'R',0,'restart after jump')):
  if key:s.key(key)
  s.wait(lambda:displayed()==expected(dx),'Movie Maker '+label,60);p.stable()
  s.ok('Movie Maker '+label,displayed()==expected(dx))
 s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'jump exit',60)
 s.select('NAVFILM');s.key(RET)
 for key,dx,actors,label in ((None,0,True,'actors initial'),(b'O',0,False,'background'),(b' ',14,False,'background next'),
                           (b'o',14,True,'actors after next'),(b'O',14,False,'background again'),(b'B',0,False,'background previous'),
                           (b'O',0,True,'actors after previous'),(b'L',28,True,'actors last'),(b'O',28,False,'last background'),
                           (b'R',0,False,'background restart'),(b'O',0,True,'actors after restart')):
  if key:s.key(key)
  wanted=expected(dx) if actors else bytes(960)
  s.wait(lambda:displayed()==wanted,'Movie Maker '+label,60);p.stable()
  s.ok('Movie Maker '+label,displayed()==wanted)
 s.key(b'O');s.wait(lambda:displayed()==bytes(960),'background before exit',60)
 s.ok('Movie Maker background before exit',True)
 s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'background exit',60)
 s.select('NAVFILM');s.key(RET);s.wait(lambda:displayed()==expected(0),'actors reset on reopen',60)
 s.ok('Movie Maker actors reset on reopen',True)
 s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'reopen exit',60)
 s.select('MIRRORFILM');s.key(RET)
 holes=[i for i in range(1024) if i%128>=120];saved_holes=None
 for key,dx,flip,actors,label in ((None,0,0,True,'mirror initial'),(b'H',0,1,True,'horizontal mirror'),
                                (b'v',0,3,True,'both mirrors'),(b'O',0,3,False,'mirrored background'),
                                (b'h',0,2,False,'vertical background'),(b'o',0,2,True,'vertical actors'),
                                (b'V',0,0,True,'orientations restored'),(b'H',0,1,True,'horizontal again'),
                                (b' ',14,1,True,'mirrored next'),(b'B',0,1,True,'mirrored previous'),
                                (b'L',28,1,True,'mirrored last'),(b'R',0,1,True,'mirrored restart'),
                                (b'+',28,1,True,'mirrored ten forward'),(b'-',0,1,True,'mirrored ten back'),
                                (b'v',0,3,True,'both before exit'),(b'h',0,2,True,'vertical before exit')):
  if key:s.key(key)
  wanted=expected(dx,flip,0x2A,actors)
  s.wait(lambda:displayed()==wanted,'Movie Maker '+label,60);p.stable()
  s.ok('Movie Maker '+label,displayed()==wanted)
  if saved_holes is None:
   page=p.peek(0x400,1024);saved_holes=bytes(page[i] for i in holes)
 page=p.peek(0x400,1024)
 s.ok('Movie Maker mirrors preserve screen holes',bytes(page[i] for i in holes)==saved_holes)
 s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'mirror exit',60)
 s.select('MIRRORFILM');s.key(RET);s.wait(lambda:displayed()==expected(0,0,0x2A),'mirrors reset on reopen',60)
 s.ok('Movie Maker mirrors reset on reopen',True)
 s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'mirror reopen exit',60)
 movie_auto_checks(p,s,expected,displayed)

def movie_auto_checks(p,s,expected,displayed):
 # --speed is cycles per video frame, not Hz. Turbo can outrun the
 # control connection before a pause key arrives; use real 1x for timers.
 p.rq('/speed',{'preset':'1x'})
 s.select('LONGFILM');s.key(RET)
 s.wait(lambda:displayed()==expected(0),'auto initial',60)
 s.key(b'S');s.wait(lambda:displayed()==expected(7),'automatic next frame',60)
 s.key(b's');p.stable();paused=displayed();time.sleep(7)
 s.ok('Movie Maker S/s pauses without advancing',paused==expected(7) and displayed()==paused, {'paused': [n for n in range(13) if paused==expected(n*7)], 'after': [n for n in range(13) if displayed()==expected(n*7)]})
 s.key(b'S');s.wait(lambda:displayed()==expected(14),'automatic resume',60)
 s.key(b'B');s.wait(lambda:displayed()==expected(7),'auto interrupted previous',60);time.sleep(7)
 s.ok('Movie Maker command stops auto and acts',displayed()==expected(7))
 s.key(b'S');s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'auto escape',60)
 s.ok('Movie Maker Escape interrupts auto',True)
 s.select('LONGFILM');s.key(RET);s.wait(lambda:displayed()==expected(0),'manual reopen',60);time.sleep(7)
 s.ok('Movie Maker auto resets on reopening',displayed()==expected(0))
 s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'auto reopen exit',60)
 s.select('NAVFILM');s.key(RET);s.wait(lambda:displayed()==expected(0),'auto short first',60)
 s.key(b'S');s.wait(lambda:displayed()==expected(14),'auto short second',60)
 s.ok('Movie Maker auto renders second frame',True)
 s.wait(lambda:displayed()==expected(28),'auto short last',60)
 s.ok('Movie Maker auto renders last frame',True)
 s.wait(lambda:s.has('Type  Aux'),'auto end',60)
 s.ok('Movie Maker auto returns at end',True)
 s.select('LONGFILM');s.key(RET);s.wait(lambda:displayed()==expected(0),'speed first',60)
 s.key(b'3');p.stable();time.sleep(1)
 s.ok('Movie Maker speed selection keeps manual frame',displayed()==expected(0))
 s.key(b'S');s.wait(lambda:displayed()==expected(7),'slow auto advance',60);s.key(b's');time.sleep(7)
 s.ok('Movie Maker slow auto advances then pauses',displayed()==expected(7))
 s.key(b'1');p.stable()
 s.ok('Movie Maker fast selection keeps paused frame',displayed()==expected(7))
 s.key(b'S');s.wait(lambda:displayed()==expected(14),'fast auto advance',60);s.key(b's');time.sleep(7)
 s.ok('Movie Maker fast auto advances then pauses',displayed()==expected(14))
 s.key(b'2');s.key(b'S');s.wait(lambda:displayed()==expected(21),'normal auto advance',60)
 s.ok('Movie Maker normal auto advances',True)
 s.key(b'3');s.wait(lambda:displayed()==expected(28),'speed change while auto',60);s.key(b's');time.sleep(7)
 s.ok('Movie Maker speed change keeps auto active',displayed()==expected(28))
 s.key(b'R');s.wait(lambda:displayed()==expected(0),'speed restart',60)
 s.key(b'S');s.wait(lambda:displayed()==expected(7),'selected speed after restart',60);s.key(b's');time.sleep(7)
 s.ok('Movie Maker selected speed works after restart',displayed()==expected(7))
 s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'speed exit',60)
 s.ok('Movie Maker speed controls exit normally',True)
 s.select('NAVFILM');s.key(RET);s.wait(lambda:displayed()==expected(0),'loop first',60)
 s.key(b'Q');p.stable();time.sleep(1)
 s.ok('Movie Maker Q keeps the manual frame',displayed()==expected(0))
 s.key(b'S');s.wait(lambda:displayed()==expected(28),'loop last',60)
 s.wait(lambda:displayed()==expected(0),'loop wraps to first',60)
 s.ok('Movie Maker loop renders first after last',True)
 s.key(b's');time.sleep(7)
 s.ok('Movie Maker loop pauses on first without advancing',displayed()==expected(0))
 s.key(b'S');s.wait(lambda:displayed()==expected(14),'loop resume',60)
 s.key(b'q');s.wait(lambda:displayed()==expected(28),'loop disabled while playing',60)
 s.ok('Movie Maker q disables loop while retaining auto',True)
 s.wait(lambda:s.has('Type  Aux'),'disabled loop end',60)
 s.ok('Movie Maker disabled loop returns at end',True)
 s.select('NAVFILM');s.key(RET);s.wait(lambda:displayed()==expected(0),'loop reopen',60)
 s.key(b'L');s.wait(lambda:displayed()==expected(28),'loop reopen last',60)
 s.key(b'S');s.wait(lambda:s.has('Type  Aux'),'loop resets on reopen',60)
 s.ok('Movie Maker loop resets on reopening',True)
 s.select('NAVFILM');s.key(RET);s.wait(lambda:displayed()==expected(0),'manual loop first',60)
 s.key(b'Q');s.key(b'L');s.wait(lambda:displayed()==expected(28),'manual loop last',60)
 s.key(b' ');s.wait(lambda:s.has('Type  Aux'),'manual loop end',60)
 s.ok('Movie Maker loop keeps manual next exit at end',True)
 s.select('NAVFILM');s.key(RET);s.wait(lambda:displayed()==expected(0),'loop escape first',60)
 s.key(b'Q');s.key(b'S');s.wait(lambda:displayed()==expected(14),'loop escape next',60)
 s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'loop escape',60)
 s.ok('Movie Maker Escape exits repeated playback',True)
 p.rq('/speed',{'preset':'max'})

def main():
 files={'WORK/WP#A00000':b'Hello WordPerfect\x0a','WORK/MW#F10000':mouse(b'Hello MouseWrite\r'),'WORK/BS#06D3C2':filer(),'WORK/MP#F40000':(SOURCE_ROOT/'extracted/MP_GRID.bin').read_bytes(),'WORK/MOVIE.MVM#066000':movie(),'WORK/PALETTE#064000':(SOURCE_ROOT/'pal-no-text.dpc').read_bytes(),'WORK/TABLE#064000':(SOURCE_ROOT/'extracted/DEMO1.PB#064000').read_bytes(),'WORK/BAD.DPC#064000':b'\x80\xFF\xFF'}
 expected=(SOURCE_ROOT/'pal-original.raw').read_bytes();pcs=(SOURCE_ROOT/'DEMO1.PB.raw').read_bytes()[:8192]
 for version in (1,4,5):files['WORK/MWIMPORT'+str(version)+'#060000']=mouse(('Hello MouseWrite V'+str(version)+'\r').encode(),version=version)
 files['WORK/BADMW#060000']=mouse()[:-1]
 sheet=files['WORK/MP#F40000'];files['WORK/MPIMPORT#060000']=sheet
 bad=bytearray(sheet);bad[666:668]=b'\xff\xff';files['WORK/BADMP#060000']=bytes(bad)
 files['WORK/FILM#060000']=movie();files['WORK/BADFILM#060000']=movie()[:-1]
 files['WORK/NAVFILM#060000']=movie_navigation()
 files['WORK/LONGFILM#060000']=movie_navigation(tuple(i*7 for i in range(13)))
 files['WORK/MIRRORFILM#060000']=movie_navigation(background=0x2A)
 toggle,background,objects=pcs_pattern();files['WORK/TOGGLE#064000']=toggle
 with tempfile.TemporaryDirectory(prefix='v1viewers-native-') as tmp:
  with boot_hd(Path(tmp),files,port=6969 if os.environ.get('A2FC_BUILD')=='build' else 6968,plugins=['wordperf','mousewr','bsfiler','multplan','mvmovie','dgmagi','pcsvw'],speed=4000000) as (p,s):
   s.key(b'/');s.select('/WORKHD');s.key(RET);s.select('WORK');s.key(RET);p.stable()
   before=Path(p.hdv).read_bytes();aux=bytes(p.peek(0x1000,0xB000,'aux'));floor=s.sym['__HIMEM__']-s.sym['__STACKSIZE__'];p.poke(floor,b'\xa5'*8)
   if '--movies-only' in sys.argv or '--auto-only' in sys.argv:
    movie_import_checks(p,s)
    movie_navigation_checks(p,s,auto_only='--auto-only' in sys.argv)
    s.ok('Movie Maker imports preserve AUX',p.peek(0x1000,0xB000,'aux')==aux)
    s.ok('Stack floor survives Movie Maker',p.peek(floor,8)==b'\xa5'*8)
    p.sync_disks();s.ok('Whole source volume preserved',Path(p.hdv).read_bytes()==before)
    return ok_all(s,'v1viewers movies')
   if '--mp-only' in sys.argv:
    multiplan_checks(p,s)
    s.ok('Multiplan BIN preserves AUX',p.peek(0x1000,0xB000,'aux')==aux)
    s.ok('Stack floor survives Multiplan',p.peek(floor,8)==b'\xa5'*8)
    p.sync_disks();s.ok('Whole source volume preserved',Path(p.hdv).read_bytes()==before)
    return ok_all(s,'v1viewers Multiplan')
   if '--pcs-only' in sys.argv or '--dpc-only' in sys.argv:
    dpc='--dpc-only' in sys.argv
    graphics_checks(p,s,'PALETTE' if dpc else 'TABLE',expected if dpc else pcs,dpc)
    if not dpc:graphics_checks(p,s,'TOGGLE',objects,background=background)
    s.ok('Stack floor survives graphics',p.peek(floor,8)==b'\xa5'*8)
    p.sync_disks();s.ok('Whole source volume preserved',Path(p.hdv).read_bytes()==before)
    return ok_all(s,'v1viewers DPC' if dpc else 'v1viewers PCS')
   text_checks(p,s)
   multiplan_checks(p,s)
   s.ok('Text and Movie Maker preserve AUX',bytes(p.peek(0x1000,0xB000,'aux'))==aux)
   if '--text-only' in sys.argv:
    s.ok('Stack floor survives text',p.peek(floor,8)==b'\xa5'*8)
    p.sync_disks();s.ok('Whole source volume preserved',Path(p.hdv).read_bytes()==before)
    return ok_all(s,'v1viewers text')
   s.select('BAD.DPC');s.key(RET);s.wait(lambda:s.has('Malformed DHGR DPC'),'malformed DPC',60);s.ok('Malformed DPC preserves AUX before consent',bytes(p.peek(0x1000,0xB000,'aux'))==aux)
   graphics_checks(p,s,'PALETTE',expected,True)
   graphics_checks(p,s,'TABLE',pcs)
   s.ok('Stack floor survives all seven viewers',p.peek(floor,8)==b'\xa5'*8);p.sync_disks();s.ok('Whole source volume preserved',Path(p.hdv).read_bytes()==before)
 return ok_all(s,'v1viewers')
if __name__=='__main__':raise SystemExit(main())
