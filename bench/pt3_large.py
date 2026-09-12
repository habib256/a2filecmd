#!/usr/bin/env python3
"""Large generated PT3: 1x playback, cache misses, transport and preservation."""
import re
import sys
import tempfile
import time
from pathlib import Path
from pom2 import BUILD, ROOT, labels
from xplug import boot_hd, RET, ESC, ok_all
from pt3 import ay_snapshot

sys.path.insert(0, str(ROOT / 'tools'))
from pt3_fixture import module


def auxiliary(p):
    # Entire AUX bank except the 80-column text screen, which is expected to change.
    return p.peek(0, 0x400, 'aux') + p.peek(0x800, 0xF800, 'aux')


def silent(p):
    ay = ay_snapshot(p, 'stopped')
    return ay[7] & 63 == 63 and not any(ay[8:11]) and not ay[16] & 127


def quiet_after_probe(p):
    # The resident card probe resets AY registers before the loader runs;
    # a rejected file must remain inaudible but need not set mixer R7 to 63.
    ay = ay_snapshot(p, 'rejected')
    return not any(ay[8:11]) and not ay[16] & 127


def main():
    big = module()
    bad = bytearray(big)
    bad[107:109] = b'\xff\xff'
    files = {'WORK/A.LARGE.PT3#000000': big,
             'WORK/B.SMALL.PT3#000000': module(2048),
             'WORK/C.BAD.PT3#000000': bytes(bad),
             'WORK/D.HUGE.PT3#000000': big + b'\0'}
    regs = int(re.search(r'al ([0-9A-Fa-f]{6}) \._pt_regs', (BUILD / 'pt3.lbl').read_text())[1], 16)
    with tempfile.TemporaryDirectory(prefix='a2fc-pt3-large-') as tmp:
        with boot_hd(Path(tmp), files, port=6972, plugins=['pt3']) as (p, s):
            path = Path(p.hdv)
            disk = path.read_bytes()
            s.key(b'/'); s.select('/WORKHD'); s.key(RET); s.select('WORK'); s.key(RET)
            s.select('A.LARGE.PT3'); before = auxiliary(p)
            sym = labels()
            cold = sym['__ONCE_RUN__']
            floor = sym['__HIMEM__'] - sym['__STACKSIZE__']
            # Only dead startup code/free space BELOW the reserved C stack.
            # Never overwrite live stack arguments to plant a watermark.
            guard = bytes([0xD7]) * (floor - cold)
            p.poke(cold, guard)
            p.rq('/speed', {'preset': '1x'})
            s.key(RET)
            s.wait(lambda: s.has('ProTracker 3 - A.LARGE.PT3'), 'large PT3', 60)
            s.wait(lambda: any(p.peek(regs + 8, 3)), 'nonzero volumes', 10)
            s.ok('65535-byte PT3 reaches actual AY hardware', any(ay_snapshot(p, 'playing')[8:11]))
            s.key(b'P'); time.sleep(.2); paused = p.peek(regs, 14); time.sleep(.3)
            s.ok('pause holds decoder frames', p.peek(regs, 14) == paused)
            s.ok('pause silences AY', silent(p))
            s.key(b'P')
            s.key(b'\x15')
            s.wait(lambda: s.has('ProTracker 3 - B.SMALL.PT3'), 'next track', 60)
            s.ok('Right closes the large file and opens the next track', True)
            s.key(b'\x08')
            s.wait(lambda: s.has('ProTracker 3 - A.LARGE.PT3'), 'previous track', 60)
            started = time.monotonic()
            s.wait(lambda: s.has('Type  Aux'), 'large track natural end at 1x', 30)
            elapsed = time.monotonic() - started
            s.ok('large track finishes without decoder or I/O error',
                 not s.has('Invalid PT3.') and not s.has('error.'))
            # 64 rows * speed 6 * 20 ms = 7.68 s, plus the closing frame.
            # Polling observes the start late; allow UI/host scheduling overhead.
            s.ok('1x hard-disk playback keeps the expected song duration', 5.5 < elapsed < 11,
                 '%.2f seconds' % elapsed)
            s.ok('natural end returns silently to both panels', silent(p))
            s.ok('all AUX outside the text screen is preserved', auxiliary(p) == before)
            s.select('C.BAD.PT3'); s.key(RET)
            s.wait(lambda: s.has('Invalid PT3.'), 'out-of-range sample', 30)
            s.ok('offset $FFFF is refused without disturbing panels', s.has('Type  Aux') and quiet_after_probe(p))
            s.select('D.HUGE.PT3'); s.key(RET)
            s.wait(lambda: s.has('Bad/large PT3'), '65536-byte refusal', 60)
            s.ok('65536-byte source is refused safely', s.has('Type  Aux') and quiet_after_probe(p))
            s.select('A.LARGE.PT3'); s.key(RET)
            s.wait(lambda: s.has('ProTracker 3 - A.LARGE.PT3'), 'replay', 60)
            s.key(ESC); s.wait(lambda: s.has('Type  Aux'), 'escape', 30)
            s.ok('Escape closes playback and silences hardware', silent(p))
            s.ok('cache/stdio calls stay above the reserved C-stack floor', p.peek(cold, len(guard)) == guard)
        s.ok('source volume is preserved byte for byte', path.read_bytes() == disk)
    return ok_all(s, 'large PT3')


if __name__ == '__main__':
    sys.exit(main())
