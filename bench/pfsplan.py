#!/usr/bin/env python3
"""PFS:Plan native sheets, preflight errors, paging and preservation."""
import sys,tempfile
from pathlib import Path
from xplug import boot_hd,menu_run,RET,ESC,ok_all
from pom2 import ROOT
sys.path.insert(0,str(ROOT/'tools'))
from test_pfsplan import originals,sheet

def main():
 docs={n.lstrip('/'):d for n,d in originals()}
 if len(docs)!=6:raise RuntimeError('Six public PFS:Plan sheets required')
 bad=bytearray(sheet());bad[3584]=1
 specs={n:(d,22,4) for n,d in docs.items()};specs.update(SAMPLE=(sheet(),22,4),BADFORM=(bytes(bad),22,4),NOTPLAN=(sheet(),22,1))
 data={'WORK/'+n+'#%02X%04X'%(t,a):d for n,(d,t,a) in specs.items()}
 with tempfile.TemporaryDirectory(prefix='pfsplan-native-') as tmp:
  with boot_hd(Path(tmp),data,port=6956,plugins=['pfsplan']) as (p,s):
   s.key(b'/');s.select('/WORKHD');s.key(RET);s.select('WORK');s.key(RET);p.stable()
   before=Path(p.hdv).read_bytes();aux=p.peek(0x1000,0xb000,'aux');floor=s.sym['__HIMEM__']-s.sym['__STACKSIZE__'];p.poke(floor,b'\xa5'*8)
   for n in (*docs,'SAMPLE'):
    s.select(n);s.key(RET);s.wait(lambda:s.has('Stored values; no recalculation'),n+' automatic',45);p.stable();s.ok(n+' automatic',True)
    if n=='COSTS.PFS':s.ok('Original personnel value',s.has('C1 Jul = 1371'))
    if n=='SALES.PFS':s.key(b' ');s.wait(lambda:s.has('R5 Total Turntables'),'sales data page',30);s.ok('Sales next page',True)
    if n=='SAMPLE':s.ok('Exact decimal',s.has('C1 Jul = 123.45'))
    s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'reader exit',45);p.stable()
   s.select('BADFORM');s.key(RET);s.wait(lambda:s.has('Malformed PFS:Plan'),'per-cell formula refused',45);s.ok('Unsupported cell formula refused',True);s.ok('No partial sheet',not s.has('Stored values;'))
   s.select('NOTPLAN');menu_run(s,p,'PFSPLAN');s.wait(lambda:s.has('Malformed PFS:Plan'),'File aux refused',45);s.ok('File auxiliary type refused',True)
   s.select('SAMPLE');menu_run(s,p,'PFSPLAN');s.wait(lambda:s.has('C1 Jul = 123.45'),'manual',45);s.ok('Manual reader',True);s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'manual exit',45);p.stable()
   s.ok('AUX preserved',p.peek(0x1000,0xb000,'aux')==aux);s.ok('Stack floor preserved',p.peek(floor,8)==b'\xa5'*8)
   p.sync_disks();s.ok('Whole source volume preserved',Path(p.hdv).read_bytes()==before)
 return ok_all(s,'pfsplan')
if __name__=='__main__':raise SystemExit(main())
