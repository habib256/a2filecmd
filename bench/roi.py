#!/usr/bin/env python3
"""Preferences, NAV and marked MOVE, only on disposable volumes."""
import subprocess
import sys
import tempfile
from pathlib import Path
from xplug import boot_hd, menu_run, RET, ESC, TAB, ok_all
from pom2 import Pom2, Session, ROOT
sys.path.insert(0,str(ROOT/'tools'))
from prodos_read import Image


def folder(s,p,name,x=0,volume='/WORKHD'):
    s.key(b'/');s.select(volume,x);s.key(RET);p.stable()
    s.select(name,x);s.key(RET);p.stable()


def pair(s,p,left,right,volume='/WORKHD'):
    folder(s,p,left)
    s.key(TAB);folder(s,p,right,40,volume);s.key(TAB);p.stable()


def mark(s,p,x=0):
    for name in ('A','C'):
        s.select(name,x);s.key(b' ');p.stable()


def entry(image,path):
    key=2
    for part in path.split('/'):
        e=next(e for e in image.entries(key) if e[1:1+(e[0]&15)].decode()==part)
        key=int.from_bytes(e[17:19],'little')
    return e


def data(image,path):return image.read(entry(image,path))


def main():
    with tempfile.TemporaryDirectory(prefix='a2fc-roi-') as tmp:
        tmp=Path(tmp);files={}
        for i in range(1,7):
            files[f'S{i}/A#041234']=b'A'+bytes(range(256))*4
            files[f'S{i}/B#040000']=b'untagged original\r'
            files[f'S{i}/C#040000']=b'C'*1800
            files[f'D{i}/KEEP#040000']=b'destination original\r'
        files['D2/C#040000']=b'collision original\r'
        files['D4/A2MOVE.LST#060000']=b'personal manifest name\r'
        stage=tmp/'target';(stage/'DST').mkdir(parents=True)
        (stage/'DST'/'KEEP#040000').write_bytes(b'other disk original\r')
        disk=tmp/'TARGET.po'
        subprocess.run([sys.executable,str(ROOT/'tools/mkvolume.py'),str(stage),str(disk),'--volume','TARGET','--blocks','280'],check=True,capture_output=True)
        with boot_hd(tmp,files,port=6893,floppy2=disk) as(p,s):
            aux=p.peek(0x1000,0xb000,'aux');floor=s.sym['__HIMEM__']-s.sym['__STACKSIZE__'];p.poke(floor,b'\xa5'*8)
            pair(s,p,'S1','D1');mark(s,p);menu_run(s,p,'MOVE')
            s.wait(lambda:s.has('Move 2 to'),'batch confirmation');s.key(b'Y')
            s.wait(lambda:s.has('2/2 moved.'),'same-volume batch',120);p.stable()
            s.ok('two marked files moved, unmarked B remains',s.has('2/2 moved.') and s.has('untagged') is False and any(r.startswith('B ') for r in s.rows()[2:20]))
            pair(s,p,'S2','D2');mark(s,p);menu_run(s,p,'MOVE');s.key(b'Y')
            s.wait(lambda:s.has('1/2 moved.'),'collision stops batch',120);p.stable()
            s.ok('collision preserves remaining source and its mark',any(r[:18].startswith('C ') and '*' in r[:18] for r in s.rows()[2:20]),s.rows()[22])
            pair(s,p,'S3','D3');mark(s,p);menu_run(s,p,'MOVE');s.key(b'N');p.stable()
            s.ok('cancel before first move keeps both source files',all(any(r.startswith(n+' ') for r in s.rows()[2:20]) for n in ('A','C')))
            pair(s,p,'S4','D4');mark(s,p);menu_run(s,p,'MOVE');s.key(b'Y')
            s.wait(lambda:s.has('Cannot reserve A2MOVE.LST'),'exclusive manifest collision');p.stable()
            s.ok('preexisting manifest is refused',s.has('no file moved'))
            pair(s,p,'D6','S6');s.key(TAB);mark(s,p,40);menu_run(s,p,'MOVE');s.key(b'Y')
            s.wait(lambda:s.has('2/2 moved.'),'right-panel batch',120);p.stable();s.ok('right-panel marked MOVE',s.has('2/2 moved.'));s.key(TAB)
            pair(s,p,'S5','DST','/TARGET');mark(s,p);menu_run(s,p,'MOVE');s.key(b'Y')
            s.wait(lambda:s.has('2/2 moved.'),'cross-volume batch',120);p.stable()
            s.ok('cross-volume batch completed',s.has('2/2 moved.'))
            s.ok('AUX preserved',p.peek(0x1000,0xb000,'aux')==aux)
            s.ok('stack floor preserved',p.peek(floor,8)==b'\xa5'*8)
            s.key(b'Q');s.wait(lambda:s.has('Quit to ProDOS?'),'quit question');s.key(b'Y');s.wait(lambda:not s.has('/WORKHD/S5'), 'return to ProDOS', 120);p.stable()
            s.ok('preferences save without a warning',not s.has('Configuration warning'))
        image=Image((tmp/'WORKHD.hdv').read_bytes());dest=Image(disk.read_bytes())
        s.ok('saved configuration exact',data(image,'A2FILE/A2FILE.CFG')==b'/WORKHD/S5\r/TARGET/DST\rS0A0\r')
        for name in ('A','C'):
            s.ok('same-volume bytes '+name,data(image,'D1/'+name)==files['S1/'+name+('#041234' if name=='A' else '#040000')])
            s.ok('right-panel moved bytes '+name,data(image,'D6/'+name)==files['S6/'+name+('#041234' if name=='A' else '#040000')])
            s.ok('cross-volume bytes '+name,data(dest,'DST/'+name)==files['S5/'+name+('#041234' if name=='A' else '#040000')])
        s.ok('collision target bytes preserved',data(image,'D2/C')==b'collision original\r')
        s.ok('preexisting list bytes preserved',data(image,'D4/A2MOVE.LST')==b'personal manifest name\r')
        for i in range(1,7):s.ok('unmarked bytes S'+str(i),data(image,f'S{i}/B')==b'untagged original\r')
        with Pom2(tmp/'WORKHD.hdv',floppy2=disk,port=6893) as p:
            s2=Session(p);s2.boot();p.stable()
            s.ok('verified configuration loads on restart',s2.rows()[0].startswith('/WORKHD/S5') and s2.rows()[0][40:].startswith('/TARGET/DST'))
        return ok_all(s,'configuration and batch MOVE')
if __name__=='__main__':raise SystemExit(main())
