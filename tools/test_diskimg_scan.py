"""Run the actual DISKIMG device scan and disk-holding check on stand-in ProDOS tables.

A driver in the language card is not proof of a Disk II: the slot ROM must
carry the Disk II signature, as FORMAT checks it. The disk holding the
panel's directory (R refuses to read it into an image there) needs the
whole volume name: /HARD does not hold /HARD2, and a disk with no ProDOS
volume (a DOS 3.3 floppy) holds nothing.
"""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT/'src/a2fc.c').read_text()


def section(start, end):
    a = SOURCE.index(start)
    return SOURCE[a:SOURCE.index(end, a)]


SCAN = section('#ifndef DI_SLOTROM', 'static void di_title(')
SCAN = SCAN.replace('*(unsigned char*)0xBF31', 'devcnt')
SCAN = SCAN.replace('((unsigned char*)0xBF32)', 'devlst')
SCAN = SCAN.replace('((unsigned int*)0xBF10)', 'devadr')
SCAN = SCAN.replace('(unsigned)online', '(unsigned long)online')

C = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define __fastcall__
#define NAME_LEN 17
struct Dev { unsigned char unit, inuse; unsigned int blocks; char name[NAME_LEN]; };
static struct { struct Dev dev[8]; unsigned char ndev, parms[6]; const unsigned char* rom; } state;
#define DI (&state)
static unsigned char copy_buf[512], devcnt, devlst[14], slotrom[8][256];
static unsigned int devadr[16];
static char cfg_path[65] = "/BOOT/A2FILE/A2FILE.CODE", full[81];
static const char* volumes[16];
#define DI_SLOTROM(slot) ((const unsigned char*)slotrom[slot])
static unsigned char mli_call(unsigned char cmd, unsigned char* p)
{
    const char* v = volumes[p[1] >> 4];
    if (cmd != 0xC5) abort();
    if (!v) { copy_buf[0] = p[1]; copy_buf[1] = 0x52; return 0; }   /* no ProDOS volume */
    copy_buf[0] = p[1] | (unsigned char)strlen(v);
    memcpy(copy_buf + 1, v, strlen(v));
    return 0;
}
static unsigned char volume_blocks(const char* v, unsigned int* total, unsigned int* free) { *total = 1600; *free = 0; return 1; }
static void diskii(unsigned char slot) { slotrom[slot][1] = 0x20; slotrom[slot][3] = 0x00; slotrom[slot][5] = 0x03; slotrom[slot][0xFF] = 0x00; }
''' + SCAN + r'''
int main(int argc, char** argv)
{
    unsigned char i;
    if (argc > 1) strcpy(full, argv[1]);   /* R: the panel's directory and a slash */
    memset(slotrom, 0xA5, sizeof slotrom);
    diskii(6);
    slotrom[5][1] = 0x20; slotrom[5][3] = 0x00; slotrom[5][5] = 0x03; slotrom[5][7] = 0x00; slotrom[5][0xFF] = 0x3C;   /* SmartPort */
    diskii(0);                          /* never read: slot 0 is the soft switches */
    devlst[0] = 0x60; devadr[6] = 0xD000; volumes[6] = "BOOT";       /* Disk II, ProDOS volume */
    devlst[1] = 0xE0; devadr[14] = 0xD000;                           /* Disk II, DOS 3.3 floppy */
    devlst[2] = 0x50; devadr[5] = 0xD400; volumes[5] = "HARD";       /* driver in the LC, SmartPort ROM */
    devlst[3] = 0xD0; devadr[13] = 0xD400;                           /* the same, no volume */
    devlst[4] = 0xB0; devadr[11] = 0xFF00; volumes[11] = "RAM";      /* /RAM */
    devlst[5] = 0x00; devadr[0] = 0xD000;                            /* a slot 0 unit */
    devlst[6] = 0x40; devadr[4] = 0xC400; volumes[4] = "CARD";       /* driver in its ROM */
    devcnt = 6;
    di_scan();
    for (i = 0; i < state.ndev; ++i)
        printf("%02X %u %u %s\n", state.dev[i].unit, state.dev[i].blocks, state.dev[i].inuse, state.dev[i].name);
    return 0;
}
'''


class DiskScan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='diskimg-scan-')
        p = Path(cls.tmp.name)
        (p/'test.c').write_text(C)
        cls.exe = p/'test'
        r = subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-fsanitize=address,undefined',
                            str(p/'test.c'), '-o', str(cls.exe)], capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError(r.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_only_a_disk_ii_counts_280_blocks(self):
        rows = subprocess.check_output([self.exe], text=True).splitlines()
        self.assertEqual(rows, [
            '60 280 1 /BOOT',       # Disk II: 280 whatever its volume says; the program's disk
            'E0 280 0 ',            # Disk II without a ProDOS volume: still readable
            '50 1600 0 /HARD',      # language-card driver, SmartPort ROM: its volume size
            'D0 0 0 ',              # the same without a volume: unknown size
            'B0 1600 0 /RAM',
            '00 0 0 ',
            '40 1600 0 /CARD',
        ])

    def inuse(self, full):
        rows = subprocess.check_output([self.exe, full], text=True).splitlines()
        return [int(r.split()[2]) for r in rows]

    def test_disk_holding_the_directory_needs_the_whole_volume_name(self):
        # units: BOOT (program), DOS 3.3 floppy, HARD, no volume, RAM, slot 0, CARD
        self.assertEqual(self.inuse('/HARD/'), [1, 0, 2, 0, 0, 0, 0])
        self.assertEqual(self.inuse('/HARD/SUB/'), [1, 0, 2, 0, 0, 0, 0])
        self.assertEqual(self.inuse('/HARD2/'), [1, 0, 0, 0, 0, 0, 0])
        self.assertEqual(self.inuse('/HARD2/SUB/'), [1, 0, 0, 0, 0, 0, 0])
        self.assertEqual(self.inuse('/BOOT/WORK/'), [2, 0, 0, 0, 0, 0, 0])   # R may not store the image on the disk it reads


if __name__ == '__main__':
    unittest.main()
