#!/usr/bin/env python3
"""Measure native 6502 boot/navigation cycles on a disposable Disk II image."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import statistics
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--disk', type=Path, required=True)
    parser.add_argument('--labels', type=Path, required=True)
    parser.add_argument('--pom2-root', type=Path, default=Path.home()/'src/pom2')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    original = args.disk.read_bytes()
    with tempfile.TemporaryDirectory(prefix='a2fc-perf-') as tmp:
        tmp = Path(tmp)
        disk = tmp/'boot.po'
        disk.write_bytes(original)
        exe = tmp/'measure'
        command = ['c++', '-std=c++17', '-O2']
        for directory in ('src', 'include', 'build/generated'):
            command += ['-I', str(args.pom2_root/directory)]
        command += [str(ROOT/'tools/measure_startup.cpp'),
                    str(args.pom2_root/'build/libpom2_core_test.a'), '-o', str(exe)]
        subprocess.run(command, check=True)
        output = subprocess.check_output([str(exe), str(args.pom2_root), str(disk),
                                          str(args.labels.resolve())], text=True, timeout=120)
        assert disk.read_bytes() == original, 'Disposable disk unexpectedly written'
    assert args.disk.read_bytes() == original, 'Source disk changed'
    samples = {}
    for name, cycles in re.findall(r'^(\w+): (\d+) cycles', output, re.M):
        samples.setdefault(name, []).append(int(cycles))
    assert set(samples) == {'boot', 'first_down', 'open_a2file', 'cursor', 'scroll'}
    report = {'disk': str(args.disk), 'sha256': hashlib.sha256(original).hexdigest(),
              'labels_sha256': hashlib.sha256(args.labels.read_bytes()).hexdigest(),
              'machine': 'IIe unenhanced, NMOS 6502, Disk II, no write-back',
              'samples': samples,
              'mean_cycles': {k: statistics.mean(v) for k, v in samples.items()}}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report['mean_cycles'], indent=2))


if __name__ == '__main__':
    main()
