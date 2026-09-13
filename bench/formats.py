#!/usr/bin/env python3
"""DOS headers, legacy DUET, IDENT and confirmed repair on disposable images."""
import sys,tempfile
from pathlib import Path
from xplug import boot_hd,menu_run,ok_all,RET,TAB,ESC
from fixtypes import open_dir,run_fixtypes,catalog
from run import volume
from pom2 import BUILD
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import mkdos33,mkdemo

def main():
 tune=mkdemo.duet();payload=bytes((i*17+3)&255 for i in range(601))
 dos=mkdos33.build([('M.CANON',4,b'\x00\x20'+len(tune).to_bytes(2,'little')+tune),('BINARY',4,b'\x34\x12'+len(payload).to_bytes(2,'little')+payload)])
 with tempfile.TemporaryDirectory(prefix='a2fc-formats-') as d:
  tmp=Path(d);stage=tmp/'output';(stage/'OUT').mkdir(parents=True);(stage/'OLD').mkdir()
  legacy=tune+bytes((-(len(tune)+4))%256)
  (stage/'OLD/M.LEGACY#060000').write_bytes(legacy)
  target=volume(stage,tmp/'OUTPUT.po','OUTPUT',280)
  files={'WORK/SOURCE.DSK':dos}
  with boot_hd(tmp,files,port=6920,plugins=['duet','ident','fixtypes'],floppy2=target) as (p,s):
   floor=s.sym['__HIMEM__']-s.sym['__STACKSIZE__'];p.poke(floor,b'\xA5'*8);aux=p.peek(0x1000,0xB000,'aux')
   s.key(TAB);open_dir(s,p,40,'/OUTPUT','OUT')
   s.key(TAB);open_dir(s,p,0,'/WORKHD','WORK');s.select('SOURCE.DSK');s.key(RET)
   s.wait(lambda:s.has('M.CANON'),'DOS directory');p.stable()
   for name in ('BINARY','M.CANON'):s.select(name);s.key(b' ');p.stable()
   s.key(b'C');s.wait(lambda:s.has('2 files extracted.'),'exact DOS extraction',60);p.stable()
   s.ok('DOSGET copies both marked files and restores the panels',s.has('M.CANON') and any('BINARY' in r[40:] for r in s.rows()))
   s.key(TAB);s.select('BINARY',40);s.ok('BIN keeps address $1234 and exact EOF 601','$1234' in s.line(40) and '601' in s.line(40))
   s.select('M.CANON',40);p.rq('/speed',{'preset':'1x'});s.key(RET)
   s.wait(lambda:s.has('Electric Duet - M.CANON'),'Return opens extracted M.*',30);s.ok('Return opens untyped DOS M.*',True)
   s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'player exit');p.stable();p.rq('/speed',{'preset':'max'})
   menu_run(s,p,'IDENT');s.wait(lambda:s.has('Electric Duet compatible'),'IDENT recognizes extraction');s.ok('IDENT reads the complete DOS song',True)
   line=run_fixtypes(s,p,b'Y');s.ok('confirmed FIXTYPES repairs exact extraction',line.startswith('1 typed, 0 renamed, 0 skipped, 0 failed'),line)
   open_dir(s,p,40,'/OUTPUT','OLD');s.select('M.LEGACY',40)
   menu_run(s,p,'IDENT');s.wait(lambda:s.has('Electric Duet compatible'),'IDENT recognizes padding');s.ok('IDENT recognizes old padded extraction',True)
   line=run_fixtypes(s,p,b'N');s.ok('N leaves legacy attributes intact',line.startswith('0 typed, 0 renamed, 1 skipped, 0 failed'),line)
   line=run_fixtypes(s,p,b'Y');s.ok('Y repairs the legacy file without renaming',line.startswith('1 typed, 0 renamed, 0 skipped, 0 failed'),line)
   s.ok('AUX unchanged',p.peek(0x1000,0xB000,'aux')==aux);s.ok('stack floor unchanged',p.peek(floor,8)==b'\xA5'*8)
  out=catalog(target,'OUT');old=catalog(target,'OLD')
  s.ok('physical output: BIN address and every byte preserved',out.get('BINARY')==(6,0x1234,payload))
  s.ok('physical output: exact DUET EOF and repaired type',out.get('M.CANON')==(0xD5,0xD0E7,tune))
  s.ok('physical output: old padding and name untouched',old.get('M.LEGACY')==(0xD5,0xD0E7,legacy))
 return ok_all(s,'formats')
if __name__=='__main__':raise SystemExit(main())
