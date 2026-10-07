#!/usr/bin/env python3
"""NIBCOPY from published DISKTOOLS, AUX refusal then full copy with BOOT removed.
Only fresh temporary images are mounted; source has its host write notch covered.
The confirmation names the target's volume (here a DOS 3.3 disk: none), and a
target holding the volume A2 File Cmd runs from (a copy of BOOT) is refused.
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path
from pom2 import Pom2,Session,ROOT,VERSION
from smoke import scratch
from xplug import menu_run,RET,ok_all
sys.path.insert(0,str(ROOT/'tools'))
from mkdos33 import build

PORT=6897+int(os.environ.get('A2FC_PORT_OFFSET','0'))

def refuse_program_volume():
    """BOOT's volume in the target drive: nothing written, BOOT intact."""
    with tempfile.TemporaryDirectory(prefix='nibcopy-boot-') as tmp:
        tmp=Path(tmp)
        boot=tmp/'boot.po';companion=tmp/'tools.po'
        shutil.copyfile(ROOT/f'dist/A2FILECMD-PRODOS-140K-{VERSION}.po',boot)
        shutil.copyfile(ROOT/'build-6502/legacy/DISKTOOLS.po',companion)
        original_boot=boot.read_bytes()
        source=tmp/'source.dsk';source.write_bytes(build([('SOURCE',0,bytes(range(256))*20)]));source.chmod(0o444)
        hd=scratch(tmp)
        with Pom2(hd,floppy=boot,floppy2=companion,port=PORT) as p:
            s=Session(p);s.boot()
            menu_run(s,p,'NIBCOPY',allow_aux=False);s.allow_aux()
            s.wait(lambda:s.has('Disk II slot'),'NIBCOPY loaded from DISKTOOLS')
            s.key(b'6');s.key(b'1');s.key(b'2')
            s.wait(lambda:s.has('Insert WRITE-PROTECTED SOURCE'),'source insertion')
            p.insert(0,str(source));p.insert(1,str(boot))
            s.key(RET)
            s.wait(lambda:s.has("Target holds A2 File Cmd's volume; nothing written; 0/35"),'program volume refused',120)
            s.ok('NIBCOPY refuses the volume A2 File Cmd runs from',True)
            p.eject(0);p.eject(1)
        s.ok('BOOT left in the target drive is intact',boot.read_bytes()==original_boot)
        source.chmod(0o644)
        return ok_all(s,'NIBCOPY UI, program volume as target')

def main(single=False):
    with tempfile.TemporaryDirectory(prefix='nibcopy-ui-') as tmp:
        tmp=Path(tmp)
        boot=tmp/'boot.po';companion=tmp/'tools.po'
        for target,role in ((boot,'BOOT'),(companion,'DISKTOOLS')):
            shutil.copyfile((ROOT/f'dist/A2FILECMD-PRODOS-140K-{VERSION}.po' if role == 'BOOT' else ROOT/f'build-6502/legacy/{role}.po'),target)
        original_boot=boot.read_bytes();original_tools=companion.read_bytes()
        source=tmp/'source.dsk';target=tmp/'target.dsk'
        original=build([('SOURCE',0,bytes(range(256))*20)])
        source.write_bytes(original);source.chmod(0o444)
        old_target=build([('DISPOSABLE',0,b'OLD TARGET\r')]);target.write_bytes(old_target)
        hd=scratch(tmp)
        with Pom2(hd,floppy=boot,floppy2=companion,port=PORT) as p:
            s=Session(p);s.boot()
            s.ram_occupied()
            before=p.peek(0x1000,0xB000,'aux')
            menu_run(s,p,'NIBCOPY',allow_aux=False)
            s.wait(lambda:s.has('ALL /RAM files will be LOST'),'AUX warning')
            s.ok('NIBCOPY AUX warning precedes damage',before==p.peek(0x1000,0xB000,'aux'))
            s.key(b'N');p.stable()
            s.ok('Refusing NIBCOPY preserves AUX',before==p.peek(0x1000,0xB000,'aux'))
            menu_run(s,p,'NIBCOPY',allow_aux=False);s.allow_aux()
            s.wait(lambda:s.has('Disk II slot'),'NIBCOPY loaded from DISKTOOLS')
            s.key(b'6');s.key(b'1');s.key(b'1' if single else b'2')
            s.wait(lambda:s.has('Insert WRITE-PROTECTED SOURCE'),'source insertion')
            p.insert(0,str(source))
            if single:p.eject(1)
            else:p.insert(1,str(target))
            s.key(RET)
            if single:
                s.wait(lambda:s.has('Insert TARGET disk'),'target insertion',120)
                p.insert(0,str(target));s.key(RET)
            s.wait(lambda:s.has('Erase TARGET S6,D'+('1' if single else '2')),'target identification',120)
            s.ok('BOOT and tools removed before first write',target.read_bytes()==old_target)
            s.ok('the confirmation names the target volume',s.has('(no ProDOS volume) ALL files?'))
            s.key(b'Y')
            if single:
                s.wait(lambda:s.has('Insert WRITE-PROTECTED SOURCE'),'second source exchange',120)
                s.key(b'\x1b')
                s.wait(lambda:s.has('Cancelled; 1/35 tracks verified.'),'cancel after one verified track',60)
            else:s.wait(lambda:s.has('Copy verified; 35/35 tracks verified.'),'35 verified tracks',240)
            s.ok('NIBCOPY returns with an exact verified track count',True)
            p.eject(0)
            if not single:p.eject(1)
        s.ok('Source image preserved',source.read_bytes()==original)
        expected=original[:4096]+old_target[4096:] if single else original
        s.ok('Target sectors match the verified count',target.read_bytes()==expected)
        s.ok('BOOT and DISKTOOLS preserved',boot.read_bytes()==original_boot and companion.read_bytes()==original_tools)
        source.chmod(0o644)
        return ok_all(s,'NIBCOPY UI, single drive' if single else 'NIBCOPY UI, two drives')
if __name__=='__main__':sys.exit(main() or main(True) or refuse_program_volume())
