#!/usr/bin/env python3
"""Build the isolated DOSVIEW prototype; enforce code+BSS below $4000."""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from test_cc65_traps import unset_pointer_low, low_byte_zero_test
from test_flag_reuse import stale_flag_booleans


def build(arch):
    out = ROOT / ('build-6502' if arch == '6502' else 'build')
    subprocess.run(['make', 'ARCH=' + arch, str(out.relative_to(ROOT) / 'dosview.PLG')],
                   cwd=ROOT, check=True)
    asm = (out / 'dosview.s').read_text()
    traps = unset_pointer_low(asm) + low_byte_zero_test(asm) + stale_flag_booleans(asm)
    if traps:
        raise RuntimeError('unsafe cc65 code generation: ' + '; '.join(traps))
    print(arch, out / 'dosview.PLG', (out / 'dosview.PLG').stat().st_size, 'file bytes')



if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arch', choices=('6502', 'enh', 'both'), default='both')
    args = parser.parse_args()
    for arch in ('6502', 'enh') if args.arch == 'both' else (args.arch,):
        build(arch)
