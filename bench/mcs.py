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
from mcs_score_ref import fixture as score_fixture, score


def main():
    tune = fixture([(60, 8), (64, 8), (68, 8), (72, 8)] * 15,
                   [(84, 8), (88, 8), (92, 8), (96, 8)] * 15)
    files = {'WORK/SONG.MCS#061000': tune,
             'WORK/BAD.MCS#061000': tune[:-1]}
    top=[(31,10,16),(15,10,20)]+[(3,10+i%3,96+i*16) for i in range(40)]+[(31,10,1000)]
    bottom=[(31,10,16),(16,30,20)]+[(3,30+i%3,96+i*16) for i in range(40)]+[(31,10,1000)]
    main_score,obj=score_fixture(top,bottom)
    files.update({'WORK/SCORE#064000':main_score,'WORK/SCORE.OBJ#067400':obj,
                  'WORK/ORPHAN#064000':main_score})
    addr = int(re.search(r'al ([0-9A-Fa-f]{6}) \._mc_regs',
                         (BUILD / 'mcs.lbl').read_text())[1], 16)
    with tempfile.TemporaryDirectory(prefix='mcs-native-') as tmp:
        with boot_hd(Path(tmp), files, port=6917, plugins=['mcs']) as (p, s):
            s.key(b'/');s.select('/WORKHD');s.key(RET);s.select('WORK');s.key(RET);p.stable()
            p.sync_disks();disk_before=Path(p.hdv).read_bytes()
            aux = p.peek(0x1000, 0xb000, 'aux')
            floor = s.sym['__HIMEM__'] - s.sym['__STACKSIZE__']
            p.poke(floor, b'\xa5'*8)
            p.rq('/speed', {'preset': '1x'})
            s.select('SONG.MCS');menu_run(s, p, 'MCS')
            s.wait(lambda: s.has('Music Construction Set - SONG.MCS'), 'MCS foreground', 30)
            s.ok('export buffer loaded into MAIN only', p.peek(0x3680, len(tune)) == tune)
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
            s.wait(lambda: s.has('Bad MCS score/export'), 'MCS truncation rejected', 30)
            p.rq('/speed', {'preset':'1x'})
            for name in ('SCORE','SCORE.OBJ'):
                s.select(name);menu_run(s,p,'MCS')
                s.wait(lambda: s.has('Music Construction Set - '+name), 'editor score foreground',30)
                s.ok(name+' converts both staffs',p.peek(0x3680,2304)==score(main_score,obj))
                time.sleep(.3)
                s.ok(name+' drives the AY',any(ay_snapshot(p,'score')[8:11]))
                s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'score exit',30);p.stable()
            s.select('ORPHAN');menu_run(s,p,'MCS')
            s.wait(lambda:s.has('Bad MCS score/export'),'missing .OBJ rejected',30)
            s.ok('missing pair leaves card silent',not any(ay_snapshot(p,'orphan')[8:11]))
            s.ok('AUX unchanged', p.peek(0x1000, 0xb000, 'aux') == aux)
            s.ok('C-stack floor unchanged', p.peek(floor, 8) == b'\xa5'*8)
            p.sync_disks()
            s.ok('source volume unchanged',Path(p.hdv).read_bytes()==disk_before)
    return ok_all(s, 'mcs')


if __name__ == '__main__':
    raise SystemExit(main())
