#!/usr/bin/env python3
"""Exercise native NIBCOPY C/6502 transport on POM2 and disposable DOS images."""
import argparse
import os
import shutil
import struct
import zlib
from pathlib import Path
import subprocess
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from mkdos33 import build
from test_nibcopy import track,GCR

def woz_fixture(seed=0):
    """Exactly 50000 four-microsecond cells/revolution, 300 RPM at 1 MHz.
    WOZ forces POM2's bit-level LSS, including ten-bit sync and the splice.
    """
    records=bytearray()
    for t in range(35):
        raw=bytearray(track(t)[:6160]);bits=[]
        if seed:
            for sector in range(16):
                checksum=0
                for i in range(342):
                    offset=sector*385+39+i;value=(GCR.index(raw[offset])+seed)&63
                    raw[offset]=GCR[value];checksum^=value
                raw[sector*385+381]=GCR[checksum]
        for i,v in enumerate(raw):
            bits.extend((v>>b)&1 for b in range(7,-1,-1))
            if i%385<16 or 30<=i%385<36:bits.extend([0,0])
        bits.extend([1]*(50000-len(bits)));assert len(bits)==50000
        packed=bytes(sum(bits[i+j]<<(7-j) for j in range(8)) for i in range(0,50000,8))
        records+=packed.ljust(6646,b'\0')+struct.pack('<HHHBB',len(packed),50000,65535,0,0)+b'\0\0'
    info=bytearray(60);info[0]=info[1]=1;info[5:37]=b'A2FC disposable NIBCOPY fixture  '
    tmap=bytes([q//4 if q<140 else 255 for q in range(160)])
    def chunk(name,data):return name+struct.pack('<I',len(data))+data
    body=chunk(b'INFO',info)+chunk(b'TMAP',tmap)+chunk(b'TRKS',records)
    return b'WOZ1\xff\x0a\x0d\x0a'+struct.pack('<I',zlib.crc32(body))+body
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--pom2-root',type=Path,required=True)
a=p.parse_args()
with tempfile.TemporaryDirectory(prefix='nibcopy-native-') as tmp:
    d=Path(tmp)
    subprocess.run([os.environ.get('CXX','c++'),'-std=c++17','-O2',
        *['-I'+str(a.pom2_root/s) for s in ('src','include','build/generated')],
        str(ROOT/'bench/nibcopy.cpp'),str(a.pom2_root/'build/libpom2_core_test.a'),'-o',str(d/'bench')],check=True)
    src=build([('SOURCE',0,bytes(range(256))*12)])
    dst=build([('TARGET',0,b'DISPOSABLE\r')])
    for cpu,target in [('6502','apple2'),('65C02','apple2enh')]:
        source=d/'source.dsk';target_path=d/'target.dsk';source.write_bytes(src);target_path.write_bytes(dst)
        env=os.environ.copy()
        compiler=Path(shutil.which('cc65')).parent
        library=target+'.lib'
        if cpu=='6502':
            head=Path(os.environ.get('CC65_HEAD',Path.home()/'opt/cc65-head'))
            compiler=head/'bin';env['CC65_HOME']=str(head/'share/cc65');library=str(head/'share/cc65/lib/apple2.lib')
        subprocess.run([str(compiler/'cc65'),'-t',target,'-O','-Oirs','-Cl','-o',str(d/'test.s'),str(ROOT/'bench/nibcopy_native.c')],check=True,env=env)
        subprocess.run([str(compiler/'ca65'),'-t',target,'-o',str(d/'test.o'),str(d/'test.s')],check=True,env=env)
        (d/'io.s').write_text((ROOT/'src/plugins/nibcopy.s').read_text()+'\n.export _nb_poll, _nb_finish\n_nb_poll=Poll\n_nb_finish=Finish\n')
        subprocess.run([str(compiler/'ca65'),'-t',target,'-o',str(d/'io.o'),str(d/'io.s')],check=True,env=env)
        subprocess.run([str(compiler/'ld65'),'-C',str(ROOT/'sdk/nibcopy.cfg'),'-D','__OVLSIZE__=0x2500','-o',str(d/'test.bin'),'-Ln',str(d/'test.lbl'),str(d/'test.o'),str(d/'io.o'),library],check=True,env=env)
        subprocess.run([str(d/'bench'),str(a.pom2_root),str(d/'test.bin'),str(d/'test.lbl'),str(source),str(target_path),cpu],check=True,timeout=120)
        assert source.read_bytes()==src,'Source changed'
        result=target_path.read_bytes()
        for t in range(35):
            want=src if t in (0,1,17,34) else dst
            assert result[t*4096:(t+1)*4096]==want[t*4096:(t+1)*4096],f'track {t} differs'
        source=d/'source.woz';target_path=d/'target.woz';woz=woz_fixture()
        source.write_bytes(woz);old_woz=woz_fixture(17);target_path.write_bytes(old_woz)
        subprocess.run([str(d/'bench'),str(a.pom2_root),str(d/'test.bin'),str(d/'test.lbl'),str(source),str(target_path),cpu],check=True,timeout=120)
        assert source.read_bytes()==woz,'WOZ source changed'
        written=target_path.read_bytes()
        for t in range(35):
            start=256+t*6656
            if t not in (0,1,17,34):assert written[start:start+6656]==old_woz[start:start+6656],f'untouched WOZ track {t} changed'
            else:assert written[start:start+6656]!=old_woz[start:start+6656],f'WOZ track {t} not written'
    print('PASS: both CPUs, native nibble transport and exact sectors, failure cleanup, source preserved')
