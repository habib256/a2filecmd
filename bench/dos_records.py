#!/usr/bin/env python3
"""DOSREC on disposable real DOS drives, DSK and 2MG; MAIN/AUX preservation."""
import sys
import tempfile
from pathlib import Path
from xplug import boot_hd,menu_run,RET,ESC,ok_all
from pom2 import ROOT
sys.path.insert(0,str(ROOT/'tools'))
from mini33_fixture import make_disk,offset
from take1_ref import DosImage
from prodos_read import Image


def main():
    disk=bytearray(make_disk([('RECORDS',0,b'A\0END'+bytes(251)+b'B'*256+b'C'*256)]))
    t,s=DosImage(disk).find(b'RECORDS');ts=offset(t,s);disk[ts+14:ts+16]=b'\0\0';disk=bytes(disk)
    head=bytearray(64);head[:4]=b'2IMG';head[24:28]=(64).to_bytes(4,'little');head[28:32]=len(disk).to_bytes(4,'little')
    data={'WORK/RECORDS.DSK#060000':disk,'WORK/RECORDS.2MG#060000':bytes(head)+disk}
    with tempfile.TemporaryDirectory(prefix='dos-record-native-') as tmp:
        tmp=Path(tmp);floppy=tmp/'records.dsk';floppy.write_bytes(disk)
        with boot_hd(tmp,data,port=6942,plugins=['dosrec'],floppy2=floppy) as (p,s):
            s.key(b'/');s.select('/WORKHD');s.key(RET);s.select('WORK');s.key(RET);p.stable()
            hd_before=Path(p.hdv).read_bytes();before=p.peek(0x1000,0xb000,'aux');floor=s.sym['__HIMEM__']-s.sym['__STACKSIZE__'];p.poke(floor,b'\xa5'*8)
            for name in ('RECORDS.DSK','RECORDS.2MG','physical'):
                if name=='physical':
                    s.key(b'/');p.stable()
                    for _ in range(15):
                        if 'DOS 3.3 disk' in s.line(1):break
                        s.key(b'\x0a')
                    s.key(RET)
                else:s.select(name);s.key(RET)
                s.wait(lambda:s.has('RECORDS'),'DOS mounted',30);s.select('RECORDS');menu_run(s,p,'DOSREC')
                s.wait(lambda:s.has('Record length'),'length editor',30);s.key(RET)
                s.wait(lambda:s.has('DOS record 0'),'record display',30);p.stable()
                s.ok(name+' NUL preserved',s.has('41 00 45 4E 44') and s.has('EOF unknown'))
                s.key(b'N');s.wait(lambda:s.has('DOS record 1'),'hole record',10);p.stable();s.ok(name+' hole distinguished',s.has('-- -- --'),'' if s.has('-- -- --') else '\n'.join(s.rows()))
                s.key(b'N');s.wait(lambda:s.has('DOS record 2'),'after hole',10);p.stable();s.ok(name+' after hole',s.has('43 43 43'))
                s.key(b'P');s.wait(lambda:s.has('DOS record 1'),'previous record',10)
                s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'viewer exit',30)
                if name!='physical':
                    s.key(b'/');s.select('/WORKHD');s.key(RET);s.select('WORK');s.key(RET)
            s.ok('AUX preserved',p.peek(0x1000,0xb000,'aux')==before)
            s.ok('Stack floor preserved',p.peek(floor,8)==b'\xa5'*8)
            p.eject(1);s.ok('Physical DOS bytes preserved',floppy.read_bytes()==disk)
            p.sync_disks();s.ok('Whole source volume preserved',Path(p.hdv).read_bytes()==hd_before)
            image=Image((tmp/'WORKHD.hdv').read_bytes());work=next(e for e in image.entries(2) if e[1:5]==b'WORK');key=int.from_bytes(work[17:19],'little')
            sources={e[1:1+(e[0]&15)].decode():image.read(e) for e in image.entries(key)}
            s.ok('DSK/2MG bytes preserved',sources['RECORDS.DSK']==disk and sources['RECORDS.2MG']==bytes(head)+disk)
    return ok_all(s,'dos_records')

if __name__=='__main__':raise SystemExit(main())
