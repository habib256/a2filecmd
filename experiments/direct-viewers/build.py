#!/usr/bin/env python3
"""Build the isolated DOSVIEW prototype; enforce code+BSS below $4000."""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from test_cc65_traps import unset_pointer_low, low_byte_zero_test
from test_flag_reuse import stale_flag_booleans


def build(arch):
    target = 'apple2' if arch == '6502' else 'apple2enh'
    out = ROOT / ('build-6502' if arch == '6502' else 'build')
    out.mkdir(exist_ok=True)
    env = os.environ.copy()
    if arch == '6502':
        home = Path.home() / 'opt/cc65-head'
        if not (home / 'bin/cc65').exists():
            raise RuntimeError('6502 qualification requires the cc65-head toolchain')
        env['PATH'] = str(home / 'bin') + os.pathsep + env['PATH']
        env['CC65_HOME'] = str(home / 'share/cc65')
    cc = shutil.which('cc65', path=env['PATH'])
    ca = shutil.which('ca65', path=env['PATH'])
    ld = shutil.which('ld65', path=env['PATH'])
    cl = shutil.which('cl65', path=env['PATH'])
    if not all((cc, ca, ld, cl)):
        raise RuntimeError('cc65 tools unavailable')
    target_dir = Path(subprocess.check_output([cl, '--print-target-path'], env=env, text=True).strip())
    library = target_dir.parent / 'lib' / (target + '.lib')
    defines = ['-DA2FC_6502', '-DA2FC_NOMOUSE'] if arch == '6502' else []
    base = out / 'dosview'
    subprocess.run([cc, '-t', target, *defines, '-O', '-Oirs', '-Cl', '--codesize', '100',
                    '-o', str(base.with_suffix('.s')), str(Path(__file__).with_name('dosview.c'))],
                   env=env, check=True)
    asm = base.with_suffix('.s').read_text()
    traps = unset_pointer_low(asm) + low_byte_zero_test(asm) + stale_flag_booleans(asm)
    if traps:
        raise RuntimeError('unsafe cc65 code generation: ' + '; '.join(traps))
    subprocess.run([ca, '-t', target, '-o', str(base.with_suffix('.o')), str(base.with_suffix('.s'))],
                   env=env, check=True)
    subprocess.run([ld, '-C', str(ROOT / 'sdk/plugin.cfg'), '-D', '__OVLSIZE__=0x2500',
                    '-m', str(base.with_suffix('.map')), '-Ln', str(base.with_suffix('.lbl')),
                    '-o', str(base.with_suffix('.PLG')), str(base.with_suffix('.o')), str(library)],
                   env=env, check=True)
    print(arch, base.with_suffix('.PLG'), base.with_suffix('.PLG').stat().st_size, 'file bytes')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arch', choices=('6502', 'enh', 'both'), default='both')
    args = parser.parse_args()
    for arch in ('6502', 'enh') if args.arch == 'both' else (args.arch,):
        build(arch)
