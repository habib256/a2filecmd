#!/usr/bin/env python3
"""Purplesoft GRLOAD pairs, original DOS images read only, disposable ProDOS."""
import os,sys,tempfile,time,urllib.request
from pathlib import Path
from xplug import boot_hd,RET,ESC,ok_all
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from test_purple import planes

def dos_binary(path):
 d=path.read_bytes()
 def sector(t,s):
  assert 0<=t<35 and 0<=s<16
  return d[(t*16+s)*256:(t*16+s+1)*256]
 cat=sector(17,0)[1:3];seen=set()
 while cat[0]:
  assert tuple(cat) not in seen;seen.add(tuple(cat));c=sector(*cat);cat=c[1:3]
  for i in range(7):
   e=c[11+i*35:46+i*35]
   if e[0] in (0,255) or e[2]&127!=4:continue
   name=bytes(v&127 for v in e[3:33]).decode().rstrip();ts=e[:2];chunks=[];chain=set()
   while ts[0]:
    assert tuple(ts) not in chain;chain.add(tuple(ts));z=sector(*ts);ts=z[1:3]
    for j in range(12,256,2):
     if z[j]:chunks.append(sector(z[j],z[j+1]))
   raw=b''.join(chunks);length=int.from_bytes(raw[2:4],'little')
   assert len(raw)>=length+4
   yield name,raw[4:4+length]

def main():
 cases={f'G{i}':planes(i) for i in range(10)}
 corpus=Path(os.environ.get('A2FC_PURPLE_CORPUS',str(Path.home()/'src/pom2/disks_5.4/chatmauve')))
 for disk,prefix in [('purplesoft-juillet83-system.dsk','J'),('purplesoft-s2-grload.dsk','S')]:
  if not (corpus/disk).exists():continue
  contents=dict(dos_binary(corpus/disk))
  for name,data in contents.items():
   if name.endswith('.FOTO1') and name[:-1]+'2' in contents:cases[prefix+name[:-6]]=(data,contents[name[:-1]+'2'])
 files={f'WORK/{name}.FOTO{i+1}#062000':plane for name,pair in cases.items() for i,plane in enumerate(pair)}
 with tempfile.TemporaryDirectory(prefix='a2fc-purple-') as tmp:
  with boot_hd(tmp,files,port=6980,plugins=['purple'],chatmauve=os.environ.get('A2FC_RGB','eve')) as(p,s):
   disk=Path(p.hdv);original=disk.read_bytes()
   s.key(b'/');s.select('/WORKHD');s.key(RET);s.select('WORK');s.key(RET);p.stable()
   s.select('G5.FOTO1');before=p.peek(0x800,0xF800,'aux');s.key(RET)
   s.wait(lambda:s.has('ALL /RAM files will be LOST'),'first consent');s.key(b'N');p.stable()
   s.ok('refusal preserves AUX before loading',p.peek(0x800,0xF800,'aux')==before)
   for name,(aux,main) in cases.items():
    s.select(name+'.FOTO2');s.key(RET);s.allow_aux()
    s.wait(lambda:p.peek(0x2000,8192)==main,name+' main plane',60)
    s.ok(name+' exact main plane from FOTO2',True)
    if aux[0x79]>=5:s.ok(name+' exact auxiliary plane from FOTO1',p.peek(0x2000,8192,'aux')==aux)
    if name in ('JIM1','SDDD'):
     time.sleep(.2)
     with urllib.request.urlopen(p.base+'/screen.ppm') as response:Path('/tmp/a2fc-purple-'+name+'-'+os.environ.get('A2FC_BUILD','build')+'.ppm').write_bytes(response.read())
    s.key(ESC);s.wait(lambda:s.has('Type  Aux'),name+' Escape');p.stable()
    s.ok(name+' Escape returns to panels',s.line().startswith(name+'.FOTO2 '))
   s.select('G5.FOTO2');s.key(RET);s.allow_aux()
   s.wait(lambda:p.peek(0x2000,8192,'aux')==cases['G5'][0],'G5 ready')
   s.key(bytes([8]));s.wait(lambda:p.peek(0x2000,8192)==cases['G4'][1],'FOTO2 previous distinct image',60)
   s.ok('Left from FOTO2 skips its own FOTO1',True)
   s.key(bytes([21]));s.wait(lambda:p.peek(0x2000,8192)==cases['G5'][1],'G5 again',60)
   s.key(bytes([21]));s.wait(lambda:p.peek(0x2000,8192,'aux')==cases['G6'][0],'next without consent or duplicate FOTO2',60)
   s.ok('Right skips partner and keeps AUX consent',True)
   s.key(bytes([8]));s.wait(lambda:p.peek(0x2000,8192,'aux')==cases['G5'][0],'previous without consent',60)
   s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'final panels');p.stable()
   before=p.peek(0x800,0xF800,'aux');s.key(RET);s.wait(lambda:s.has('ALL /RAM files will be LOST'),'new session consent');s.key(b'N');p.stable()
   s.ok('new session asks again and refusal preserves AUX',p.peek(0x800,0xF800,'aux')==before)
  s.ok('source disk unchanged',disk.read_bytes()==original)
 return ok_all(s,'Purplesoft')
if __name__=='__main__':raise SystemExit(main())
