#!/usr/bin/env python3
"""Direct MCS audio on disposable write-protected DOS disks and images."""
import re
import sys
import tempfile
import time
from pathlib import Path
from xplug import boot_hd,menu_run,RET,ESC,ok_all
from pom2 import ROOT,BUILD
from pt3 import ay_snapshot
sys.path.insert(0,str(ROOT/'tools'))
from mini33_fixture import make_disk
from mcs_ref import fixture
from mcs_score_ref import fixture as score_fixture,score


def main():
    song=fixture([(60,12),(64,12),(68,12),(72,12)]*8,
                 [(84,12),(88,12),(92,12),(96,12)]*8)
    bad=bytearray(song);bad[0]=255
    main,obj=score_fixture([(31,10,16)]+[(4,10,100+i*4) for i in range(64)]+[(31,10,500)],
                           [(31,10,16)]+[(4,30,100+i*4) for i in range(64)]+[(31,10,500)])
    normalized=score(main,obj)
    raw=make_disk([('SONG',0x84,b'\0\x10\0\x09'+song),
                   ('BAD',4,b'\0\x10\0\x09'+bad),
                   ('SCORE',4,b'\0A'+len(main).to_bytes(2,'little')+main),
                   ('SCORE.OBJ',4,b'\0t'+len(obj).to_bytes(2,'little')+obj),
                   ('ORPHAN',4,b'\0A'+len(main).to_bytes(2,'little')+main)])
    head=bytearray(64);head[:4]=b'2IMG';head[24:28]=(64).to_bytes(4,'little');head[28:32]=len(raw).to_bytes(4,'little')
    files={'WORK/DIRECT.DSK#060000':raw,'WORK/DIRECT.2MG#060000':bytes(head)+raw}
    addr=int(re.search(r'al ([0-9A-Fa-f]{6}) \._mc_regs',(BUILD/'mcsplay.lbl').read_text())[1],16)
    with tempfile.TemporaryDirectory(prefix='dosmcs-native-') as tmp:
        tmp=Path(tmp);floppy=tmp/'SOURCE.DSK';floppy.write_bytes(raw);floppy.chmod(0o444)
        with boot_hd(tmp,files,port=6933,plugins=['dosmcs','mcsimport','mcsplay'],floppy2=floppy) as (p,s):
            hd=Path(p.hdv);before=hd.read_bytes()
            s.key(b'/');s.select('/WORKHD');s.key(RET);s.select('WORK');s.key(RET);p.stable()
            aux=p.peek(0x1000,0xb000,'aux');floor=s.sym['__HIMEM__']-s.sym['__STACKSIZE__']
            p.poke(floor,b'\xa5'*8)
            s.key(b'\t');s.key(b'/');p.stable()
            for _ in range(15):
                if 'DOS 3.3 disk' in s.line(41):break
                s.key(b'\x0a')
            s.key(RET);s.wait(lambda:s.has('SONG') and '/DOS 3.3' in s.rows()[0],'real DOS catalog',60)
            for backend in ('Disk II','DSK','2IMG'):
                panel=40 if backend=='Disk II' else 0
                p.rq('/speed',{'preset':'1x'})
                s.select('SONG',panel);menu_run(s,p,'DOSMCS')
                s.wait(lambda:s.has('Music Construction Set - SONG'),'direct DOS playback',30)
                s.ok(backend+': complete export in MAIN',p.peek(0x3700,2304)==song)
                time.sleep(.3)
                s.ok(backend+': audible AY volumes',any(ay_snapshot(p,'DOSMCS')[8:11]))
                s.key(b'P');time.sleep(.1);paused=p.peek(addr,28);time.sleep(.2)
                s.ok(backend+': pause freezes sequencer',p.peek(addr,28)==paused)
                s.ok(backend+': pause silences card',not any(ay_snapshot(p,'pause')[8:11]))
                s.key(b'P');s.wait(lambda:p.peek(addr,28)!=paused,'resume',5)
                s.key(b'+');s.key(b'-');s.key(b'R');s.key(ESC)
                s.wait(lambda:s.has('Type  Aux'),'panels after sound',30);p.stable()
                s.ok(backend+': Escape silences card',not any(ay_snapshot(p,'exit')[8:11]))
                p.rq('/speed',{'preset':'max'})
                s.select('SONG',panel);menu_run(s,p,'DOSMCS')
                s.wait(lambda:s.has('Type  Aux'),'natural end',60)
                s.ok(backend+': natural end silences card',not any(ay_snapshot(p,'end')[8:11]))
                s.select('BAD',panel);menu_run(s,p,'DOSMCS')
                s.wait(lambda:s.has('Bad DOS MCS score/export'),'malformed export refused',30)
                s.ok(backend+': bad source leaves card silent',not any(ay_snapshot(p,'bad')[8:11]))
                for selected in ('SCORE','SCORE.OBJ'):
                    p.rq('/speed',{'preset':'1x'})
                    s.select(selected,panel);menu_run(s,p,'DOSMCS')
                    s.wait(lambda:s.has('Music Construction Set - '+selected),'paired DOS score playback',30)
                    s.ok(backend+': '+selected+' exact imported MAIN score',p.peek(0x3700,2304)==normalized)
                    time.sleep(.2)
                    s.ok(backend+': '+selected+' audible AY volumes',any(ay_snapshot(p,'DOS score')[8:11]))
                    s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'panels after score',30);p.stable()
                    s.ok(backend+': '+selected+' Escape silences card',not any(ay_snapshot(p,'score exit')[8:11]))
                p.rq('/speed',{'preset':'max'})
                s.select('ORPHAN',panel);menu_run(s,p,'DOSMCS')
                s.wait(lambda:s.has('Bad DOS MCS score/export'),'missing pair refused',30)
                s.ok(backend+': missing pair keeps card silent',not any(ay_snapshot(p,'orphan')[8:11]))
                s.ok(backend+': AUX RAM-disk storage unchanged',p.peek(0x1000,0xb000,'aux')==aux)
                if backend=='Disk II':
                    p.eject(1);s.ok('physical DOS source unchanged',floppy.read_bytes()==raw)
                    s.key(b'\t');s.select('DIRECT.DSK');s.key(RET)
                elif backend=='DSK':
                    s.key(ESC);s.wait(lambda:s.has('DIRECT.2MG'),'leave DOS image',30)
                    s.select('DIRECT.2MG');s.key(RET)
                if backend!='2IMG':s.wait(lambda:s.has('SONG') and s.has('BAD'),'DOS image catalog',30);p.stable()
            s.ok('C-stack floor unchanged',p.peek(floor,8)==b'\xa5'*8)
            p.sync_disks()
        s.ok('ProDOS source volume and metadata unchanged',hd.read_bytes()==before)
        s.ok('DOS source unchanged after shutdown',floppy.read_bytes()==raw)
    return ok_all(s,'direct DOS MCS')


if __name__=='__main__':raise SystemExit(main())
