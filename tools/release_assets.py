#!/usr/bin/env python3
"""Hash only this release's five images and manual, never stale dist contents."""
import hashlib
from distribution import ROOT, VERSION, image_names


def main():
    names = image_names() + [f'A2FILECMD-MANUAL-EN-{VERSION}.pdf']
    # Read every required artifact before publishing a checksum manifest.
    lines = [f'{hashlib.sha256((ROOT / "dist" / name).read_bytes()).hexdigest()}  {name}\n' for name in names]
    (ROOT / 'dist' / f'SHA256SUMS-{VERSION}.txt').write_text(''.join(lines))
    print(''.join(lines), end='')


if __name__ == '__main__':
    main()
