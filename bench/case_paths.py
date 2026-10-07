#!/usr/bin/env python3
"""Two panels on one directory spelt in two cases: V must refuse.

A2FILE.CFG puts the left panel on /workhd/dir and the right one on
/WORKHD/DIR. Bug hunt 2 (bench/hunt2_case.py on the reviewer's branch):
target_check compared the two spellings byte for byte, let V go on, and
moving VICTIM.TXT onto itself deleted its only copy. The configuration is
read upshifted now: both panels show /WORKHD/DIR, and V says "Both panels
show the same directory." A trailing slash is dropped the same way.
Disposable volume only.

    A2FC_PORT_OFFSET=2000 python3 bench/case_paths.py
"""
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from xplug import boot_hd, ok_all  # noqa: E402
from pom2 import ROOT  # noqa: E402
sys.path.insert(0, str(ROOT / 'tools'))
from prodos_read import Image  # noqa: E402

PORT = 7101
VICTIM = b'the only copy of this file\r' * 40


def entry(image, path):
    key = 2
    for part in path.split('/'):
        e = next((e for e in image.entries(key) if e[1:1 + (e[0] & 15)].decode() == part), None)
        if e is None:
            return None
        key = int.from_bytes(e[17:19], 'little')
    return e


def main():
    s = None
    for cfg in (b'/workhd/dir\r/WORKHD/DIR\rS0A0\r', b'/WORKHD/DIR\r/WorkHD/Dir/\rS0A1\r'):
        files = {'A2FILE/A2FILE.CFG#040000': cfg, 'DIR/VICTIM.TXT#040000': VICTIM,
                 'DIR/OTHER.TXT#040000': b'x\r'}
        with tempfile.TemporaryDirectory(prefix='a2fc-case-paths-') as tmp:
            tmp = Path(tmp)
            with boot_hd(tmp, files, port=PORT) as (p, s0):
                if s is not None:
                    s0.checks[:0] = s.checks     # one verdict over both boots
                s = s0
                rows = p.stable()
                s.ok('%r: both panels on /WORKHD/DIR' % cfg,
                     sum(r.count('/WORKHD/DIR') for r in rows[:2]) == 2 and 'workhd' not in ''.join(rows[:2]),
                     rows[:2])
                s.select('VICTIM.TXT', 0 if cfg.endswith(b'A0\r') else 40)
                s.key(b'V')
                time.sleep(1.0)
                rows = p.stable()
                s.ok('%r: V refused, same directory' % cfg,
                     any('Both panels show the same directory.' in r for r in rows[20:24]), rows[20:24])
                if any('Overwrite' in r for r in rows):
                    s.key(b'N'); p.stable()
            img = Image((tmp / 'WORKHD.hdv').read_bytes())
            e = entry(img, 'DIR/VICTIM.TXT')
            s.ok('%r: VICTIM.TXT intact' % cfg, e is not None and img.read(e) == VICTIM)
            s.ok('%r: no A2FC.COPY or A2FC.BAK left' % cfg,
                 entry(img, 'DIR/A2FC.COPY') is None and entry(img, 'DIR/A2FC.BAK') is None)
    return ok_all(s, 'case_paths')


if __name__ == '__main__':
    raise SystemExit(main())
