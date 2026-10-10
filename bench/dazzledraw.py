#!/usr/bin/env python3
"""Compare real Dazzle Draw pictures with its unchanged DD.PICLOADER in POM2.

Uses a local copy of 132_DAZZLE_DRAW_SLIDE_SHOW.dsk; no copyrighted files
are distributed. All emulated volumes are disposable. Run on both builds:
 A2FC_IMG=A2FILECMD-full python3 bench/dazzledraw.py
 A2FC_BUILD=build-6502 A2FC_PRESET=iie_unenh python3 bench/dazzledraw.py
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from prodos_read import Image
from po2dsk import SECTORS
from xplug import boot_hd, RET, ESC, ok_all
from pom2 import Pom2, ROOT, PRESET

NAMES = ('MONARCH', 'ROOM', 'SCREEN.SHOE')


def corpus(path):
    raw = path.read_bytes()
    assert len(raw) == 143360, 'expected a 35-track DOS-order image'
    po = bytearray(len(raw))
    for block in range(280):
        track, pair = divmod(block, 8)
        for half, sector in enumerate(SECTORS[pair]):
            off = (track * 16 + sector) * 256
            po[block * 512 + half * 256:block * 512 + (half + 1) * 256] = raw[off:off + 256]
    image = Image(bytes(po))
    entries = {e[1:1 + (e[0] & 15)].decode(): e for e in image.entries(2)}
    files = {}
    for name in ('DD.PICLOADER', *NAMES):
        e = entries[name]
        files[name] = image.read(e)
        assert e[0x10] == (0xFC if name == 'DD.PICLOADER' else 6)
        if name in NAMES:
            assert int.from_bytes(e[0x1F:0x21], 'little') == 0x2000
            assert len(files[name]) == 16384
    return raw, files


def planes(p):
    return bytes(p.peek(0x2000, 8192, 'aux')) + bytes(p.peek(0x2000, 8192))


def frame(p):
    with urllib.request.urlopen(p.base + '/screen.ppm', timeout=10) as response:
        return response.read()


def wait(test, label, seconds=30):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if test():
            return
        time.sleep(0.05)
    raise AssertionError('timeout: ' + label)


def oracle(tmp, files):
    stage = tmp / 'oracle-stage'
    stage.mkdir()
    for name in ('PRODOS.SYS', 'BASIC.SYSTEM.SYS'):
        shutil.copyfile(ROOT / 'data' / name, stage / name)
    for name, data in files.items():
        (stage / (name + ('#FC0801' if name == 'DD.PICLOADER' else '#062000'))).write_bytes(data)
    hd = tmp / 'oracle.hdv'
    subprocess.run([sys.executable, str(ROOT / 'tools/mkvolume.py'), str(stage), str(hd),
                    '--volume', 'DDTEST', '--boot', str(ROOT / 'data/prodos_boot.tmpl'),
                    '--blocks', '4000'], check=True, capture_output=True)
    before = hd.read_bytes()
    result = {}
    with Pom2(hd, port=6979, boot=None, preset=PRESET) as p:
        wait(lambda: any(']' in r for r in p.screen40()), 'Applesoft prompt')
        for name in NAMES:
            p.keys('RUN DD.PICLOADER\r')
            wait(lambda: any('Name of picture to load?' in r for r in p.screen()), 'loader prompt')
            p.keys(name + '\r')
            wait(lambda: planes(p) == files[name], 'original picture ' + name)
            p.stable()
            result[name] = (planes(p), frame(p))
            print('PASS: DD.PICLOADER loads both complete planes of ' + name, flush=True)
        p.sync_disks()
    assert hd.read_bytes() == before, 'oracle volume changed'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus', type=Path, default=Path.home() / '.cache/a2fc/dazzle/132_DAZZLE_DRAW_SLIDE_SHOW.dsk')
    parser.add_argument('--out', type=Path, help='optional JSON report')
    args = parser.parse_args()
    original, files = corpus(args.corpus)
    with tempfile.TemporaryDirectory(prefix='a2fc-dazzledraw-') as directory:
        tmp = Path(directory)
        expected = oracle(tmp, files)
        work = {f'WORK/{name}#062000': files[name] for name in NAMES}
        with boot_hd(tmp, work, port=6980) as (p, s):
            before_hd = Path(p.hdv).read_bytes()
            s.key(b'/'); s.select('/WORKHD'); s.key(RET)
            s.select('WORK'); s.key(RET); p.stable()
            s.select(NAMES[0]); s.ram_occupied()
            before_aux = bytes(p.peek(0x1000, 0xB000, 'aux'))
            s.key(RET)
            s.wait(lambda: s.has('ALL /RAM files will be LOST'), 'RAM consent')
            s.ok('Dazzle Draw asks before touching occupied RAM',
                 bytes(p.peek(0x1000, 0xB000, 'aux')) == before_aux)
            s.key(b'N'); p.stable()
            s.ok('declining preserves occupied RAM',
                 bytes(p.peek(0x1000, 0xB000, 'aux')) == before_aux and s.value('view', 1) == 0)
            for name in NAMES:
                for key in (RET, b'I'):
                    s.select(name); s.key(key); s.allow_aux()
                    label = name + (' Return' if key == RET else ' I')
                    s.wait(lambda: s.value('view', 1) == 1, label)
                    s.wait(lambda: planes(p) == expected[name][0], label + ' native pixels')
                    s.ok(label + ' matches DD.PICLOADER: all 16384 bytes', True)
                    s.wait(lambda: frame(p) == expected[name][1], label + ' rendered screen')
                    s.ok(label + ' rendered screen matches DD.PICLOADER', True)
                    s.key(ESC); s.wait(lambda: s.has('Type  Aux'), 'panels'); p.stable()
            p.sync_disks()
        assert Path(p.hdv).read_bytes() == before_hd, 'A2FC volume changed'
    assert args.corpus.read_bytes() == original, 'corpus changed'
    if args.out:
        args.out.write_text(json.dumps({'preset': PRESET, 'corpus': str(args.corpus),
            'corpus_sha256': hashlib.sha256(original).hexdigest(),
            'loader_sha256': hashlib.sha256(files['DD.PICLOADER']).hexdigest(),
            'pictures': {n: hashlib.sha256(files[n]).hexdigest() for n in NAMES},
            'checks': s.checks}, indent=2) + '\n')
    return ok_all(s, 'dazzledraw')


if __name__ == '__main__':
    sys.exit(main())
