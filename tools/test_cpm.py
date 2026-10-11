"""Execute the shipped CP/M C over Apple CP/M images and I/O faults.

The fixtures come from tools/cpm_ref.py, which is also the oracle: every
extracted file is compared with the bytes that reference reads out of the
same image, through each of the candidate sector orders in turn -- the
overlay is not told which one a disk uses, it finds the one whose directory
explains itself. Nothing is written to the image, and a refusal must leave
the destination directory exactly as it was.
"""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import cpm_ref as P

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
#include "src/plugins/cpm.c"

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
static int mode, reads, fail_at, creates,image_reads,image_seeks;
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
 if(f==image_file)++image_reads;
 ++reads; if(mode==2 && reads==fail_at) return 0;
 if(f==image_file && ((mode==14 && reads==fail_at) ||
    ((mode==15 || mode==16) && verify_file && creates==fail_at)))errored=f;
 if(f==verify_file && creates==fail_at) {
  if((mode==9 || mode==11) && n==1){errored=f;return 0;}
  if(mode==10 && n>1)errored=f; /* full count, error flag set */
 }
 return fread(p,s,n,f);
}
static int seek_(FILE* f,long off,int whence){
 if(f==image_file && ++image_seeks==fail_at && mode==34)return -1;
 return fseek(f,off,whence);
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
static void message_(const char* s){(void)s;}
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
static unsigned char dir_close_(void){return mode==35?fail_at:0;}

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
 api.fseek=seek_; api.remove=remove_; api.progress_bar=progress_;
 api.message=message_; api.confirm=confirm_;
 api.dir_open=dir_open_; api.dir_next=dir_next_; api.dir_close=(void (*)(void))dir_close_;
 plugin_entry(&api);
 fprintf(stderr,"SOURCE-CLOSE %u\n",image_closes);
 fprintf(stderr,"CREATES %d\n",creates);
 fprintf(stderr,"IMAGE-READS %d\n",image_reads);
 fprintf(stderr,"IMAGE-SEEKS %d\n",image_seeks);
 printf("%s\n",note_text);
 return 0;
}
'''

FILES = [('HELLO.TXT', b'Hello, CP/M.\r\n' * 10),
         ('BIG.DAT', bytes(range(256)) * 90),          # more than one extent
         ('TINY.COM', b'\xc9'),
         ('NOEXT', b'no type at all\r\n')]


class Cpm(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='cpm-build-')
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
        self.case = tempfile.TemporaryDirectory(prefix='cpm-')
        self.addCleanup(self.case.cleanup)
        self.dir = Path(self.case.name)
        self.out = self.dir / 'out'
        self.out.mkdir()
        self.image = self.dir / 'VOL.PO'
        self.build('apple')

    def build(self, skew):
        self.skew = skew
        self.data = P.make(FILES, skew=skew)
        self.image.write_bytes(self.data)

    def run_op(self, mode=0, at=1):
        run = subprocess.run(
            [str(self.exe), str(self.image), str(self.out) + '/', str(mode), str(at)],
            text=True, capture_output=True, check=True)
        note = run.stdout.strip()
        self.bars = [l.split()[1:] for l in run.stderr.splitlines() if l.startswith('BAR ')]
        self.image_closes=[int(l.split()[1]) for l in run.stderr.splitlines() if l.startswith('SOURCE-CLOSE ')][0]
        self.creates=[int(l.split()[1]) for l in run.stderr.splitlines() if l.startswith('CREATES ')][0]
        self.image_reads=[int(l.split()[1]) for l in run.stderr.splitlines() if l.startswith('IMAGE-READS ')][0]
        self.image_seeks=[int(l.split()[1]) for l in run.stderr.splitlines() if l.startswith('IMAGE-SEEKS ')][0]
        # read only: the image never changes, whatever happened
        self.assertEqual(self.image.read_bytes(), self.data)
        return note

    def extracted(self):
        return sorted(p.name for p in self.out.iterdir())

    # -- what must happen ---------------------------------------------------

    def test_every_file_redraws_its_bar_for_both_passes(self):
        # A kilobyte at a time from 0, once for the copy and once for the
        # read-back: a small file after a big one still shows its own name.
        self.assertEqual(self.run_op(), '4 extracted, 0 skipped (name taken).')
        for name, data in FILES:
            with self.subTest(name=name):
                size = (len(data) + 127) // 128 * 128     # CP/M counts 128-byte records
                done = [int(d) for n, d, t in self.bars if n == name]
                self.assertTrue(all(t == str(size) for n, d, t in self.bars if n == name))
                one = list(range(0, size, 1024))
                self.assertEqual(done, one * 2)

    def test_each_candidate_sector_order_is_found_and_read(self):
        """The overlay is never told the skew; it keeps the one that
        explains the directory, and the bytes must match the reference."""
        for skew in P.SKEWS:
            with self.subTest(skew=skew):
                for f in self.out.iterdir():
                    f.unlink()
                self.build(skew)
                note = self.run_op()
                self.assertEqual(note, '4 extracted, 0 skipped (name taken).')
                v = P.volume(self.data)
                self.assertIsNotNone(v)
                for entry in v['files']:
                    got = (self.out / entry['name']).read_bytes()
                    want = P.contents(self.data, entry, v['skew'])
                    self.assertEqual(got, want, entry['name'])

    def test_a_file_longer_than_one_extent_comes_out_whole(self):
        self.run_op()
        v = P.volume(self.data)
        big = next(f for f in v['files'] if f['name'] == 'BIG.DAT')
        self.assertGreater(len(big['blocks']), 16)      # it really spans extents
        got = (self.out / 'BIG.DAT').read_bytes()
        self.assertEqual(got, P.contents(self.data, big, v['skew']))
        self.assertEqual(got[:len(FILES[1][1])], FILES[1][1])

    def test_extent_attributes_do_not_split_a_file_identity(self):
        for skew in P.SKEWS:
            for entry in (1,2):  # BIG.DAT's first and second extents
                for attribute in (9,10,11):
                    with self.subTest(skew=skew,entry=entry,attribute=attribute):
                        for p in self.out.iterdir():p.unlink()
                        (self.out/'KEEP').write_bytes(b'existing bytes')
                        self.build(skew)
                        logical,within=divmod(entry*P.ENTRY+attribute,256)
                        offset=P.sector_offset(P.RESERVED_TRACKS+logical//16,
                                               P.SKEWS[skew][logical%16])+within
                        image=bytearray(self.data);image[offset]^=0x80
                        self.data=bytes(image);self.image.write_bytes(self.data)
                        note=self.run_op()
                        volume=P.volume(self.data)
                        expected={'KEEP':b'existing bytes'}
                        expected.update({e['name']:P.contents(self.data,e,volume['skew'])
                                         for e in volume['files']})
                        self.assertEqual({p.name:p.read_bytes() for p in self.out.iterdir()},expected)
                        self.assertEqual(note,'4 extracted, 0 skipped (name taken).')
                        self.assertEqual(self.creates,4)

    def test_directory_read_failure_during_measurement_is_not_an_empty_file(self):
        volume=P.volume(self.data)
        first=next(e for e in volume['files'] if e['name']=='HELLO.TXT')
        verified=P.contents(self.data,first,volume['skew'])
        # Reads 1-8 validate the directory; read 9 starts extraction.
        # 10-16 measure HELLO, 22-28 measure BIG after HELLO is verified.
        for at in list(range(10,17))+list(range(22,29)):
            with self.subTest(at=at):
                for p in self.out.iterdir():p.unlink()
                (self.out/'KEEP').write_bytes(b'existing bytes')
                note=self.run_op(2,at)
                self.assertIn('failed, stopped',note)
                self.assertIn('0 skipped',note)
                files={p.name:p.read_bytes() for p in self.out.iterdir()}
                self.assertEqual(files,{'KEEP':b'existing bytes',**({'HELLO.TXT':verified} if at>=22 else {})})

    def test_zero_record_file_is_extracted_and_verified(self):
        data=bytearray(P.make([('EMPTY',b''),('NORMAL',b'kept')],skew=self.skew))
        # The fixture writer pads even empty input to one record. Encode
        # an actual zero-record directory entry with no allocation blocks.
        off=P.sector_offset(P.RESERVED_TRACKS,P.SKEWS[self.skew][0])
        data[off+15:off+32]=bytes(17)
        self.data=bytes(data)
        self.image.write_bytes(self.data)
        self.assertEqual(self.run_op(),'2 extracted, 0 skipped (name taken).')
        self.assertEqual(self.extracted(),['EMPTY','NORMAL'])
        self.assertEqual((self.out/'EMPTY').read_bytes(),b'')
        volume=P.volume(self.data)
        normal=next(e for e in volume['files'] if e['name']=='NORMAL')
        self.assertEqual((self.out/'NORMAL').read_bytes(),P.contents(self.data,normal,volume['skew']))

    def test_cancellation_during_output_closes_stops_and_cleans_current_file(self):
        volume=P.volume(self.data)
        ordered={e['name']:P.contents(self.data,e,volume['skew']) for e in volume['files']}
        for mode in (17,18,19,20):
            for at in (1,4):
                with self.subTest(mode=mode,at=at):
                    for p in self.out.iterdir():p.unlink()
                    (self.out/'KEEP').write_bytes(b'existing bytes')
                    note=self.run_op(mode,at)
                    kept=mode in (18,20)
                    expected={'KEEP':b'existing bytes'}
                    expected.update({name:ordered[name] for name,_ in FILES[:at if kept else at-1]})
                    self.assertEqual({p.name:p.read_bytes() for p in self.out.iterdir()},expected)
                    self.assertEqual(self.creates,at)
                    self.assertEqual(self.image_closes,1)
                    self.assertIn('Cleanup failed' if kept else '; stopped.',note)
                    # Closing the write pass with ESC must prevent read-back.
                    name=FILES[at-1][0]
                    starts=sum(n==name and d=='0' for n,d,t in self.bars)
                    self.assertEqual(starts,1 if mode in (19,20) else 2)

    def test_full_count_source_errors_stop_before_accepting_current_output(self):
        # Full fread counts with a source error: directory validation,
        # first entry, measurement, copying, and final-file verification.
        cases=[(14,at) for at in list(range(1,17))+[18]]+[(15,4),(16,4)]
        volume=P.volume(self.data)
        ordered={e['name']:P.contents(self.data,e,volume['skew']) for e in volume['files']}
        for mode,at in cases:
            with self.subTest(mode=mode,at=at):
                for p in self.out.iterdir():p.unlink()
                (self.out/'KEEP').write_bytes(b'existing bytes')
                note=self.run_op(mode,at)
                expected={'KEEP':b'existing bytes'}
                if mode in (15,16):
                    expected.update({name:ordered[name] for name,_ in FILES[:4 if mode==16 else 3]})
                self.assertEqual({p.name:p.read_bytes() for p in self.out.iterdir()},expected)
                self.assertEqual(self.image_closes,1)
                self.assertEqual(self.creates,4 if mode in (15,16) else int(at==18))
                if mode==16:self.assertIn('Cleanup failed',note)
                elif mode==14 and at<=8:self.assertEqual(note,'Not a CP/M volume this can read.')
                else:self.assertIn('failed, stopped',note)

    def test_final_source_errors_report_failure_and_keep_verified_outputs(self):
        for skew in P.SKEWS:
            for mode in (12,13):
                with self.subTest(skew=skew,mode=mode):
                    for p in self.out.iterdir():p.unlink()
                    self.build(skew);(self.out/'KEEP').write_bytes(b'existing bytes')
                    note=self.run_op(mode)
                    self.assertIn('4 extracted, 0 skipped',note)
                    self.assertIn('failed, stopped',note)
                    self.assertEqual(self.image_closes,1)
                    volume=P.volume(self.data)
                    expected={'KEEP':b'existing bytes'}
                    expected.update({e['name']:P.contents(self.data,e,volume['skew']) for e in volume['files']})
                    self.assertEqual({p.name:p.read_bytes() for p in self.out.iterdir()},expected)

    def test_cancel_during_final_source_close_preserves_verified_outputs(self):
        for zero_records in (False,True):
            for mode in (32,33):
                with self.subTest(zero_records=zero_records,mode=mode):
                    for p in self.out.iterdir():p.unlink()
                    if zero_records:
                        data=bytearray(P.make([('EMPTY',b'')],skew=self.skew))
                        off=P.sector_offset(P.RESERVED_TRACKS,P.SKEWS[self.skew][0])
                        data[off+15:off+32]=bytes(17)
                        self.data=bytes(data)
                    else:self.data=P.make(FILES,skew=self.skew)
                    self.image.write_bytes(self.data)
                    (self.out/'KEEP').write_bytes(b'existing bytes')
                    note=self.run_op(mode)
                    expected={'KEEP':b'existing bytes'}
                    volume=P.volume(self.data)
                    expected.update({e['name']:P.contents(self.data,e,volume['skew'])
                                     for e in volume['files']})
                    made=1 if zero_records else len(FILES)
                    self.assertEqual({p.name:p.read_bytes() for p in self.out.iterdir()},expected)
                    self.assertEqual(self.creates,made)
                    self.assertEqual(self.image_closes,1)
                    self.assertEqual(note,f'{made} extracted, 0 skipped (name taken); stopped.')

    def test_empty_file_collisions_io_faults_and_cancel_preserve_owned_bytes(self):
        for skew in ('apple','none'):
            for mode in (0,4,5,9,11,17,18,19,20,29,30):
                for collision in (False,True):
                    with self.subTest(skew=skew,mode=mode,collision=collision):
                        for p in self.out.iterdir():p.unlink()
                        data=bytearray(P.make([('EMPTY',b''),('NORMAL',b'next file')],skew=skew))
                        off=P.sector_offset(P.RESERVED_TRACKS,P.SKEWS[skew][0])
                        data[off+15:off+32]=bytes(17)
                        self.data=bytes(data);self.image.write_bytes(self.data)
                        (self.out/'KEEP').write_bytes(b'existing bytes')
                        if collision:(self.out/'EMPTY').write_bytes(b'previous empty-name file')
                        note=self.run_op(mode)
                        self.assertEqual((self.out/'KEEP').read_bytes(),b'existing bytes')
                        if collision:
                            self.assertEqual((self.out/'EMPTY').read_bytes(),b'previous empty-name file')
                            # CREATE failures precede name-collision discovery.
                            if mode in (4,5,29,30):
                                self.assertFalse((self.out/'NORMAL').exists())
                            else:
                                self.assertIn('1 skipped (name taken)',note)
                                self.assertIn('1 extracted',note)
                                vol=P.volume(self.data)
                                entry=next(e for e in vol['files'] if e['name']=='NORMAL')
                                self.assertEqual((self.out/'NORMAL').read_bytes(),P.contents(self.data,entry,vol['skew']))
                        elif mode==0:
                            self.assertTrue((self.out/'EMPTY').exists())
                            self.assertEqual((self.out/'EMPTY').read_bytes(),b'')
                            self.assertIn('2 extracted, 0 skipped',note)
                        else:
                            self.assertNotIn('1 skipped',note)
                            self.assertFalse((self.out/'NORMAL').exists())
                            if mode in (11,18,20):
                                self.assertEqual((self.out/'EMPTY').read_bytes(),b'')
                                self.assertIn('Cleanup failed',note)
                                self.assertEqual(self.creates,1)
                                retry=self.run_op()
                                self.assertEqual((self.out/'EMPTY').read_bytes(),b'')
                                self.assertIn('1 extracted, 1 skipped (name taken)',retry)
                                vol=P.volume(self.data)
                                entry=next(e for e in vol['files'] if e['name']=='NORMAL')
                                self.assertEqual((self.out/'NORMAL').read_bytes(),P.contents(self.data,entry,vol['skew']))
                            else:
                                self.assertFalse((self.out/'EMPTY').exists())
                                self.assertIn('0 extracted',note)

    def test_duplicate_extents_refuse_before_creating_a_file(self):
        for skew in ('apple','none'):
            for duplicate in (0,1):
                for collision in (False,True):
                    with self.subTest(skew=skew,duplicate=duplicate,collision=collision):
                        for p in self.out.iterdir():p.unlink()
                        data=bytearray(P.make([('BROKEN.DAT',b'A'*16384+b'B'*128),
                                               ('LATER',b'untouched')],skew=skew))
                        off=P.sector_offset(P.RESERVED_TRACKS,P.SKEWS[skew][0])
                        # Distinct allocation blocks, but two entries claim the
                        # same file extent. Attribute bits do not change identity.
                        data[off+duplicate*32+12]=1-duplicate
                        data[off+32+9]|=128
                        self.data=bytes(data);self.image.write_bytes(self.data)
                        expected={'KEEP':b'existing bytes'}
                        if collision:expected['BROKEN.DAT']=b'previous file'
                        for name,payload in expected.items():(self.out/name).write_bytes(payload)
                        note=self.run_op()
                        self.assertEqual(self.creates,0)
                        self.assertIn('failed, stopped',note)
                        self.assertEqual({p.name:p.read_bytes() for p in self.out.iterdir()},expected)

    def test_extent_bitmap_bounds_and_directory_cache_changes(self):
        for skew in ('apple','none'):
            for last_slot in (2,7,8,63):
                for extent in (2,1,64,256,8191):
                    with self.subTest(skew=skew,last_slot=last_slot,extent=extent):
                        for p in self.out.iterdir():p.unlink()
                        payload=b'A'*16384+b'B'*16384+b'C'*128
                        data=bytearray(P.make([('BROKEN.DAT',payload)],skew=skew))
                        def offset(slot):
                            logical=slot//8
                            return P.sector_offset(P.RESERVED_TRACKS,
                                                   P.SKEWS[skew][logical])+slot%8*32
                        first,third,target=offset(0),offset(2),offset(last_slot)
                        entry=bytearray(data[third:third+32])
                        entry[12]=extent&31;entry[14]=extent>>5
                        data[third:third+32]=b'\xe5'*32
                        data[target:target+32]=entry
                        # Put the highest extent first: directory order must
                        # not affect identity validation or healthy extraction.
                        saved=bytes(data[first:first+32])
                        data[first:first+32]=data[target:target+32]
                        data[target:target+32]=saved
                        self.data=bytes(data);self.image.write_bytes(self.data)
                        expected={'KEEP':b'existing bytes'}
                        (self.out/'KEEP').write_bytes(expected['KEEP'])
                        note=self.run_op()
                        if extent==2:
                            expected['BROKEN.DAT']=payload
                            self.assertEqual(self.creates,1)
                            self.assertEqual(note,'1 extracted, 0 skipped (name taken).')
                        else:
                            self.assertEqual(self.creates,0)
                            self.assertIn('failed, stopped',note)
                        self.assertEqual({p.name:p.read_bytes() for p in self.out.iterdir()},expected)

    def test_record_counts_and_missing_required_blocks_refuse_before_create(self):
        for skew in ('apple','none'):
            for defect in ('short-first','zero-first','missing-first','missing-second','missing-extent'):
                for collision in (False,True):
                    with self.subTest(skew=skew,defect=defect,collision=collision):
                        for p in self.out.iterdir():p.unlink()
                        payload=(b'A'*16384+b'B'*128 if defect.endswith('first')
                                 and defect.startswith(('short','zero')) else
                                 b'A'*1024+b'B'*1024+b'C'*1024)
                        data=bytearray(P.make([('BROKEN.DAT',payload)],skew=skew))
                        off=P.sector_offset(P.RESERVED_TRACKS,P.SKEWS[skew][0])
                        if defect=='short-first':data[off+15]=127
                        elif defect=='zero-first':data[off+15]=0
                        elif defect=='missing-first':
                            data[off+15]=1;data[off+16]=0
                        elif defect=='missing-second':
                            data[off+15]=9;data[off+17]=0
                        else:data[off+12]=1
                        self.data=bytes(data);self.image.write_bytes(self.data)
                        expected={'KEEP':b'existing bytes'}
                        if collision:expected['BROKEN.DAT']=b'previous file'
                        for name,payload in expected.items():(self.out/name).write_bytes(payload)
                        note=self.run_op()
                        self.assertEqual(self.creates,0)
                        self.assertIn('failed, stopped',note)
                        self.assertEqual({p.name:p.read_bytes() for p in self.out.iterdir()},expected)

    def test_record_prefix_boundaries_and_empty_terminal_extent(self):
        for skew in ('apple','none'):
            for records in (0,1,8,9,127,128,129,256,257):
                with self.subTest(skew=skew,records=records):
                    for p in self.out.iterdir():p.unlink()
                    size=records*128
                    payload=bytes(i%251 for i in range(max(size,3072)))
                    data=bytearray(P.make([('GOOD.DAT',payload)],skew=skew))
                    off=P.sector_offset(P.RESERVED_TRACKS,P.SKEWS[skew][0])
                    if records<128:data[off+15]=records
                    self.data=bytes(data);self.image.write_bytes(self.data)
                    (self.out/'KEEP').write_bytes(b'existing bytes')
                    self.assertEqual(self.run_op(),'1 extracted, 0 skipped (name taken).')
                    self.assertEqual({p.name:p.read_bytes() for p in self.out.iterdir()},
                                     {'KEEP':b'existing bytes','GOOD.DAT':payload[:size]})
            for p in self.out.iterdir():p.unlink()
            payload=b'A'*16384
            data=bytearray(P.make([('GOOD.DAT',payload+b'B'*128)],skew=skew))
            off=P.sector_offset(P.RESERVED_TRACKS,P.SKEWS[skew][0])
            data[off+32+15:off+64]=bytes(17)
            self.data=bytes(data);self.image.write_bytes(self.data)
            (self.out/'KEEP').write_bytes(b'existing bytes')
            self.assertEqual(self.run_op(),'1 extracted, 0 skipped (name taken).')
            self.assertEqual({p.name:p.read_bytes() for p in self.out.iterdir()},
                             {'KEEP':b'existing bytes','GOOD.DAT':payload})

    def test_a_name_already_there_is_skipped_and_left_alone(self):
        (self.out / 'TINY.COM').write_bytes(b'KEEP ME')
        note = self.run_op()
        self.assertEqual(note, '3 extracted, 1 skipped (name taken).')
        self.assertEqual((self.out / 'TINY.COM').read_bytes(), b'KEEP ME')

    # -- what must not ------------------------------------------------------

    def test_image_metadata_close_error_refuses_before_open_or_create(self):
        (self.out/'KEEP').write_bytes(b'existing bytes')
        for skew in P.SKEWS:
            self.build(skew)
            for error in (1,27):
                with self.subTest(skew=skew,error=error):
                    for p in self.out.iterdir():
                        if p.name!='KEEP':p.unlink()
                    note=self.run_op(35,error)
                    self.assertEqual(self.creates,0)
                    self.assertEqual(self.image_closes,0)
                    self.assertEqual(self.image_reads,0)
                    self.assertEqual({p.name:p.read_bytes() for p in self.out.iterdir()},
                                     {'KEEP':b'existing bytes'})
                    self.assertEqual(note,'Not a disk image this can open.')

    def test_skew_search_stops_on_io_error_instead_of_trying_next_order(self):
        self.build('none')
        (self.out/'KEEP').write_bytes(b'existing bytes')
        for mode in (2,14,34):
            for at in (1,2):
                with self.subTest(mode=mode,at=at):
                    for p in self.out.iterdir():
                        if p.name!='KEEP':p.unlink()
                    note=self.run_op(mode,at)
                    self.assertEqual({p.name:p.read_bytes() for p in self.out.iterdir()},
                                     {'KEEP':b'existing bytes'})
                    self.assertEqual(self.creates,0)
                    self.assertEqual(self.image_closes,1)
                    self.assertEqual(self.image_seeks,at)
                    self.assertEqual(self.image_reads,at-int(mode==34))
                    self.assertEqual(note,'Not a CP/M volume this can read.')

    def test_a_directory_that_does_not_explain_itself_is_refused(self):
        """A wrong skew reads as noise, and noise must be refused -- which
        is the same test that stops a corrupt directory."""
        off = P.sector_offset(P.RESERVED_TRACKS, P.SKEWS['apple'][0])
        breaks = {
            'an impossible user number': (off, 200),
            'a control character in a name': (off + 2, 3),
            'a record count past 128': (off + 15, 200),
            'a block number past the disk': (off + 16, 250),
            'a block inside the directory': (off + 16, 1),
        }
        for why, (at, value) in breaks.items():
            with self.subTest(why=why):
                bad = bytearray(self.data)
                bad[at] = value
                self.image.write_bytes(bytes(bad))
                self.data = bytes(bad)
                note = self.run_op()
                self.assertEqual(note, 'Not a CP/M volume this can read.', why)
                self.assertEqual(self.extracted(), [])
                self.build('apple')

    def test_an_empty_disk_is_not_a_volume(self):
        self.data = bytes(35 * 16 * 256)
        self.image.write_bytes(self.data)
        self.assertEqual(self.run_op(), 'Not a CP/M volume this can read.')
        self.assertEqual(self.extracted(), [])

    def test_the_wrong_panels_are_refused(self):
        for mode in (6, 7, 8):
            note = self.run_op(mode=mode)
            self.assertIn(note, ('Select a disk image; ProDOS folder opposite.',
                                 'Other panel: open a ProDOS directory.'), note)
            self.assertEqual(self.extracted(), [])

    def test_a_failure_removes_the_file_it_was_writing(self):
        for mode in (2, 3, 5):
            for at in (1, 2, 3, 8):
                with self.subTest(mode=mode, at=at):
                    for f in self.out.iterdir():
                        f.unlink()
                    note = self.run_op(mode=mode, at=at)
                    if 'stopped' not in note:
                        continue
                    done = int(note.split()[0])
                    self.assertEqual(len(self.extracted()), done, note)

    def test_readback_stream_errors_never_count_as_verified(self):
        volume = P.volume(self.data)
        by_name = {entry['name']:entry for entry in volume['files']}
        entries = [by_name[name] for name,_ in FILES]  # native directory order
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
                        expected[name]=P.contents(self.data,entry,volume['skew'])
                    self.assertEqual({p.name:p.read_bytes() for p in self.out.iterdir()},expected)
                    self.assertIn('Cleanup failed' if mode==11 else 'failed, stopped',note)

    def test_path_limit_stops_without_reporting_a_name_collision(self):
        volume=P.volume(self.data)
        for length,done in ((53,4),(54,0),(63,0)):
            with self.subTest(length=length):
                with tempfile.TemporaryDirectory(dir=self.dir) as tmp:
                    self.out=Path(tmp)
                    suffix=''.join('/' if i%16==4 else 'A' for i in range(4,length))
                    target=self.out/suffix.lstrip('/');target.mkdir(parents=True)
                    (target/'KEEP').write_bytes(b'existing bytes')
                    note=self.run_op(31,length)
                    expected={'KEEP':b'existing bytes'}
                    if done:expected.update({e['name']:P.contents(self.data,e,volume['skew'])
                                            for e in volume['files']})
                    self.assertEqual({p.name:p.read_bytes() for p in self.out.rglob('*') if p.is_file()},expected)
                    self.assertEqual(self.creates,done)
                    self.assertEqual(self.image_closes,1)
                    self.assertEqual(note,f'{done} extracted, 0 skipped (name taken)'+
                                     ('.' if done==4 else '; failed, stopped.'))

    def test_creation_errors_stop_and_preserve_verified_and_existing_bytes(self):
        volume=P.volume(self.data)
        entries={e['name']:e for e in volume['files']}
        for mode in (4,29,30):
            for at in (1,2,4):
                with self.subTest(mode=mode,at=at):
                    for p in self.out.iterdir():p.unlink()
                    (self.out/'KEEP').write_bytes(b'existing bytes')
                    note=self.run_op(mode,at)
                    expected={'KEEP':b'existing bytes'}
                    expected.update({name:P.contents(self.data,entries[name],volume['skew'])
                                     for name,_ in FILES[:at-1]})
                    self.assertEqual({p.name:p.read_bytes() for p in self.out.iterdir()},expected)
                    self.assertEqual(self.creates,at)
                    self.assertEqual(self.image_closes,1)
                    self.assertEqual(note,f'{at-1} extracted, 0 skipped (name taken); failed, stopped.')


if __name__ == '__main__':
    unittest.main()
