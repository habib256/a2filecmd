#!/usr/bin/env python3
"""MCS foreground playback on a disposable ProDOS disk; both CPUs.

Menu invocation, real AY audio state, pause/restart/tempo, natural end,
invalid data, AUX preservation and C-stack floor.
"""
import re
import sys
import tempfile
import time
from pathlib import Path
from xplug import boot_hd, menu_run, RET, ESC, ok_all
from pom2 import BUILD, ROOT
from pt3 import ay_snapshot
sys.path.insert(0, str(ROOT / 'tools'))
from mcs_ref import fixture


def main():
    tune = fixture([(60, 8), (64, 8), (68, 8), (72, 8)] * 15,
                   [(84, 8), (88, 8), (92, 8), (96, 8)] * 15)
    files = {'WORK/SONG.MCS#061000': tune,
             'WORK/BAD.MCS#061000': tune[:-1]}
    addr = int(re.search(r'al ([0-9A-Fa-f]{6}) \._mc_regs',
                         (BUILD / 'mcs.lbl').read_text())[1], 16)
    with tempfile.TemporaryDirectory(prefix='mcs-native-') as tmp:
        with boot_hd(Path(tmp), files, port=6917, plugins=['mcs']) as (p, s):
            s.key(b'/');s.select('/WORKHD');s.key(RET);s.select('WORK');s.key(RET);p.stable()
            aux = p.peek(0x1000, 0xb000, 'aux')
            floor = s.sym['__HIMEM__'] - s.sym['__STACKSIZE__']
            p.poke(floor, b'\xa5'*8)
            p.rq('/speed', {'preset': '1x'})
            s.select('SONG.MCS');menu_run(s, p, 'MCS')
            s.wait(lambda: s.has('Music Construction Set - SONG.MCS'), 'MCS foreground', 30)
            s.ok('export buffer loaded into MAIN only', p.peek(0x3000, len(tune)) == tune)
            time.sleep(.4)
            s.ok('AY receives nonzero music volumes', any(ay_snapshot(p, 'MCS')[8:11]))
            s.key(b'P');time.sleep(.1)
            paused = p.peek(addr, 28);time.sleep(.2)
            s.ok('pause freezes song registers', p.peek(addr, 28) == paused)
            ay = ay_snapshot(p, 'MCS paused')
            s.ok('pause silences hardware', ay[7] & 63 == 63 and not any(ay[8:11]))
            s.key(b'P');s.wait(lambda: p.peek(addr, 28) != paused, 'MCS resume', 5)
            s.key(b'+');s.key(b'-');s.key(b'R')
            s.ok('tempo/restart keep foreground active', s.has('Music Construction Set'))
            s.key(ESC);s.wait(lambda: s.has('Type  Aux'), 'MCS exit', 30);p.stable()
            s.ok('Escape silences hardware', not any(ay_snapshot(p, 'MCS exit')[8:11]))
            p.rq('/speed', {'preset': 'max'})
            s.select('SONG.MCS');menu_run(s, p, 'MCS')
            s.wait(lambda: s.has('Type  Aux'), 'MCS natural end', 60)
            s.ok('natural end silences hardware', not any(ay_snapshot(p, 'MCS end')[8:11]))
            s.select('BAD.MCS');menu_run(s, p, 'MCS')
            s.wait(lambda: s.has('Bad MCS export/I/O'), 'MCS truncation rejected', 30)
            s.ok('AUX unchanged', p.peek(0x1000, 0xb000, 'aux') == aux)
            s.ok('C-stack floor unchanged', p.peek(floor, 8) == b'\xa5'*8)
    return ok_all(s, 'mcs')


if __name__ == '__main__':
    raise SystemExit(main())
