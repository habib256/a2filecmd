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
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--pom2-root',type=Path,required=True)
p.add_argument('--disk',type=Path,default=ROOT/'dist/A2FC-MINI-DOS33-0.7.0.dsk')
a=p.parse_args()
original=a.disk.read_bytes()
with tempfile.TemporaryDirectory(prefix='mini33-write-') as tmp:
    d=Path(tmp); boot=d/'boot.dsk'; target=d/'target.dsk'
    boot.write_bytes(original)
    original_target=make_disk([('KEEP.DST',0x80,b'PRESERVE THESE BYTES\r\0')])
    target.write_bytes(original_target)
    subprocess.run([os.environ.get('CXX','c++'),'-std=c++17','-O2',
        *['-I'+str(a.pom2_root/s) for s in ('src','include','build/generated')],
        str(ROOT/'bench/mini33_write.cpp'),str(a.pom2_root/'build/libpom2_core_test.a'),'-o',str(d/'bench')],check=True)
    subprocess.run([str(d/'bench'),str(a.pom2_root),str(boot),str(target),str(ROOT/'build-mini/A2FC.MINI')],check=True,timeout=120)
    assert boot.read_bytes()==original
    before=read_files(original_target); after=read_files(target.read_bytes()); source=read_files(original)
    assert after['KEEP.DST']==before['KEEP.DST']
    assert after['A2FC.MINI']['data']==source['A2FC.MINI']['data']
    assert after['A2FC.MINI']['type']==source['A2FC.MINI']['type']
    assert set(after)=={'KEEP.DST','A2FC.MINI','CHECK.DOS'}
    assert a.disk.read_bytes()==original
    print('PASS: source image unchanged; existing target bytes preserved; binary exact; DOS allocation graph valid')
