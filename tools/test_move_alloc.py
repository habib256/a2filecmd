"""Exercise MOVE's allocator with native and real 16-bit cc65 arithmetic.

Only the block I/O is replaced. Extract the actual allocator so sim65 can
run it without linking the Apple II UI and overlay header.
"""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREFIX = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define H_BITMAP 0x23
#define H_TOTAL 0x25
static unsigned char storage[8192], buf[512];
static unsigned int total_blocks, reads, writes;
static unsigned int rd16(const unsigned char* p) {
    return p[0] | ((unsigned int)p[1] << 8);
}
static unsigned char rd(unsigned int b) {
    if (b == 2) {
        memset(buf, 0, 512);
        buf[4 + H_BITMAP] = 6;
        buf[4 + H_TOTAL] = total_blocks;
        buf[5 + H_TOTAL] = total_blocks >> 8;
        return 1;
    }
    /* Bound a broken scan so an arithmetic-wrap regression fails promptly. */
    ++reads;
    if (reads > 16 || b < 6 || b > 21) return 0;
    memcpy(buf, storage + (b - 6) * 512, 512);
    return 1;
}
static unsigned char wr(unsigned int b) {
    ++writes;
    memcpy(storage + (b - 6) * 512, buf, 512);
    return 1;
}
'''
SUFFIX = r'''
int main(int argc, char** argv) {
    unsigned long b;
    unsigned int result, free_block;
    total_blocks = (unsigned int)strtoul(argv[1], 0, 10);
    free_block = (unsigned int)strtoul(argv[2], 0, 10);
    /* Padding bits outside the volume are free: they must be ignored. */
    for (b = total_blocks; b < 65536UL; ++b)
        storage[b >> 3] |= 0x80 >> (b & 7);
    if (free_block) storage[free_block >> 3] |= 0x80 >> (free_block & 7);
    result = alloc_block();
    printf("%u %u %u %u\n", result, reads, writes,
           free_block ? !!(storage[free_block >> 3] & (0x80 >> (free_block & 7))) : 0);
    return 0;
}
'''


class MoveAllocator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='move-alloc-')
        folder = Path(cls.tmp.name)
        source = (ROOT / 'src/plugins/move.c').read_text()
        allocator = source.split('static unsigned int alloc_block(void)', 1)[1]
        allocator = 'static unsigned int alloc_block(void)' + allocator.split('\n/*', 1)[0]
        test = folder / 'test.c'
        test.write_text(PREFIX + allocator + SUFFIX)
        cls.commands = {}
        native = folder / 'native'
        subprocess.run(['cc', str(test), '-o', str(native)], check=True)
        cls.commands['native'] = [str(native)]
        if shutil.which('cl65') and shutil.which('sim65'):
            binary = folder / 'sim'
            subprocess.run(['cl65', '-t', 'sim6502', '-O', '-o', str(binary), str(test)],
                           check=True, capture_output=True)
            cls.commands['6502'] = ['sim65', str(binary)]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_allocation_at_bitmap_and_16_bit_boundaries(self):
        for cpu, command in self.commands.items():
            for total in (280, 4096, 4097, 61440, 61441, 65535):
                for free in (0, total - 1):
                    with self.subTest(cpu=cpu, total=total, free=free):
                        result = subprocess.check_output(command + [str(total), str(free)],
                                                         text=True, timeout=15)
                        self.assertEqual(list(map(int, result.split())),
                                         [free, (total + 4095) // 4096, int(free != 0), 0])


if __name__ == '__main__':
    unittest.main()
