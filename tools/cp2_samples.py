"""CiderPress II's test files: a corpus of real files.

    cp2_samples.py          # lists what is at hand

fadden/CiderPress2 keeps samples of most formats it converts in TestData/.
The ones A2 File Cmd reads are in data/CP2/, in their CiderPress folders and
with their ProDOS type in the name (NAME#TTAAAA); the XL image carries them
in DEMO/CIDERPRESS. The rest of the corpus is looked for in
A2FC_CP2_SAMPLES (default ~/.cache/a2fc/cp2): `test-files.po`, the 800K
ProDOS volume inside TestData/fileconv/test-files.sdk (unpacked with
nulib2), and other TestData files downloaded as they are, their path with
'/' and ' ' turned into '_'. Tests skip what is missing.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prodos_read import Image  # noqa: E402

DIR = Path(os.environ.get('A2FC_CP2_SAMPLES', str(Path.home() / '.cache/a2fc/cp2')))


def path(name):
    """A downloaded TestData file, or None."""
    p = DIR / name.replace('/', '_').replace(' ', '_')
    return p if p.exists() else None


REPO = Path(__file__).resolve().parents[1] / 'data/CP2'


def volume():
    """{path: (type, aux, data)}: data/CP2, and test-files.po when it is there."""
    out = {}
    for f in sorted(REPO.rglob('*#*')):
        name, tt = f.name.rsplit('#', 1)
        key = '/' + str(f.parent.relative_to(REPO) / name)
        out[key] = (int(tt[:2], 16), int(tt[2:], 16), f.read_bytes())
    disk = DIR / 'test-files.po'
    if not disk.exists():
        return out
    img = Image(disk.read_bytes())

    def walk(key, prefix):
        for e in img.entries(key):
            name = prefix + '/' + e[1:1 + (e[0] & 15)].decode('ascii')
            if e[0] >> 4 == 0xD:
                walk(int.from_bytes(e[0x11:0x13], 'little'), name)
            elif e[0] >> 4 in (1, 2, 3):
                out.setdefault(name, (e[0x10], int.from_bytes(e[0x1F:0x21], 'little'), img.read(e)))
    walk(2, '')
    return out


if __name__ == '__main__':
    for name, (t, a, data) in sorted(volume().items()):
        print('%-40s $%02X $%04X %7d' % (name, t, a, len(data)))
