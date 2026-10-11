#!/usr/bin/env python3
"""Experimental ZX02 boot on disposable HD copies; no physical-drive timing."""
import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bench'))
from pom2 import Pom2, Session, ROOT


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--build', choices=('build', 'build-6502'), required=True)
    ap.add_argument('--disk-ii', action='store_true')
    ap.add_argument('--cycles-per-frame',type=int,help='default: 17045 on IIe')
    ap.add_argument('--repeat',type=int,default=1)
    ap.add_argument('--json-output',type=Path,help='exclusively create a measurement report')
    ap.add_argument('--variant',choices=('compressed','plain','bad-crc'),action='append',
                    help='run selected variants only (default: all three)')
    a = ap.parse_args()
    if a.repeat < 1:ap.error('--repeat must be positive')
    if a.json_output and a.json_output.exists():ap.error('report already exists')
    if a.cycles_per_frame is None:a.cycles_per_frame=17045
    if not 1 <= a.cycles_per_frame <= 2_000_000:ap.error('invalid cycle budget')
    build = ROOT/a.build
    preset = 'iie_unenh' if a.build == 'build-6502' else 'iie'
    # POM2 scales mechanical clocks with the base CPU budget above 1x.
    clock_hz=1022727 * max(1,a.cycles_per_frame/17045)
    results=[]
    with tempfile.TemporaryDirectory(prefix='zxboot-native-') as t:
        tmp = Path(t)
        for trial in range(a.repeat):
          for variant in a.variant or ('compressed', 'plain', 'bad-crc'):
            stage = tmp/f'{trial}-{variant}'
            shutil.copytree(build/('zx02-140-stage' if a.disk_ii else 'zx02-stage'),stage)
            if variant == 'plain':
                shutil.copyfile(build/'A2FILE.SYSTEM.SYS',stage/'A2FILE.SYSTEM.SYS')
                shutil.copyfile(build/'A2FILE.CODE.BIN',stage/'A2FILE/A2FILE.CODE.BIN')
            if variant == 'bad-crc':
                p = stage/'A2FILE/A2FILE.CODE.BIN'
                d = bytearray(p.read_bytes());d[8] ^= 1;p.write_bytes(d)
            hd = tmp/f'{trial}-{variant}.po'
            import subprocess
            subprocess.run([sys.executable,str(ROOT/'tools/mkvolume.py'),str(stage),str(hd),'--volume','ZXTEST','--blocks','280' if a.disk_ii else '2000','--sparse','--a2fc-layout','--boot',str(ROOT/'data/prodos_boot.tmpl')],check=True,capture_output=True)
            before = hd.read_bytes()
            if a.disk_ii:
                dummy = tmp/'dummy.po'
                shutil.copyfile(build/'A2FC-ZX02-800.po',dummy)
            start = time.monotonic()
            with Pom2(dummy if a.disk_ii else hd,floppy=hd if a.disk_ii else None,port=6974,speed=a.cycles_per_frame,preset=preset) as p:
                s = Session(p)
                if variant != 'plain':
                    s.wait(lambda:s.has('Loading A2FILE.CODE'),'launcher',60)
                    aux = p.peek(0x1000,0xB000,'aux')
                    p.poke(0xBEDF,b'\xA5')  # below reserved 32-byte launcher stack
                s.wait(lambda:s.has('Compressed image invalid') if variant=='bad-crc' else s.has('Type  Aux     Size'),variant,120)
                elapsed = time.monotonic()-start
                cycles=p.rq('/status')['cpu']['cycles']
                if variant != 'plain':
                    s.ok('AUX including /RAM preserved',p.peek(0x1000,0xB000,'aux')==aux)
                    s.ok('Launcher stack floor preserved',p.peek(0xBEDF,1)==b'\xA5')
                if variant == 'compressed':
                    p.stable()
                    s.wait(lambda:s.has('RECOVER'),'boot root directory',30)
                    s.select('RECOVER');s.key(b't')
                    s.wait(lambda:s.has('KEEP THE EVIDENCE'),'TEXT overlay content after compressed boot',60)
                    s.ok('Normal overlay remains usable',True)
                p.sync_disks()
                s.ok('Whole boot image preserved',hd.read_bytes()==before)
                medium='Disk II' if a.disk_ii else 'HD'
                result=dict(build=a.build,preset=preset,medium=medium,variant=variant,trial=trial+1,
                            wall_seconds=elapsed,cycles=cycles,cpu_clock_hz=clock_hz,
                            emulated_seconds=cycles/clock_hz)
                results.append(result)
                print(f'{a.build} {variant} #{trial+1}: {elapsed:.2f}s wall, {cycles/clock_hz:.2f}s emulated, {cycles} cycles, {medium}, {a.cycles_per_frame} cycles/frame',flush=True)
    if a.json_output:
        with a.json_output.open('x') as f:json.dump(results,f,indent=2);f.write('\n')
    return 0


if __name__=='__main__':raise SystemExit(main())
