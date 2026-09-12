"""Real decoder/cache-miss bridge: far offsets, eviction, I/O abort and ZP."""
import subprocess
import re
import tempfile
import unittest
from pathlib import Path
from pt3_fixture import module, used_pages

ROOT = Path(__file__).resolve().parents[1]
PLUGINS = ROOT / 'src/plugins'
C = r'''
#include <stdio.h>
#include <string.h>
extern unsigned pt_end;
extern unsigned char pt_regs[];
unsigned char pt_pages[256];
unsigned char pt_init(void),pt_frame(void);
void __fastcall__ pt_tables(unsigned char*);
unsigned char __fastcall__ test_guard(unsigned);
static unsigned char tables[512], frames[1024][14], saved_zp[32];
static unsigned char large,slot,fault,cache_bad;
static unsigned misses;
static unsigned char ids[5],used;
static void check_zp(void){if(memcmp((void*)0x60,saved_zp,32))cache_bad=1;}
unsigned char __fastcall__ pt_page(unsigned char page){
 unsigned i;unsigned char*dest=(unsigned char*)(0x9000+256*slot);
 ++misses;check_zp();memset((void*)0x60,0x55,32);
 if(fault)return 0;
 if(used==5)pt_pages[ids[slot]]=0;else ++used;
 ids[slot]=page;
 for(i=0;i<(large?sizeof(large_ids):sizeof(small_ids));++i)
  if(page==(large?large_ids[i]:small_ids[i]))break;
 if(i==(large?sizeof(large_ids):sizeof(small_ids)))return 0;
 memcpy(dest,large?large_data[i]:small_data[i],256);
 pt_pages[page]=0x90+slot;
 if(++slot==5)slot=0;
 return pt_pages[page];
}
static void fixture(unsigned char kind){
 large=kind;used=slot=fault=cache_bad=0;misses=0;
 memset(pt_pages,0,sizeof pt_pages);
 memcpy((void*)0x8000,large?large_data[0]:small_data[0],256);
 memcpy((void*)0x8100,large?large_data[1]:small_data[1],256);
 pt_pages[0]=0x80;pt_pages[1]=0x81;
 pt_end=large?65535u:2048;
 memset((void*)0x60,0xA7,32);memcpy(saved_zp,(void*)0x60,32);
 pt_tables(tables);
}
int main(void){
 unsigned i,count;unsigned char r;
 fixture(0);if(pt_init())return 1;check_zp();
 for(count=0;count<1024;++count){r=pt_frame();check_zp();if(r)break;memcpy(frames[count],pt_regs,14);}
 if(r!=2||count<64||cache_bad)return 2;
 fixture(1);if(pt_init())return 3;check_zp();
 for(i=0;i<count;++i){if(pt_frame()||memcmp(frames[i],pt_regs,14))return 4;check_zp();}
 if(pt_frame()!=2||cache_bad||misses<10)return 5;
 /* Miss failure at initialization and after audible frames. */
 fixture(1);fault=1;if(pt_init()!=1)return 6;check_zp();if(cache_bad)return 7;
 fixture(1);if(pt_init())return 8;
 memset(pt_pages+2,0,254);fault=1;if(pt_frame()!=1)return 9;check_zp();if(cache_bad)return 10;
 /* Explicit 16-bit wrap and end-exclusive guard, through pt_enter. */
 fixture(1);if(test_guard(65535u)!=1||test_guard(65534u)!=1)return 11;
 if(test_guard(65533u))return 12;check_zp();if(cache_bad)return 13;
 printf("ok: %u identical frames, page eviction, $FFFE, failed misses and restored zero page\n",count);
 return 0;
}
'''
PROBE = r'''
.export _test_guard
.segment "BSS"
probe_addr: .res 2
.segment "CODE"
_test_guard:
 sta probe_addr
 stx probe_addr+1
 lda #<probe_body
 sta call_song+1
 lda #>probe_body
 jmp pt_enter
probe_body:
 lda #0
 sta DONE_SONG
 lda probe_addr
 sta SAMPLE_L
 lda probe_addr+1
 sta SAMPLE_H
 ldy #1
 jmp checked_sample
'''


def records(name, data):
    pages = used_pages(data)
    return ('static const unsigned char ' + name + '_ids[]={' + ','.join(str(p) for p, _ in pages) + '};\n'
            + 'static const unsigned char ' + name + '_data[][256]={\n'
            + ',\n'.join('{' + ','.join(map(str, block)) + '}' for _, block in pages) + '};\n')


class CacheDecoder(unittest.TestCase):
    def test_large_and_small_songs_match_on_both_cpus(self):
        with tempfile.TemporaryDirectory(prefix='pt3-cache-') as tmp:
            p = Path(tmp)
            (p / 'test.c').write_text(records('small', module(2048)) + records('large', module()) + C)
            (p / 'pt3.s').write_text((PLUGINS / 'pt3.s').read_text().replace('PT3_LOC=$3300', 'PT3_LOC=$8000') + PROBE)
            for cpu in ('sim6502', 'sim65c02'):
                with self.subTest(cpu=cpu):
                    subprocess.run(['cl65', '-t', cpu, '-O', '--asm-include-dir', str(PLUGINS), '-m', str(p / 'test.map'), '-o', str(p / 'test'), str(p / 'test.c'), str(p / 'pt3.s')], check=True)
                    end = re.search(r'^BSS\s+[0-9A-F]+\s+([0-9A-F]+)', (p / 'test.map').read_text(), re.M)
                    self.assertLess(int(end[1], 16), 0x8000, 'fixture header must not overwrite simulator code/BSS')
                    result = subprocess.run(['sim65', str(p / 'test')], capture_output=True, text=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn('identical frames', result.stdout)


if __name__ == '__main__':
    unittest.main()
