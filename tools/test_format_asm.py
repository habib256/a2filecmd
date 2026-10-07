#!/usr/bin/env python3
"""FORMAT's assembly helpers under sim65, on the 6502 and the 65C02.

- online_unit (src/format_mli.s): one ON_LINE for all units, then the unit
  holding a volume name, ended by '/' or by its zero byte, skipping one
  unit. tools/test_format.py relies on a C model of it; this runs the real
  routine against a fake MLI at $BF00 that checks the call (ON_LINE $C5,
  unit 0, buffer $3E00) and copies prepared records.
- block_fold (src/format_mli.s): the identity checksum of the 512 bytes at
  $3E00, compared with a Python model.
- diskii_begin (src/format_diskii.s): the write-protect answer BEFORE any
  track. On 0b64a8c (release-0.9.6) it always returned 0 and the protection
  was read inside the first diskii_track, after the resident had been
  copied into AUX over /RAM. sim65's memory has no soft switches: the byte at
  $C08E + slot x 16 is what the sense line reads.
"""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FAKE = r'''
        .export _fakemli, _mli_cmd, _mli_unit, _mli_buf, _mli_fail, _records, _mli_calls
        .importzp ptr1, ptr2
        .bss
_mli_cmd:  .res 1
_mli_unit: .res 1
_mli_buf:  .res 2
_mli_fail: .res 1
_mli_calls: .res 1
_records:  .res 512
        .code
; JSR $BF00 / .byte cmd / .word parms: record the call, copy _records to
; the buffer of the parameters, return past them, carry = _mli_fail.
_fakemli:
        inc _mli_calls
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
        lda _mli_fail
        bne done
        lda _mli_buf
        sta ptr2
        lda _mli_buf+1
        sta ptr2+1
        ldy #0
cp:     lda _records,y
        sta (ptr2),y
        iny
        bne cp
done:   clc
        lda ptr1
        adc #4
        sta ptr1
        bcc :+
        inc ptr1+1
:       lda _mli_fail
        cmp #1
        lda #$27
        jmp (ptr1)
'''

HARNESS = r'''
#include <stdio.h>
#include <string.h>
extern unsigned char mli_cmd, mli_unit, mli_fail, mli_calls, records[512];
extern unsigned int mli_buf;
void fakemli(void);
unsigned char __fastcall__ online_unit(const char* name, unsigned char skip);
unsigned int __fastcall__ block_fold(unsigned int sig);
unsigned char __fastcall__ diskii_begin(unsigned char slotdrive);
#define POKE(a,v) (*(unsigned char*)(a) = (v))
static unsigned char* rec(unsigned char i, unsigned char unit, const char* name)
{
    unsigned char* r = records + 16 * i;
    unsigned char n = strlen(name);
    memset(r, 0, 16);
    r[0] = unit | n;
    memcpy(r + 1, name, n);
    return r;
}
static void ask(const char* label, const char* name, unsigned char skip)
{
    unsigned char u;
    mli_cmd = mli_unit = 0; mli_buf = 0;
    memset((void*)0x3E00, 0xA5, 512);      /* stale bytes: must not count */
    u = online_unit(name, skip);
    printf("%s %02X cmd=%02X unit=%02X buf=%04X\n", label, u, mli_cmd, mli_unit, mli_buf);
}
int main(void)
{
    unsigned int i;
    POKE(0xBF00, 0x4C); POKE(0xBF01, (unsigned)fakemli & 0xFF); POKE(0xBF02, (unsigned)fakemli >> 8);
    memset(records, 0, sizeof records);
    rec(0, 0x60, "FLOPPY");
    records[16] = 0xE0; records[17] = 0x27;           /* an error record */
    rec(2, 0x70, "BOOT");
    rec(3, 0x50, "RAM");
    rec(4, 0xB0, "RAM");
    rec(5, 0x40, "ABCDEFGHIJKLMNO");
    mli_fail = 0;
    ask("bootpath", "BOOT/A2FILE/A2FILE.CFG", 0);
    ask("ram", "RAM", 0);
    ask("ramskip", "RAM", 0x50);
    ask("ramskip2", "RAM", 0xB0);
    ask("prefix", "BOO", 0);
    ask("longer", "BOOTX", 0);
    ask("floppy", "FLOPPY", 0x70);
    ask("floppyself", "FLOPPY", 0x60);
    ask("fifteen", "ABCDEFGHIJKLMNO", 0);
    ask("absent", "WORK", 0);
    /* sixteen records, no terminator after them: the last one counts, the
     * bytes past 256 never do */
    for (i = 0; i < 16; ++i) rec(i, 0x10 + (i << 4 & 0x70) + (i >= 8 ? 0x80 : 0), "X");
    rec(15, 0xF0, "LAST");
    memset(records + 256, 0x41, 256);
    ask("last", "LAST", 0);
    ask("past16", "AAAA", 0);
    mli_fail = 1;
    ask("fail", "BOOT", 0);
    /* block_fold over a pattern */
    for (i = 0; i < 512; ++i) ((unsigned char*)0x3E00)[i] = (unsigned char)(i * 7 + (i >> 8) * 3 + 1);
    printf("fold %u %u\n", block_fold(0), block_fold(0xBEEF));
    /* diskii_begin: slot 6, both drives, sense line clear then set */
    POKE(0xC0EE, 0x00);
    printf("begin60 %02X\n", diskii_begin(0x60));
    printf("beginE0 %02X\n", diskii_begin(0xE0));
    POKE(0xC0EE, 0x80);
    printf("begin60p %02X\n", diskii_begin(0x60));
    printf("beginE0p %02X\n", diskii_begin(0xE0));
    POKE(0xC0DE, 0x80); POKE(0xC0EE, 0x00);
    printf("begin50p %02X\n", diskii_begin(0x50));
    return 0;
}
'''


def seg(src):
    return (src.replace('.segment "FORMATBSS"', '.bss')
               .replace('.segment "FORMATRO"', '.rodata')
               .replace('.segment "FORMAT"', '.code'))


def fold(sig, data):
    for b in data:
        sig = (((sig << 1) | (sig >> 15)) + b) & 0xFFFF
    return sig


class FormatAsm(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='format-asm-')
        p = Path(cls.tmp.name)
        (p / 'mli.s').write_text(seg((ROOT / 'src/format_mli.s').read_text()))
        # The write loop's 64-byte alignment and its page assertions guard
        # its cycle timing, which this test does not run (Trans is never
        # called): sim65's CODE segment is not aligned for them.
        diskii = (ROOT / 'src/format_diskii.s').read_text()
        cut = diskii.index('; A taken branch must never add')
        assert diskii.count('        .align 64\n') == 1 and diskii[cut:].count('.assert') == 2
        (p / 'diskii.s').write_text(seg(diskii[:cut].replace('        .align 64\n', '')))
        (p / 'fake.s').write_text(FAKE)
        (p / 'h.c').write_text(HARNESS)
        cls.out = {}
        for target in ('sim6502', 'sim65c02'):
            exe = p / ('t_' + target)
            subprocess.run(['cl65', '-t', target, '-O', '-o', str(exe), str(p / 'h.c'),
                            str(p / 'mli.s'), str(p / 'diskii.s'), str(p / 'fake.s')], check=True, cwd=p)
            cls.out[target] = {l.split()[0]: l.split()[1:] for l in
                               subprocess.check_output(['sim65', str(exe)], text=True).splitlines()}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_online_unit(self):
        expect = {'bootpath': '70', 'ram': '50', 'ramskip': 'B0', 'ramskip2': '50', 'prefix': '00',
                  'longer': '00', 'floppy': '60', 'floppyself': '00', 'fifteen': '40', 'absent': '00',
                  'last': 'F0', 'past16': '00', 'fail': 'FF'}
        for target, out in self.out.items():
            for case, unit in expect.items():
                with self.subTest(target=target, case=case):
                    self.assertEqual(out[case][0], unit)
                    self.assertEqual(out[case][1:], ['cmd=C5', 'unit=00', 'buf=3E00'])

    def test_block_fold(self):
        data = bytes((i * 7 + (i >> 8) * 3 + 1) & 255 for i in range(512))
        for target, out in self.out.items():
            with self.subTest(target=target):
                self.assertEqual(out['fold'], [str(fold(0, data)), str(fold(0xBEEF, data))])

    def test_diskii_begin_reports_write_protect(self):
        """Before (0b64a8c): 00 in every case below."""
        for target, out in self.out.items():
            with self.subTest(target=target):
                self.assertEqual(out['begin60'], ['00'])
                self.assertEqual(out['beginE0'], ['00'])
                self.assertEqual(out['begin60p'], ['2B'])
                self.assertEqual(out['beginE0p'], ['2B'])
                self.assertEqual(out['begin50p'], ['2B'], 'slot 5: its own sense line')


if __name__ == '__main__':
    unittest.main()
