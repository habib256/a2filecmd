#!/usr/bin/env python3
"""Build one themed companion using only the declared tools of this build."""
import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from disk_packages import PACKAGES, VOLUMES, BASIC, ROOT


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('build', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--role', choices=PACKAGES, required=True)
    p.add_argument('--cpu', choices=('6502', '65C02'), required=True)
    a = p.parse_args()
    with tempfile.TemporaryDirectory(prefix='a2fc-package-') as tmp:
        stage = Path(tmp)
        directory = stage / 'A2FILE'
        directory.mkdir()
        shutil.copyfile(a.build / 'EXTRAS.CAT', directory / 'EXTRAS.CAT.BIN')
        for name in ['MENU'] + PACKAGES[a.role]:
            native = a.build / ('A2FILE.CODE.BIN.' + name)
            source = a.build / (name.lower() + '.PLG') if (ROOT / 'src/plugins' / (name.lower() + '.c')).exists() else native
            shutil.copyfile(source, directory / (name + '.PLG#061B00'))
        if a.role == BASIC:
            shutil.copyfile(ROOT / 'data/BASIC.SYSTEM.SYS', stage / 'BASIC.SYSTEM.SYS')
        subprocess.run([sys.executable, str(ROOT / 'tools/mkvolume.py'), str(stage),
                        str(a.output), '--volume', VOLUMES[a.role] + a.cpu,
                        '--blocks', '280'], check=True)


if __name__ == '__main__':
    main()
