#!/usr/bin/env python3
"""Seal internal MCS stages with their complete load length (not BSS)."""
import re
import sys
from pathlib import Path


def seal(path,labels,end_limit=0x3700,flags=5):
    data=bytearray(path.read_bytes())
    symbols={m[2]:int(m[1],16) for m in re.finditer(r'al ([0-9A-Fa-f]{6}) \.([^\s]+)',labels.read_text())}
    if not 256<=len(data)<=end_limit-0x1b00 or data[:3]!=bytes((0xfd,0xa2,flags)) or data[7] not in (1,129):
        raise ValueError('invalid MCS stage header/length')
    entry=int.from_bytes(data[3:5],'little')
    if not 0x1b08<=entry<0x1b00+len(data):raise ValueError('MCS entry outside payload')
    start=symbols['__BSS_RUN__'];end=start+symbols['__BSS_SIZE__']
    if not (0xc00<=start<=end<=0x1000 or 0x1b00<=start<=end<=end_limit):raise ValueError('MCS BSS crosses reserved boundary')
    data[5:7]=len(data).to_bytes(2,'little');path.write_bytes(data)


if __name__=='__main__':seal(Path(sys.argv[1]),Path(sys.argv[2]),*(map(lambda v:int(v,0),sys.argv[3:])))
