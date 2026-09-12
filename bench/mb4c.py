#!/usr/bin/env python3
"""MB1/PT3 on a //c with and without an MB4c, using disposable volumes.

python3 bench/build_pt3_trace.py
POM2=/tmp/a2fc-pt3-trace A2FC_IMG=A2FILECMD-full python3 bench/mb4c.py
POM2=/tmp/a2fc-pt3-trace A2FC_BUILD=build-6502 python3 bench/mb4c.py

The trace adapter parks the card on virtual slot 3; POM2 exposes its VIA/AY
window at $C400. Successful hardware output proves A2FC selected page 4.
"""
import os
import tempfile
import time
from pathlib import Path
from xplug import boot_hd, RET, ESC, ok_all
from pt3 import autumn, ay_snapshot
from mkdemo import fanfare


def main():
    files = {'WORK/WELCOME.MB#061000': fanfare(),
             'WORK/AUTUMN.PT3#000000': autumn()}
    previous = os.environ.pop('A2FC_MB4C', None)
    try:
        for present in (False, True):
            if present:
                os.environ['A2FC_MB4C'] = '1'
            with tempfile.TemporaryDirectory(prefix='a2fc-mb4c-') as tmp:
                with boot_hd(Path(tmp), files, port=6997, plugins=['music', 'pt3'],
                             preset='iic') as (p, s):
                    before_disk = Path(p.hdv).read_bytes()
                    s.key(b'/'); s.select('/WORKHD'); s.key(RET)
                    s.select('WORK'); s.key(RET); p.stable()
                    for name, title in (('WELCOME.MB', 'MB1 - WELCOME.MB'),
                                        ('AUTUMN.PT3', 'ProTracker 3 - AUTUMN.PT3')):
                        s.select(name); p.stable()
                        before_aux = bytes(p.peek(0x1000, 0xB000, 'aux'))
                        p.rq('/speed', {'preset': '1x'}); s.key(RET)
                        if present:
                            s.wait(lambda: s.has(title), name + ' on MB4c', 30)
                            s.wait(lambda: any(ay_snapshot(p, 'playing')[8:11]),
                                   name + ' audible AY registers', 5)
                            s.ok(name + ': MB4c detected at $C400, AY receives volume', True)
                            s.key(b'P'); time.sleep(.3)
                            ay = ay_snapshot(p, 'paused')
                            s.ok(name + ': pause silences hardware',
                                 ay[7] & 63 == 63 and not any(ay[8:11]))
                            s.key(ESC); s.wait(lambda: s.has('Type  Aux'), 'panels', 30)
                            ay = ay_snapshot(p, 'stopped')
                            s.ok(name + ': exit silences AY and disables VIA IRQ',
                                 ay[7] & 63 == 63 and not any(ay[8:11]) and ay[16] & 127 == 0)
                        else:
                            s.wait(lambda: s.has('No Mockingboard.'), name + ' without card', 30)
                            s.ok(name + ': absent card refused, panels intact', s.has('Type  Aux'))
                        s.ok(name + ': AUX storage preserved byte for byte',
                             bytes(p.peek(0x1000, 0xB000, 'aux')) == before_aux)
                        p.rq('/speed', {'preset': 'max'}); p.stable()
                s.ok('Source volume preserved byte for byte', Path(p.hdv).read_bytes() == before_disk)
                if ok_all(s, 'mb4c present' if present else 'mb4c absent'):
                    return 1
    finally:
        os.environ.pop('A2FC_MB4C', None)
        if previous is not None:
            os.environ['A2FC_MB4C'] = previous
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
