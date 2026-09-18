"""The disks a session on real hardware needs, and what each must show.

POM2 proves the code; the drive proves the machine. A hardware session is
expensive -- a floppy to write, a machine to set up, an afternoon -- so it
should not also be spent building fixtures and guessing what a correct
screen looks like. This writes them, and prints the findings the checks
must report, from the same two oracles the benches use: `corrupt_prodos.py`
declares what each corruption produces, `prodos_check.py` reads it back on
the image, and a disagreement condemns the fixture before anyone boots.

    python3 tools/hw_media.py --out dist/hw          # the three floppies
    python3 tools/hw_media.py --out dist/hw --big    # plus a 20,000-block volume

The result, next to docs/HARDWARE-CHECKLIST.md:

    HW-CLEAN.dsk    a healthy 280-block ProDOS volume: FIXIT must say nothing
    HW-BROKEN.dsk   the same volume, broken in four places REPAIR can fix
    HW-DOS33.dsk    a DOS 3.3 disk with three files, for DOSWRITE and DOSGET
    HW-BIG.po       (--big) a 20,000-block volume broken past the first
                    bitmap page, for the FIXIT/REPAIR pass in auxiliary memory

Nothing here is written to a real disk by this tool: it produces images.
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import corrupt_prodos                                          # noqa: E402
import prodos_check                                            # noqa: E402
import mkdos33                                                 # noqa: E402

VOLUME = 'HWTEST'
BLOCKS = 280
# The same four faults bench/repair.py plays: a count, an eof, a parent and a
# lost block -- one of each family REPAIR knows how to put right.
BROKEN = ['file_count_high', 'dir_eof_wrong', 'parent_wrong', 'bitmap_lost']
# On a volume of more than 4,096 blocks the claims live in auxiliary memory:
# a fault in a far subdirectory and one in the fourth bitmap page prove it.
BROKEN_BIG = ['file_count_high', 'bitmap_lost']


def make_volume(stage, out, blocks=BLOCKS, volume=VOLUME):
    subprocess.run([sys.executable, str(ROOT / 'tools/mkvolume.py'), str(stage), str(out),
                    '--volume', volume, '--blocks', str(blocks)],
                   check=True, capture_output=True)
    return out


def files_into(stage, count=3):
    """A little tree: two files, a subdirectory, one file inside it."""
    stage.mkdir(parents=True, exist_ok=True)
    (stage / 'A.TXT').write_bytes(b'alpha\r' * 40)
    (stage / 'B.TXT').write_bytes(b'beta\r' * 400)
    (stage / 'SUB').mkdir(exist_ok=True)
    (stage / 'SUB' / 'NEST.TXT').write_bytes(b'nested\r' * 10)
    for i in range(count):
        (stage / ('FILL%d.TXT' % i)).write_bytes(b'fill\r' * 100)


def break_volume(clean, names, out):
    """The broken image and the findings both halves of the oracle agree on."""
    data = bytearray(clean.read_bytes())
    declared = corrupt_prodos.apply(data, names)
    out.write_bytes(bytes(data))
    read_back = prodos_check.check(bytes(data))
    if (prodos_check.to_json(declared.findings) != prodos_check.to_json(read_back.findings)
            or declared.complete != read_back.complete):
        raise SystemExit('the two oracles disagree on %s: fixture refused' % out.name)
    counts = {}
    for f in read_back.findings:
        counts[f.id] = counts.get(f.id, 0) + 1
    return counts


def po2dsk(po, dsk):
    subprocess.run([sys.executable, str(ROOT / 'tools/po2dsk.py'), str(po), str(dsk)],
                   check=True, capture_output=True)


def dos33(out):
    """A DOS 3.3 disk: a text to read, a binary to look at, a program name.

    The same shapes the benches use (bench/ident.py, bench/catalog_overlay.py):
    a text file ends its record, a binary carries its load address and length.
    """
    payload = bytes(range(64)) * 4
    image = mkdos33.build([
        ('GREETINGS', 0x00, b'A DOS 3.3 FILE READ FROM A2 FILE CMD\r' * 4 + b'\x00'),
        ('BINARY', 0x04, b'\x00\x20' + len(payload).to_bytes(2, 'little') + payload),
        ('HELLO', 0x02, b'\x00' * 300),
    ])
    out.write_bytes(image)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--out', type=Path, default=ROOT / 'dist/hw')
    p.add_argument('--big', action='store_true', help='also a 20,000-block volume')
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    report = {}

    with tempfile.TemporaryDirectory(prefix='hw-media-') as tmp:
        tmp = Path(tmp)
        stage = tmp / 'stage'
        files_into(stage)
        clean = make_volume(stage, tmp / 'clean.po')
        (args.out / 'HW-CLEAN.po').write_bytes(clean.read_bytes())
        po2dsk(clean, args.out / 'HW-CLEAN.dsk')

        counts = break_volume(clean, BROKEN, args.out / 'HW-BROKEN.po')
        po2dsk(args.out / 'HW-BROKEN.po', args.out / 'HW-BROKEN.dsk')
        report['HW-BROKEN'] = counts

        dos33(args.out / 'HW-DOS33.dsk')

        if args.big:
            big_stage = tmp / 'big'
            files_into(big_stage, count=30)
            deep = big_stage / 'SUB' / 'DEEP'
            deep.mkdir(parents=True)
            (deep / 'FAR.TXT').write_bytes(b'far\r' * 50)
            big = make_volume(big_stage, tmp / 'big.po', blocks=20000, volume='HWBIG')
            report['HW-BIG'] = break_volume(big, BROKEN_BIG, args.out / 'HW-BIG.po')

    (args.out / 'EXPECTED.json').write_text(json.dumps(report, indent=1, sort_keys=True) + '\n')
    print('written in %s:' % args.out)
    for name in sorted(p.name for p in args.out.iterdir()):
        print('  ' + name)
    for image, counts in sorted(report.items()):
        print('%s: FIXIT must report' % image)
        for ident, n in sorted(counts.items()):
            print('  %-20s %d' % (ident, n))
        print('  REPAIR plan: %d corrections' % sum(counts.values()))
    return 0


if __name__ == '__main__':
    sys.exit(main())
