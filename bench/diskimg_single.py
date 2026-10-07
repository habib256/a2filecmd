#!/usr/bin/env python3
"""DISKIMG O with one drive: the mark goes only onto the target, read again.

Bug hunt 3. A single-drive copy first writes a mark (512 x $A5) on block 2
of the target -- its volume directory key block. The ERASE prompt came after
the first TARGET prompt and waited as long as the user liked; a disk swapped
in meanwhile received the mark without block 2 being read again, so the
source put back lost its volume directory. And with the target inserted
after the device list, before the first read, the target's own block 2 was
kept as the source's: the source was then taken for the target. Three runs
on disposable floppies:

1. the source put back during the ERASE prompt: "Failed: disk switched.",
   both floppies byte for byte as they were;
2. the target inserted between the FROM and the TO picks: refused the same
   way before any read or write;
3. the whole copy, swapping at every prompt: the target becomes the source.

    make disk && python3 bench/diskimg_single.py
    A2FC_IMG=A2FILECMD-full python3 bench/diskimg_single.py   # 65C02
"""
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from xplug import boot_hd, ok_all, RET, ESC, ROOT


def volume(tmp, name, text):
    stage = tmp / ('stage-' + name)
    stage.mkdir()
    (stage / 'NOTE.TXT#040000').write_bytes(text * 200)
    image = tmp / (name + '.po')
    subprocess.run([sys.executable, str(ROOT / 'tools/mkvolume.py'), str(stage), str(image),
                    '--volume', name, '--blocks', '280'], check=True, capture_output=True)
    return image


def main():
    with tempfile.TemporaryDirectory(prefix='a2fc-diskimg1-') as t:
        tmp = Path(t)
        source = volume(tmp, 'SRCDSK', b'the source floppy\r')
        target = volume(tmp, 'TGTDSK', b'the target floppy\r')
        src_bytes, tgt_bytes = source.read_bytes(), target.read_bytes()
        # the source in drive 2 at power-on (drive 1 would be booted), then
        # moved to drive 1, as bench/disksingle.py does
        with boot_hd(tmp, {'WORK/README.TXT': b'bench\r'}, port=6999, floppy2=source) as (p, s):
            p.eject(1); p.insert(0, str(source)); time.sleep(.5)

            def drive_key(slot, drive):
                for _ in range(20):
                    for r in s.rows():
                        if f'slot {slot} drive {drive}' in r:
                            return r.strip()[0].encode()
                    time.sleep(0.1)
                raise AssertionError('drive not listed\n' + '\n'.join(s.rows()))

            def open_copy():
                s.select('WORK'); s.key(b'W'); s.allow_aux()
                s.wait(lambda: s.has('DISK IMAGES'), 'the disk images menu'); p.stable()
                s.key(b'O'); s.wait(lambda: s.has('Copy FROM which disk'), 'FROM'); p.stable()

            def settle():
                p.eject(0); time.sleep(.5)

            # 1. the source put back during the ERASE prompt
            open_copy()
            s.key(drive_key(6, 1)); s.wait(lambda: s.has('Copy TO which drive'), 'TO'); p.stable()
            s.key(drive_key(6, 1))
            s.wait(lambda: s.has('Insert TARGET copy for /SRCDSK'), 'the first TARGET prompt', 30); p.stable()
            p.insert(0, str(target)); s.key(RET)
            s.wait(lambda: s.has('Type ERASE'), 'the ERASE prompt', 30); p.stable()
            s.ok('the warning names the target', s.has('(/TGTDSK) WILL BE LOST'), s.rows()[20].strip())
            p.insert(0, str(source))                     # back in while ERASE is being typed
            s.type('ERASE'); s.key(RET)
            s.wait(lambda: s.has('Failed:') or s.has('Insert'), 'the verdict', 60); p.stable()
            s.ok('the source put back is refused before the mark',
                 s.has('Failed: disk switched.'), s.rows()[22].strip())
            settle()
            s.ok('the source is intact, byte for byte', source.read_bytes() == src_bytes)
            s.ok('the target is untouched', target.read_bytes() == tgt_bytes)

            # 2. the target inserted between the FROM and the TO picks
            p.insert(0, str(source)); time.sleep(.5)
            open_copy()
            s.key(drive_key(6, 1)); s.wait(lambda: s.has('Copy TO which drive'), 'TO'); p.stable()
            p.insert(0, str(target))
            s.key(drive_key(6, 1))
            s.wait(lambda: s.has('Failed:') or s.has('Insert') or s.has('Type ERASE'), 'the verdict', 60); p.stable()
            s.ok('a target inserted after the list is refused at once',
                 s.has('Failed: disk switched.'), s.rows()[22].strip())
            settle()
            s.ok('nothing written on either floppy',
                 source.read_bytes() == src_bytes and target.read_bytes() == tgt_bytes)

            # 3. the whole copy, swapping at every prompt
            p.insert(0, str(source)); time.sleep(.5)
            open_copy()
            s.key(drive_key(6, 1)); s.wait(lambda: s.has('Copy TO which drive'), 'TO'); p.stable()
            s.key(drive_key(6, 1))
            s.wait(lambda: s.has('Insert TARGET copy for /SRCDSK'), 'the first TARGET prompt', 30); p.stable()
            p.insert(0, str(target)); s.key(RET)
            s.wait(lambda: s.has('Type ERASE'), 'the ERASE prompt', 30); p.stable()
            s.type('ERASE'); s.key(RET)
            swaps = 0
            while True:
                s.wait(lambda: s.has('Insert SOURCE') or s.has('Insert TARGET') or s.has('copied to')
                       or s.has('Failed') or s.has('Readback failed'), 'a prompt or the verdict', 300)
                p.stable()
                if not (s.has('Insert SOURCE') or s.has('Insert TARGET')):
                    break
                want = 'SOURCE' if s.has('Insert SOURCE') else 'TARGET'
                p.insert(0, str(source if want == 'SOURCE' else target)); s.key(RET, 0.03)
                s.wait(lambda: not s.has('Insert ' + want), 'the read after the swap', 300)
                swaps += 1
                if swaps > 12:
                    raise AssertionError('the swaps do not end\n' + '\n'.join(s.rows()))
            s.ok('the one-drive copy completes', s.has('280 blocks copied to slot 6 drive 1'),
                 s.rows()[22].strip())
            s.ok('four passes, two prompts each', swaps == 8, swaps)
            settle()
            s.ok('the target is the source, byte for byte', target.read_bytes() == src_bytes)
            s.ok('the source is intact', source.read_bytes() == src_bytes)
        return ok_all(s, 'diskimg_single')


if __name__ == '__main__':
    raise SystemExit(main())
