"""Execute the shipped DOSREPL C: a ProDOS file over the DOS 3.3 file of the
same name, on disposable disks and through I/O faults.

What matters is the one promise the order of the writes makes: the old file
stays whole and readable until the catalog sector is switched. Every failure
before that switch is checked by reading the old bytes back off the image.
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
#include "src/plugins/dosrepl.c"

static FILE* disk;
static struct Panel panels[2];
static struct Entry sel;
static unsigned char scratch[512], active;
static char note_text[120], full_path[128];
static char prodos_path[] = "/V/NEW";
static int mode, reads, writes, fail_at, srctype;
static unsigned char target_unit = 0xE0;
static const unsigned char dos_order[16]={0,14,13,12,11,10,9,8,7,6,5,4,3,2,1,15};

void dw_mainbank(void) {}
unsigned char dw_protected(unsigned char u) { return mode==1 ? 1 : mode==2 ? 0x80 : 0; }

/* mode 3: the nth read fails. 4: the nth write fails. 5: the nth write is
 * half done then fails. 6: the nth write reads back different. */
static unsigned char mli(unsigned char cmd, void* p) {
 struct Block* b=p; unsigned int h; unsigned char* q;
 if(cmd==0xC5){ struct Online* o=p; memset(o->buffer,0,256);
                o->buffer[0]=0x51; o->buffer[1]='V'; return mode==12?0x27:0; }
 if(cmd==0xC4){ struct Info* i=p; i->storage=1; i->access=0xC3; i->aux=0x2000;
                i->type=(unsigned char)srctype; return mode==11?0x27:0; }
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
static void progress(const char* s,unsigned long n,unsigned long t){(void)s;(void)n;(void)t;}
static void message(const char* s){(void)s;}
/* The overlay is handed a ProDOS path (it resolves its drive through
 * ON_LINE); the bytes come from the real file the test wrote. */
static FILE* src_open(const char* p,const char* m){(void)p;return fopen(full_path,m);}

int main(int argc,char** argv) {
 struct A2fcApi api; memset(&api,0,sizeof api);
 disk=fopen(argv[1],"r+b");
 strcpy(full_path,argv[2]);
 mode=atoi(argv[3]); fail_at=atoi(argv[4]); srctype=atoi(argv[5]);
 strcpy(sel.name,argv[6]);
 panels[1].fs=FS_DOS33; panels[1].dir_key=target_unit;
 panels[0].path[0]='/'; panels[0].path[1]='V'; panels[0].path[2]=0;
 if(mode==8) panels[1].img_len=5;          /* an image, not a real disk */
 if(mode==9) panels[1].fs=FS_PRODOS;       /* not a DOS panel at all */
 if(mode==10) target_unit=panels[1].dir_key=0x50;   /* the source's own drive */
 api.panels=panels; api.active=&active; api.selected=&sel;
 api.full=prodos_path;
 api.copy_buf=scratch; api.note=note_text;
 api.memcpy=memcpy; api.memset=memset; api.strcpy=strcpy; api.strlen=strlen;
 api.sprintf=sprintf; api.mli=mli; api.confirm=do_confirm;
 api.fopen=src_open; api.fread=fread; api.fwrite=fwrite; api.fclose=fclose;
 api.fseek=fseek; api.progress_bar=progress; api.message=message;
 plugin_entry(&api);
 fclose(disk);
 printf("%d %d %s\n",writes,reads,note_text);
 return 0;
}
'''

OLD = b'the old file, kept whole\r' * 60
KEEP = b'a neighbour that must not move\r' * 40
FILES = [('KEEP', 0x00, KEEP), ('NEW', 0x00, OLD), ('LOCKED', 0x82, b'locked\r' * 10)]


class DosRepl(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='drepl-build-')
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
        self.case = tempfile.TemporaryDirectory(prefix='drepl-')
        self.addCleanup(self.case.cleanup)
        self.dir = Path(self.case.name)
        self.disk = self.dir / 'disk.do'
        self.original = make_disk(FILES)
        self.disk.write_bytes(self.original)
        self.before = read_files(self.original)
        self.payload = b'the new contents, quite different\r' * 30
        self.src = self.dir / 'SRC'
        self.src.write_bytes(self.payload)

    def run_op(self, mode=0, at=1, typ=4, name='NEW'):
        out = subprocess.check_output(
            [str(self.exe), str(self.disk), str(self.src), str(mode), str(at),
             str(typ), name], text=True).strip().split(' ', 2)
        self.assertEqual(self.src.read_bytes(), self.payload)   # never touched
        return int(out[0]), (out[2] if len(out) > 2 else '')

    def assert_old_file_intact(self):
        after = read_files(self.disk.read_bytes())
        self.assertEqual(after['NEW']['data'][:len(OLD)], OLD)
        self.assertEqual(after['KEEP']['data'][:len(KEEP)], KEEP)

    # -- what must happen ---------------------------------------------------

    def test_replacing_puts_the_new_bytes_under_the_old_name(self):
        writes, note = self.run_op()
        self.assertIn('Replaced', note)
        after = read_files(self.disk.read_bytes())
        self.assertEqual(after['NEW']['data'][:len(self.payload)], self.payload)
        self.assertEqual(after['KEEP']['data'][:len(KEEP)], KEEP)
        # the new copy is somewhere else entirely, and the old sectors are free
        self.assertFalse(set(after['NEW']['blocks']) & set(self.before['NEW']['blocks']))
        vtoc = self.disk.read_bytes()[offset(17, 0):offset(17, 0) + 256]
        for t, s in self.before['NEW']['blocks'] + self.before['NEW']['lists']:
            self.assertTrue(vtoc[0x38 + t * 4 + (s < 8)] & (1 << (s & 7)), (t, s))

    def test_a_binary_keeps_its_address_and_length_header(self):
        writes, note = self.run_op(typ=6)
        self.assertIn('Replaced', note)
        after = read_files(self.disk.read_bytes())
        head = b'\x00\x20' + len(self.payload).to_bytes(2, 'little')
        self.assertEqual(after['NEW']['data'][:len(head)], head)
        self.assertEqual(after['NEW']['data'][4:4 + len(self.payload)], self.payload)

    # -- what must not ------------------------------------------------------

    def test_a_name_that_is_not_there_is_refused(self):
        writes, note = self.run_op(name='ABSENT')
        self.assertEqual(writes, 0, note)
        self.assertIn('No such DOS file', note)
        self.assertEqual(self.disk.read_bytes(), self.original)

    def test_a_locked_target_is_refused(self):
        writes, note = self.run_op(name='LOCKED')
        self.assertEqual(writes, 0, note)
        self.assertIn('locked', note)
        self.assertEqual(self.disk.read_bytes(), self.original)

    def test_answering_no_writes_nothing(self):
        writes, note = self.run_op(mode=7)
        self.assertEqual(writes, 0, note)
        self.assertEqual(self.disk.read_bytes(), self.original)

    def test_a_protected_or_unknown_drive_is_refused(self):
        for mode, word in ((1, 'Disk II'), (2, 'protected')):
            self.disk.write_bytes(self.original)
            writes, note = self.run_op(mode=mode)
            self.assertEqual(writes, 0, note)
            self.assertIn(word, note)
            self.assertEqual(self.disk.read_bytes(), self.original)

    def test_the_wrong_panels_or_one_drive_for_both_are_refused(self):
        for mode in (8, 9, 10, 11, 12):
            self.disk.write_bytes(self.original)
            writes, note = self.run_op(mode=mode)
            self.assertEqual(writes, 0, (mode, note))
            self.assertEqual(self.disk.read_bytes(), self.original)

    def test_an_unsupported_source_type_is_refused(self):
        for typ in (0x0F, 0x19, 0xFF):
            self.disk.write_bytes(self.original)
            writes, note = self.run_op(typ=typ)
            self.assertEqual(writes, 0, note)
            self.assertEqual(self.disk.read_bytes(), self.original)

    def test_a_disk_without_room_for_both_copies_is_refused(self):
        """The old file's sectors stay in use while the new one is written,
        so the disk has to hold the two at once and says so when it cannot."""
        big = [('KEEP', 0x00, bytes(400 * 256)), ('NEW', 0x00, OLD)]
        self.disk.write_bytes(make_disk(big))
        untouched = self.disk.read_bytes()
        self.payload = b'x' * 40000
        self.src.write_bytes(self.payload)
        writes, note = self.run_op()
        self.assertEqual(writes, 0, note)
        self.assertIn('free sectors', note)
        self.assertEqual(self.disk.read_bytes(), untouched)

    def test_a_failure_before_the_switch_leaves_the_old_file_readable(self):
        """Everything up to the catalog write can fail; the name still means
        the old file, and its bytes are still there."""
        for mode in (3, 4, 5, 6):
            for at in range(1, 6):
                with self.subTest(mode=mode, at=at):
                    self.disk.write_bytes(self.original)
                    writes, note = self.run_op(mode=mode, at=at)
                    if 'Replaced' in note:
                        continue          # it got past the switch
                    self.assert_old_file_intact()


if __name__ == '__main__':
    unittest.main()
