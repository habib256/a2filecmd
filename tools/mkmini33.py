#!/usr/bin/env python3
"""Create a NEW DOS 3.3 boot disk from boot tracks of a supplied DOS master.
Never changes the master; refuses existing output. No personal file imports.
"""
import argparse
import struct
from pathlib import Path

SIZE = 35 * 16 * 256

def build(master, binary):
    if len(master) != SIZE or master[0] != 1:
        raise ValueError('expected a 140 KB DOS-order DOS 3.3 master')
    v = master[17*4096:17*4096+256]
    if v[3] != 3 or v[0x34:0x38] != bytes([35,16,0,1]):
        raise ValueError('not a standard 35-track DOS 3.3 master')
    if bytes(c|128 for c in b'HELLO'.ljust(30)) not in master[:3*4096]:
        raise ValueError('boot tracks must use HELLO as startup program')
    if not binary or len(binary) > 0x5c00:
        raise ValueError('binary exceeds reserved code region')
    image = bytearray(SIZE)
    image[:3*4096] = master[:3*4096]
    # 10 PRINT CHR$(4);"BRUN A2FC.MINI" -- normal Applesoft startup.
    body = bytes([0xba,0xe7,ord('('),ord('4'),ord(')'),ord(';'),ord('"')])+b'BRUN A2FC.MINI'+b'"\0'
    program = struct.pack('<HH',0x801+4+len(body),10)+body+b'\0\0'
    files = [('HELLO',2,struct.pack('<H',len(program))+program),
             ('A2FC.MINI',4,struct.pack('<HH',0x2000,len(binary))+binary),
             ('README',0,b'A2FC MINI DOS 3.3\rAPPLE II+ 48 KB - DOS 3.3 COPY\rTAB: PANEL - I/K: SELECT\rRETURN: PREVIEW - /: DRIVE\rC: COPY TO THE OTHER PANEL\rCTRL-R: REREAD - Q: DOS\rT/H: TEXT/HEX - ?: HELP\rY: CONFIRM - N/ESC: CANCEL\r\0')]
    free = [(t,s) for t in range(3,35) if t != 17 for s in range(16)]
    used = {(t,s) for t in (0,1,2,17) for s in range(16)}
    def alloc():
        ts=free.pop(0); used.add(ts); return ts
    def put(ts, data):
        assert len(data)<=256
        off=(ts[0]*16+ts[1])*256
        image[off:off+len(data)]=data
    cat=bytearray(256)
    for index,(name,kind,data) in enumerate(files):
        blocks=[data[i:i+256] for i in range(0,len(data),256)]
        lists=[alloc() for _ in range((len(blocks)+121)//122)]
        sectors=[alloc() for _ in blocks]
        for ts,block in zip(sectors,blocks): put(ts,block)
        for i,ts in enumerate(lists):
            table=bytearray(256)
            if i+1<len(lists): table[1:3]=bytes(lists[i+1])
            struct.pack_into('<H',table,5,i*122)
            for j,pair in enumerate(sectors[i*122:(i+1)*122]): table[12+j*2:14+j*2]=bytes(pair)
            put(ts,table)
        entry=bytearray(35); entry[:2]=bytes(lists[0]); entry[2]=kind|128
        entry[3:33]=bytes(c|128 for c in name.encode().ljust(30))
        struct.pack_into('<H',entry,33,len(blocks)+len(lists))
        cat[11+index*35:46+index*35]=entry
    # A standard full catalog: all 105 slots are available for new copies.
    for s in range(15,0,-1):
        page=cat if s==15 else bytearray(256)
        if s>1: page[1:3]=bytes([17,s-1])
        put((17,s),page)
    vtoc=bytearray(256)
    vtoc[1:4]=bytes([17,15,3]); vtoc[6]=254; vtoc[0x27]=122
    vtoc[0x30:0x32]=bytes([18,1]); vtoc[0x34:0x38]=bytes([35,16,0,1])
    for t in range(35):
        bits=sum(1<<s for s in range(16) if (t,s) not in used)
        vtoc[0x38+t*4:0x3a+t*4]=bits.to_bytes(2,'big')
    put((17,0),vtoc)
    return bytes(image)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--master',required=True,type=Path)
    p.add_argument('--binary',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    a=p.parse_args()
    data=build(a.master.read_bytes(),a.binary.read_bytes())
    # Exclusive reservation: cannot truncate an existing disk or the master.
    with a.output.open('xb') as f:
        if f.write(data)!=len(data): raise OSError('short write')
    if a.output.read_bytes()!=data: raise OSError('disk verification failed')
    print(f'{a.output}: {len(data)} bytes, DOS 3.3 boot disk')
if __name__=='__main__': main()
