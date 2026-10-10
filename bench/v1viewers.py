#!/usr/bin/env python3
"""1.0 readers: actual overlays, pixels, AUX consent and preserved source HD."""
import os,sys,tempfile
from pathlib import Path
from xplug import boot_hd,RET,ESC,ok_all
from pom2 import ROOT
sys.path.insert(0,str(ROOT/'tools'))
from test_v1text import mouse,filer,SOURCE_ROOT
from test_v1media import movie

def main():
 files={'WORK/WP#A00000':b'Hello WordPerfect\x0a','WORK/MW#F10000':mouse(b'Hello MouseWrite\r'),'WORK/BS#06D3C2':filer(),'WORK/MP#F40000':(SOURCE_ROOT/'extracted/MP_GRID.bin').read_bytes(),'WORK/MOVIE.MVM#066000':movie(),'WORK/PAL.DPC#064000':(SOURCE_ROOT/'pal-no-text.dpc').read_bytes(),'WORK/TABLE.PB#064000':(SOURCE_ROOT/'extracted/DEMO1.PB#064000').read_bytes(),'WORK/BAD.DPC#064000':b'\x80\xFF\xFF'}
 expected=(SOURCE_ROOT/'pal-original.raw').read_bytes();pcs=(SOURCE_ROOT/'DEMO1.PB.raw').read_bytes()[:8192]
 with tempfile.TemporaryDirectory(prefix='v1viewers-native-') as tmp:
  with boot_hd(Path(tmp),files,port=6968,plugins=['wordperf','mousewr','bsfiler','multplan','mvmovie','dgmagi','pcsvw'],speed=4000000) as (p,s):
   s.key(b'/');s.select('/WORKHD');s.key(RET);s.select('WORK');s.key(RET);p.stable()
   before=Path(p.hdv).read_bytes();aux=bytes(p.peek(0x1000,0xB000,'aux'));floor=s.sym['__HIMEM__']-s.sym['__STACKSIZE__'];p.poke(floor,b'\xa5'*8)
   for name,text in (('WP','Hello WordPerfect'),('MW','Hello MouseWrite'),('BS','Name: Hello'),('MP','R2C2 = -1.25')):
    s.select(name);s.key(RET);s.wait(lambda:s.has(text),name,60);s.ok(name+' automatic reader',True);s.key(ESC);s.wait(lambda:s.has('Type  Aux'),name+' exit',60)
   s.select('MOVIE.MVM');s.key(RET);s.wait(lambda:p.peek(0x400,3)==b'\xff'*3,'Movie Maker first colour frame',60);s.ok('Movie Maker colour frame',True);s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'movie exit',60)
   s.ok('Text and Movie Maker preserve AUX',bytes(p.peek(0x1000,0xB000,'aux'))==aux)
   s.select('BAD.DPC');s.key(RET);s.wait(lambda:s.has('Malformed DHGR DPC'),'malformed DPC',60);s.ok('Malformed DPC preserves AUX before consent',bytes(p.peek(0x1000,0xB000,'aux'))==aux)
   s.select('PAL.DPC');s.ram_occupied();aux=bytes(p.peek(0x1000,0xB000,'aux'));s.key(RET);s.wait(lambda:s.has('ALL /RAM files will be LOST'),'RAM warning',60)
   s.ok('No AUX write before confirmation',bytes(p.peek(0x1000,0xB000,'aux'))==aux);s.key(b'N');p.stable();s.ok('Decline preserves occupied RAM',bytes(p.peek(0x1000,0xB000,'aux'))==aux)
   for name in ('PAL.DPC','TABLE.PB'):
    s.select(name);s.key(RET);s.allow_aux()
    if name=='PAL.DPC':s.wait(lambda:bytes(p.peek(0x2000,8192,'aux'))+bytes(p.peek(0x2000,8192))==expected,'all native DHGR pixels',120)
    else:s.wait(lambda:bytes(p.peek(0x2000,8192))==pcs,'PCS static background and polygons',600)
    s.ok(name+' native pixel comparison',True);s.key(ESC);s.wait(lambda:s.has('Type  Aux'),name+' exit',60);s.ok(name+' reconstructs empty RAM',s.ram_files()==0)
   s.ok('Stack floor survives all seven viewers',p.peek(floor,8)==b'\xa5'*8);p.sync_disks();s.ok('Whole source volume preserved',Path(p.hdv).read_bytes()==before)
 return ok_all(s,'v1viewers')
if __name__=='__main__':raise SystemExit(main())
