#!/usr/bin/env python3
"""Native copy/move/save and RAM consent on disposable ProDOS media.

A2FC_IMG=A2FILECMD-65C02-BOOT python3 bench/data_safety.py
A2FC_IMG=A2FILECMD-6502-BOOT A2FC_PRESET=iie_unenh python3 bench/data_safety.py
"""
import os
import shutil
import subprocess
import tempfile
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from pom2 import Pom2,Session,BUILD,ROOT
from xplug import stage_hd,RET,TAB,ESC,ok_all
from prodos_read import Image

DATA=b'keep every byte\r'*40
TEXT=b'Original editor text\r'

def contents(path,parts):
    img=Image(path.read_bytes());key=2
    for part in parts:
        entries={e[1:1+(e[0]&15)].decode():e for e in img.entries(key)}
        e=entries[part]
        if e[0]>>4==13:key=int.from_bytes(e[17:19],'little')
        else:return img.read(e)
    return entries

def main():
    with tempfile.TemporaryDirectory(prefix='a2fc-safety-') as tmp:
        tmp=Path(tmp)
        hd=stage_hd(tmp)
        # Core viewers/editor are not all in the BOOT set. Match THIS link.
        for name in ('EDIT','IMAGE'):
            shutil.copyfile(BUILD/('A2FILE.CODE.BIN.'+name),tmp/'hdstage/A2FILE'/(name+'.PLG#061B00'))
        subprocess.run([sys.executable,ROOT/'tools/mkvolume.py',tmp/'hdstage',hd,'--volume','WORKHD',
                        '--boot',ROOT/'data/prodos_boot.tmpl','--blocks','4000'],check=True,capture_output=True)
        stage=tmp/'floppy';(stage/'SRC').mkdir(parents=True);(stage/'DST').mkdir()
        (stage/'SRC/DATA.TXT').write_bytes(DATA)
        (stage/'SRC/EDIT.TXT').write_bytes(TEXT)
        (stage/'SRC/KEEP.TXT').write_bytes(b'RAM must survive refusal\r')
        (stage/'SRC/PICTURE#062000').write_bytes(bytes(16384))
        (stage/'DST/DATA.TXT').write_bytes(b'previous destination\r')
        po=tmp/'SAFE.po'
        subprocess.run([sys.executable,ROOT/'tools/mkvolume.py',stage,po,'--volume','SAFE','--blocks','280'],check=True,capture_output=True)
        with Pom2(hd,floppy2=po,port=6986+int(os.environ.get('A2FC_PORT_OFFSET','0'))) as p:
            s=Session(p);s.boot()
            def panel(x,vol,*parts):
                if s.cursor_row(x) is None:s.key(TAB)
                s.key(b'/');s.wait(lambda:s.has('[Volumes]'),'volumes')
                s.select(vol,x);s.key(RET);p.stable()
                for part in parts:s.select(part,x);s.key(RET);p.stable()
            panel(40,'/SAFE','DST');panel(0,'/SAFE','SRC')
            s.select('DATA',0);s.key(b'C');s.wait(lambda:s.has('Overwrite, Skip'),'overwrite confirmation')
            s.key(b'O');s.wait(lambda:s.has('1 file copied'),'verified copy',60);p.stable()
            s.ok('native overwrite copied and left its source',s.has('1 file copied') and any(r.startswith('DATA ') for r in s.rows()))
            s.key(b'V');s.wait(lambda:s.has('Overwrite, Skip'),'move overwrite confirmation')
            s.key(b'O');s.wait(lambda:s.has('1 file moved'),'verified move',60);p.stable()
            s.ok('native move removes source only after verification',not any(r.startswith('DATA ') for r in s.rows()))
            s.select('EDIT',0);s.key(b'E');s.wait(lambda:s.value('view',1)==5,'editor')
            s.type('NEW ');s.key(ESC);s.wait(lambda:s.has('Save and exit'),'editor save menu')
            s.key(b'S');p.stable()
            s.ok('save stays in editor',s.value('view',1)==5)
            s.type('AGAIN ');s.key(ESC);s.wait(lambda:s.has('Save and exit'),'second save menu')
            s.key(b'X');s.wait(lambda:s.value('view',1)==0,'save and exit');p.stable()
            s.ok('repeated saves return to panels',s.has('Type  Aux'))
            panel(40,'/RAM');panel(0,'/SAFE','SRC')
            s.select('KEEP',0);s.key(b'C');s.wait(lambda:s.has('1 file copied'),'copy into RAM');p.stable()
            s.ok('RAM holds a user file before viewing',any(r[40:].startswith('KEEP ') for r in s.rows()))
            s.select('PICTURE',0)
            before=p.peek(0x1000,0xB000,'aux')
            s.key(b'I');s.wait(lambda:s.has('ALL /RAM files will be LOST'),'RAM warning')
            s.ok('warning precedes any AUX damage',p.peek(0x1000,0xB000,'aux')==before)
            s.key(b'N');p.stable()
            s.ok('declining keeps RAM bytes and never enters viewer',p.peek(0x1000,0xB000,'aux')==before and s.value('view',1)==0)
            s.key(b'I');s.wait(lambda:s.has('ALL /RAM files will be LOST'),'RAM warning again')
            s.key(b'Y');s.wait(lambda:s.value('view',1)==1,'consented viewer');p.stable()
            s.key(ESC);s.wait(lambda:s.value('view',1)==0,'viewer return');p.stable()
            s.ok('consented DHGR view reports RAM reconstruction',s.has('/RAM was rebuilt empty'))
            s.ok('RAM has been rebuilt after consent',not any(r[40:].startswith('KEEP ') for r in s.rows()))
            cached=p.peek(0x1000,0xB000,'aux')
            s.key(b'I');s.wait(lambda:s.has('ALL /RAM files will be LOST'),'cached viewer warning')
            s.key(b'N');p.stable()
            s.ok('cached viewer also requires consent',s.value('view',1)==0 and p.peek(0x1000,0xB000,'aux')==cached)
            def disk_mode(key):
                s.key(b'W');s.wait(lambda:s.has('ALL /RAM files will be LOST'),'disk AUX warning')
                s.key(b'Y');s.wait(lambda:s.has('DISK IMAGES'),'disk menu')
                s.key(key);s.wait(lambda:any('/SAFE' in row and 'drive' in row for row in s.rows()),'disk choice')
                row=next(row for row in s.rows() if '/SAFE' in row and 'drive' in row)
                s.key(row.strip()[0].encode())
            disk_mode(b'W');s.wait(lambda:s.has('Disk in use'),'source volume refused')
            s.ok('image cannot overwrite its own source volume',s.has('Disk in use'))
            s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'disk writer return');p.stable()
            disk_mode(b'R');s.wait(lambda:s.has('Disk in use'),'self capture refused');p.stable()
            s.ok('disk cannot be captured onto itself',s.has('Disk in use') and s.has('Type  Aux'))
        s.ok('moved file bytes persisted on floppy',contents(po,['DST','DATA'])==DATA)
        s.ok('two editor saves persisted exact bytes',contents(po,['SRC','EDIT'])==b'NEW AGAIN '+TEXT)
        return ok_all(s,'data_safety')
if __name__=='__main__':sys.exit(main())
