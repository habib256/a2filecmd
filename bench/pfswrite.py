#!/usr/bin/env python3
"""PFS:Write native: public documents, refusal, paging and preservation."""
import sys,tempfile
from pathlib import Path
from xplug import boot_hd,menu_run,RET,ESC,ok_all
from pom2 import ROOT
sys.path.insert(0,str(ROOT/'tools'))
from test_pfswrite import originals,pfs

def main():
    docs=list(originals())
    if len(docs)!=8:raise RuntimeError('Eight unique public PFS:Write documents required')
    specs={n.lstrip('/'):(d,22,2) for _,_,n,d in docs}
    specs.update(PAGES=(pfs(b'Line\r'*100),22,2),BADPFS=(pfs()+b'X',22,2),BADCOUNT=(pfs()[:6]+b'\0\0'+pfs()[8:],22,2),NOTWRITE=(pfs(),22,1))
    specs['SETTINGS']=(b'\x84\0\0\0\x03\0'+pfs()[6:10]+b'\xa5'*1014+pfs()[1024:],22,2)
    data={'WORK/'+n+'#%02X%04X'%(t,a):d for n,(d,t,a) in specs.items()}
    with tempfile.TemporaryDirectory(prefix='pfswrite-native-') as tmp:
        with boot_hd(Path(tmp),data,port=6947,plugins=['pfswrite']) as (p,s):
            s.key(b'/');s.select('/WORKHD');s.key(RET);s.select('WORK');s.key(RET);p.stable()
            original=Path(p.hdv).read_bytes();aux=p.peek(0x1000,0xb000,'aux');floor=s.sym['__HIMEM__']-s.sym['__STACKSIZE__'];p.poke(floor,b'\xa5'*8)
            expected={'NAME.PFS':'P.S.  The Board','MEMO.PFS':'John Leader','HOUSE.PFS':'Hope Chamberlain','ANNUAL.PFS':'ANNUAL REPORT','FLYER.PFS':'SPEND CHRISTMAS','LETTER.PFS':'William Anthony','EXTRA.PFS':'This is an extra','NILSSON':'TO: NILSSON CONSTRUCTION','PAGES':'Line','SETTINGS':'Hello'}
            for n,label in expected.items():
                s.select(n);s.key(RET)
                s.wait(lambda:s.has(label),n+' automatic',30);p.stable();s.ok(n+' automatic',True)
                if n=='PAGES':
                    s.key(b' ');s.wait(lambda:s.rows()[1].strip()=='Line','next page',15);s.ok('Next page',True)
                s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'reader exit',30);p.stable()
            s.select('BADCOUNT');s.key(RET);s.wait(lambda:s.has('Malformed PFS:Write'),'bad count refused',30);s.ok('Bad count refused',True)
            for n in ('BADPFS','NOTWRITE'):
                s.select(n);menu_run(s,p,'PFSWRITE');s.wait(lambda:s.has('Malformed PFS:Write'),'bad file refused',30);s.ok(n+' refused',True)
            s.select('EXTRA.PFS');menu_run(s,p,'PFSWRITE');s.wait(lambda:s.has('This is an extra'),'manual reader',30);s.ok('Manual reader',True);s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'manual exit',30);p.stable()
            s.ok('AUX preserved',p.peek(0x1000,0xb000,'aux')==aux);s.ok('Stack floor preserved',p.peek(floor,8)==b'\xa5'*8)
            p.sync_disks();s.ok('Whole source volume preserved',Path(p.hdv).read_bytes()==original)
    return ok_all(s,'pfswrite')

if __name__=='__main__':raise SystemExit(main())
