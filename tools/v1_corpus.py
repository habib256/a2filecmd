#!/usr/bin/env python3
"""Extract local 1.0 document fixtures without modifying their disk images.
Outputs are exclusively created; an identical existing extraction is kept.
No download and no original files are redistributed by this tool.
"""
import argparse,hashlib
from pathlib import Path
from corpus_read import images,files
from legacy_corpus import dos_files
SIGNATURE=bytes.fromhex('08E70000D6100100')
FILER=bytes(c|128 for c in b'AFILER 1.0')

def selected(t,a,d):
 return (t==160 and not a and bool(d)) or (t==241 and not a and d[:2]==b'MW') or (t==6 and d[:10]==FILER) or (t==244 and d[:8]==SIGNATURE)

def exclusive(path,data):
 if path.exists():
  if path.read_bytes()!=data:raise ValueError('different extraction already exists: '+str(path))
  return
 with path.open('xb') as f:
  if f.write(data)!=len(data):raise OSError('short extraction')

def extract(root,out,authored=None):
 out.mkdir(parents=True,exist_ok=True);count=0
 for p in sorted(root.rglob('*')):
  if not p.is_file() or p.suffix.lower() not in ('.zip','.dsk','.po','.2mg'):continue
  before=hashlib.sha256(p.read_bytes()).digest()
  for member,data in images(p):
   try:fs,entries=files(data)
   except ValueError:
    # Only the observed byte-swapped sector-size field is admitted here;
    # the ordinary filesystem dispatcher remains strict. Export AFILER only.
    if len(data)!=143360 or data[17*4096+52:17*4096+56]!=bytes([35,16,1,0]):continue
    entries=[x for x in dos_files(data,bank_street_geometry=True) if x[3][:10]==FILER]
   for name,t,a,d in entries:
    if not selected(t,a,d):continue
    label=Path(member).stem+'__'+name.strip('/').replace('/','__')+'#%02X%04X'%(t,a)
    exclusive(out/label,d);count+=1
  if hashlib.sha256(p.read_bytes()).digest()!=before:raise ValueError('source changed during read: '+str(p))
 if authored:
  before=authored.read_bytes()
  for n,t,a,d in dos_files(before):
   if t==244 and d[:8]==SIGNATURE and n in ('EMPTY','FORMULA','GRID','LABEL','MULTI','NUMBER','SAMPLE'):
    exclusive(out/('MP_'+n+'.bin'),d);count+=1
  if authored.read_bytes()!=before:raise ValueError('authored source changed during read')
 return count
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('images',type=Path);ap.add_argument('output',type=Path);ap.add_argument('--authored-multiplan',type=Path);a=ap.parse_args()
 print(extract(a.images,a.output,a.authored_multiplan),'selected file occurrences')
