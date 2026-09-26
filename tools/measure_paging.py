#!/usr/bin/env python3
"""Measure the cycles of paging through large directories on a disposable HDV.

Stages BUILD/vol plus directories of 300, 700 and 1,500 files on a throwaway
hard disk image, runs tools/measure_paging.cpp against POM2's core library
(no write-back, deterministic cycle counts), and prints, per directory and
per window change, the cycles of the key press that loaded the window.
BUILD follows A2FC_BUILD as in bench/pom2.py (build-6502/ by default, run on
an NMOS unenhanced IIe; A2FC_BUILD=build runs the 65C02 build on an enhanced
IIe).
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'bench'))
from xplug import stage_hd, BUILD  # noqa: E402

SIZES = (300, 700, 1500)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pom2-root', type=Path, default=Path.home() / 'src/pom2')
    parser.add_argument('--sizes', default=','.join(map(str, SIZES)))
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    build = BUILD
    cpu = 'unenh' if '6502' in build.name else 'enh'
    sizes = [int(s) for s in args.sizes.split(',')]
    files = {}
    for n in sizes:
        for i in range(n):
            files[f'P{n}/F{i:04}#040000'] = b'x'
    with tempfile.TemporaryDirectory(prefix='a2fc-paging-') as tmp:
        tmp = Path(tmp)
        hdv = stage_hd(tmp, files, blocks=4 * sum(sizes) + 3000)
        original = hdv.read_bytes()
        exe = tmp / 'measure'
        command = ['c++', '-std=c++17', '-O2']
        for directory in ('src', 'include', 'build/generated'):
            command += ['-I', str(args.pom2_root / directory)]
        command += [str(ROOT / 'tools/measure_paging.cpp'),
                    str(args.pom2_root / 'build/libpom2_core_test.a'), '-o', str(exe)]
        subprocess.run(command, check=True)
        # Lines are echoed as they come: a 1,500-entry run takes minutes.
        proc = subprocess.Popen([str(exe), str(args.pom2_root), str(hdv),
                                 str(build / 'a2fc.lbl'), cpu] + [f'P{n}' for n in sizes],
                                stdout=subprocess.PIPE, text=True)
        out = ''
        for line in proc.stdout:
            print(line, end='', file=sys.stderr, flush=True)
            out += line
        assert proc.wait(timeout=60) == 0, 'measurement failed'
        assert hdv.read_bytes() == original, 'Disposable disk unexpectedly written'
    report = {'build': build.name, 'cpu': cpu, 'dirs': {}}
    for line in out.splitlines():
        kind, name, k, first, *cycles = line.split()
        d = report['dirs'].setdefault(name, {'fwd': [], 'back': []})
        if kind == 'open':
            d['open'] = int(cycles[0])
        elif kind == 'last':
            d['windows'] = int(k) + 1
        elif kind == 'wrongway':
            d['wrongway'] = int(k)      # Left paged forward from window k
        else:
            d[kind].append({'window': int(k), 'first': int(first), 'cycles': int(cycles[0])})
    for name, d in report['dirs'].items():
        fwd = sum(x['cycles'] for x in d['fwd'])
        d['fwd_total'] = fwd
        print(f"{report['cpu']} {name}: open {d['open']:,}; {d['windows']} windows; "
              f"forward to last {fwd:,} cycles ({fwd / 1.023e6:.2f} s at 1 MHz); "
              f"last page {d['fwd'][-1]['cycles']:,}"
              + (f"; first back {d['back'][0]['cycles']:,}" if d['back'] else '')
              + (f"; LEFT PAGED FORWARD from window {d['wrongway']}" if 'wrongway' in d else ''))
        print('   fwd  ' + ' '.join(f"{x['cycles']:,}" for x in d['fwd']))
        print('   back ' + ' '.join(f"{x['cycles']:,}" for x in d['back']))
    if args.out:
        args.out.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
