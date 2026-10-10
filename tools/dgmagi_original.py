"""Read-only oracle: execute the original DPC drivers in the bounded 6502 CPU.
No original binaries are redistributed. Main writes target the emulated RAM only.
"""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from mos6502 import CPU
root=Path.home()/'.cache/a2fc/gmagic/x'
class DPC(CPU):
 def __init__(self,data):
  super().__init__();self.aux=bytearray(65536);self.store=False;self.page=False;self.hires=False
  self.m[0xD000:0xDF00]=next(root.rglob('DPICDRAWH#BD000')).read_bytes()
  low=next(root.rglob('DPICDRAWL#B9500')).read_bytes();self.m[0x9500:0x9500+len(low)]=low
  self.m[0x8000:0x8000+len(data)]=data;self.m[:2]=bytes([0,128]);self.m[0x951F]=255
  self.pc=0x9500;self.push(0xFF);self.push(0xEF)
 def sw(self,a):
  if a==0xC000:self.store=False
  elif a==0xC001:self.store=True
  elif a==0xC054:self.page=False
  elif a==0xC055:self.page=True
  elif a==0xC056:self.hires=False
  elif a==0xC057:self.hires=True
 def rd(self,a):
  self.sw(a)
  if a==0xC018:return 128 if self.store else 0
  if a==0xC01D:return 128 if self.hires else 0
  if 0x2000<=a<0x4000 and self.store and self.hires and self.page:return self.aux[a]
  return super().rd(a)
 def wr(self,a,v):
  self.sw(a)
  if 0x2000<=a<0x4000 and self.store and self.hires and self.page:self.aux[a]=v
  else:super().wr(a,v)
 def render(self):
  while self.pc!=0xFFF0:
   if self.steps>30000000:raise ValueError('loop')
   self.ops[self.fetch()]();self.steps+=1
  return bytes(self.aux[0x2000:0x4000]+self.m[0x2000:0x4000])
def stripped(data):
 out=bytearray();i=0
 while i<len(data):
  t=data[i]>>4;n=1 if t in(0,2,4) else 2 if t in(3,5,6) else 3
  if t not in(1,3,5):out+=data[i:i+n]
  i+=n
 return bytes(out)
if __name__=='__main__':
 f=next(root.rglob('PAL560.DPC#*'));d=stripped(f.read_bytes());(Path(sys.argv[1] if len(sys.argv)>1 else '/tmp/a2fc-v1-corpus')/'pal-no-text.dpc').write_bytes(d)
 c=DPC(d);b=c.render();(Path(sys.argv[1] if len(sys.argv)>1 else '/tmp/a2fc-v1-corpus')/'pal-original.raw').write_bytes(b);print('original steps',c.steps)
