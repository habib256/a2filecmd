#!/usr/bin/env python3
"""BLKEDIT on an image file, under the real cc65 stdio and ProDOS.

    make ARCH=6502 && python3 bench/blkedit.py
    make && A2FC_IMG=A2FILECMD-full python3 bench/blkedit.py

cc65's fopen("rb") is O_RDONLY: an editor that opened its image that way
could never write, and a failed write left the stream's error flag set, so
every later read failed too. The image lives on a floppy in drive 2, which
POM2 writes back, so the host checks the bytes: the edited byte is there,
nothing else moved, and a LOCKED image opens, can be looked at, and is
refused at W without a byte written. So is a .2MG whose own flags say write
protected (bit 31, header byte 19). Last, the volume itself: a plain file
under the cursor opens the floppy it is on, and one byte of its block 0 goes
out through WRITE_BLOCK and is read back -- the device half of imageio.h's
write path, which the image cases never take."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from xplug import boot_hd, menu_run, ok_all, RET, ESC
from volname import make_po
from prodos_read import Image

PORT = 6824
DATA = bytes((i * 7) & 255 for i in range(16 * 512))     # a 16-block .PO image
# The same sixteen blocks in a 2IMG container that says "write protected".
PROT = (b'2IMG' + b'A2FC' + (64).to_bytes(2, 'little') + (1).to_bytes(2, 'little') +
        (1).to_bytes(4, 'little') + (0x80000000).to_bytes(4, 'little') +
        (16).to_bytes(4, 'little') + (64).to_bytes(4, 'little') +
        len(DATA).to_bytes(4, 'little')).ljust(64, b'\0') + DATA


def main():
    with tempfile.TemporaryDirectory(prefix='a2fc-blkedit-') as tmp:
        tmp = Path(tmp)
        po = make_po(tmp, 'BLKPO', {'IMAGE.PO#060000': DATA, 'LOCKED.PO#060000': DATA,
                                    'PROT.2MG#060000': PROT, 'NOTE.TXT#040000': b'a plain file\r'})
        floppy = po.read_bytes()
        with boot_hd(tmp, {}, port=PORT, plugins=['blkedit'], floppy2=po) as (p, s):
            s.key(b'/'); s.wait(lambda: s.rows()[0].startswith('[Volumes]'), 'volumes'); p.stable()
            s.select('/BLKPO'); s.key(RET)
            s.wait(lambda: s.has('LOCKED.PO'), 'the floppy', 30); p.stable()

            s.select('IMAGE.PO'); menu_run(s, p, 'BLKEDIT')
            s.wait(lambda: s.has('BLKEDIT - unchanged'), 'the editor', 30); p.stable()
            s.key(b'4'); s.key(b'1'); p.stable()
            s.ok('an edited byte marks the block changed', s.has('CHANGED, NOT WRITTEN'))
            s.key(b'W'); s.wait(lambda: s.has('Type ERASE'), 'the ERASE prompt'); p.stable()
            s.type('ERASE'); s.key(RET)
            s.wait(lambda: s.has('read back identical') or s.has('failed') or s.has('DIFFERS')
                   or s.has('cannot be read back'), 'the write', 30)
            s.ok('the image opened for update takes the block and reads it back',
                 s.has('Block 0 written and read back identical'), s.rows()[22])
            s.key(RET); p.stable()
            s.key(b'N'); p.stable(); s.key(b'P'); p.stable()
            s.ok('the session still reads after the write (block 0 shows 41)',
                 s.has('Block 0 ($0000)') and s.rows()[3][5:7] == '41', s.rows()[3])
            s.key(ESC); p.stable()

            s.select('LOCKED.PO'); s.key(b'L'); p.stable()
            menu_run(s, p, 'BLKEDIT')
            s.wait(lambda: s.has('BLKEDIT - unchanged') or s.has('Invalid'), 'the locked image', 30)
            p.stable()
            s.ok('a locked image still opens to be looked at', s.has('BLKEDIT - unchanged'), s.rows()[0])
            s.key(b'5'); s.key(b'5'); s.key(b'W'); p.stable()
            s.wait(lambda: s.has('locked or read-only') or s.has('Type ERASE'), 'the refusal', 20)
            refused = s.has('locked or read-only')
            if not refused:                     # never type ERASE here: leave the prompt
                s.key(ESC); p.stable()
            s.ok('W on a locked image is refused before any prompt', refused, s.rows()[22])
            s.key(RET); p.stable()
            s.key(ESC); p.stable()
            if s.has('Discard?'):
                s.key(b'Y'); p.stable()

            # A 2IMG that says "write protected" in its own header.
            s.select('PROT.2MG'); menu_run(s, p, 'BLKEDIT')
            s.wait(lambda: s.has('BLKEDIT - unchanged') or s.has('Invalid'), 'the protected 2MG', 30)
            p.stable()
            s.ok('a write-protected 2MG still opens to be looked at',
                 s.has('BLKEDIT - unchanged'), s.rows()[0])
            s.key(b'5'); s.key(b'5'); s.key(b'W'); p.stable()
            s.wait(lambda: s.has('locked or read-only') or s.has('Type ERASE'), 'the refusal', 20)
            refused = s.has('locked or read-only')
            if not refused:                     # never type ERASE here: leave the prompt
                s.key(ESC); p.stable()
            s.ok('W on a write-protected 2MG is refused before any prompt', refused, s.rows()[22])
            s.key(RET); p.stable()
            s.key(ESC); p.stable()
            if s.has('Discard?'):
                s.key(b'Y'); p.stable()

            # The volume itself: WRITE_BLOCK, on this disposable floppy.
            s.select('NOTE.TXT'); menu_run(s, p, 'BLKEDIT')
            s.wait(lambda: s.has('BLKEDIT - unchanged'), 'the editor on the volume', 30); p.stable()
            s.ok('a plain file under the cursor opens the volume it is on',
                 '/BLKPO' in s.rows()[0] and 'NOTE' not in s.rows()[0], s.rows()[0])
            s.key(b'5'); s.key(b'A'); p.stable()
            s.key(b'W'); s.wait(lambda: s.has('Type ERASE'), 'the ERASE prompt'); p.stable()
            s.type('ERASE'); s.key(RET)
            s.wait(lambda: s.has('read back identical') or s.has('failed') or s.has('DIFFERS')
                   or s.has('cannot be read back'), 'the block write', 30)
            s.ok('a block of the volume is written and read back',
                 s.has('Block 0 written and read back identical'), s.rows()[22])
            s.key(RET); p.stable()
            s.key(ESC); p.stable()

        img = Image(po.read_bytes())
        files = {e[1:1 + (e[0] & 15)].decode(): img.read(e) for e in img.entries(2)}
        want = bytes([0x41]) + DATA[1:]
        s.ok('on the host, IMAGE.PO has byte 0 = $41 and every other byte intact',
             files.get('IMAGE.PO') == want,
             (files.get('IMAGE.PO') or b'')[:4].hex())
        s.ok('on the host, LOCKED.PO is byte for byte unchanged', files.get('LOCKED.PO') == DATA)
        s.ok('on the host, PROT.2MG is byte for byte unchanged', files.get('PROT.2MG') == PROT)
        raw = po.read_bytes()
        s.ok('on the host, block 0 of the floppy has byte 0 = $5A and the rest of it intact',
             raw[0] == 0x5A and raw[1:512] == floppy[1:512], raw[:4].hex())
    return ok_all(s, 'blkedit')


if __name__ == '__main__':
    sys.exit(main())
