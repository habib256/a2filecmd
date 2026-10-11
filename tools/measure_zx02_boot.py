#!/usr/bin/env python3
"""Measure ZX02 with POM2's actual controllers and instruction cycle counts.

Disk II: NMOS/CMOS IIe. Sony 800K: CMOS //c+ at 1.022727 MHz (slow mode).
Same reduced contents for raw/packed images. No host pacing, synthetic HD,
user media, or modifications to A2FC. Each run uses a disposable image.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--pom2-root',type=Path,default=Path('/Users/gistair/src/pom2'))
    ap.add_argument('--repeat',type=int,default=3)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    if args.repeat<1:ap.error('--repeat must be positive')
    if args.output.exists():ap.error('report already exists')
    exe=ROOT/'build/zx02_timing'
    if not exe.is_file():ap.error('build zx02_timing first (see ZX02-EXPERIMENT.md)')
    results=[]
    with tempfile.TemporaryDirectory(prefix='a2fc-cycle-timing-') as name:
        scratch=Path(name)
        for medium,arch in [('disk2','6502'),('disk2','65c02'),('sony35','65c02')]:
            build=ROOT/('build-6502' if arch=='6502' else 'build')
            for variant in ('plain','compressed'):
                stage=scratch/f'{medium}-{arch}-{variant}'
                shutil.copytree(build/'zx02-140-stage',stage)
                if variant=='plain':
                    shutil.copyfile(build/'A2FILE.SYSTEM.SYS',stage/'A2FILE.SYSTEM.SYS')
                    shutil.copyfile(build/'A2FILE.CODE.BIN',stage/'A2FILE/A2FILE.CODE.BIN')
                for trial in range(args.repeat):
                    image=scratch/f'{medium}-{arch}-{variant}-{trial}.po'
                    subprocess.run(['python3',str(ROOT/'tools/mkvolume.py'),str(stage),str(image),
                                    '--volume','ZXTEST','--blocks','280' if medium=='disk2' else '1600',
                                    '--sparse','--a2fc-layout','--boot',str(ROOT/'data/prodos_boot.tmpl')],
                                   check=True,capture_output=True)
                    run=subprocess.run([str(exe),str(args.pom2_root),medium,arch,str(image)],
                                       check=True,capture_output=True,text=True,timeout=120)
                    row=json.loads(next(line for line in run.stdout.splitlines() if line.startswith('{')))
                    row.update(variant=variant,trial=trial+1)
                    row['boot_seconds']=row['panels_cycles']/row['clock_hz']
                    row['load_seconds']=(row['entry_cycles']-row['launcher_cycles'])/row['clock_hz']
                    results.append(row)
                    print(f'{medium} {arch} {variant} #{trial+1}: '
                          f'boot {row["boot_seconds"]:.3f}s, load {row["load_seconds"]:.3f}s; '
                          'AUX and whole volume preserved',flush=True)
    # Exclusive reservation: an earlier report is never overwritten.
    with args.output.open('x') as f:
        json.dump(dict(clock_hz=1022727,pom2_root=str(args.pom2_root),
                       measurement='instruction cycles; identical reduced volumes; Sony //c+ slow mode',
                       runs=results),f,indent=2)
        f.write('\n')


if __name__=='__main__':main()
