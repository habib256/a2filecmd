#!/usr/bin/env python3
"""Run real DOS copy/write tests solely on temporary images; compare file bytes."""
import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from mini33_fixture import make_disk,read_files
from mkmini33 import MINI_VERSION
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--pom2-root',type=Path,required=True)
p.add_argument('--disk',type=Path,default=ROOT/f'dist/A2FC-MINI-DOS33-{MINI_VERSION}.dsk')
a=p.parse_args()
original=a.disk.read_bytes()
MINI_ENV = dict(os.environ, MINI_FILES=str(len(read_files(original))))   # the boot disk's file count, for the screen checks
with tempfile.TemporaryDirectory(prefix='mini33-write-') as tmp:
    d=Path(tmp); boot=d/'boot.dsk'; target=d/'target.dsk'
    boot.write_bytes(original)
    original_target=make_disk([('KEEP.DST',0x80,b'PRESERVE THESE BYTES\r\0')])
    target.write_bytes(original_target)
    # a different disk, swapped in at the COPY prompt: its VTOC differs
    swapped=d/'swapped.dsk'
    original_swapped=make_disk([('OTHER.DISK',0,bytes(700)),('NOT.TARGET',0,b'X')])
    assert original_swapped[17*4096:17*4096+256]!=original_target[17*4096:17*4096+256]
    swapped.write_bytes(original_swapped)
    subprocess.run([os.environ.get('CXX','c++'),'-std=c++17','-O2',
        *['-I'+str(a.pom2_root/s) for s in ('src','include','build/generated')],
        str(ROOT/'bench/mini33_write.cpp'),str(a.pom2_root/'build/libpom2_core_test.a'),'-o',str(d/'bench')],check=True)
    subprocess.run([str(d/'bench'),str(a.pom2_root),str(boot),str(target),str(ROOT/'build-mini/A2FC.MINI'),str(swapped)],env=MINI_ENV,check=True,timeout=180)
    assert boot.read_bytes()==original
    assert swapped.read_bytes()==original_swapped, 'the swapped-in disk must stay untouched'
    before=read_files(original_target); after=read_files(target.read_bytes()); source=read_files(original)
    assert after['KEEP.DST']==before['KEEP.DST']
    assert after['A2FC']['data']==source['A2FC']['data']
    assert after['A2FC']['type']==source['A2FC']['type']
    assert set(after)=={'KEEP.DST','A2FC','CHECK.DOS'}
    assert a.disk.read_bytes()==original
    print('PASS: source image unchanged; swapped disk untouched; existing target bytes preserved; binary exact; DOS allocation graph valid')
