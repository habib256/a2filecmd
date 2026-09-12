#!/usr/bin/env python3
"""Foreground PT3 on a disposable disk: frame output, pause, exit and bad data."""
import re
import sys
import time
import tempfile
from pathlib import Path
from xplug import boot_hd,RET,ESC,ok_all
from pom2 import BUILD
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from prodos_read import Image
from mkdemo import fanfare
from sample_media import sample_directory



def autumn():
    import os
    path=Path(os.environ.get('A2FC_SAMPLE_DISK',str(Path.home()/'src/pom2/hdv/GISTDATA.hdv')))
    im=Image(path.read_bytes());k=sample_directory(im)
    e=next(e for e in im.entries(k) if e[1:1+(e[0]&15)].decode()=='AUTUMN.PT3')
    return im.read(e)


def ay_snapshot(p, name):
    # Read the card's actual registers from the disposable trace host.
    time.sleep(.15)
    log=(Path(p.hdv).parent/'pom2.log').read_text()
    matches=re.findall(r'AYTRACE ([0-9A-F]{32}) ([0-9A-F]{2})',log)
    assert matches, 'Use POM2=/tmp/a2fc-pt3-trace (bench/build_pt3_trace.py)'
    return bytes.fromhex(matches[-1][0]+matches[-1][1])


def main():
    raw=autumn()
    files={'WORK/AUTUMN.PT3#000000':raw,'WORK/BAD.PT3#000000':raw[:203]}
    bad=bytearray(raw);bad[107:109]=(len(raw)+1).to_bytes(2,'little')
    files['WORK/SAMPLE.PT3#000000']=bytes(bad)
    bad=bytearray(raw);table=int.from_bytes(raw[103:105],'little')+2*raw[201]
    bad[table:table+2]=(len(raw)+1).to_bytes(2,'little')
    files['WORK/PATTERN.PT3#000000']=bytes(bad)
    bad=bytearray(raw);start=int.from_bytes(raw[table:table+2],'little')
    bad[start:start+300]=bytes([0x20])*300
    files['WORK/LOOP.PT3#000000']=bytes(bad)
    bad=bytearray(raw);bad[start:start+3]=bytes([1,2,0x50])
    files['WORK/EFFECTS.PT3#000000']=bytes(bad)
    files['WORK/WELCOME.MB#061000']=fanfare()
    addr=int(re.search(r'al ([0-9A-Fa-f]{6}) \._pt_regs',(BUILD/'pt3.lbl').read_text())[1],16)
    with tempfile.TemporaryDirectory(prefix='a2fc-pt3-native-') as tmp:
        with boot_hd(Path(tmp),files,port=6994,plugins=['pt3']) as (p,s):
            s.key(b'/');s.select('/WORKHD');s.key(RET);s.select('WORK');s.key(RET);p.stable()
            s.select('AUTUMN.PT3');before=bytes(p.peek(0x1000,0xB000,'aux'))
            p.rq('/speed',{'preset':'1x'})
            s.key(RET);s.wait(lambda:s.has('ProTracker 3 - AUTUMN.PT3'),'PT3 playback',30)
            values=[]
            for _ in range(20):
                values.append(bytes(p.peek(addr,14)));time.sleep(.1)
            s.ok('PT3 generates changing AY frames',len(set(values))>4)
            s.ok('PT3 opens tones or noise with nonzero volumes',any(any(v[8:11]) and v[7]!=63 for v in values))
            s.ok('AY hardware receives audible register values',any(ay_snapshot(p,'playing')[8:11]))
            s.key(b'P');time.sleep(.15);paused=bytes(p.peek(addr,14));time.sleep(.4)
            s.ok('P pauses decoder frames',bytes(p.peek(addr,14))==paused)
            ay=ay_snapshot(p,'paused');s.ok('Pause silences the AY',ay[7]&63==63 and not any(ay[8:11]))
            s.key(b'P');s.wait(lambda:bytes(p.peek(addr,14))!=paused,'PT3 resume',5)
            s.ok('P resumes PT3',True)
            p.rq('/speed',{'preset':'max'})
            s.wait(lambda:s.has('Type  Aux'),'whole AUTUMN.PT3 finishes',60)
            s.ok('AUTUMN.PT3 plays through to its end',not s.has('Invalid PT3.'))
            p.stable();s.select('AUTUMN.PT3');p.rq('/speed',{'preset':'1x'})
            s.key(RET);s.wait(lambda:s.has('ProTracker 3 - AUTUMN.PT3'),'second playback',30)
            s.ok('PT3 preserves auxiliary RAM',bytes(p.peek(0x1000,0xB000,'aux'))==before)
            s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'panels after PT3',30)
            ay=ay_snapshot(p,'stopped');s.ok('Exit silences the AY',ay[7]&63==63 and not any(ay[8:11]))
            s.ok('Exit disables VIA interrupts',ay[16]&127==0)
            p.rq('/speed',{'preset':'max'});p.stable()
            s.select('BAD.PT3');s.key(RET)
            s.wait(lambda:s.has('Bad/large PT3'),'malformed module refused',30)
            s.ok('truncated PT3 returns safely',s.has('Type  Aux'))
            for name in ('SAMPLE.PT3','PATTERN.PT3','LOOP.PT3','EFFECTS.PT3'):
                s.select(name);s.key(RET)
                s.wait(lambda:s.has('Invalid PT3.'),name+' rejected',30)
                s.ok(name+' decoder guard returns safely',s.has('Type  Aux'))
            s.select('WELCOME.MB');p.rq('/speed',{'preset':'1x'});s.key(RET)
            s.wait(lambda:s.has('MB1 - WELCOME.MB'),'MB1 regression',30)
            p.rq('/speed',{'preset':'max'});s.wait(lambda:s.has('Type  Aux'),'MB1 end',30)
            s.ok('MB1 still opens and finishes after PT3',True)
            if BUILD.name=='build':
                with tempfile.TemporaryDirectory(prefix='a2fc-pt3-nocard-') as other:
                    with boot_hd(Path(other),{'WORK/AUTUMN.PT3#000000':raw},port=6996,plugins=['pt3'],preset='iic') as (p2,s2):
                        s2.key(b'/');s2.select('/WORKHD');s2.key(RET);s2.select('WORK');s2.key(RET)
                        s2.select('AUTUMN.PT3');s2.key(RET)
                        s2.wait(lambda:s2.has('No Mockingboard.'),'no card',30)
                        s.ok('No Mockingboard: clear refusal and intact panels',s2.has('Type  Aux'))
    return ok_all(s,'pt3')


if __name__=='__main__':sys.exit(main())
