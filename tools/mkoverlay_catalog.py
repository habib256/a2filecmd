#!/usr/bin/env python3
"""Build the fixed-width menu catalog used while the companion is absent."""
import argparse
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output', type=Path)
    p.add_argument('build', type=Path)
    p.add_argument('--native', nargs='+', required=True)
    p.add_argument('--plugins', nargs='+', required=True)
    a = p.parse_args()
    records = []
    paths = [(n, a.build / ('A2FILE.CODE.BIN.' + n)) for n in a.native]
    paths += [(n.upper(), a.build / (n + '.PLG')) for n in a.plugins]
    for name, path in sorted(paths):
        if name == 'MENU':
            continue
        data = path.read_bytes()
        description = data[8:].split(b'\0', 1)[0]
        if not 0 < len(name) < 12 or len(description) > 65:
            raise ValueError('invalid overlay header: ' + str(path))
        records.append(name.encode('ascii').ljust(12, b'\0') + description.ljust(66, b'\0'))
    a.output.write_bytes(b''.join(records))
    print('%s: %d overlay descriptions' % (a.output, len(records)))


if __name__ == '__main__':
    main()
