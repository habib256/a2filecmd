"""Execute the shipped PASCAL C over Apple Pascal images and I/O faults.

The fixtures come from tools/pascal_ref.py, which is also the oracle: every
extracted file is compared with the bytes that reference reads out of the
same image. Nothing is written to the image itself, and a refusal must leave
the destination directory exactly as it was.
"""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import pascal_ref as P

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
static int error_(FILE*);
#define ferror error_
#include "src/plugins/pascal.c"

#undef ferror
static FILE* verify_file;
static FILE* image_file;
static unsigned int image_closes;
static FILE* errored;
static int error_(FILE* f){return f==errored || ferror(f);}
static struct Panel panels_[2];
static struct Entry sel;
static struct DirEntry de;
static unsigned char scratch[512], active_;
static char note_text[120], full_[80];
static int mode, reads, fail_at, creates;
static char outdir[256], imagepath[256];

/* The destination directory is a real one: CREATE, and the writes that
 * follow, work on files under it. */
static void joinpath(char* out,const char* p){
 const char* s=p; if(*s=='/')++s;
 while(*s && *s!='/')++s;            /* drop the volume, keep what follows */
 sprintf(out,"%s%s",outdir,s);
}
static unsigned char mli_(unsigned char cmd,void* q){
 struct Create* c=q; char path[300]; char pas[80]; unsigned char n; FILE* f;
 if(cmd!=0xC0) abort();
 n=c->path[0]; memcpy(pas,c->path+1,n); pas[n]=0;
 joinpath(path,pas);
 ++creates;
 if(mode==4 && creates==fail_at) return 0x27;      /* CREATE refused */
 if(creates==fail_at && (mode==29 || mode==30))return mode==29?0x48:0x4E;
 f=fopen(path,"rb"); if(f){fclose(f);return 0x47;} /* the name is taken */
 f=fopen(path,"wb"); if(!f) return 0x27; fclose(f);
 return 0;
}
static FILE* open_(const char* p,const char* m){
 char path[300];FILE* f;
 if(!strcmp(p,"/I/VOL.PO")){image_file=fopen(imagepath,m);return image_file;}
 joinpath(path,p);f=fopen(path,m);verify_file=!strcmp(m,"rb")?f:NULL;return f;
}
static int remove_(const char* p){char path[300];joinpath(path,p);if((mode==11 || mode==16 || mode==18 || mode==20) && creates==fail_at)return -1;return remove(path);}
static size_t read_(void* p,size_t s,size_t n,FILE* f){
 ++reads; if(mode==2 && reads==fail_at) return 0;
 if(f==image_file && ((mode==14 && reads==fail_at) ||
    ((mode==15 || mode==16) && verify_file && creates==fail_at)))errored=f;
 if(f==verify_file && creates==fail_at) {
  if((mode==9 || mode==11) && n==1){errored=f;return 0;}
  if(mode==10 && n>1)errored=f; /* full count, error flag set */
 }
 return fread(p,s,n,f);
}
static size_t write_(const void* p,size_t s,size_t n,FILE* f){
 if(mode==3 && --fail_at==0) return 0;
 return fwrite(p,s,n,f);
}
static int close_(FILE* f){
 int failed=mode==5 || (mode==12 && f==image_file),r;
 if(f==image_file && (mode==32 || mode==33)){cancelled=1;if(mode==33)failed=1;}
 if(creates==fail_at && f!=image_file &&
    (((mode==17 || mode==18) && f==verify_file) ||
     ((mode==19 || mode==20) && f!=verify_file)))cancelled=1;
 if(mode==13 && f==verify_file && creates==4)errored=image_file;
 if(f==image_file){++image_closes;image_file=NULL;}
 r=fclose(f);if(f==errored)errored=NULL;return failed?-1:r;
}
static void progress_(const char* n,unsigned long d,unsigned long t){fprintf(stderr,"BAR %s %lu %lu\n",n,d,t);}
static void message_(const char* s){fprintf(stderr,"MSG %s\n",s);}
static unsigned char confirm_(const char* s){(void)s;return 1;}
/* dir_open/dir_next: imageio's size_of asks the core for the image's size. */
static int listing;
static unsigned char dir_open_(const char* p){(void)p;listing=0;return 1;}
static unsigned char dir_next_(void){
 FILE* f; long n;
 if(listing++) return 0;
 strcpy(de.name,"VOL.PO");
 f=fopen(imagepath,"rb"); fseek(f,0,SEEK_END); n=ftell(f); fclose(f);
 de.size=(unsigned long)n; de.type=6; return 1;
}
static unsigned char dir_close_(void){return mode==34?fail_at:0;}

int main(int argc,char** argv){
 struct A2fcApi api; memset(&api,0,sizeof api);
 strcpy(imagepath,argv[1]); strcpy(outdir,argv[2]);
 mode=atoi(argv[3]); fail_at=atoi(argv[4]);
 strcpy(full_,"/I/VOL.PO");   /* a ProDOS path: size_of has 64 bytes for it */
 strcpy(sel.name,"VOL.PO");
 sel.type=6;
 strcpy(panels_[0].path,"/IMG"); strcpy(panels_[1].path,"/OUT");
 if(mode==6) panels_[0].fs=FS_IMG;          /* the wrong panel */
 if(mode==7) panels_[1].path[0]=0;          /* no destination */
 if(mode==8) sel.type=0x0F;                 /* a directory under the cursor */
 if(mode==31){int i;for(i=4;i<fail_at;++i)panels_[1].path[i]=i%16==4?'/':'A';panels_[1].path[fail_at]=0;}
 api.panels=panels_; api.active=&active_; api.selected=&sel; api.full=full_;
 api.copy_buf=scratch; api.note=note_text; api.dir_entry=&de;
 api.memcpy=memcpy; api.memset=memset; api.strcpy=strcpy; api.strcmp=strcmp;
 api.strlen=strlen; api.sprintf=sprintf; api.mli=mli_;
 api.fopen=open_; api.fread=read_; api.fwrite=write_; api.fclose=close_;
 api.fseek=fseek; api.remove=remove_; api.progress_bar=progress_;
 api.message=message_; api.confirm=confirm_;
 api.dir_open=dir_open_; api.dir_next=dir_next_; api.dir_close=(void (*)(void))dir_close_;
 plugin_entry(&api);
 fprintf(stderr,"SOURCE-CLOSE %u\n",image_closes);
 fprintf(stderr,"CREATES %d\n",creates);
 printf("%s\n",note_text);
 return 0;
}
'''

FILES = [('HELLO.TEXT', 3, bytes(1024) + b'Hello, Pascal.\r'.ljust(1024, b'\0')),
         ('SYSTEM.APPLE', 2, bytes(range(256)) * 20),
         ('ODD-NAME', 5, b'y' * 700),
         ('SHORT', 0, b'x')]


class Pascal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='pascal-build-')
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
        self.case = tempfile.TemporaryDirectory(prefix='pascal-')
        self.addCleanup(self.case.cleanup)
        self.dir = Path(self.case.name)
        self.out = self.dir / 'out'
        self.out.mkdir()
        self.image = self.dir / 'VOL.PO'
        self.data = P.make('MYVOL', FILES)
        self.image.write_bytes(self.data)

    def run_op(self, mode=0, at=1):
        run = subprocess.run(
            [str(self.exe), str(self.image), str(self.out) + '/', str(mode), str(at)],
            text=True, capture_output=True, check=True)
        note = run.stdout.strip()
        self.trace = run.stderr.splitlines()
        self.image_closes=[int(l.split()[1]) for l in self.trace if l.startswith('SOURCE-CLOSE ')][0]
        self.creates=[int(l.split()[1]) for l in self.trace if l.startswith('CREATES ')][0]
        # the image is read only: it never changes, whatever happened
        self.assertEqual(self.image.read_bytes(), self.data)
        return note

    def extracted(self):
        return sorted(p.name for p in self.out.iterdir())

    # -- what must happen ---------------------------------------------------

    def test_every_file_comes_out_with_the_bytes_the_reference_reads(self):
        note = self.run_op()
        self.assertEqual(note, '4 extracted, 0 skipped (name taken).')
        v = P.volume(self.data)
        for entry in v['files']:
            name = entry['name'].replace('-', '.')
            got = (self.out / name).read_bytes()
            self.assertEqual(got, P.contents(self.data, entry), name)

    def test_the_directory_read_is_announced_and_each_pass_fills_its_bar(self):
        note = self.run_op()
        self.assertEqual(self.trace[0], 'MSG Reading the Pascal directory...')
        for entry in P.volume(self.data)['files']:
            name = entry['name'].replace('-', '.')
            with self.subTest(name=name):
                blocks = entry['last'] - entry['first']
                done = [l.split()[2:] for l in self.trace if l.startswith('BAR %s ' % name)]
                steps = [[str(k), str(blocks)] for k in range(1, blocks + 1)]
                self.assertEqual(done, steps * 2)

    def test_final_source_errors_keep_verified_outputs_and_refuse_success(self):
        for empty,mode in ((False,12),(False,13),(True,12),(True,0)):
            with self.subTest(empty=empty,mode=mode):
                for p in self.out.iterdir():p.unlink()
                self.data=P.make('MYVOL',[] if empty else FILES);self.image.write_bytes(self.data)
                (self.out/'KEEP').write_bytes(b'existing bytes')
                note=self.run_op(mode)
                self.assertEqual(self.image_closes,1)
                if mode:self.assertIn('failed, stopped',note)
                else:self.assertEqual(note,'0 extracted, 0 skipped (name taken).')
                expected={'KEEP':b'existing bytes'}
                for e in P.volume(self.data)['files']:
                    expected[e['name'].replace('-','.')]=P.contents(self.data,e)
                self.assertEqual({p.name:p.read_bytes() for p in self.out.iterdir()},expected)

    def test_cancel_during_final_source_close_preserves_verified_outputs(self):
        for empty in (False,True):
            for mode in (32,33):
                with self.subTest(empty=empty,mode=mode):
                    for p in self.out.iterdir():p.unlink()
                    self.data=P.make('MYVOL',[] if empty else FILES)
                    self.image.write_bytes(self.data)
                    (self.out/'KEEP').write_bytes(b'existing bytes')
                    note=self.run_op(mode)
                    entries=P.volume(self.data)['files']
                    expected={'KEEP':b'existing bytes'}
                    expected.update({e['name'].replace('-','.'):P.contents(self.data,e)
                                     for e in entries})
                    self.assertEqual({p.name:p.read_bytes() for p in self.out.iterdir()},expected)
                    self.assertEqual(self.creates,len(entries))
                    self.assertEqual(self.image_closes,1)
                    self.assertEqual(note,f'{len(entries)} extracted, 0 skipped (name taken); stopped.')

    def test_full_count_source_errors_stop_before_accepting_directory_or_data(self):
        cases=[(14,at) for at in range(2,9)]+[(15,4),(16,4)]
        for mode,at in cases:
            with self.subTest(mode=mode,at=at):
                for p in self.out.iterdir():p.unlink()
                (self.out/'KEEP').write_bytes(b'existing bytes')
                note=self.run_op(mode,at)
                expected={'KEEP':b'existing bytes'}
                if mode in (15,16):
                    entries=P.volume(self.data)['files']
                    for e in entries[:4 if mode==16 else 3]:
                        expected[e['name'].replace('-','.')]=P.contents(self.data,e)
                self.assertEqual({p.name:p.read_bytes() for p in self.out.iterdir()},expected)
                self.assertEqual(self.image_closes,1)
                self.assertEqual(self.creates,4 if mode in (15,16) else (0 if at<=6 else 1))
                if mode==16:self.assertIn('Cleanup failed',note)
                elif mode==14 and at<=5:self.assertEqual(note,'Not an Apple Pascal volume.')
                else:self.assertIn('failed, stopped',note)

    def test_cancellation_during_output_closes_cleans_only_current_file(self):
        entries=P.volume(self.data)['files']
        for mode in (17,18,19,20):
            for at in (1,4):
                with self.subTest(mode=mode,at=at):
                    for p in self.out.iterdir():p.unlink()
                    (self.out/'KEEP').write_bytes(b'existing bytes')
                    note=self.run_op(mode,at)
                    kept=mode in (18,20)
                    expected={'KEEP':b'existing bytes'}
                    expected.update({e['name'].replace('-','.'):P.contents(self.data,e)
                                     for e in entries[:at if kept else at-1]})
                    self.assertEqual({p.name:p.read_bytes() for p in self.out.iterdir()},expected)
                    self.assertEqual(self.creates,at)
                    self.assertEqual(self.image_closes,1)
                    self.assertIn('Cleanup failed' if kept else '; stopped.',note)
                    name=entries[at-1]['name'].replace('-','.')
                    bars=[l for l in self.trace if l.startswith('BAR %s ' % name)]
                    blocks=entries[at-1]['last']-entries[at-1]['first']
                    self.assertEqual(len(bars),blocks*(1 if mode in (19,20) else 2))

    def test_a_name_already_there_is_skipped_and_left_alone(self):
        (self.out / 'SHORT').write_bytes(b'KEEP ME')
        note = self.run_op()
        self.assertEqual(note, '3 extracted, 1 skipped (name taken).')
        self.assertEqual((self.out / 'SHORT').read_bytes(), b'KEEP ME')

    def test_path_limit_stops_without_reporting_a_name_collision(self):
        entries=P.volume(self.data)['files']
        for length,done in ((50,4),(51,1),(53,0),(63,0)):
            with self.subTest(length=length):
                with tempfile.TemporaryDirectory(dir=self.dir) as tmp:
                    self.out=Path(tmp)
                    suffix=''.join('/' if i%16==4 else 'A' for i in range(4,length))
                    target=self.out/suffix.lstrip('/');target.mkdir(parents=True)
                    (target/'KEEP').write_bytes(b'existing bytes')
                    note=self.run_op(31,length)
                    expected={'KEEP':b'existing bytes'}
                    expected.update({e['name'].replace('-','.'):P.contents(self.data,e)
                                     for e in entries[:done]})
                    self.assertEqual({p.name:p.read_bytes() for p in self.out.rglob('*') if p.is_file()},expected)
                    self.assertEqual(self.creates,done)
                    self.assertEqual(self.image_closes,1)
                    self.assertEqual(note,f'{done} extracted, 0 skipped (name taken)'+
                                     ('.' if done==4 else '; failed, stopped.'))

    # -- what must not ------------------------------------------------------

    def test_image_metadata_close_error_refuses_before_open_or_create(self):
        (self.out/'KEEP').write_bytes(b'existing bytes')
        for error in (1,27):
            with self.subTest(error=error):
                for p in self.out.iterdir():
                    if p.name!='KEEP':p.unlink()
                note=self.run_op(34,error)
                self.assertEqual(self.creates,0)
                self.assertEqual(self.image_closes,0)
                self.assertEqual({p.name:p.read_bytes() for p in self.out.iterdir()},
                                 {'KEEP':b'existing bytes'})
                self.assertEqual(note,'Not a disk image this can open.')

    def test_a_directory_that_does_not_explain_itself_is_refused(self):
        breaks = {
            'the directory does not end at block 6': (P.DIR_BLOCK * 512 + 2, 9),
            'an empty volume name': (P.DIR_BLOCK * 512 + 6, 0),
            'a volume name with a space': (P.DIR_BLOCK * 512 + 8, 32),
            'more files than a directory holds': (P.DIR_BLOCK * 512 + 16, 99),
            'a file with no name': (P.DIR_BLOCK * 512 + P.ENTRY + 6, 0),
            'a last block before the first': (P.DIR_BLOCK * 512 + P.ENTRY + 2, 0),
            'a file past the end of the volume': (P.DIR_BLOCK * 512 + P.ENTRY + 3, 0x7F),
        }
        for why, (at, value) in breaks.items():
            with self.subTest(why=why):
                bad = bytearray(self.data)
                bad[at] = value
                self.image.write_bytes(bytes(bad))
                self.data = bytes(bad)
                note = self.run_op()
                self.assertEqual(note, 'Not an Apple Pascal volume.', why)
                self.assertEqual(self.extracted(), [])

    def test_volume_must_contain_its_entire_directory_even_when_empty(self):
        for blocks in range(7):
            with self.subTest(blocks=blocks):
                data=bytearray(P.make('MYVOL',[]))
                data[P.DIR_BLOCK*512+14:P.DIR_BLOCK*512+16]=blocks.to_bytes(2,'little')
                self.data=bytes(data);self.image.write_bytes(self.data)
                self.assertEqual(P.volume(self.data) is not None,blocks==6)
                (self.out/'KEEP').write_bytes(b'existing bytes')
                note=self.run_op()
                self.assertEqual(self.creates,0)
                self.assertEqual(self.image_closes,1)
                self.assertEqual({p.name:p.read_bytes() for p in self.out.iterdir()},
                                 {'KEEP':b'existing bytes'})
                self.assertEqual(note,'0 extracted, 0 skipped (name taken).'
                                 if blocks==6 else 'Not an Apple Pascal volume.')

    def test_something_that_is_not_a_pascal_volume_is_refused(self):
        self.data = bytes(280 * 512)
        self.image.write_bytes(self.data)
        self.assertEqual(self.run_op(), 'Not an Apple Pascal volume.')
        self.assertEqual(self.extracted(), [])

    def test_the_wrong_panels_are_refused(self):
        for mode in (6, 7, 8):
            note = self.run_op(mode=mode)
            self.assertIn(note, ('Select a disk image; ProDOS folder opposite.',
                                 'Other panel: open a ProDOS directory.'), note)
            self.assertEqual(self.extracted(), [])

    def test_a_failure_removes_the_file_it_was_writing(self):
        """Only the file of the moment: what came out before it stays."""
        for mode in (2, 3, 5):
            for at in (1, 2, 3, 8):
                with self.subTest(mode=mode, at=at):
                    for p in self.out.iterdir():
                        p.unlink()
                    note = self.run_op(mode=mode, at=at)
                    if 'stopped' not in note:
                        continue
                    v = P.volume(self.data)
                    done = int(note.split()[0])
                    names = [f['name'].replace('-', '.') for f in v['files']]
                    self.assertEqual(self.extracted(), sorted(names[:done]))
                    for entry, name in zip(v['files'], names[:done]):
                        self.assertEqual((self.out / name).read_bytes(),
                                         P.contents(self.data, entry))

    def test_readback_stream_errors_never_count_as_verified(self):
        volume = P.volume(self.data)
        entries = volume['files']
        (self.out/'KEEP').write_bytes(b'preexisting bytes')
        for mode in (9,10,11):
            for at in (1,2):
                with self.subTest(mode=mode,at=at):
                    for path in self.out.iterdir():
                        if path.name != 'KEEP':path.unlink()
                    note=self.run_op(mode=mode,at=at)
                    self.assertNotEqual(note,'4 extracted, 0 skipped (name taken).')
                    self.assertEqual((self.out/'KEEP').read_bytes(),b'preexisting bytes')
                    expected={'KEEP':b'preexisting bytes'}
                    for entry in entries[:at if mode==11 else at-1]:
                        name=entry['name'].replace('-', '.')
                        expected[name]=P.contents(self.data,entry)
                    self.assertEqual({p.name:p.read_bytes() for p in self.out.iterdir()},expected)
                    self.assertIn('Cleanup failed' if mode==11 else 'failed, stopped',note)

    def test_creation_errors_stop_and_preserve_verified_and_existing_bytes(self):
        entries=P.volume(self.data)['files']
        for mode in (4,29,30):
            for at in (1,2,4):
                with self.subTest(mode=mode,at=at):
                    for p in self.out.iterdir():p.unlink()
                    (self.out/'KEEP').write_bytes(b'existing bytes')
                    note=self.run_op(mode,at)
                    expected={'KEEP':b'existing bytes'}
                    expected.update({e['name'].replace('-','.'):P.contents(self.data,e)
                                     for e in entries[:at-1]})
                    self.assertEqual({p.name:p.read_bytes() for p in self.out.iterdir()},expected)
                    self.assertEqual(self.creates,at)
                    self.assertEqual(self.image_closes,1)
                    self.assertEqual(note,f'{at-1} extracted, 0 skipped (name taken); failed, stopped.')


if __name__ == '__main__':
    unittest.main()
