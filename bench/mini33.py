#!/usr/bin/env python3
"""Run mini on POM2's NMOS core, using only temporary copies of disk images.
Usage: python3 bench/mini33.py --pom2-root /path/to/pom2
Requires a built libpom2_core_test.a and Apple II+ / Disk II ROMs there.
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from mkdos33 import build
from mkmini33 import MINI_VERSION
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--pom2-root',type=Path,required=True)
p.add_argument('--disk',type=Path,default=ROOT/f'dist/A2FC-MINI-DOS33-{MINI_VERSION}.dsk')
a=p.parse_args()
with tempfile.TemporaryDirectory(prefix='a2fc-mini-') as tmp:
    d=Path(tmp)
    boot=a.disk.read_bytes(); data=bytearray(build([('GREETINGS',0,b'HELLO\r\0')] +
        [(f'FILE{i:02}',0,b'PAGE TWO\r\0') for i in range(1,19)] +
        [('ABCDEFGHIJKLMNOPQRSTUVWXYZ1234',0,b'LONG NAME CONTENT\r\0')]))
    data[17*4096+13*256+1:17*4096+13*256+3]=b'\0\0'
    bad=bytearray(data); bad[17*4096+15*256+1:17*4096+15*256+3]=bytes([17,15])
    images=[boot,bytes(data),bytes(bad)]
    paths=[d/name for name in ('boot.dsk','data.dsk','bad.dsk')]
    for path,image in zip(paths,images): path.write_bytes(image)
    subprocess.run([os.environ.get('CXX','c++'),'-std=c++17','-O2',
        *['-I'+str(a.pom2_root/s) for s in ('src','include','build/generated')],
        str(ROOT/'bench/mini33.cpp'),str(a.pom2_root/'build/libpom2_core_test.a'),
        '-o',str(d/'bench')],check=True)
    subprocess.run([str(d/'bench'),str(a.pom2_root),*map(str,paths)],check=True,timeout=120)
    for path,image in zip(paths,images):
        assert path.read_bytes()==image, f'disk changed: {path}'
    print('PASS: all three disposable images preserved byte for byte')
