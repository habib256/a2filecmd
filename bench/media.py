#!/usr/bin/env python3
"""Same-format foreground navigation and PT3 credits, disposable media only."""
import tempfile,time
from pathlib import Path
from xplug import boot_hd,RET,ESC,ok_all
from pt3 import autumn
from open_images import visible
from test_paint816 import pack
from test_sample_media import font_page,clip_page

RIGHT=bytes([21]);LEFT=bytes([8])
def main():
 pt=bytearray(autumn());pt[30:62]=b'Test title'.ljust(32);pt[66:98]=b'Test artist'.ljust(32)
 mb=b'MB1\0\0\0\x08\0'+bytes([0xA0,12,0x80,24])+bytes([127])*30+bytes([0xE0])
 files={'WORK/A.MB#061000':mb,'WORK/B.PT3#000000':bytes(pt),'WORK/C.MB#061000':mb,'WORK/D.PT3#000000':bytes(pt),'WORK/TEXT#040000':b'Not media'}
 cases=[]
 for prefix,typ,aux,encode,oracle in [
  ('EXT',0xF2,0,lambda c:b'\0\0'+bytes([128,c])*120,lambda c:bytes([c])*8192),
  ('PACK',8,0x4000,lambda c:bytes([255,c])*32,lambda c:bytes([c])*8192),
  ('PAINT',6,0xE001,lambda c:pack(bytes([c])*7680),lambda c:bytes([c])*8192),
  ('LZ',8,0x8066,lambda c:bytes([0x66,0x1F,c,254]),lambda c:bytes([c])+bytes(8191)),
  ('FONT',7,0,lambda c:bytes([0,0,8,7])+bytes([c])*8,lambda c:font_page(bytes([0,0,8,7])+bytes([c])*8)),
  ('CLIP',6,0x4800,lambda c:bytes([c])*572,lambda c:clip_page(bytes([c])*572))]:
  for n,c in [(1,0x11),(2,0x22)]:files[f'WORK/{prefix}{n}#{typ:02X}{aux:04X}']=encode(c)
  cases.append((prefix,aux in (0x4000,0xE001) or typ==0xF2,oracle))
 for n,c in [(1,0x55),(2,0x66)]:files[f'WORK/LORES{n}#060400']=bytes([c])*1024
 with tempfile.TemporaryDirectory(prefix='media-nav-') as t:
  with boot_hd(Path(t),files,port=6901) as(p,s):
   original=Path(p.hdv).read_bytes();floor=s.sym['__HIMEM__']-s.sym['__STACKSIZE__'];p.poke(floor,b'\xA5'*8)
   s.key(b'/');s.select('/WORKHD');s.key(RET);s.select('WORK');s.key(RET);p.stable()
   s.select('A.MB');s.key(b' ');s.select('A.MB')
   before=p.peek(0x1000,0xB000,'aux');p.rq('/speed',{'preset':'1x'})
   for first,last,title in [('A.MB','C.MB','MB1 - '),('B.PT3','D.PT3','ProTracker 3 - ')]:
    s.select(first);s.key(RET);s.wait(lambda:s.has(title+first),'start '+first)
    if first.endswith('PT3'):
     s.ok('PT3 title and artist',s.has('Title: Test title') and s.has('Test artist'))
     s.ok('PT3 player credit',s.has('Player: Vince Weaver - A2FC adapter'))
    s.key(LEFT);p.stable();s.ok(first+' boundary stays',s.has(title+first))
    s.key(b'P');s.key(RIGHT);s.wait(lambda:s.has(title+last),'next same format')
    s.ok(first+' skips other formats',True)
    s.key(RIGHT);p.stable();s.ok(last+' boundary stays',s.has(title+last))
    s.key(LEFT);s.wait(lambda:s.has(title+first),'previous same format');s.ok(first+' previous',True)
    s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'music exit');p.stable()
   s.select('A.MB');s.ok('music navigation preserves marks','*' in s.line())
   s.ok('music navigation preserves AUX',p.peek(0x1000,0xB000,'aux')==before)
   p.rq('/speed',{'preset':'max'})
   for prefix,consent,oracle in cases:
    s.select(prefix+'1');s.key(RET)
    if consent:s.allow_aux()
    s.wait(lambda:visible(p.peek(0x2000,8192))==visible(oracle(0x11)),prefix+' first',60)
    s.key(LEFT);p.stable();s.ok(prefix+' first boundary stays',visible(p.peek(0x2000,8192))==visible(oracle(0x11)))
    s.key(RIGHT)
    if consent:s.allow_aux()
    s.wait(lambda:visible(p.peek(0x2000,8192))==visible(oracle(0x22)),prefix+' next',60);s.ok(prefix+' next',True)
    s.key(LEFT)
    if consent:s.allow_aux()
    s.wait(lambda:visible(p.peek(0x2000,8192))==visible(oracle(0x11)),prefix+' previous',60)
    s.key(ESC);s.wait(lambda:s.has('Type  Aux'),prefix+' exit');p.stable();s.ok(prefix+' cursor restored',s.line().startswith(prefix+'1 '))
   s.select('LORES1');s.key(RET);s.wait(lambda:p.peek(0x400,40)==b'\x55'*40,'lores first')
   s.key(RIGHT);s.wait(lambda:p.peek(0x400,40)==b'\x66'*40,'lores next');s.ok('DGRVIEW next',True)
   s.key(LEFT);s.wait(lambda:p.peek(0x400,40)==b'\x55'*40,'lores previous');s.ok('DGRVIEW previous',True)
   s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'final panels');p.stable()
   s.ok('media stack floor preserved',p.peek(floor,8)==b'\xA5'*8)
  s.ok('all media source bytes preserved',Path(p.hdv).read_bytes()==original)
 return ok_all(s,'media')
if __name__=='__main__':raise SystemExit(main())
