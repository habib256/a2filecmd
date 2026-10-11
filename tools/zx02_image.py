#!/usr/bin/env python3
"""Wrap a split-load A2FC core in an experimental, bounded ZX02 envelope.

Requires dmsc/zx02's compressor (default forward options). Source untouched;
output exclusively created, never replacing an existing file.
"""
import argparse
import binascii
import struct
import subprocess
import tempfile
from pathlib import Path


def pack(source, output, compressor, cpu):
    raw = source.read_bytes()
    if not 0xC00 < len(raw) <= 0x8AE0:
        raise ValueError('core exceeds split-load memory bounds')
    with tempfile.TemporaryDirectory(prefix='a2fc-zx02-') as tmp:
        original, encoded = Path(tmp) / 'core', Path(tmp) / 'encoded'
        original.write_bytes(raw)
        subprocess.run([str(compressor), str(original), str(encoded)], check=True, capture_output=True)
        payload = encoded.read_bytes()
    if not 0 < len(payload) <= 65535:
        raise ValueError('compressed extent exceeds envelope')
    header = struct.pack('<4sHHHBB', b'A2Z2', len(raw), len(payload), binascii.crc_hqx(raw, 65535), cpu, 0).ljust(512,b'\0')
    with output.open('xb') as f:
        f.write(header + payload)
    print(f'{source}: {len(raw)} -> {len(header) + len(payload)} bytes')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--zx02', required=True, type=Path)
    p.add_argument('--cpu', choices=('6502', '65C02'), required=True)
    a = p.parse_args()
    pack(a.source, a.output, a.zx02, int(a.cpu == '65C02'))


if __name__ == '__main__':
    main()
