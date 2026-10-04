"""ram_empty (src/a2fc_mli.s) under sim65: when may the auxiliary bank be
used without asking?

Only when ProDOS's /RAM (the unit whose DEVADR is $FF00) is on line and its
volume directory -- block 2, a volume header (storage type $F) -- counts no
file. Anything else answers 0 and the question is asked, as before: no /RAM
driver (the bank may serve another one), a read error, another storage type,
a file count of 1 or of 256. The real routine runs, sliced out of
a2fc_mli.s with ram_format and findram, against a fake ProDOS global page
(DEVCNT, DEVLST, DEVADR) and a fake MLI at $BF00 that checks the call
(READ_BLOCK, the /RAM unit, copy_buf, block 2) and copies a prepared block.
The block read lands in copy_buf only.
"""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FAKE = r'''
        .export _fakemli, _mli_cmd, _mli_unit, _mli_buf, _mli_blk, _mli_fail, _ramblock
        .export _copy_buf, _guard
        .importzp ptr1, ptr2
        .bss
; copy_buf and its guard, adjacent in this order (one segment, one file):
; a read that ran past the 512 bytes would land in the guard.
_copy_buf: .res 512
_guard:    .res 64
_mli_cmd:  .res 1
_mli_unit: .res 1
_mli_buf:  .res 2
_mli_blk:  .res 2
_mli_fail: .res 1
_ramblock: .res 512
        .code
; JSR $BF00 / .byte cmd / .word parms: pop the return address, read them,
; copy _ramblock to the buffer the parameters name, return past them.
_fakemli:
        pla
        sta ptr1
        pla
        sta ptr1+1
        ldy #1
        lda (ptr1),y
        sta _mli_cmd
        iny
        lda (ptr1),y
        sta ptr2
        iny
        lda (ptr1),y
        sta ptr2+1
        ldy #1
        lda (ptr2),y
        sta _mli_unit
        iny
        lda (ptr2),y
        sta _mli_buf
        iny
        lda (ptr2),y
        sta _mli_buf+1
        iny
        lda (ptr2),y
        sta _mli_blk
        iny
        lda (ptr2),y
        sta _mli_blk+1
        lda _mli_buf            ; copy 512 bytes to the buffer
        sta ptr2
        lda _mli_buf+1
        sta ptr2+1
        ldx #2
        ldy #0
cp:     lda _ramblock,y
cpsrc = cp + 1
        sta (ptr2),y
        iny
        bne cp
        inc cpsrc+1
        inc ptr2+1
        dex
        bne cp
        lda #<_ramblock
        sta cpsrc
        lda #>_ramblock
        sta cpsrc+1
        clc                     ; return past the call: address + 4
        lda ptr1
        adc #4
        sta ptr1
        bcc :+
        inc ptr1+1
:       lda _mli_fail
        cmp #1                  ; carry set: the error
        lda #$27
        jmp (ptr1)
'''

HARNESS = r'''
#include <stdio.h>
#include <string.h>
extern unsigned char copy_buf[512], guard[64];   /* fake.s: adjacent */
extern unsigned char mli_cmd, mli_unit, mli_fail, ramblock[512];
extern unsigned int mli_buf, mli_blk;
void fakemli(void);
unsigned char ram_empty(void);
#define POKE(a,v) (*(unsigned char*)(a) = (v))
static void devices(unsigned char ram_driver)
{
    POKE(0xBF31, 2);                       /* three units */
    POKE(0xBF32, 0x60); POKE(0xBF33, 0xB0); POKE(0xBF34, 0x70);
    memset((void*)0xBF10, 0, 32);
    POKE(0xBF10 + 2 * 6, 0x00); POKE(0xBF11 + 2 * 6, 0xD0);   /* slot 6: a disk */
    POKE(0xBF10 + 2 * 7, 0x00); POKE(0xBF11 + 2 * 7, 0xC7);
    POKE(0xBF10 + 2 * 3 + 16, 0x00);                           /* $B0: drive 2 slot 3 */
    POKE(0xBF11 + 2 * 3 + 16, ram_driver ? 0xFF : 0xD1);
}
static void run(const char* name, unsigned char ram_driver, unsigned char storage,
                unsigned int files, unsigned char fail)
{
    unsigned char r;
    devices(ram_driver);
    memset(ramblock, 0x5A, 512);
    ramblock[4] = storage; ramblock[0x25] = files & 0xFF; ramblock[0x26] = files >> 8;
    memset(copy_buf, 0, 512); memset(guard, 0xC3, sizeof guard);
    mli_cmd = 0; mli_unit = 0; mli_buf = 0; mli_blk = 0; mli_fail = fail;
    r = ram_empty();
    printf("%s %u cmd=%02X unit=%02X buf=%s blk=%u copied=%u guard=%u\n", name, r, mli_cmd,
           mli_unit, mli_buf == (unsigned)copy_buf ? "copy_buf" : (mli_buf ? "other" : "none"),
           mli_blk, copy_buf[4] == storage && mli_cmd, !memchr(guard, 0, sizeof guard) && guard[0] == 0xC3 && guard[63] == 0xC3);
}
int main(void)
{
    POKE(0xBF00, 0x4C); POKE(0xBF01, (unsigned)fakemli & 0xFF); POKE(0xBF02, (unsigned)fakemli >> 8);
    run("empty", 1, 0xF4, 0, 0);
    run("onefile", 1, 0xF4, 1, 0);
    run("files256", 1, 0xF4, 256, 0);
    run("readerror", 1, 0xF4, 0, 1);
    run("subdir", 1, 0xE4, 0, 0);
    run("noram", 0, 0xF4, 0, 0);
    return 0;
}
'''


class RamEmpty(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='ram-empty-')
        p = Path(cls.tmp.name)
        src = (ROOT / 'src/a2fc_mli.s').read_text()
        a = src.index('        .export _ram_format')
        b = src.index('; unsigned int __fastcall__ panel_hash')
        (p / 'ram.s').write_text('        .setcpu "6502"\n' + src[a:b])
        (p / 'fake.s').write_text(FAKE)
        (p / 'h.c').write_text(HARNESS)
        cls.out = {}
        for target in ('sim6502', 'sim65c02'):
            exe = p / ('t_' + target)
            subprocess.run(['cl65', '-t', target, '-O', '-o', str(exe), str(p / 'h.c'),
                            str(p / 'ram.s'), str(p / 'fake.s')], check=True, cwd=p)
            cls.out[target] = {l.split()[0]: l.split()[1:] for l in
                               subprocess.check_output(['sim65', str(exe)], text=True).splitlines()}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_answers(self):
        for target, out in self.out.items():
            with self.subTest(target=target):
                self.assertEqual(out['empty'][0], '1')
                for case in ('onefile', 'files256', 'readerror', 'subdir', 'noram'):
                    self.assertEqual(out[case][0], '0', case)

    def test_the_read_is_block_2_of_ram_into_copy_buf(self):
        for target, out in self.out.items():
            with self.subTest(target=target):
                for case in ('empty', 'onefile', 'files256', 'readerror', 'subdir'):
                    f = dict(x.split('=') for x in out[case][1:])
                    self.assertEqual((f['cmd'], f['unit'], f['buf'], f['blk']),
                                     ('80', 'B0', 'copy_buf', '2'), case)
                    self.assertEqual(f['guard'], '1')
                f = dict(x.split('=') for x in out['noram'][1:])
                self.assertEqual(f['cmd'], '00', 'no /RAM: no read at all')


if __name__ == '__main__':
    unittest.main()
