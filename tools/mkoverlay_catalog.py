#!/usr/bin/env python3
"""Build the fixed-width menu catalog used while the companion is absent."""
import argparse
from pathlib import Path
from disk_packages import assignments, VOLUMES, BASIC, RUNTIMES


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output', type=Path)
    p.add_argument('build', type=Path)
    p.add_argument('--cpu', choices=('6502', '65C02'), required=True)
    p.add_argument('--native', nargs='+', required=True)
    p.add_argument('--plugins', nargs='+', required=True)
    a = p.parse_args()
    locations = assignments(a.native, a.plugins)
    records = []
    paths = [(n, a.build / ('A2FILE.CODE.BIN.' + n)) for n in a.native]
    paths += [(n.upper(), a.build / (n + '.PLG')) for n in a.plugins]
    for name, path in sorted(paths):
        data = path.read_bytes()
        description = data[8:].split(b'\0', 1)[0]
        if not 0 < len(name) < 12 or len(description) > 65:
            raise ValueError('invalid overlay header: ' + str(path))
        role = locations[name]
        volume = ('A2FC' if role == 'BOOT' else VOLUMES[role]) + a.cpu
        description = (volume.encode('ascii') + b': ' + description)[:65]
        key = bytearray(name.encode('ascii').ljust(12, b'\0'))
        if name in ('MENU', 'COPY', 'OPEN', 'NAV', 'BATCH'):
            key[11] = 1  # routing only, never a menu command
        records.append(bytes(key) + description.ljust(66, b'\0'))
    # Runtime routing uses the first twelve name bytes, as ask_disk does.
    # Non-NUL byte 11 hides these records from the overlay menu.
    for runtime in RUNTIMES:
        description = (VOLUMES[BASIC] + a.cpu + ': ' + runtime).encode('ascii')
        records.append(runtime.encode('ascii')[:12] + description.ljust(66, b'\0'))
    a.output.write_bytes(b''.join(records))
    print('%s: %d overlay descriptions' % (a.output, len(records)))


if __name__ == '__main__':
    main()
