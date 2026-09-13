#!/usr/bin/env python3
"""ProDOS C into a DOS image: actual overlays, MLI and closed disk bytes."""
import os
import sys
import tempfile
from pathlib import Path
from pom2 import Pom2,Session,ROOT,BUILD
from xplug import ok_all
sys.path.insert(0,str(ROOT/'tools'))
from mini33_fixture import read_files
from prodos_read import Image

def demo(image):
 e=next(e for e in image.entries(2) if e[1:5]==b'DEMO')
 return {e[1:1+(e[0]&15)].decode():e for e in image.entries(int.from_bytes(e[17:19],'little'))}

def main():
 with tempfile.TemporaryDirectory(prefix='dosimage-ui-') as d:
  hd=Path(d)/'test.hdv';cpu='6502' if BUILD.name=='build-6502' else '65C02'
  original=(BUILD/f'A2FILECMD-{cpu}-BOOT.hdv').read_bytes();hd.write_bytes(original)
  before=Image(original);entries=demo(before);old=before.read(entries['DOS33.DSK'])
  with Pom2(hd,port=6897,exe=os.environ.get('POM2_DOS','/tmp/a2fc-dos-host')) as p:
   s=Session(p);s.boot();s.select('DEMO');s.key(b'\r');p.stable();s.select('HELLO')
   s.key(b'\t');s.select('DOS33.DSK',x=40);s.key(b'\r')
   s.wait(lambda:s.has('GREETINGS'),'DOS image catalog');p.stable();s.key(b'\t');s.key(b'C')
   s.wait(lambda:s.has('Copy HELLO into '),'image confirmation',60)
   s.ok('Image untouched before consent',hd.read_bytes()==original)
   s.key(b'N');p.stable();s.ok('Cancelled image copy preserves volume',hd.read_bytes()==original)
   for name in ('HELLO','HGR.RLE','README'):
    s.select(name);s.key(b'C');s.wait(lambda:s.has('Copy '+name+' into '),'image copy '+name,60)
    aux=p.peek(0x1000,0xB000,'aux');s.key(b'Y')
    s.wait(lambda:s.has('Copied to DOS 3.3 image; source kept.') or s.has('original image kept.'),'image committed '+name,120)
    assert s.has('Copied to DOS 3.3 image; source kept.'),'\n'.join(s.rows())
    s.ok('AUX preserved for '+name,aux==p.peek(0x1000,0xB000,'aux'))
    s.ok(name+' visible in target catalog',any(name in r[40:] for r in s.rows()[1:20]))
   s.key(b'C');s.wait(lambda:s.has('Copy README into '),'collision consent');s.key(b'Y')
   s.wait(lambda:s.has('Name exists or DOS catalog inconsistent; original image kept.'),'collision refused',120)
  after=Image(hd.read_bytes());result_entries=demo(after);result=read_files(after.read(result_entries['DOS33.DSK']))
  for name,value in read_files(old).items():s.ok('Preserved original DOS file '+name,result[name]==value)
  for name,kind in (('HELLO',2),('HGR.RLE',4),('README',0)):
   e=entries[name];payload=before.read(e);expected=payload
   if kind:expected=(e[31:33] if kind==4 else b'')+len(payload).to_bytes(2,'little')+payload
   s.ok(name+' exact DOS bytes and type',result[name]['type']==kind and result[name]['data']==expected+bytes((-len(expected))%256))
   s.ok(name+' source unchanged',after.read(result_entries[name])==payload)
  s.ok('No temporary or backup remains',not {'A2FC.DOS','A2FC.BAK'}&result_entries.keys())
  return ok_all(s,'DOS image copy')
if __name__=='__main__':sys.exit(main())
