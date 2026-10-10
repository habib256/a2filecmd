#!/usr/bin/env python3
"""PFS:File native records, preflight refusals, paging and preservation."""
import sys,tempfile
from pathlib import Path
from xplug import boot_hd,menu_run,RET,ESC,ok_all
from pom2 import ROOT
sys.path.insert(0,str(ROOT/'tools'))
from test_pfsfile import real_files,database

def main():
    originals={n.lstrip('/'):d for n,d in real_files()}
    if len(originals)!=2:raise RuntimeError('Two public PFS:File databases required')
    bad=bytearray(database());bad[64*128+126:64*128+128]=(127).to_bytes(2,'little')
    specs={n:(d,22,1) for n,d in originals.items()}
    specs.update(SAMPLE=(database(),22,1),EMPTY=(database([]),22,1),BADLINK=(bytes(bad),22,1),NOTFILE=(database(),22,4))
    data={'WORK/'+n+'#%02X%04X'%(t,a):d for n,(d,t,a) in specs.items()}
    with tempfile.TemporaryDirectory(prefix='pfsfile-native-') as tmp:
        with boot_hd(Path(tmp),data,port=6949,plugins=['pfsfile']) as (p,s):
            s.key(b'/');s.select('/WORKHD');s.key(RET);s.select('WORK');s.key(RET);p.stable()
            original=Path(p.hdv).read_bytes();aux=p.peek(0x1000,0xb000,'aux');floor=s.sym['__HIMEM__']-s.sym['__STACKSIZE__'];p.poke(floor,b'\xa5'*8)
            for n,label in (('STAFF.PFS','Name: Woolf, James'),('COSTFILE.PFS','Pay to: West Coast Gas'),('SAMPLE','Name: Alice'),('EMPTY','[0]')):
                s.select(n);s.key(RET);s.wait(lambda:s.has(label),n+' automatic',45);p.stable();s.ok(n+' automatic',True)
                if n=='STAFF.PFS':s.ok('Staff identifier and salary',s.has('Employee #: A0139') and s.has('Monthly Salary: 1,000'))
                if n=='COSTFILE.PFS':
                    s.ok('Multiline address',s.has('44189 S. Main St.'))
                    s.key(b' ');s.wait(lambda:s.has('Record 3/41'),'third record page',30);p.stable();s.ok('Next page in record chain',s.has('Record 3/41'))
                s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'reader exit',45);p.stable()
            s.select('BADLINK');s.key(RET);s.wait(lambda:s.has('Malformed PFS:File'),'shared block refused',45);s.ok('Aliased form/data refused',True);s.ok('No partial record displayed',not s.has('Record 1/'))
            s.select('NOTFILE');menu_run(s,p,'PFSFILE');s.wait(lambda:s.has('Malformed PFS:File'),'wrong auxiliary type',45);s.ok('Plan refused',True)
            s.select('SAMPLE');menu_run(s,p,'PFSFILE');s.wait(lambda:s.has('Name: Alice'),'manual reader',45);s.ok('Manual reader',True);s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'manual exit',45);p.stable()
            s.ok('AUX preserved',p.peek(0x1000,0xb000,'aux')==aux);s.ok('Stack floor preserved',p.peek(floor,8)==b'\xa5'*8)
            p.sync_disks();s.ok('Whole source volume preserved',Path(p.hdv).read_bytes()==original)
    return ok_all(s,'pfsfile')

if __name__=='__main__':raise SystemExit(main())
