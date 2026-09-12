#!/usr/bin/env python3
"""Applesoft/Integer launches on disposable XL volumes, with cancellation."""
import sys,tempfile,shutil,subprocess
from contextlib import contextmanager
from pathlib import Path
from xplug import boot_hd,RET,ok_all
from pom2 import ROOT, BUILD, VERSION, Pom2, Session
from smoke import scratch
sys.path.insert(0,str(ROOT/'tools'))
from mkdemo import applesoft, HOME, PRINT, END
from test_intbasic import prog,chars,const
from prodos_read import Image


def get_file(image,path):
    block=2
    for part in path.split('/'):
        entry=next(e for e in image.entries(block) if e[1:1+(e[0]&15)].decode()==part)
        block=int.from_bytes(entry[17:19],'little')
    return image.read(entry)


@contextmanager
def launch_session(tmp,files,companion):
    if not companion:
        with boot_hd(tmp,files,port=6970) as pair:
            yield (*pair,'/WORKHD')
        return
    assert BUILD.name=='build-6502', 'BOOT and DEVTOOLS contain the 6502 build'
    hd=scratch(tmp)
    for name,data in files.items():(tmp/'scratch'/name).write_bytes(data)
    subprocess.run([sys.executable,str(ROOT/'tools/mkvolume.py'),str(tmp/'scratch'),str(hd),
                    '--volume','SCRATCH','--blocks','1600'],check=True,capture_output=True)
    boot=tmp/'BOOT.po';tools=tmp/'DEVTOOLS.po'
    for dest,role in ((boot,'BOOT'),(tools,'DEVTOOLS')):
        shutil.copyfile(ROOT/('dist/A2FILECMD-6502-%s-%s.po'%(role,VERSION)),dest)
    with Pom2(hd,floppy=boot,floppy2=tools,port=6970) as p:
        s=Session(p);s.boot();yield p,s,'/SCRATCH'


def main():
    companion='--companion' in sys.argv
    programs={
        'INTEGER': ('#FA0000',prog([(10,bytes([0x61,0x28])+chars('INTEGER BASIC OK')+bytes([0x29])),
                                   (20,bytes([0x5F])+const(20))])),
        'APPLE': ('#FC0801',applesoft([(10,bytes([HOME])),
                                     (20,bytes([PRINT])+b'"APPLESOFT BASIC OK"'),
                                     (30,bytes([END]))]))}
    for name,(suffix,program) in programs.items():
        with tempfile.TemporaryDirectory(prefix='a2fc-launch-') as tmp:
            with launch_session(Path(tmp),{'WORK/'+name+suffix:program},companion) as (p,s,volume):
                s.key(b'/');s.select(volume);s.key(RET);s.select('WORK');s.key(RET)
                s.select(name);s.key(b'T');s.wait(lambda:s.has('PRINT'),'BASIC source listing',30)
                s.ok(name+': T lists source without executing',True)
                s.key(b'\x1b');s.wait(lambda:s.has('Type  Aux'),'panels after listing',30)
                s.select(name);s.key(RET);s.wait(lambda:s.has('Run '+name+'?'),'confirm',30)
                s.key(b'N');s.wait(lambda:s.has('Type  Aux'),'cancel',30)
                s.ok(name+': cancellation restores panels',True)
                s.select(name);s.key(RET);s.wait(lambda:s.has('Run '+name+'?'),'confirm again',30)
                s.key(b'Y')
                expected='INTEGER BASIC OK' if name=='INTEGER' else 'APPLESOFT BASIC OK'
                s.wait(lambda:s.has('Configuration warning.') or
                              any(expected in r for r in s.rows40()) or s.has(expected),
                       'launch or config warning',60)
                if s.has('Configuration warning.'):
                    s.ok(name+': full BOOT reports unsaved configuration before launching',True)
                    s.key(b'Y')
                try:
                    s.wait(lambda:any(expected in r for r in s.rows40()) or s.has(expected),name+' executes',60)
                except Exception:
                    print('\n'.join(s.rows()),flush=True);print('\n'.join(s.rows40()),flush=True);raise
                s.ok(name+': selected program executes through its interpreter',True)
            s.ok(name+': source program bytes preserved',get_file(Image(Path(p.hdv).read_bytes()),'WORK/'+name)==program)
            if ok_all(s,'launch'):return 1
    return 0

if __name__=='__main__':raise SystemExit(main())
