#!/usr/bin/env python3
"""Build one themed companion using only the declared tools of this build."""
import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from disk_packages import PACKAGES, BENCH_PACKAGES, VOLUMES, BASIC, RUNTIMES, ROOT
from distribution import inventories


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('build', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--role', choices=PACKAGES, required=True)
    p.add_argument('--cpu', choices=('6502', '65C02'), required=True)
    p.add_argument('--bench', action='store_true', help='compact disk-swap fixture')
    a = p.parse_args()
    with tempfile.TemporaryDirectory(prefix='a2fc-package-') as tmp:
        stage = Path(tmp)
        directory = stage / 'A2FILE'
        directory.mkdir()
        catalog = (a.build / 'EXTRAS.CAT').read_bytes()
        if a.bench:
            selected = {n for names in BENCH_PACKAGES.values() for n in names}
            selected.update(inventories()[0])
            selected.update(name[:12] for name in RUNTIMES)
            if len(catalog) % 78:
                raise ValueError('truncated overlay catalog')
            catalog = b''.join(row for at in range(0, len(catalog), 78)
                              if (row := catalog[at:at+78])[:12].split(b'\0', 1)[0].decode('ascii') in selected)
        (directory / 'EXTRAS.CAT.BIN').write_bytes(catalog)
        for name in ['MENU'] + (BENCH_PACKAGES if a.bench else PACKAGES)[a.role]:
            native = a.build / ('A2FILE.CODE.BIN.' + name)
            source = a.build / (name.lower() + '.PLG') if (ROOT / 'src/plugins' / (name.lower() + '.c')).exists() else native
            shutil.copyfile(source, directory / (name + '.PLG#061B00'))
        if a.role == BASIC:
            for runtime in RUNTIMES:
                shutil.copyfile(ROOT / ('data/' + runtime + '.SYS'), stage / (runtime + '.SYS'))
        subprocess.run([sys.executable, str(ROOT / 'tools/mkvolume.py'), str(stage),
                        str(a.output), '--volume', VOLUMES[a.role] + a.cpu,
                        '--blocks', '280'], check=True)


if __name__ == '__main__':
    main()
