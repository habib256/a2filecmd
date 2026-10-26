"""Exercise MOVE's allocator with native and real 16-bit cc65 arithmetic.

Only the block I/O is replaced. Extract the actual allocator so sim65 can
run it without linking the Apple II UI and overlay header.
"""
import os
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
static unsigned int total_blocks, bitmap_block = 6, reads, writes;
static unsigned int rd16(const unsigned char* p) {
    return p[0] | ((unsigned int)p[1] << 8);
}
static unsigned char rd(unsigned int b) {
    if (b == 2) {
        memset(buf, 0, 512);
        buf[4 + H_BITMAP] = bitmap_block;
        buf[5 + H_BITMAP] = bitmap_block >> 8;
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
    if (argc > 3) bitmap_block = (unsigned int)strtoul(argv[3], 0, 10);
    /* Padding bits outside the volume are free: they must be ignored. */
    for (b = total_blocks; b < 65536UL; ++b)
        storage[b >> 3] |= 0x80 >> (b & 7);
    if (free_block || argc > 4) storage[free_block >> 3] |= 0x80 >> (free_block & 7);
    result = alloc_block();
    printf("%u %u %u %u\n", result, reads, writes,
           free_block || argc > 4 ? !!(storage[free_block >> 3] & (0x80 >> (free_block & 7))) : 0);
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

    def test_reserved_block_marked_free_is_not_allocated_or_written(self):
        for cpu, command in self.commands.items():
            for total, block in ((280, 0), (280, 1), (280, 2), (280, 5),
                                 (280, 6), (5000, 7), (65535, 21)):
                with self.subTest(cpu=cpu, total=total, block=block):
                    result = subprocess.check_output(command + [str(total), str(block), '6', 'set'],
                                                     text=True, timeout=15)
                    self.assertEqual(list(map(int, result.split())), [0, 1, 0, 1])

    def test_invalid_bitmap_bounds_refuse_before_bitmap_io(self):
        for cpu, command in self.commands.items():
            for total, bitmap in ((280, 0), (280, 1), (280, 2), (280, 5),
                                  (280, 280), (280, 65535), (5000, 4999), (6, 6)):
                with self.subTest(cpu=cpu, total=total, bitmap=bitmap):
                    result = subprocess.check_output(command + [str(total), '0', str(bitmap)],
                                                     text=True, timeout=15)
                    self.assertEqual(list(map(int, result.split())), [0, 0, 0, 0])


RAW_IO = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#ifndef __CC65__
#define __fastcall__
#endif
static unsigned char unit=0x60, buf[512],scratch[512],disk[512],mode,phase;
static unsigned int volume_blocks,reads,writes,escaped,damage;
static uint16_t sum1,sum2;
struct Block {unsigned char n,unit;unsigned char* buffer;unsigned int block;};
static struct Block bio;
static unsigned char io_mli(unsigned char cmd,void* parameter) {
    struct Block* p=parameter;
    if(p->n!=3 || p->unit!=0x60)exit(2);
    if(cmd==0x80)++reads;else if(cmd==0x81)++writes;else exit(3);
    if(p->block<2 || p->block>=volume_blocks){++escaped;return 0x27;}
    if(cmd==0x81) {
        if(mode==2)return 0x27;
        memcpy(disk,p->buffer,512);
        if(mode==5)disk[damage]^=1;
        return mode==3?0x27:0;
    }
    if(mode==1)return 0x27;
    memcpy(p->buffer,disk,512);
    if(mode==4 && phase)p->buffer[damage]^=1;
    return 0;
}
#define RF(name) io_##name
static unsigned char readblk(unsigned char u,unsigned int b,unsigned char* p) {
    struct Block parameter;
    parameter.n=3;parameter.unit=u;parameter.block=b;parameter.buffer=p;
    return io_mli(0x80,&parameter);
}
'''
RAW_MAIN = r'''
int main(int argc,char** argv) {
    unsigned int b,i,rr,nr,s1,s2,ww;
    (void)argc;
    volume_blocks=(unsigned int)strtoul(argv[1],0,10);
    b=(unsigned int)strtoul(argv[2],0,10);mode=atoi(argv[3]);damage=atoi(argv[4]);
    for(i=0;i<512;++i){buf[i]=(unsigned char)(i*17+3);disk[i]=(unsigned char)(i^0xA5);}
    sum1=0x1234;sum2=0xABCD;
    rr=rd(b);nr=reads;s1=sum1;s2=sum2;
    for(i=0;i<512;++i)buf[i]=(unsigned char)(i*17+3);
    reads=writes=0;phase=1;ww=wr(b);
    printf("%u %u %u %u %u %u %u %u %u\n",rr,nr,s1,s2,ww,writes,reads,escaped,!memcmp(disk,buf,512));
    return 0;
}
'''


class MoveRawIO(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='move-raw-');folder=Path(cls.tmp.name)
        source=(ROOT/'src/plugins/move.c').read_text()
        code=source[source.index('static unsigned char __fastcall__ block_valid'):source.index('/* The name of entry')]
        test=folder/'raw.c';test.write_text(RAW_IO+code+RAW_MAIN)
        executable=folder/'host'
        subprocess.run(['cc',str(test),'-o',str(executable)],check=True,capture_output=True)
        cls.commands={'host':[str(executable)]}
        head=Path(os.environ.get('CC65_HEAD',str(Path.home()/'opt/cc65-head')))
        for cpu in ('sim6502','sim65c02'):
            compiler,simulator=shutil.which('cl65'),shutil.which('sim65');env=os.environ.copy()
            if cpu=='sim6502' and (head/'bin/cl65').exists():
                compiler,simulator=str(head/'bin/cl65'),str(head/'bin/sim65')
                env['CC65_HOME']=str(head/'share/cc65')
            executable=folder/cpu
            subprocess.run([compiler,'-t',cpu,'-O','-Oirs','-Cl','--codesize','100',
                            '-o',str(executable),str(test)],env=env,check=True,capture_output=True)
            cls.commands[cpu]=[simulator,str(executable)]

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def test_bounds_errors_and_full_block_readback(self):
        s1,s2=0x1234,0xABCD
        for i in range(512):
            s1=(s1+((i^0xA5)&255))&65535
            s2=(s2+s1)&65535
        for cpu,command in self.commands.items():
            for total in (0,1,2,3,280,4096,61440,65535):
                for block in sorted(b for b in {0,1,2,total-1,total,65535} if b>=0):
                    valid=2<=block<total
                    for mode in (range(6) if valid else (0,)):
                        for damage in ((0,255,256,511) if mode in (4,5) else (0,)):
                            with self.subTest(cpu=cpu,total=total,block=block,mode=mode,damage=damage):
                                result=subprocess.check_output(command+[str(total),str(block),str(mode),str(damage)],text=True,timeout=15)
                                expected=[int(valid and mode!=1),int(valid),
                                          s1 if valid and mode!=1 else 0x1234,s2 if valid and mode!=1 else 0xABCD,
                                          int(valid and mode==0),int(valid),int(valid and mode not in (2,3)),0,
                                          int(valid and mode not in (2,5))]
                                self.assertEqual(list(map(int,result.split())),expected)


if __name__ == '__main__':
    unittest.main()
