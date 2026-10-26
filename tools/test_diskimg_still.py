"""DISKIMG W and two-drive O check the target again after ERASE.

di_pick and the ERASE prompt leave all the time needed to swap disks;
before the fix, W and two-drive O then wrote by unit whatever the drive
held, the program's own disk included (di_pick refuses it only when the
list is shown). di_still reads the list again: same unit, same volume
name, still free to write. The actual di_scan and di_still run here on
stand-in ProDOS tables; a disk swap is a change of the volume on line.
"""
import subprocess
import tempfile
import unittest
from test_diskimg_scan import section, SCAN

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
static char question[64];
static void activity_tick(void) {}
static char cfg_path[65] = "/BOOT/A2FILE/A2FILE.CODE", full[81] = "/HARD/DISK.PO";
static const char* volumes[16];
#define DI_SLOTROM(slot) ((const unsigned char*)slotrom[slot])
static unsigned char mli_call(unsigned char cmd, unsigned char* p)
{
    const char* v = volumes[p[1] >> 4];
    if (cmd != 0xC5) abort();
    if (!v) { copy_buf[0] = p[1]; copy_buf[1] = 0x52; return 0; }
    copy_buf[0] = p[1] | (unsigned char)strlen(v);
    memcpy(copy_buf + 1, v, strlen(v));
    return 0;
}
static unsigned char volume_blocks(const char* v, unsigned int* total, unsigned int* free) { (void)v; *total = 1600; *free = 0; return 1; }
''' + SCAN + section('/* After ERASE, before the first write', '/* Opens the image `full`') + r'''
int main(int argc, char** argv)
{
    /* argv[1]: the target's volume when picked ("-": none); argv[2]: the
     * one in that drive after ERASE. Unit $50 (slot 5) is the target. */
    const char* before = strcmp(argv[1], "-") ? argv[1] : NULL;
    const char* after = strcmp(argv[2], "-") ? argv[2] : NULL;
    (void)argc;
    memset(slotrom, 0xA5, sizeof slotrom);
    devlst[0] = 0x60; devadr[6] = 0xD400; volumes[6] = "BOOT";
    devlst[1] = 0x50; devadr[5] = 0xD400; volumes[5] = before;
    devlst[2] = 0x40; devadr[4] = 0xD400; volumes[4] = "HARD";   /* holds the image */
    devcnt = 2;
    di_scan();
    if (state.dev[1].unit != 0x50 || state.dev[1].inuse) return 2;   /* di_pick would take it */
    volumes[5] = after;
    printf("%u\n", di_still(&state.dev[1]));
    return 0;
}
'''


class DiskStill(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='diskimg-still-')
        from pathlib import Path
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

    def still(self, before, after):
        r = subprocess.run([str(self.exe), before, after], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout.strip() == '1'

    def test_the_disk_warned_about_is_written(self):
        self.assertTrue(self.still('SCRATCH', 'SCRATCH'))
        self.assertTrue(self.still('-', '-'))        # no volume either time: not told apart (the stated limit)

    def test_a_swapped_disk_is_refused(self):
        self.assertFalse(self.still('SCRATCH', 'DATA'))
        self.assertFalse(self.still('SCRATCH', 'SCRATCH2'))
        self.assertFalse(self.still('SCRATCH', '-'))      # a blank or DOS 3.3 disk now
        self.assertFalse(self.still('-', 'DATA'))         # a ProDOS disk put in an empty drive

    def test_the_program_disk_or_the_image_disk_is_refused(self):
        self.assertFalse(self.still('SCRATCH', 'BOOT'))   # the program's disk: inuse 1
        self.assertFalse(self.still('-', 'HARD'))         # the disk holding the image: inuse 2


if __name__ == '__main__':
    unittest.main()
