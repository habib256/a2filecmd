#!/usr/bin/env python3
"""FORMAT (src/format.c, the F key) run for real on the host.

The shipped C is compiled with clang, AddressSanitizer and UBSan. Only its
absolute-address accessors (DEVCNT/DEVLST/DEVADR at $BF10-$BF3F, BLOCK at
$3E00, the slot ROMs, the clock at $BF90) and probe()'s two static MLI
buffers (whose 16-bit addresses a 64-bit host cannot follow) are mapped to
mock arrays. The assembly helpers are modelled in C here: format_mli.s's
online_unit and block_fold, and the Disk II writer (diskii_begin/track/end);
tools/test_format_asm.py runs the real ones under sim65.

The mock keeps a 280-block disk per unit, an ON_LINE answer per unit, the
/RAM state (files present, AUX borrowed, rebuilt) and the keys typed. Each
case checks the bytes kept or written, not only the screen.

The first version of this file is the second bug hunt's harness: every case
below failed on 0b64a8c (release-0.9.6) as its docstring says.
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SUBS = [
    ('#define DEVCNT (*(unsigned char*)0xBF31)', '#define DEVCNT (mock_devcnt)'),
    ('#define DEVLST ((unsigned char*)0xBF32)', '#define DEVLST (mock_devlst)'),
    ('#define DEVADR ((unsigned int*)0xBF10)', '#define DEVADR (mock_devadr)'),
    ('#define BLOCK  ((unsigned char*)0x3E00)', '#define BLOCK (mock_block)'),
    ('return (const unsigned char*)(drv & 0xFF00);', 'return mock_rom(drv & 0xFF00);'),
    ('return (const unsigned char*)(0xC000 + slot_of(unit) * 256);', 'return mock_rom(0xC000 + slot_of(unit) * 256);'),
    ('(void*)0xBF90', '(void*)mock_time'),
    ('static unsigned char parms[4], online[16], gfi[18];', 'static unsigned char parms[4];'),
]

PRE = r'''#define __fastcall__
extern unsigned char mock_devcnt, mock_devlst[16], mock_block[512], mock_time[4], online[16], gfi[18];
extern unsigned int mock_devadr[16];
const unsigned char* mock_rom(unsigned int a);
'''

MOCK = r'''
#define __fastcall__
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <stdarg.h>
#include "a2fc_plugin.h"
void format_entry(const struct A2fcApi*);
unsigned char mock_devcnt, mock_devlst[16], mock_block[512], mock_time[4], online[16], gfi[18];
unsigned int mock_devadr[16];
static unsigned char roms[8][256];
const unsigned char* mock_rom(unsigned int a){ return roms[(a>>8)&7]; }

/* The machine */
#define NB 280
static unsigned char disk[16][NB][512];          /* by unit >> 4 */
static char vname[16][16];                       /* ON_LINE: "" = not ProDOS ($52) */
static unsigned int vsize[16];
static int fail_read_block[16][NB];              /* 0, or the error: every read */
static int fail_second[16];                      /* 1 + the block whose read fails after the first identify */
static int reads[16][NB], writes[16][NB], identify_done;
static int aux_borrowed, ram_rebuilt, ram_files = 1, tracks, begin_result, online_fail;
static char screen[60000]; static const char* keys; static int keyi, escapes;
static int swap_at_aux;                          /* the user swaps the disk in S6D1 at the AUX question */
static unsigned char swap_blocks[NB][512]; static char swap_name[16];

void clrscr(void){} void gotoxy(unsigned char x,unsigned char y){(void)x;(void)y;}
unsigned char revers(unsigned char r){(void)r;return 0;}
static void out(const char* t){ if(strlen(screen)+strlen(t)<59000){strcat(screen,t);strcat(screen,"|");} }
int cprintf(const char* f,...){va_list ap;char t[300];va_start(ap,f);vsnprintf(t,300,f,ap);va_end(ap);out(t);return 0;}
void cputs(const char* s){out(s);}
char cgetc(void){ if(keys[keyi]) return keys[keyi++]; if(++escapes>20){printf("RESULT loop\n");exit(3);} return 27; }
void activity_tick(void){}
unsigned char ram_empty(void){ return !ram_files; }
unsigned int format_driver_blocks;
unsigned char format_driver_call(unsigned char unit, unsigned char cmd, unsigned char lc){
  (void)lc; format_driver_blocks=0;
  if(cmd==3 && mock_devadr[unit>>4]==0xFF00){ ram_rebuilt=1; ram_files=0; aux_borrowed=0; return 0; }
  if(cmd==0){ format_driver_blocks = vsize[unit>>4]; return 0; }
  return 0;
}
/* The Disk II writer: begin may refuse (write protect); each track borrows AUX. */
static int dii_unit;
unsigned char diskii_begin(unsigned char sd){ dii_unit=(sd>>4)|(sd&0x80?8:0); return (unsigned char)begin_result; }
unsigned char diskii_track(unsigned char t){
  int b; aux_borrowed=1; ++tracks;
  for(b=t*8;b<t*8+8;++b){ memset(disk[dii_unit][b],0,512); fail_read_block[dii_unit][b]=0; }
  return 0;
}
void diskii_end(void){}

/* format_mli.s modelled: block_fold and online_unit (ON_LINE unit 0) */
unsigned int block_fold(unsigned int sig){
  int i; for(i=0;i<512;++i) sig=(unsigned int)(((sig<<1)|(sig>>15))+mock_block[i])&0xFFFF; return sig;
}
unsigned char online_unit(const char* name, unsigned char skip){
  int i;
  if(online_fail) return 0xFF;
  for(i=0;i<=mock_devcnt;++i){
    unsigned char u=mock_devlst[i]&0xF0; size_t n=strlen(vname[u>>4]);
    if(!n || u==skip || (name[n] && name[n]!='/')) continue;
    if(!memcmp(name,vname[u>>4],n)) return u;
  }
  return 0;
}
static int last_u;
unsigned char mli_call(unsigned char cmd, void* p){
  unsigned char* q=p;
  if(cmd==0xC5){ unsigned char u=(q[1]>>4)&15; size_t n=strlen(vname[u]); last_u=u;
    if(!n) return 0x52; online[0]=(unsigned char)((q[1]&0xF0)|n); memcpy(online+1,vname[u],n); return 0; }
  if(cmd==0xC4){ gfi[5]=vsize[last_u]&255; gfi[6]=vsize[last_u]>>8; return 0; }
  if(cmd==0x82) return 0;
  if(cmd==0x80 || cmd==0x81){
    unsigned char u=(q[1]>>4)&15; unsigned b=q[4]|(q[5]<<8);
    if(q[2]!=0x00 || q[3]!=0x3E){ printf("RESULT bad-buffer\n"); exit(4); }
    if(b>=NB){ if(cmd==0x80) memset(mock_block,0,512); return 0; }   /* large devices: past the model */
    if(cmd==0x81){ ++writes[u][b]; memcpy(disk[u][b],mock_block,512); return 0; }
    ++reads[u][b];
    if(fail_read_block[u][b]){ memset(mock_block,0xEE,512); return (unsigned char)fail_read_block[u][b]; }
    if(identify_done && fail_second[u]==(int)b+1){ memset(mock_block,0xEE,512); return 0x27; }
    memcpy(mock_block,disk[u][b],512); return 0;
  }
  return 0;
}
static unsigned char confirm(const char* q){
  (void)q; identify_done=1;
  if(swap_at_aux){ memcpy(disk[6],swap_blocks,sizeof swap_blocks); strcpy(vname[6],swap_name); }
  return 1;
}
static void diskii_rom(int s){ roms[s][1]=0x20; roms[s][3]=0; roms[s][5]=3; roms[s][0xFF]=0; roms[s][7]=0x3C; }
static void prodos(int u, const char* name){
  size_t n=strlen(name); strcpy(vname[u],name);
  disk[u][2][4]=(unsigned char)(0xF0|n); memcpy(disk[u][2]+5,name,n);
}
/* A DOS 3.3 disk: blocks 0-279 a pattern; block 2 = DOS image, the same on
 * every disk INITed by one DOS; track 17 (blocks 136-143) the VTOC and
 * catalog. Not ProDOS: ON_LINE answers $52. */
static void dos(int u, int seed){
  int b,i;
  vname[u][0]=0;
  for(b=0;b<NB;++b) for(i=0;i<512;++i) disk[u][b][i]=(unsigned char)(b*31+i*7+3);
  for(b=136;b<144;++b) for(i=0;i<512;++i) disk[u][b][i]=(unsigned char)(b+i*13+seed);
}
static void dump(const char* path){
  FILE* f=fopen(path,"wb"); fwrite(disk,1,sizeof disk,f); fclose(f);
}
int main(int argc,char** argv){
  struct A2fcApi api; char note[80]="";
  const char* sc=argv[1]; int i, n=0;
  memset(&api,0,sizeof api);
  diskii_rom(6);
  api.cfg_path="/BOOT/A2FILE/A2FILE.CFG"; api.note=note; api.confirm=confirm;
  mock_devadr[7]=0xC70A; mock_devadr[15]=0xC70A;            /* slot 7: a block device */
  mock_devadr[6]=0xD000; mock_devadr[14]=0xD000;            /* Disk II slot 6, drives 1 and 2 */
  mock_devadr[11]=0xFF00;                                   /* $B0: /RAM */
  prodos(7,"BOOT"); vsize[7]=1600;
  prodos(11,"RAM"); vsize[11]=127;
  prodos(6,"FLOPPY"); vsize[6]=280;
  keys="1\rERASE\r";
  if(!strncmp(sc,"eleven",6)){
    /* 11 units: the Disk II, slot 7, 5, 4, 2, then VDrive-like extras; /RAM last */
    unsigned char units[]={0x60,0xE0,0x70,0xF0,0x50,0xD0,0x40,0xC0,0x20,0xA0,0xB0};
    for(i=0;i<11;++i) mock_devlst[i]=units[i];
    mock_devcnt=10;
    mock_devadr[5]=mock_devadr[13]=0xC50A; mock_devadr[4]=mock_devadr[12]=0xC40A;
    mock_devadr[2]=mock_devadr[10]=0xC20A;
    for(i=0;i<16;++i) if(!vsize[i]) vsize[i]=1600;
    if(strcmp(sc,"eleven")) api.cfg_path="/RAM/A2FILE/A2FILE.CFG";
    online_fail=!strcmp(sc,"eleven_online_fail");
  } else {
    mock_devlst[0]=0x60; mock_devlst[1]=0x70; mock_devlst[2]=0xB0; mock_devlst[3]=0x40; mock_devcnt=3;
    mock_devadr[4]=0xC40A; vsize[4]=1600;
    if(!strcmp(sc,"dos_swap") || !strncmp(sc,"dos_diff",8) || !strcmp(sc,"dos_same") || !strcmp(sc,"cpm_diff")){
      int which = !strncmp(sc,"dos_diff",8) ? atoi(sc+8) : -1;
      dos(6,0); memcpy(swap_blocks,disk[6],sizeof swap_blocks); swap_name[0]=0;
      if(!strcmp(sc,"dos_swap")) for(i=0;i<NB*512;++i) ((unsigned char*)swap_blocks)[i]^=(i/512>=136&&i/512<144)?0x55:0;
      if(which>=0) swap_blocks[which][100]^=1;                /* one catalog byte */
      if(!strcmp(sc,"cpm_diff")) swap_blocks[25][7]^=0x20;   /* one CP/M directory byte */
      swap_at_aux=1;
    } else if(!strcmp(sc,"pro_swap")){
      prodos(6,"WORK"); disk[6][2][0x25]=3;
      memcpy(swap_blocks,disk[6],sizeof swap_blocks); swap_blocks[2][0x25]=4; strcpy(swap_name,"WORK");
      swap_at_aux=1;
    } else if(!strcmp(sc,"dos_fails_later")){
      dos(6,0); fail_second[6]=1+140;
    } else if(!strcmp(sc,"blank")){
      vname[6][0]=0; for(i=0;i<NB;++i) fail_read_block[6][i]=0x27;
    } else if(!strcmp(sc,"protected")){
      begin_result=0x2B;
    } else if(!strcmp(sc,"verify_error")){
      /* the formatted floppy fails one block once the format is done */
      fail_second[6]=1+200;
    } else if(!strcmp(sc,"name_taken")){
      keys="1BOOT\r\x7f\x7f\x7f\x7fNEW\rERASE\r";
    } else if(!strcmp(sc,"name_own")){
      keys="1FLOPPY\rERASE\r";
    } else if(!strcmp(sc,"name_ram")){
      keys="1RAM\r\x7f\x7f\x7fNEW\rERASE\r";
    } else if(!strcmp(sc,"block")){
      keys="4\rERASE\r"; prodos(4,"HARD");
    }
  }
  format_entry(&api);
  for(i=0;i<NB;++i) n+=reads[6][i]>0;
  printf("RESULT tracks=%d aux_borrowed=%d ram_rebuilt=%d ram_files=%d blocks_read=%d\n",
         tracks,aux_borrowed,ram_rebuilt,ram_files,n);
  printf("NOTE %s\n",note);
  printf("SCREEN %s\n",screen);
  if(argc>2) dump(argv[2]);
  return 0;
}
'''


def build(root, work):
    src = (root / 'src/format.c').read_text()
    for a, b in SUBS:
        assert src.count(a) == 1, a
        src = src.replace(a, b)
    (work / 'format.c').write_text(PRE + src)
    (work / 'a2fc_plugin.h').write_text((root / 'src/a2fc_plugin.h').read_text())
    (work / 'music.h').write_text('')
    (work / 'conio.h').write_text('void clrscr(void); void gotoxy(unsigned char,unsigned char); unsigned char revers(unsigned char);\n'
                                  'int cprintf(const char*,...); void cputs(const char*); char cgetc(void);\n')
    (work / 'mock.c').write_text(MOCK)
    exe = work / 'fmt'
    r = subprocess.run(['cc', '-std=c99', '-w', '-g', '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                        '-I', str(work), str(work / 'format.c'), str(work / 'mock.c'), '-o', str(exe)],
                       capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr)
    return exe


class Format(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='format-')
        cls.work = Path(cls.tmp.name)
        cls.exe = build(Path(sys.argv[1]) if len(sys.argv) > 1 and Path(sys.argv[1]).is_dir() else ROOT, cls.work)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_case(self, name):
        img = self.work / (name + '.bin')
        p = subprocess.run([str(self.exe), name, str(img)], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        res = dict(kv.split('=', 1) for kv in p.stdout.split('\n')[0].split()[1:] if '=' in kv)
        res['note'] = p.stdout.split('\n')[1][5:]
        res['screen'] = p.stdout.split('\n')[2]
        data = img.read_bytes()
        res['disk'] = lambda u, b: data[(u * 280 + b) * 512:(u * 280 + b + 1) * 512]
        return res

    def assertNoLoss(self, r):
        """AUX borrowed means /RAM was rebuilt; /RAM's files survive otherwise."""
        self.assertFalse(r['aux_borrowed'] == '1' and r['ram_rebuilt'] == '0',
                         'AUX overwritten while /RAM keeps its directory')
        if r['tracks'] == '0':
            self.assertEqual(r['ram_files'], '1', '/RAM files lost without any track written')

    # -- finding 1: the whole DEVLST ---------------------------------------
    def test_ram_rebuilt_when_it_is_the_eleventh_unit(self):
        """Before: only devs[0..8] were searched for /RAM; with 11 units and
        /RAM last, 35 tracks borrowed AUX and /RAM kept its old directory
        over the resident's bytes (ram_rebuilt=0, no note)."""
        r = self.run_case('eleven')
        self.assertEqual(r['tracks'], '35')
        self.assertEqual(r['ram_rebuilt'], '1')
        self.assertIn('/RAM was rebuilt empty.', r['note'] + r['screen'])
        self.assertNoLoss(r)

    def test_running_from_ram_past_the_ninth_unit_refuses_disk_ii(self):
        """Before: boot_unit was only set by probing the nine listed units;
        running from /RAM as unit 11, a Disk II format went ahead and
        overwrote the volume the program runs from."""
        r = self.run_case('eleven_ram_boot')
        self.assertIn('cannot be formatted', r['screen'])
        self.assertEqual(r['tracks'], '0')
        self.assertEqual(r['ram_files'], '1')

    def test_on_line_failure_refuses(self):
        """When ON_LINE cannot say where the program runs from (here /RAM,
        unit 11, outside the list), nothing is formatted; the new name
        cannot be checked either and is refused."""
        r = self.run_case('eleven_online_fail')
        self.assertIn('cannot be formatted', r['screen'])
        self.assertEqual(r['tracks'], '0')
        self.assertEqual(r['ram_files'], '1')

    # -- finding 2: DOS 3.3 and CP/M identity ------------------------------
    def test_dos_disk_swapped_at_the_aux_question(self):
        """Before: two DOS 3.3 floppies (no ProDOS name, size forced to 280,
        identical block 2) compared equal and disk B was formatted."""
        r = self.run_case('dos_swap')
        self.assertIn('The disk changed: nothing written.', r['screen'])
        self.assertEqual(r['tracks'], '0')
        self.assertNoLoss(r)

    def test_every_catalog_block_counts(self):
        """Disks differing by one byte in any block of track 17 differ."""
        for b in range(136, 144):
            with self.subTest(block=b):
                r = self.run_case('dos_diff%d' % b)
                self.assertIn('The disk changed', r['screen'])
                self.assertEqual(r['tracks'], '0')

    def test_cpm_directory_counts(self):
        r = self.run_case('cpm_diff')
        self.assertIn('The disk changed', r['screen'])
        self.assertEqual(r['tracks'], '0')

    def test_same_dos_disk_is_formatted(self):
        r = self.run_case('dos_same')
        self.assertEqual(r['tracks'], '35')
        self.assertIn('Done: /BLANK, 280 blocks, 273 free.', r['screen'])

    def test_read_failing_at_the_second_look_refuses(self):
        """A block that read at the first look and fails at the last one is
        a different disk (or a dying one): nothing written."""
        r = self.run_case('dos_fails_later')
        self.assertIn('The disk changed', r['screen'])
        self.assertEqual(r['tracks'], '0')

    def test_unreadable_blank_disk_can_be_formatted(self):
        """A never-formatted floppy fails every read, both times: it stays
        itself and can be formatted (its errors, not the garbage left in the
        buffer, are what identify folds)."""
        r = self.run_case('blank')
        self.assertNotIn('The disk changed', r['screen'])
        self.assertEqual(r['tracks'], '35')

    def test_prodos_control(self):
        r = self.run_case('pro_swap')
        self.assertIn('The disk changed', r['screen'])
        self.assertEqual(r['tracks'], '0')

    # -- finding 3: write protect before AUX -------------------------------
    def test_protected_floppy_keeps_ram(self):
        """Before: whatever diskii_begin said, /RAM was rebuilt after the
        track loop -- with the writer's protect test inside the first track,
        after AUX had been borrowed, a protected floppy cost the /RAM files.
        Now diskii_begin answers $2B first and /RAM is left alone."""
        r = self.run_case('protected')
        self.assertIn('write protected ($2B)', r['screen'])
        self.assertEqual(r['tracks'], '0')
        self.assertEqual(r['ram_rebuilt'], '0')
        self.assertEqual(r['ram_files'], '1')
        self.assertEqual(r['disk'](6, 2)[5:11], b'FLOPPY')

    # -- finding 4: what "verified" means ----------------------------------
    def test_disk_ii_reads_every_block_back(self):
        """Before: "Read back and verified." after reading blocks 0 and 2."""
        r = self.run_case('dos_same')
        self.assertEqual(r['blocks_read'], '280')
        self.assertIn('All 280 blocks read back.', r['screen'])
        self.assertNotIn('verified', r['screen'])

    def test_verify_read_error_fails(self):
        r = self.run_case('verify_error')
        self.assertIn('Failed: I/O error', r['screen'])
        self.assertNotIn('Done:', r['screen'])

    def test_block_device_message_says_what_is_read(self):
        r = self.run_case('block')
        self.assertIn('Boot block and header read back.', r['screen'])
        self.assertIn('Done: /BLANK, 1600 blocks, 1593 free.', r['screen'])

    # -- finding 5: a name already on line ---------------------------------
    def test_name_of_another_volume_is_refused(self):
        """Before: /BOOT was accepted while /BOOT was on line: two /BOOT."""
        r = self.run_case('name_taken')
        self.assertIn('That name is on line: choose another.', r['screen'])
        self.assertIn('Done: /NEW, 280 blocks', r['screen'])
        self.assertEqual(r['disk'](6, 2)[4:8], bytes([0xF3]) + b'NEW')

    def test_ram_name_is_refused(self):
        r = self.run_case('name_ram')
        self.assertIn('That name is on line', r['screen'])
        self.assertIn('Done: /NEW', r['screen'])

    def test_target_may_keep_its_own_name(self):
        r = self.run_case('name_own')
        self.assertNotIn('That name is on line', r['screen'])
        self.assertIn('Done: /FLOPPY, 280 blocks, 273 free.', r['screen'])

    # -- the structures written (guard for the header rewrite) -------------
    def check_structures(self, r, unit, total, name):
        hdr = r['disk'](unit, 2)
        self.assertEqual(hdr[0:4], bytes([0, 0, 3, 0]))
        self.assertEqual(hdr[4], 0xF0 | len(name))
        self.assertEqual(hdr[5:5 + len(name)], name.encode())
        self.assertEqual(hdr[0x20:0x2B], bytes([0, 0, 0xC3, 0x27, 0x0D, 0, 0, 6, 0, total & 255, total >> 8]))
        self.assertEqual(hdr[0x2B:], bytes(512 - 0x2B))
        for b in (3, 4, 5):
            blk = r['disk'](unit, b)
            self.assertEqual(blk[:4], bytes([b - 1, 0, b + 1 if b < 5 else 0, 0]))
            self.assertEqual(blk[4:], bytes(508))
        bm = r['disk'](unit, 6)
        used = 6 + (total + 4095) // 4096
        expect = bytearray(512)
        for blk in range(min(total, 4096)):
            if blk >= used:
                expect[blk >> 3] |= 0x80 >> (blk & 7)
        self.assertEqual(bm, bytes(expect))
        self.assertEqual(r['disk'](unit, 1), bytes(512))

    def test_structures_floppy(self):
        r = self.run_case('dos_same')
        self.check_structures(r, 6, 280, 'BLANK')

    def test_structures_block_device(self):
        r = self.run_case('block')
        self.check_structures(r, 4, 1600, 'BLANK')


if __name__ == '__main__':
    unittest.main(argv=sys.argv[:1])
