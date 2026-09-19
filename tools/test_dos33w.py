"""Execute the shipped DOS33W C against disposable DOS 3.3 disks and I/O faults.

Every case runs the real `src/plugins/dos33w.c` -- no reimplementation --
over a disk image `tools/mini33_fixture.py` built, and reads the bytes back
with the same module's independent catalog walker. What is checked is the
disk, not the message: a refusal must leave the image byte for byte as it
was, and a delete must free exactly the sectors of that one file.
"""
import subprocess
import tempfile
import unittest
from pathlib import Path

from mini33_fixture import make_disk, read_files, offset

ROOT = Path(__file__).resolve().parents[1]

C = r'''
#define __fastcall__
#define PLUGIN_HOST
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#undef memcpy
#undef memset
#undef strcpy
#undef sprintf
struct A2fcApi;
#include "src/plugins/dos33w.c"

static FILE* disk;
static struct Panel panels[2];
static struct Entry sel;
static unsigned char scratch[512], active;
static char note_text[120], input_text[32], newname[32];
static int mode, reads, writes, fail_at;
static char answer;
static unsigned char target_unit = 0xE0;
static const unsigned char dos_order[16]={0,14,13,12,11,10,9,8,7,6,5,4,3,2,1,15};

void dw_mainbank(void) {}
/* 1: not a Disk II. $80: write protected. */
unsigned char dw_protected(unsigned char u) { return mode==1 ? 1 : mode==2 ? 0x80 : 0; }

/* READ_BLOCK/WRITE_BLOCK over the image, two DOS sectors a ProDOS block.
 * mode 3: the nth read fails. 4: the nth write fails before touching the
 * disk. 5: the nth write half-writes then fails. 6: the nth write lands
 * but reads back different, which is a drive that has silently lost it. */
static unsigned char mli(unsigned char cmd, void* p) {
 struct Block* b=p; unsigned int h; unsigned char* q;
 if(b->unit!=target_unit || b->block>=280 || (cmd!=0x80 && cmd!=0x81)) abort();
 if(cmd==0x80){++reads; if(mode==3 && reads==fail_at) return 0x27;}
 else {++writes; if(mode==4 && writes==fail_at) return 0x27;}
 for(h=0;h<2;++h){
  long at=((long)(b->block/8)*16+dos_order[(b->block%8)*2+h])*256;
  fseek(disk,at,SEEK_SET); q=b->buffer+h*256;
  if(cmd==0x80){ if(fread(q,1,256,disk)!=256) abort(); }
  else {
   if(mode==5 && writes==fail_at){ if(!h) fwrite(q,1,128,disk); fflush(disk); return 0x27; }
   if(fwrite(q,1,256,disk)!=256) abort();
  }
 }
 if(cmd==0x81){
  fflush(disk);
  if(mode==6 && writes==fail_at){
   long at=((long)(b->block/8)*16+dos_order[(b->block%8)*2])*256;
   fseek(disk,at,SEEK_SET); h=fgetc(disk);
   fseek(disk,at,SEEK_SET); fputc(h^1,disk); fflush(disk);
  }
 }
 return 0;
}
static unsigned char do_confirm(const char* s) { (void)s; return mode!=7; }
static unsigned char do_prompt(const char* label,const char* init,unsigned char n) {
 (void)label; (void)init; (void)n;
 if(mode==8) return 0;                     /* ESC on the name */
 strcpy(input_text,newname); return 1;
}
static char do_wait_key(void) { return answer; }
static void do_message(const char* s) { (void)s; }
static void do_bar_begin(void) {}
static void do_keys_bar(unsigned char x,const char* s) { (void)x; (void)s; }

int main(int argc,char** argv) {
 struct A2fcApi api; memset(&api,0,sizeof api);
 disk=fopen(argv[1],"r+b");
 answer=argv[2][0]; mode=atoi(argv[3]); fail_at=atoi(argv[4]);
 strcpy(newname,argv[5]);
 strcpy(sel.name,argv[6]);
 sel.mdate=(unsigned int)(atoi(argv[7])<<8)|atoi(argv[8]);
 sel.access=(unsigned char)atoi(argv[9]);
 sel.type=(unsigned char)atoi(argv[10]);
 panels[0].fs=FS_DOS33; panels[0].count=1;
 panels[0].dir_key=target_unit;
 if(mode==9) panels[0].fs=FS_PRODOS;       /* not a DOS panel at all */
 if(mode==10) panels[0].img_len=5;         /* a DOS image, not a real disk */
 api.panels=panels; api.active=&active; api.selected=&sel;
 api.copy_buf=scratch; api.note=note_text; api.input=input_text;
 api.memcpy=memcpy; api.memset=memset; api.strcpy=strcpy; api.strlen=strlen;
 api.sprintf=sprintf; api.mli=mli; api.confirm=do_confirm; api.prompt=do_prompt;
 api.wait_key=do_wait_key; api.message=do_message;
 api.bar_begin=do_bar_begin; api.keys_bar=do_keys_bar;
 plugin_entry(&api);
 fclose(disk);
 printf("%d %d %s\n",writes,reads,note_text);
 return 0;
}
'''

FILES = [('KEEP', 0x00, b'kept\r' * 100),
         ('GONE', 0x04, b'removed\r' * 300),
         ('LOCKED', 0x82, b'locked\r' * 20)]
UNLOCKED, LOCKED = 0xC3, 0x01


class Dos33W(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='d33w-build-')
        p = Path(cls.tmp.name)
        (p / 'test.c').write_text(C)
        cls.exe = p / 'test'
        subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-I', str(ROOT),
                        str(p / 'test.c'), '-o', str(cls.exe)],
                       check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.case = tempfile.TemporaryDirectory(prefix='d33w-')
        self.addCleanup(self.case.cleanup)
        self.disk = Path(self.case.name) / 'disk.do'
        self.original = make_disk(FILES)
        self.disk.write_bytes(self.original)
        self.before = read_files(self.original)

    def run_op(self, key='D', name='GONE', mode=0, at=1, newname='NEUF',
               access=UNLOCKED):
        e = self.before[name]['entry']
        out = subprocess.check_output(
            [str(self.exe), str(self.disk), key, str(mode), str(at), newname,
             name, str(e[0]), str(e[1]), str(access), str(e[2] & 0x7F)],
            text=True).strip().split(' ', 2)
        return int(out[0]), (out[2] if len(out) > 2 else '')

    def assert_untouched(self):
        self.assertEqual(self.disk.read_bytes(), self.original)

    # -- what must happen ---------------------------------------------------

    def test_delete_frees_exactly_that_file_and_keeps_the_others(self):
        writes, note = self.run_op()
        self.assertIn('Deleted', note)
        # Exactly two: the catalog sector, then the bitmap. Anything else
        # means the path did not run, or ran somewhere it should not.
        self.assertEqual(writes, 2, note)
        after = read_files(self.disk.read_bytes())
        self.assertNotIn('GONE', after)
        for name in ('KEEP', 'LOCKED'):
            self.assertEqual(after[name]['data'], self.before[name]['data'])
            self.assertEqual(after[name]['blocks'], self.before[name]['blocks'])
        # every sector of GONE is free again, and no other sector moved
        disk = self.disk.read_bytes()
        vtoc = disk[offset(17, 0):offset(17, 0) + 256]
        was = self.original[offset(17, 0):offset(17, 0) + 256]
        freed = set(self.before['GONE']['blocks']) | set(self.before['GONE']['lists'])
        for t in range(35):
            for s in range(16):
                bit = 1 << (s & 7)
                i = 0x38 + t * 4 + (s < 8)
                now, then = bool(vtoc[i] & bit), bool(was[i] & bit)
                self.assertEqual(now, then or (t, s) in freed, (t, s))

    def test_the_deleted_entry_keeps_its_track_where_undelete_reads_it(self):
        self.run_op()
        disk = self.disk.read_bytes()
        track = self.before['GONE']['entry'][0]
        for s in range(15, 0, -1):
            cat = disk[offset(17, s):offset(17, s) + 256]
            for i in range(7):
                e = cat[11 + i * 35:46 + i * 35]
                if e[0] == 0xFF and e[32] == track:
                    return
        self.fail('no entry marked deleted with its original track')

    def test_rename_writes_one_sector_and_touches_nothing_else(self):
        writes, note = self.run_op(key='R', newname='RENOMME')
        self.assertIn('Renamed', note)
        self.assertEqual(writes, 1)
        after = read_files(self.disk.read_bytes())
        self.assertNotIn('GONE', after)
        self.assertEqual(after['RENOMME']['data'], self.before['GONE']['data'])
        self.assertEqual(after['RENOMME']['blocks'], self.before['GONE']['blocks'])
        self.assertEqual(after['KEEP']['data'], self.before['KEEP']['data'])

    # -- what must not ------------------------------------------------------

    def test_a_locked_file_is_refused_by_both_verbs(self):
        for key in ('D', 'R'):
            self.disk.write_bytes(self.original)
            writes, note = self.run_op(key=key, name='LOCKED', access=LOCKED)
            self.assertEqual(writes, 0, note)
            self.assertIn('Locked', note)
            self.assert_untouched()

    def test_a_name_already_on_the_disk_is_refused(self):
        writes, note = self.run_op(key='R', newname='KEEP')
        self.assertEqual(writes, 0, note)
        self.assertIn('already', note)
        self.assert_untouched()

    def test_answering_no_writes_nothing(self):
        for key in ('D', 'R'):
            self.disk.write_bytes(self.original)
            writes, note = self.run_op(key=key, mode=7)
            self.assertEqual(writes, 0, note)
            self.assert_untouched()

    def test_escaping_the_new_name_writes_nothing(self):
        writes, _ = self.run_op(key='R', mode=8)
        self.assertEqual(writes, 0)
        self.assert_untouched()

    def test_a_key_that_is_neither_verb_writes_nothing(self):
        for key in ('\x1b', 'X', 'C'):
            writes, _ = self.run_op(key=key)
            self.assertEqual(writes, 0)
            self.assert_untouched()

    def test_a_protected_or_unknown_drive_is_refused(self):
        for mode, word in ((1, 'Disk II'), (2, 'protected')):
            for key in ('D', 'R'):
                writes, note = self.run_op(key=key, mode=mode)
                self.assertEqual(writes, 0, note)
                self.assertIn(word, note)
                self.assert_untouched()

    def test_a_panel_that_is_not_a_real_dos_disk_is_refused(self):
        for mode in (9, 10):
            writes, note = self.run_op(mode=mode)
            self.assertEqual(writes, 0, note)
            self.assert_untouched()

    def test_an_entry_whose_link_moved_is_not_the_file_we_meant(self):
        """The panel was read before the disk changed: no entry answers."""
        e = self.before['GONE']['entry']
        out = subprocess.check_output(
            [str(self.exe), str(self.disk), 'D', '0', '1', 'NEUF', 'GONE',
             str(e[0]), str((e[1] + 1) % 16), str(UNLOCKED), '4'], text=True)
        self.assertEqual(int(out.split()[0]), 0, out)
        self.assert_untouched()

    def test_a_volume_the_audit_cannot_explain_is_never_written(self):
        disk = bytearray(self.original)
        breaks = {
            'a bitmap that frees a live sector':
                (offset(17, 0) + 0x38 + 3 * 4, 0xFF),
            'a catalog link off the disk':
                (offset(17, 15) + 1, 40),
            'a VTOC that is not one':
                (offset(17, 0) + 0x27, 121),
            'a boot track marked free':
                (offset(17, 0) + 0x38, 0xFF),
        }
        for why, (at, value) in breaks.items():
            with self.subTest(why=why):
                bad = bytearray(disk)
                bad[at] = value
                self.disk.write_bytes(bytes(bad))
                writes, note = self.run_op()
                self.assertEqual(writes, 0, note)
                self.assertEqual(self.disk.read_bytes(), bytes(bad))

    def test_a_read_error_before_any_write_leaves_the_disk_alone(self):
        for at in range(1, 12):
            self.disk.write_bytes(self.original)
            writes, note = self.run_op(mode=3, at=at)
            self.assertEqual(writes, 0, (at, note))
            self.assert_untouched()

    def test_a_failed_write_never_claims_the_file_is_gone(self):
        """The catalog sector is written first: if it fails, nothing moved.
        If the bitmap write fails after it, the file IS gone and the note
        says the sectors stay in use -- never 'nothing deleted'."""
        for mode in (4, 5, 6):
            for at in (1, 2):
                self.disk.write_bytes(self.original)
                writes, note = self.run_op(mode=mode, at=at)
                after = read_files(self.disk.read_bytes()) if at == 2 else None
                if at == 1:
                    self.assertIn('Nothing deleted', note, (mode, note))
                else:
                    self.assertNotIn('Nothing deleted', note, (mode, note))
                    self.assertNotIn('GONE', after, (mode, note))


if __name__ == '__main__':
    unittest.main()
