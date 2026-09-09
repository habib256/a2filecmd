#!/usr/bin/env python3
"""Execute tous les bancs des nouvelles surcouches, avec journaux separes.

make disk && make xplugins ARCH=6502
python3 bench/plugins.py --out /tmp/a2fc-plugins
A2FC_BUILD=build python3 bench/plugins.py --out /tmp/a2fc-plugins-enh
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import sys

BENCHES = ('bootblk', 'crc', 'date', 'findfile', 'fixtypes', 'goto', 'ident',
           'imgconv', 'mdview', 'rename', 'tagpat', 'txtconv', 'verify', 'volname', 'wipe')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--jobs', type=int, choices=range(1, 5), default=1)
    parser.add_argument('benches', nargs='*', help='noms des bancs (tous par defaut)')
    args = parser.parse_args()
    benches = args.benches or BENCHES
    if any(name not in BENCHES for name in benches):
        parser.error('banc inconnu')
    args.out.mkdir(parents=True, exist_ok=True)

    def run(name):
        log = args.out / (name + '.log')
        with log.open('w') as f:
            result = subprocess.run([sys.executable, str(Path(__file__).with_name(name + '.py'))],
                                    stdout=f, stderr=subprocess.STDOUT)
        print('%s %s (%s)' % ('PASS' if result.returncode == 0 else 'FAIL', name, log), flush=True)
        return result.returncode == 0

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        results = list(pool.map(run, benches))
    print('%d/%d bancs reussis' % (sum(results), len(results)), flush=True)
    return 0 if all(results) else 1


if __name__ == '__main__':
    sys.exit(main())
