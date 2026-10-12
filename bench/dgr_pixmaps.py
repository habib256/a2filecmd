#!/usr/bin/env python3
"""Full 80x48 pixmaps through the existing DGRVIEW on disposable volumes."""
import tempfile
from pathlib import Path
from xplug import boot_hd,RET,ESC,ok_all,menu_run

def main():
 data=bytes(((0 if (x+y)%11==0 else 0xF0)|((x+3*y)%15+1)) for y in range(48) for x in range(80))
 small=bytes(((0 if (x+y)%3==0 else 0xF0)|((x+3*y)%16)) for y in range(12) for x in range(20))
 files={'WORK/FULL#060000':data,'WORK/SMALL#060000':small,'WORK/TOOBIG#060000':data+b'\xF9','WORK/BADPAGE#060400':bytes(3000)}
 with tempfile.TemporaryDirectory(prefix='dgr-pixmaps-') as tmp:
  with boot_hd(Path(tmp),files,port=6872,plugins=['dgrview']) as (p,s):
   s.key(b'/');s.select('/WORKHD');s.key(RET);s.select('WORK');s.key(RET);p.stable()
   s.ram_occupied();ram=p.peek(0x0800,0xB800,'aux');volume=Path(p.hdv).read_bytes()
   floor=s.sym['__HIMEM__']-s.sym['__STACKSIZE__'];p.poke(floor,b'\xA5'*8)
   s.select('FULL');menu_run(s,p,'DGRVIEW',allow_aux=False);s.wait(lambda:s.has('Pixmap width'),'full pixmap width')
   s.ok('Full pixmap asks width without RAM consent',not s.has('ALL /RAM files will be LOST'))
   p.poke(0x3F01,b'\xC7'*255);s.key(b'50'+RET)
   expected=[bytearray(1024),bytearray(1024)]
   for y in range(48):
    for x in range(80):
     b=data[y*80+x];value=(b&15) if b&0xF0 else 0
     row=y//2;at=(row&7)*128+(row>>3)*40+x//2
     expected[x%2][at]|=value<<(4*(y%2))
   def visible(page):return b''.join(page[(y&7)*128+(y>>3)*40:(y&7)*128+(y>>3)*40+40] for y in range(24))
   def pixels():return [visible(p.peek(0x400,1024,'aux')),visible(p.peek(0x400,1024))]
   s.wait(lambda:pixels()==[visible(a) for a in expected],'80x48 pixmap pixels',60)
   s.ok('80x48 pixels, masks and all four edges',True)
   s.ok('Staging stops below $3F01',p.peek(0x3F01,255)==b'\xC7'*255)
   s.ok('Full pixmap preserves occupied RAM',p.peek(0x0800,0xB800,'aux')==ram)
   s.key(b'F');p.stable()
   s.ok('Fit keeps full 80x48 pixels at x1',pixels()==[visible(a) for a in expected])
   s.ok('Fit full pixmap preserves occupied RAM',p.peek(0x0800,0xB800,'aux')==ram)
   s.key(b'O');p.stable()
   s.ok('Rotation refuses 80x48 without changing pixels',pixels()==[visible(a) for a in expected])
   s.ok('Refused rotation preserves staged pixels',p.peek(0x3000,len(data))==data)
   s.ok('Refused rotation preserves occupied RAM',p.peek(0x0800,0xB800,'aux')==ram)
   s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'pixmap exit')
   s.select('SMALL');menu_run(s,p,'DGRVIEW',allow_aux=False);s.wait(lambda:s.has('Pixmap width'),'small pixmap width');s.key(b'14'+RET)
   flip=0;rows=[list(small[y*20:(y+1)*20]) for y in range(12)]
   for key,scale,check,mask in ((None,1,False,False),(b'Z',2,False,False),(b'Z',4,False,False),(b'Z',1,False,False),
                              (b'C',1,True,False),(b'Z',2,True,False),(b'Z',4,True,False),(b'c',4,False,False),
                              (b'M',4,False,True),(b'C',4,True,True),(b'Z',1,True,True),(b'Z',2,True,True),(b'm',2,True,False),
                              (b'H',2,True,False),(b'v',2,True,False),(b'M',2,True,True),(b'h',2,True,True),(b'V',2,True,True),(b'M',2,True,False),
                              (b'H',2,True,False),(b'V',2,True,False),(b'M',2,True,True),(b'R',1,False,False),
                              (b'r',1,False,False),(b'C',1,True,False),(b'Z',2,True,False),(b'H',2,True,False),
                              (b'V',2,True,False),(b'M',2,True,True),(b'r',1,False,False),
                              (b'F',4,False,False),(b'f',4,False,False),(b'C',4,True,False),
                              (b'H',4,True,False),(b'V',4,True,False),(b'M',4,True,True),
                              (b'Z',1,True,True),(b'f',4,True,True),(b'R',1,False,False),
                              (b'F',4,False,False),(b'O',2,False,False),(b'o',2,False,False),
                              (b'O',2,False,False),(b'O',2,False,False),(b'F',4,False,False),
                              (b'H',4,False,False),(b'O',2,False,False),(b'V',2,False,False),
                              (b'C',2,True,False),(b'M',2,True,True),(b'O',2,True,True),
                              (b'O',2,True,True),(b'O',2,True,True),(b'R',1,False,False)):
    if key:s.key(key)
    if key in (b'H',b'h'):flip^=1
    if key in (b'V',b'v'):flip^=2
    if key in (b'H',b'h'):rows=[row[::-1] for row in rows]
    if key in (b'V',b'v'):rows=rows[::-1]
    if key in (b'O',b'o'):rows=[list(row) for row in zip(*rows[::-1])]
    if key in (b'R',b'r'):
     flip=0;rows=[list(small[y*20:(y+1)*20]) for y in range(12)]
    w,h=len(rows[0]),len(rows)
    wanted=[bytearray(1024),bytearray(1024)];x0=(80-w*scale)//2;y0=(48-h*scale)//2
    for py in range(48):
     for px in range(80):
      value=(15 if (px//4+py//4)%2 else 5) if check and not mask else 0
      if x0<=px<x0+w*scale and y0<=py<y0+h*scale:
       sx=(px-x0)//scale;sy=(py-y0)//scale
       b=rows[sy][sx]
       if b&0xF0:value=15 if mask else b&15
      row=py//2;at=(row&7)*128+(row>>3)*40+px//2
      wanted[px%2][at]|=value<<(4*(py%2))
    label='Sprite zoom x'+str(scale)+(' opacity mask' if mask else ' checkerboard' if check else ' black background')
    label+=' flip '+str(flip)+' '+str(w)+'x'+str(h)
    s.wait(lambda:pixels()==[visible(a) for a in wanted],label,60)
    s.ok(label+' pixels and masks',True)
    s.ok(label+' preserves occupied RAM',p.peek(0x0800,0xB800,'aux')==ram)
    if key in (b'O',b'o'):
     s.ok('Rotation preserves staged sprite bytes',p.peek(0x3000,len(small))==small)
    if key in (b'R',b'r'):
     s.ok('Reset preserves staged sprite bytes',p.peek(0x3000,len(small))==small)
   s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'zoom exit')
   s.select('FULL');menu_run(s,p,'DGRVIEW',allow_aux=False);s.wait(lambda:s.has('Pixmap width'),'cancel width');s.key(ESC)
   s.wait(lambda:s.has('Type  Aux'),'cancel exit');s.ok('Width cancellation preserves RAM',p.peek(0x0800,0xB800,'aux')==ram)
   for name,note in (('TOOBIG','over 3840'),('BADPAGE','exceeds 2048')):
    s.select(name);menu_run(s,p,'DGRVIEW',allow_aux=False);s.wait(lambda:s.has(note),name+' refused')
    s.ok(name+' refuses oversized data',True)
    s.ok(name+' preserves occupied RAM',p.peek(0x0800,0xB800,'aux')==ram)
   s.ok('DGRVIEW stack floor preserved',p.peek(floor,8)==b'\xA5'*8)
   p.sync_disks();s.ok('Whole pixmap source volume preserved',Path(p.hdv).read_bytes()==volume)
   return ok_all(s,'DGR full pixmaps')

if __name__=='__main__':raise SystemExit(main())
