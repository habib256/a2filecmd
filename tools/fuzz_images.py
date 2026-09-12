#!/usr/bin/env python3
"""Deterministic, sanitizer-backed mutation campaign for the real image decoders.

Only temporary inputs are read. Native assembly is represented by the existing
host geometry harnesses; run bench/open_images.py for the actual 6502 geometry.
Failures retain the input and diagnostics in --out for reproduction.
"""
import argparse
import os
import random
import subprocess
import tempfile
from pathlib import Path
from test_six_plugins import ROOT
from test_dgrview import HARNESS as DGR
from test_extasie import HARNESS as EXT, BASTILLE
from test_packfot import HARNESS as PACK
from test_paint816 import HARNESS as PAINT, LADDER_PACKED, RUNS_PACKED
from test_sample_media import HARNESS as MEDIA, FONT, PS

# Poison unread input bytes too: ASan alone cannot detect reads of stale bytes
# inside a statically allocated staging buffer.
DGR = DGR.replace('static char host_input[17];', '''
#include <sanitizer/asan_interface.h>
static size_t checked_read(void* p, size_t size, size_t count, FILE* f) {
    size_t n = fread(p, size, count, f);
    __asan_poison_memory_region((char*)p + n * size, (count - n) * size);
    return n;
}
static char host_input[17];''').replace('api.fread = fread;', 'api.fread = checked_read;')
SINGLE = b'DGR\x01\x28\x30\0\0' + bytes([0x55]) * 960
DOUBLE = b'DGR\x01\x50\x30\x01\0' + bytes([0x33]) * 1920
SPECS = {
    'dgr': (DGR, [SINGLE, DOUBLE, bytes([0xF1]) * 1536], ['6', '03']),
    'extasie': (EXT, [BASTILLE], []),
    'packfot': (PACK, [bytes([255, 0x33]) * 32, bytes([255, 0x55]) * 64], ['2']),
    'paint816': (PAINT, [LADDER_PACKED, RUNS_PACKED], ['2']),
    'fontview': (MEDIA.replace('PLUGIN.c','fontview.c').replace('HELPERS',FONT),
                 [bytes([128,127,22])+bytes([14])*128+bytes([127])*5632], ['0','7']),
    'printshop': (MEDIA.replace('PLUGIN.c','printshop.c').replace('HELPERS',PS),
                  [bytes([0x55])*572,bytes([0x33])*576], ['0','6']),
    'lz4fh': (MEDIA.replace('PLUGIN.c','lz4fh.c').replace('HELPERS',''),
              [bytes([0x66,0x1F,0x55,254]),bytes([0x66,0x10,0x33,0,0,15,254])], ['0','6']),
}


def mutations(seeds, count, rng):
    for seed in seeds:
        yield seed
        for cut in sorted({0, 1, 2, 3, 4, 7, 8, 9, len(seed) // 2, len(seed) - 1}):
            yield seed[:cut]
    for _ in range(count):
        data = bytearray(rng.choice(seeds))
        kind = rng.randrange(4)
        if kind == 0:
            data = data[:rng.randrange(len(data) + 1)]
        elif kind == 1:
            for _ in range(rng.randrange(1, 12)):
                data[rng.randrange(len(data))] = rng.randrange(256)
        elif kind == 2:
            at = rng.randrange(len(data))
            data[at:at] = rng.randbytes(rng.randrange(1, 64))
        else:
            data = bytearray(rng.randbytes(rng.randrange(0, 2050)))
        yield bytes(data)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cases', type=int, default=128, help='random mutations per decoder, plus boundary cases')
    p.add_argument('--seed', type=int, default=0xA2FC)
    p.add_argument('--out', type=Path, default=ROOT / 'build/fuzz-images')
    p.add_argument('--decoder', choices=SPECS, action='append')
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:abort_on_error=1', UBSAN_OPTIONS='halt_on_error=1')
    total = 0
    with tempfile.TemporaryDirectory(prefix='a2fc-fuzz-images-') as tmp:
        tmp = Path(tmp)
        for name in a.decoder or SPECS:
            source, seeds, args = SPECS[name]
            c = tmp / (name + '.c'); exe = tmp / name
            c.write_text(source)
            subprocess.run([os.environ.get('CC', 'cc'), '-std=c99', '-g', '-O1',
                            '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                            '-Wno-unknown-pragmas', '-I', str(ROOT), str(c), '-o', str(exe)],
                           check=True, capture_output=True)
            count = 0
            for i, data in enumerate(mutations(seeds, a.cases, random.Random(a.seed))):
                path = tmp / 'input.bin'; path.write_bytes(data)
                try:
                    r = subprocess.run([str(exe), str(path), *args], env=env,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=3)
                    failed = r.returncode not in (0, 2) or b'ERROR: AddressSanitizer' in r.stderr or b'runtime error:' in r.stderr
                    diagnostic = r.stderr
                except subprocess.TimeoutExpired:
                    failed, diagnostic = True, b'decoder exceeded 3 seconds'
                if path.read_bytes() != data:
                    failed, diagnostic = True, b'source file was modified'
                if failed:
                    stem = a.out / f'{name}-{a.seed}-{i}'
                    stem.with_suffix('.bin').write_bytes(data)
                    stem.with_suffix('.log').write_bytes(diagnostic)
                    print(f'FAIL {name} case {i}: {stem}.bin', flush=True)
                    return 1
                count += 1
            total += count
            print(f'PASS {name}: {count} inputs, no bounds violation, timeout or source modification', flush=True)
    print(f'{total} cases passed (seed {a.seed})')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
