#!/usr/bin/env python3
"""Validate GISTDATA sample copies against independent full-page render oracles.

The corpus is opened read-only. All emulator disks are temporary copies.
A2FC_SAMPLE_DISK overrides ~/src/pom2/hdv/GISTDATA.hdv.
"""
import os
import sys
import tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from prodos_read import Image
from test_sample_media import font_page,clip_page,lz_page
from xplug import boot_hd,RET,ESC,ok_all


def sample_directory(im):
    # The corpus may be at the root or in its earlier IMG location.
    for parts in (('SAMPLE.MEDIA',),('IMG','SAMPLE.MEDIA')):
        k=2
        for part in parts:
            e=next((e for e in im.entries(k) if e[1:1+(e[0]&15)].decode()==part),None)
            if e is None:break
            k=int.from_bytes(e[17:19],'little')
        else:return k
    raise ValueError('SAMPLE.MEDIA not found in GISTDATA')


def samples():
    path=Path(os.environ.get('A2FC_SAMPLE_DISK',str(Path.home()/'src/pom2/hdv/GISTDATA.hdv')))
    im=Image(path.read_bytes());k=sample_directory(im)
    out=[]
    for e in im.entries(k):
        name=e[1:1+(e[0]&15)].decode()
        if name=='FONTS':
            for f in im.entries(int.from_bytes(e[17:19],'little')):
                out.append(('FONT/'+f[1:1+(f[0]&15)].decode(),7,0,im.read(f),font_page))
        elif name in ('DIP.CHIPS','BBROS.MINI','WOZ.BREAKOUT','APPLEVISION'):
            out.append(('WORK/'+name,e[16],int.from_bytes(e[31:33],'little'),im.read(e),
                        lz_page if name=='DIP.CHIPS' else clip_page if name=='BBROS.MINI' else None))
    return out


def main():
    cases=samples();files={f'{path}#{typ:02X}{aux:04X}':data for path,typ,aux,data,_ in cases}
    with tempfile.TemporaryDirectory(prefix='a2fc-media-native-') as tmp:
        with boot_hd(Path(tmp),files,port=6992,plugins=['fontview','printshop','lz4fh','intbasic']) as (p,s):
            s.key(b'/');s.select('/WORKHD');s.key(RET);p.stable()
            folder=''
            for path,typ,aux,data,oracle in cases:
                target,name=path.split('/')
                if folder!=target:
                    if folder:s.key(ESC);p.stable()
                    s.select(target);s.key(RET);p.stable();folder=target
                for key in ((RET,b'I') if target=='WORK' and oracle else (RET,)):
                    s.select(name)
                    before=bytes(p.peek(0x1000,0xB000,'aux'))
                    s.key(key)
                    if oracle:
                        expected=oracle(data)
                        s.wait(lambda:bytes(p.peek(0x2000,8192))==expected,name+' rendered',60)
                        s.ok(name+' full HGR page '+repr(key),True)
                        s.ok(name+' preserves AUX',bytes(p.peek(0x1000,0xB000,'aux'))==before)
                    else:
                        s.wait(lambda:s.has(name) and s.has('page 1'),name+' listing',30)
                        s.ok(name+' Return opens INTBASIC',True)
                    s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'panels restored',30);p.stable()
    return ok_all(s,'sample_media')


if __name__=='__main__':sys.exit(main())
