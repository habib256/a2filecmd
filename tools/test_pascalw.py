"""Execute the shipped PASCALW C: ProDOS files written into an Apple Pascal
(UCSD) volume, on disposable images only, and through I/O faults.

The volume is built and read back by tools/pascal_ref.py, which knows
nothing of the overlay -- the fixture must never share an assumption with
the code it checks.

What matters is the order: the data goes past the last block any file uses,
then the entry at index count+1, and the file count last of all. So a
failure anywhere before the count write must leave a volume that reads
exactly as it did, with the files put in before it intact.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pascal_ref
from po22mg import to_2mg
from po2dsk import to_dsk

ROOT = Path(__file__).resolve().parents[1]

C = r'''
#define __fastcall__
#define PLUGIN_HOST
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <dirent.h>
#undef memcpy
#undef memset
#undef strcpy
#undef sprintf
struct A2fcApi;
static int h_error(FILE*);
static void h_clear(FILE*);
#define ferror h_error
#define clearerr h_clear
#include "src/plugins/pascalw.c"
#undef ferror
#undef clearerr

static struct Panel panels[2];
static struct Entry sel;
static struct DirEntry de;
static unsigned char scratch[512], act;
static char note_text[160], full_path[280], other_scratch[280], reselect_text[64];
static char img_path[280], dir_path[280];
static int mode, fail_at, writes,image_updates;
static FILE* source_stream;
static FILE* image_stream;
static FILE* flagged;
static int source_reads,source_closes,image_reads,image_closes;
static int h_error(FILE* f){return f==flagged || ferror(f);}
static void h_clear(FILE* f){if(f==flagged)flagged=NULL;clearerr(f);}
static FILE* h_open(const char* p,const char* m){
    if(!strcasecmp(p,img_path) && !strcmp(m,"r+b"))++image_updates;
    FILE* f=fopen(!strcasecmp(p,img_path)?img_path:p,m);
    if(f && strcasecmp(p,img_path)){source_stream=f;source_reads=0;}
    else if(f)image_stream=f;
    return f;
}
static size_t h_read(void* p,size_t s,size_t n,FILE* f){
    size_t result=fread(p,s,n,f);
    if(f==image_stream){
        ++image_reads;
        if(mode==15 && image_reads==fail_at)return 0;
        if(((mode==11 || mode==20) && image_reads==fail_at) ||
           (mode==13 && image_reads>=fail_at))flagged=f;
    }
    if(f==source_stream){
        ++source_reads;
        if((mode==5 && source_reads==fail_at) || (mode==6 && n==1) ||
           (mode==19 && source_reads==1))flagged=f;
    }
    return result;
}
static int h_close(FILE* f){
    int failed=0,result;
    if(f==image_stream){
        ++image_closes;image_stream=NULL;
        if(mode==16 || mode==18 || mode==19 || mode==20)failed=1;
        if(mode==17 || mode==18)cancelled=1;
    }
    if(f==source_stream){
        ++source_closes;
        if(mode==7)failed=1;
        if(mode==8)cancelled=1;
        source_stream=NULL;
    }
    if(f==flagged)flagged=NULL;
    result=fclose(f);return failed?-1:result;
}

/* mode 1: answer No. 2: the nth fwrite fails. 3: it writes half. 4: it
 * comes back different. */
static size_t h_fwrite(const void* p, size_t s, size_t n, FILE* f) {
    ++writes;
    if(mode==35 && !(fail_at&2))return 0; /* ProDOS rejects WRITE, not OPEN. */
    if((mode==12 && writes==fail_at) || (mode==14 && writes>=fail_at))flagged=f;
    if (mode == 2 && writes == fail_at) return 0;
    if (mode == 3 && writes == fail_at) { fwrite(p, 1, 128, f); fflush(f); return 0; }
    if (mode == 4 && writes == fail_at) {
        unsigned char copy[512];
        memcpy(copy, p, s * n); copy[0] ^= 0xFF;
        return fwrite(copy, s, n, f) == n ? n : 0;
    }
    return fwrite(p, s, n, f);
}
static unsigned char h_confirm(const char* s) { (void)s; return mode != 1; }
static void h_message(const char* s) { (void)s; }
static void h_progress(const char* s, unsigned long a, unsigned long b)
{ fprintf(stderr, "BAR %s %lu %lu\n", s, a, b); }

/* One directory at a time, real files on the host. A ProDOS name carries no
 * suffix, so the types come from a ".types" manifest the enumerator skips. */
static char open_dir[280];
static char names[64][64];
static unsigned char types[64];
static int ncount, nat,source_passes,listing_error;

static void load_types(const char* dir) {
    char path[600], name[64]; unsigned int t; FILE* f; int i;
    for (i = 0; i < 64; ++i) types[i] = 0;
    sprintf(path, "%s/.types", dir);
    f = fopen(path, "r");
    if (!f) return;
    while (fscanf(f, "%63s %x", name, &t) == 2)
        for (i = 0; i < ncount; ++i)
            if (!strcmp(names[i], name)) types[i] = (unsigned char)t;
    fclose(f);
}

static unsigned char h_dir_open(const char* p) {
    DIR* dh; struct dirent* e;
    if(!strcasecmp(p,dir_path))p=dir_path; /* ProDOS case-insensitive lookup */
    ncount = nat = 0;
    listing_error=0;if(!strcmp(p,dir_path))++source_passes;
    dh = opendir(p);
    if (!dh) return 0;
    while ((e = readdir(dh)) && ncount < 64)
        if (e->d_name[0] != '.') strcpy(names[ncount++], e->d_name);
    closedir(dh);
    strcpy(open_dir, p);
    load_types(p);
    return 1;
}

static unsigned char h_dir_next(void) {
    char path[600]; FILE* f;
    if(mode==21 && !strcmp(open_dir,dir_path) && source_passes==fail_at && nat==fail_at-1){listing_error=1;return 0;}
    if (nat >= ncount) return 0;
    sprintf(path, "%s/%s", open_dir, names[nat]);
    strcpy(de.name, names[nat]);
    de.type = types[nat];
    de.access=(mode==35 && !strcmp(path,img_path))?fail_at:0xE3;
    de.aux = 0;
    de.mdate = 0x3533;                  /* 19 September 2026, ProDOS-shaped */
    de.size = 0;
    f = fopen(path, "rb");
    if (f) { fseek(f, 0, SEEK_END); de.size = ftell(f); fclose(f); }
    if(!strcmp(de.name,"NEWFILE")){
        if(mode==9 && de.size) --de.size; /* stale size: a truncated prefix */
        if(mode==10) ++de.size;          /* stale size: beyond actual EOF */
    }
    ++nat;
    return 1;
}
static unsigned char h_dir_close(void) {
    if(mode==34 && strcmp(open_dir,dir_path))return fail_at;
    return listing_error || (mode==22 && !strcmp(open_dir,dir_path) && source_passes==fail_at);
}

int main(int argc, char** argv) {
    struct A2fcApi api;
    memset(&api, 0, sizeof api);
    strcpy(img_path, argv[1]);
    strcpy(dir_path, argv[2]);
    mode = atoi(argv[3]); fail_at = atoi(argv[4]);
    strcpy(full_path, img_path);
    if(mode==32 || mode==33){
        char* end=strrchr(full_path,'/');char* p;
        for(p=full_path;p<end;++p)
            if(*p>='a' && *p<='z' && (mode==32 || (p-full_path)%2))*p-=32;
    }
    { const char* s = strrchr(img_path, '/'); strcpy(sel.name, s ? s + 1 : img_path); }
    sel.type = 6;sel.access=(mode==35 && (fail_at&2))?1:0xE3;
    /* Stale panel permissions differ from the freshly read directory. */
    panels[0].fs = FS_PRODOS;
    strcpy(panels[0].path, "/V");
    panels[1].fs = FS_PRODOS;
    strcpy(panels[1].path, dir_path);
    if (argc > 5 && atoi(argv[5])) panels[1].fs = FS_IMG;      /* wrong panel */

    api.panels = panels; api.active = &act; api.selected = &sel;
    api.full = full_path; api.other_full = other_scratch;
    api.copy_buf = scratch; api.note = note_text; api.reselect = reselect_text;
    api.dir_entry = &de;
    api.dir_open = h_dir_open; api.dir_next = h_dir_next; api.dir_close = (void (*)(void))h_dir_close;
    api.memcpy = memcpy; api.memset = memset; api.strcpy = strcpy;
    api.strcmp = strcmp; api.strlen = strlen; api.sprintf = sprintf;
    api.fopen = h_open; api.fread = h_read; api.fwrite = h_fwrite;
    api.fclose = h_close; api.fseek = fseek;
    api.confirm = h_confirm; api.message = h_message; api.progress_bar = h_progress;
    plugin_entry(&api);
    fprintf(stderr,"SOURCE-CLOSE %d\n",source_closes);
    fprintf(stderr,"IMAGE-CLOSE %d\n",image_closes);
    fprintf(stderr,"IMAGE-UPDATE %d\n",image_updates);
    fprintf(stderr,"SOURCE-PASSES %d\n",source_passes);
    printf("%d %s\n", writes, note_text);
    return 0;
}
'''

KEEP = ('ALREADY', 5, b'this one was in the volume\r' * 20)


class PascalW(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='pw-build-')
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
        self.case = tempfile.TemporaryDirectory(prefix='pw', dir='/tmp')
        self.addCleanup(self.case.cleanup)
        self.dir = Path(self.case.name)
        self.img = self.dir / 'VOL.PO'
        self.original = pascal_ref.make('MYVOL', [KEEP])
        self.img.write_bytes(self.original)
        self.src = self.dir / 'src'
        self.src.mkdir()
        self.files = {}

    def give(self, name, data, type_=0):
        """A file in the directory opposite, with its ProDOS type beside it.

        A ProDOS name carries no suffix, so the type goes in a manifest the
        harness reads and the enumerator skips."""
        self.files[name] = data
        (self.src / name).write_bytes(data)
        with (self.src / '.types').open('a') as f:
            f.write('%s %02X\n' % (name, type_))

    def run_op(self, mode=0, at=1, wrong=0):
        run = subprocess.run(
            [str(self.exe), str(self.img), str(self.src), str(mode), str(at), str(wrong)],
            text=True, capture_output=True, check=True)
        out = run.stdout.strip()
        self.trace = run.stderr.splitlines()
        n, _, note = out.partition(' ')
        return int(n), note

    def volume(self):
        return pascal_ref.volume(self.img.read_bytes())

    def contents(self, name):
        v = self.volume()
        e = next(f for f in v['files'] if f['name'] == name)
        return pascal_ref.contents(self.img.read_bytes(), e)

    # -- what must happen ---------------------------------------------------

    def test_every_file_shows_its_name_then_its_blocks(self):
        # `name` is one buffer for every file: 0 redraws it, so the bar
        # names each file -- a skipped one too -- then fills to the end.
        self.give('HELLO', b'hello, pascal\r' * 60, 3)          # 840 bytes: 2 blocks
        self.give('EMPTY', b'', 3)                               # skipped
        writes, note = self.run_op()
        self.assertIn('1 put', note)
        bars = [tuple(l.split()[1:]) for l in self.trace if l.startswith('BAR ')]
        self.assertEqual(sorted(set(bars)), sorted({('EMPTY', '0', '1'), ('HELLO', '0', '1'),
                                                    ('HELLO', '1', '2'), ('HELLO', '2', '2')}))

    def test_volume_smaller_than_its_directory_refuses_every_write(self):
        self.give('NEWFILE',b'new contents')
        for blocks in range(7):
            with self.subTest(blocks=blocks):
                data=bytearray(pascal_ref.make('MYVOL',[]))
                data[2*512+14:2*512+16]=blocks.to_bytes(2,'little')
                # Bytes beyond the declared volume belong to no writable
                # Pascal allocation: preserve the whole container.
                data[6*512:]=b'P'*(len(data)-6*512)
                original=bytes(data);self.img.write_bytes(original)
                sources={p.name:p.read_bytes() for p in self.src.iterdir()}
                writes,note=self.run_op()
                self.assertEqual(writes,0)
                self.assertEqual(self.img.read_bytes(),original)
                self.assertEqual({p.name:p.read_bytes() for p in self.src.iterdir()},sources)
                if blocks<6:self.assertEqual(note,'Not an Apple Pascal volume.')

    def test_one_data_block_volume_preserves_container_tail(self):
        self.give('NEWFILE',b'new contents')
        original=pascal_ref.make('MYVOL',[],blocks=7)+b'P'*(273*512)
        self.img.write_bytes(original)
        writes,note=self.run_op()
        self.assertGreater(writes,0)
        self.assertIn('1 put',note)
        self.assertEqual(self.contents('NEWFILE'),b'new contents')
        self.assertEqual(self.img.read_bytes()[7*512:],original[7*512:])
        self.assertEqual((self.src/'NEWFILE').read_bytes(),b'new contents')

    def test_source_errors_and_stale_sizes_never_publish_the_file(self):
        self.give('NEWFILE',bytes(range(256))*4)
        sources={p.name:p.read_bytes() for p in self.src.iterdir()}
        for mode,at in ((5,1),(5,2),(6,1),(7,1),(8,1),(9,1),(10,1)):
            with self.subTest(mode=mode,at=at):
                self.img.write_bytes(self.original)
                writes,note=self.run_op(mode,at)
                self.assertEqual([e['name'] for e in self.volume()['files']],['ALREADY'])
                self.assertEqual(self.contents('ALREADY'),KEEP[2])
                self.assertEqual(self.img.read_bytes()[:6*512],self.original[:6*512])
                self.assertEqual({p.name:p.read_bytes() for p in self.src.iterdir()},sources)
                self.assertIn('SOURCE-CLOSE 1',self.trace)
                self.assertNotIn('1 put',note)
                if mode==5 and at==1:self.assertEqual(writes,0)
                self.assertEqual(note,'Stopped; the volume is whole.' if mode==8
                                 else 'Cannot read a file opposite.')

    def test_image_full_count_errors_do_not_validate_data_or_directory(self):
        self.give('NEWFILE',bytes(range(256))*4)
        sources={p.name:p.read_bytes() for p in self.src.iterdir()}
        # Six reads validate the directory/tail before and after consent;
        # read 7 checks the name, 8/9 verify data, 10 backs up the directory,
        # 11 verifies publication, and 12 verifies restoration if needed.
        cases=[(11,at) for at in (*range(1,7),8,9,10,11)]
        cases += [(12,at) for at in (1,2,3)]+[(13,11),(14,3)]
        for mode,at in cases:
            with self.subTest(mode=mode,at=at):
                self.img.write_bytes(self.original)
                writes,note=self.run_op(mode,at)
                self.assertEqual(self.img.read_bytes()[:6*512],self.original[:6*512])
                self.assertEqual([e['name'] for e in self.volume()['files']],['ALREADY'])
                self.assertEqual(self.contents('ALREADY'),KEEP[2])
                self.assertEqual({p.name:p.read_bytes() for p in self.src.iterdir()},sources)
                self.assertNotIn('1 put',note)
                if mode==11 and at<=6:self.assertEqual(writes,0)
                if mode in (13,14):self.assertEqual(note,'Directory write failed; check the volume.')

    def test_name_search_read_errors_stop_without_skipping_or_writing(self):
        self.give('NEWFILE',b'new contents')
        self.give('LATER',b'another source must not be imported')
        for count in (1,19):
            original=pascal_ref.make('MYVOL',[(f'KEEP{i:02}',5,bytes([i])*512)
                                            for i in range(count)])
            reads=lambda i:1+int((i*26)%512+26>512)
            first=2*(1+sum(reads(i) for i in range(1,count+1))+reads(count))+1
            last=first+sum(reads(i) for i in range(1,count))-1
            points=(first,) if count==1 else (first,last+1,last+2)
            for mode in (11,15):
                for at in points:
                    with self.subTest(count=count,mode=mode,at=at):
                        self.img.write_bytes(original)
                        sources={p.name:p.read_bytes() for p in self.src.iterdir()}
                        writes,note=self.run_op(mode,at)
                        self.assertEqual(writes,0)
                        self.assertEqual(self.img.read_bytes(),original)
                        self.assertEqual({p.name:p.read_bytes() for p in self.src.iterdir()},sources)
                        self.assertIn('SOURCE-CLOSE 0',self.trace)
                        self.assertEqual(note,'Cannot read the Pascal directory.')

    def test_final_image_close_failure_or_cancel_keeps_published_files(self):
        for with_source,mode in ([(s,m) for s in (False,True) for m in (16,17,18)]+
                                 [(True,19),(True,20)]):
            with self.subTest(with_source=with_source,mode=mode):
                self.img.write_bytes(self.original)
                for p in self.src.iterdir():p.unlink()
                if with_source:self.give('NEWFILE',bytes(range(256))*4)
                sources={p.name:p.read_bytes() for p in self.src.iterdir()}
                writes,note=self.run_op(mode,7 if mode==20 else 1)
                volume=self.volume()
                expected={'ALREADY':KEEP[2]}
                if with_source and mode in (16,17,18):expected['NEWFILE']=sources['NEWFILE']
                self.assertEqual({e['name']:pascal_ref.contents(self.img.read_bytes(),e)
                                  for e in volume['files']},expected)
                self.assertEqual({p.name:p.read_bytes() for p in self.src.iterdir()},sources)
                self.assertIn('IMAGE-CLOSE 1',self.trace)
                self.assertIn(f'SOURCE-CLOSE {int(with_source and mode!=20)}',self.trace)
                if not with_source or mode==20:
                    self.assertEqual(writes,0)
                    self.assertEqual(self.img.read_bytes(),self.original)
                self.assertEqual(note,'Stopped; imported files kept.' if mode==17
                                 else 'Image close failed; check the volume.')

    def test_source_listing_errors_stop_and_keep_previously_imported_files(self):
        self.give('ALPHA',b'A'*300);self.give('ZULU',b'Z'*300)
        sources={p.name:p.read_bytes() for p in self.src.iterdir()}
        for mode in (21,22):
            for at in (1,2,3):
                with self.subTest(mode=mode,at=at):
                    self.img.write_bytes(self.original)
                    writes,note=self.run_op(mode,at)
                    volume=self.volume();data=self.img.read_bytes()
                    self.assertEqual(len(volume['files']),at)
                    for e in volume['files']:
                        expected=KEEP[2] if e['name']=='ALREADY' else sources[e['name']]
                        self.assertEqual(pascal_ref.contents(data,e),expected)
                    self.assertEqual({p.name:p.read_bytes() for p in self.src.iterdir()},sources)
                    self.assertIn(f'SOURCE-PASSES {at}',self.trace)
                    self.assertIn(f'SOURCE-CLOSE {at-1}',self.trace)
                    self.assertIn('IMAGE-CLOSE 1',self.trace)
                    self.assertEqual(writes,2*(at-1))
                    if at==1:self.assertEqual(data,self.original)
                    self.assertEqual(note,'Cannot read the other panel.')

    def test_container_read_errors_refuse_before_any_image_write(self):
        self.give('NEWFILE',b'new contents')
        for suffix,wrap,at in (('.2MG',to_2mg,1),('.DSK',to_dsk,1),('.DSK',to_dsk,2)):
            with self.subTest(suffix=suffix,at=at):
                self.img=self.dir/('VOL'+suffix)
                original=wrap(self.original);self.img.write_bytes(original)
                writes,note=self.run_op(11,at)
                self.assertEqual(writes,0)
                self.assertEqual(self.img.read_bytes(),original)
                self.assertEqual((self.src/'NEWFILE').read_bytes(),b'new contents')
                self.assertNotIn('1 put',note)

    def test_self_image_is_skipped_with_different_path_case(self):
        self.img=self.src/'VOL.PO'
        for mode in (32,33):
            with self.subTest(mode=mode):
                self.img.write_bytes(self.original)
                writes,note=self.run_op(mode)
                self.assertEqual(writes,0)
                self.assertEqual(self.img.read_bytes(),self.original)
                self.assertIn('SOURCE-CLOSE 0',self.trace)
                self.assertEqual(note,'0 put, 1 skipped (name taken or empty).')

    def test_image_metadata_close_error_refuses_before_open_or_write(self):
        self.give('NEWFILE',b'new bytes'*80)
        for suffix,wrap in (('.PO',bytes),('.2MG',to_2mg),('.DSK',to_dsk)):
            for error in (1,27):
                with self.subTest(suffix=suffix,error=error):
                    self.img=self.dir/('VOL'+suffix)
                    original=wrap(self.original);self.img.write_bytes(original)
                    writes,note=self.run_op(34,error)
                    self.assertEqual(writes,0)
                    self.assertEqual(self.img.read_bytes(),original)
                    self.assertEqual((self.src/'NEWFILE').read_bytes(),self.files['NEWFILE'])
                    self.assertIn('SOURCE-CLOSE 0',self.trace)
                    self.assertIn('IMAGE-CLOSE 0',self.trace)
                    self.assertEqual(note,'Not a disk image this can open.')

    def test_fresh_image_write_protection_is_respected(self):
        self.give('NEWFILE',b'new bytes'*80)
        for suffix,wrap in (('.PO',bytes),('.2MG',to_2mg),('.DSK',to_dsk)):
            for access in (1,0x21,0x41,0x81,0xC1):
                with self.subTest(suffix=suffix,access=access):
                    self.img=self.dir/('VOL'+suffix)
                    original=wrap(self.original);self.img.write_bytes(original)
                    writes,note=self.run_op(35,access)
                    self.assertEqual(writes,0)
                    self.assertEqual(self.img.read_bytes(),original)
                    self.assertEqual((self.src/'NEWFILE').read_bytes(),self.files['NEWFILE'])
                    self.assertIn('IMAGE-UPDATE 0',self.trace)
                    self.assertIn('SOURCE-CLOSE 0',self.trace)
                    self.assertEqual(note,'The image is read-only.')

    def test_image_write_permission_does_not_require_destroy_permission(self):
        self.give('NEWFILE',b'new bytes'*80)
        for access in (3,0x43,0xC3):
            with self.subTest(access=access):
                self.img.write_bytes(self.original)
                writes,note=self.run_op(35,access)
                self.assertGreater(writes,0)
                self.assertIn('1 put',note)
                self.assertEqual(self.contents('ALREADY'),KEEP[2])
                self.assertEqual(self.contents('NEWFILE'),self.files['NEWFILE'])
                self.assertEqual((self.src/'NEWFILE').read_bytes(),self.files['NEWFILE'])

    def test_case_variant_self_image_does_not_stop_other_imports(self):
        self.img=self.src/'VOL.PO'
        self.give('DATA',bytes(range(256))*3,5)
        for mode in (32,33):
            with self.subTest(mode=mode):
                self.img.write_bytes(self.original)
                writes,note=self.run_op(mode)
                self.assertGreater(writes,0)
                self.assertEqual(note,'1 put, 1 skipped (name taken or empty).')
                self.assertEqual(sorted(e['name'] for e in self.volume()['files']),
                                 ['ALREADY','DATA'])
                self.assertEqual(self.contents('ALREADY'),KEEP[2])
                self.assertEqual(self.contents('DATA'),self.files['DATA'])
                self.assertEqual((self.src/'DATA').read_bytes(),self.files['DATA'])

    def test_files_land_in_the_volume_with_their_bytes(self):
        self.give('HELLO', b'hello, pascal\r' * 40, 3)
        self.give('DATA', bytes(range(256)) * 5, 5)
        writes, note = self.run_op()
        self.assertIn('2 put', note)
        v = self.volume()
        self.assertEqual(sorted(f['name'] for f in v['files']),
                         ['ALREADY', 'DATA', 'HELLO'])
        for name in ('HELLO', 'DATA'):
            self.assertEqual(self.contents(name), self.files[name], name)

    def test_the_date_comes_across_from_the_prodos_entry(self):
        """ProDOS keeps year 9-15, month 5-8, day 0-4; UCSD keeps year in
        the same place but day 4-8 and month 0-3. A month of zero would
        mean no date at all, which is what a zero word used to write."""
        self.give('DATED', b'x' * 600)
        self.run_op()
        e = next(f for f in self.volume()['files'] if f['name'] == 'DATED')
        self.assertEqual(e['date'], (26, 9, 19), e)

    def test_the_kind_is_the_inverse_of_what_the_reader_gives(self):
        for type_, kind in ((0x02, 2), (0x03, 3), (0x05, 5), (0x04, 0), (0xFF, 0)):
            with self.subTest(type=type_):
                self.setUp()
                self.give('F', b'x' * 600, type_)
                self.run_op()
                e = next(f for f in self.volume()['files'] if f['name'] == 'F')
                self.assertEqual(e['kind'], kind)

    def test_files_are_placed_after_the_last_one_and_do_not_overlap(self):
        self.give('ONE', b'1' * 700)
        self.give('TWO', b'2' * 700)
        self.run_op()
        v = self.volume()
        runs = sorted((f['first'], f['last']) for f in v['files'])
        for (f1, l1), (f2, _) in zip(runs, runs[1:]):
            self.assertLessEqual(l1, f2, runs)

    def test_the_containers_that_move_the_blocks_around(self):
        """A .DSK stores the halves of every block in DOS sector order and a
        .2MG puts a header in front of the volume. The Asimov Pascal disks
        are .do files, so the DOS order is the real case, not the exotic
        one -- and nothing exercised either path for writing."""
        for suffix, wrap, unwrap in (
                ('.DSK', to_dsk, to_dsk),          # the order is its own inverse
                ('.2MG', to_2mg, lambda d: d[int.from_bytes(d[24:26], 'little'):])):
            with self.subTest(suffix=suffix):
                self.setUp()
                img = self.dir / ('VOL' + suffix)
                img.write_bytes(wrap(self.original))
                self.give('NEW', b'new bytes\r' * 30)
                out = subprocess.check_output(
                    [str(self.exe), str(img), str(self.src), '0', '1', '0'],
                    text=True).strip()
                self.assertIn('1 put', out)
                raw = unwrap(img.read_bytes())
                v = pascal_ref.volume(raw)
                self.assertIsNotNone(v, out)
                e = next(f for f in v['files'] if f['name'] == 'NEW')
                self.assertEqual(pascal_ref.contents(raw, e), b'new bytes\r' * 30)

    # -- what must not ------------------------------------------------------

    def test_a_name_already_in_the_volume_is_skipped(self):
        self.give('ALREADY', b'different bytes entirely\r' * 3)
        writes, note = self.run_op()
        self.assertIn('0 put', note)
        self.assertEqual(self.contents('ALREADY'), KEEP[2])
        self.assertEqual(self.img.read_bytes(), self.original)

    def test_an_empty_file_is_skipped_not_written(self):
        self.give('EMPTY', b'')
        writes, note = self.run_op()
        self.assertIn('0 put', note)
        self.assertEqual(self.img.read_bytes(), self.original)

    def test_answering_no_writes_nothing(self):
        self.give('HELLO', b'x' * 600)
        writes, note = self.run_op(mode=1)
        self.assertEqual(writes, 0, note)
        self.assertEqual(self.img.read_bytes(), self.original)

    def test_the_wrong_panel_is_refused(self):
        self.give('HELLO', b'x' * 600)
        writes, note = self.run_op(wrong=1)
        self.assertEqual(writes, 0, note)
        self.assertIn('ProDOS directory', note)

    def test_a_volume_without_room_is_refused_and_untouched(self):
        big = ('FILL', 0, bytes(270 * 512))
        self.original = pascal_ref.make('MYVOL', [big])
        self.img.write_bytes(self.original)
        self.give('HELLO', b'x' * 5000)
        writes, note = self.run_op()
        self.assertIn('No room', note)
        self.assertEqual(self.img.read_bytes(), self.original)

    def test_a_write_protected_2mg_is_refused_untouched(self):
        """Bit 31 of the 2IMG flags (header byte 19, $80) says the disk is
        write protected. Measured before image_open looked at it: "1 put",
        and the volume inside changed."""
        image = bytearray(to_2mg(self.original))
        image[0x13] |= 0x80
        self.img = self.dir / 'VOL.2MG'
        self.img.write_bytes(bytes(image))
        self.give('HELLO', b'x' * 600)
        writes, note = self.run_op()
        self.assertIn('read-only', note)
        self.assertEqual(writes, 0, note)
        self.assertEqual(self.img.read_bytes(), bytes(image))
        image[0x13] &= 0x7F                        # the same container, unlocked
        self.img.write_bytes(bytes(image))
        writes, note = self.run_op()
        self.assertIn('1 put', note)

    def test_the_image_itself_is_never_copied_into_itself(self):
        (self.src / 'VOL.PO').write_bytes(self.img.read_bytes())
        out = subprocess.check_output(
            [str(self.exe), str(self.src / 'VOL.PO'), str(self.src), '0', '1', '0'],
            text=True).strip()
        v = pascal_ref.volume((self.src / 'VOL.PO').read_bytes())
        self.assertEqual([f['name'] for f in v['files']], ['ALREADY'], out)

    def test_a_failure_before_the_count_leaves_the_volume_as_it_was(self):
        """Data blocks land past the last file and the entry sits past the
        count, so every write before the count is invisible."""
        self.give('HELLO', b'h' * 900)
        for mode in (2, 3, 4):
            for at in range(1, 5):
                with self.subTest(mode=mode, at=at):
                    self.img.write_bytes(self.original)
                    writes, note = self.run_op(mode=mode, at=at)
                    v = self.volume()
                    self.assertIsNotNone(v, (mode, at, note))
                    names = [f['name'] for f in v['files']]
                    if 'HELLO' in names:
                        self.assertEqual(self.contents('HELLO'), self.files['HELLO'])
                    else:
                        self.assertEqual(names, ['ALREADY'])
                    self.assertEqual(self.contents('ALREADY'), KEEP[2])


HEAD = Path(os.environ.get('CC65_HEAD', str(Path.home() / 'opt/cc65-head')))
SOURCE = (ROOT / 'src/plugins/pascalw.c').read_text()


def room_source():
    """A program around the shipped room test, lifted out of pascalw.c as it
    is written."""
    i = SOURCE.index('static unsigned char fits(unsigned int blocks)')
    return ROOM % SOURCE[i:SOURCE.index('\n}\n', i) + 3]


ROOM = r'''
#include <stdio.h>
#include <stdlib.h>
static unsigned int tail, vblocks;
%s
/* The test it replaced, kept to show what the machine makes of it. */
static unsigned char sum_refuses(unsigned int blocks) { return tail + blocks > vblocks; }
int main(int argc, char** argv) {
    unsigned int blocks;
    (void)argc;
    tail = (unsigned int)atol(argv[1]);
    blocks = (unsigned int)atol(argv[2]);
    vblocks = (unsigned int)atol(argv[3]);
    printf("%%u %%u\n", fits(blocks), sum_refuses(blocks));
    return 0;
}
'''

# (tail, blocks, vblocks) -> does it fit
ROOM_CASES = [
    ((6, 1, 280), 1), ((6, 274, 280), 1), ((6, 275, 280), 0),
    ((279, 1, 280), 1), ((280, 1, 280), 0), ((280, 0, 280), 1),
    ((65530, 5, 65535), 1), ((65530, 6, 65535), 0),
    # the sums that pass 65,535 and come back small
    ((65530, 10, 65535), 0), ((65000, 600, 65000), 0), ((65535, 1, 65535), 0),
    ((40000, 32768, 65535), 0), ((32768, 32768, 65535), 0), ((1, 65535, 65535), 0),
]


def toolchains():
    found = []
    if shutil.which('cl65') and shutil.which('sim65'):
        found.append(('sim65c02', shutil.which('cl65'), shutil.which('sim65'), {}))
    if (HEAD / 'bin/cl65').exists():
        found.append(('sim6502', str(HEAD / 'bin/cl65'), str(HEAD / 'bin/sim65'),
                      {'CC65_HOME': str(HEAD / 'share/cc65')}))
    return found


class RoomOnTheMachine(unittest.TestCase):
    """`tail + blocks > vblocks` is sixteen bits wide where it runs.

    The host harness above builds PASCALW with clang, whose unsigned is 32
    bits: there the sum never wraps and the old test was right. Compiled by
    cc65 it wraps -- measured under sim65: a tail of 65,530 and 10 blocks
    make 4, not more than 65,535, so the room was "there" and the data loop
    wrote from the tail onwards until source_write refused block 65,535
    (the last block an image can have is 65,534, which is also why the
    wrap never reached blocks 0 to 5). This runs the shipped fits(), as
    each edition's compiler builds it."""

    def test_directory_close_status_survives_the_frozen_void_api(self):
        expression='((unsigned char (*)(void))a.dir_close)()'
        self.assertIn(expression,SOURCE)
        self.assertIn(expression,(ROOT/'src/plugins/cpmw.c').read_text())
        self.assertIn(expression,(ROOT/'src/plugins/imageio.h').read_text())
        chains=toolchains()
        if not chains:self.skipTest('no cc65 toolchain')
        source='''#include <stdio.h>
#include <stdlib.h>
static struct { void (*dir_close)(void); } a;
static unsigned char status;
static unsigned char resident_close(void){return status;}
int main(int argc,char** argv){
 (void)argc;status=(unsigned char)atoi(argv[1]);
 a.dir_close=(void (*)(void))resident_close;
 printf("%%u\\n",(unsigned)%s);return 0;
}
''' % expression
        with tempfile.TemporaryDirectory(prefix='pascalw-dir-close-') as d:
            p=Path(d);(p/'close.c').write_text(source)
            for cpu,cl65,sim65,env in chains:
                env={**os.environ,**env};exe=p/cpu
                subprocess.run([cl65,'-t',cpu,'-O','-Oirs','-Cl','-o',str(exe),str(p/'close.c')],
                               check=True,env=env,capture_output=True)
                for status in (0,1,0x27):
                    with self.subTest(cpu=cpu,status=status):
                        result=subprocess.check_output([sim65,str(exe),str(status)],
                                                       text=True,env=env,timeout=10)
                        self.assertEqual(int(result),status)

    def test_the_room_is_counted_without_wrapping(self):
        chains = toolchains()
        if not chains:
            self.skipTest('no cc65 toolchain')
        with tempfile.TemporaryDirectory(prefix='pascalw-room-') as d:
            p = Path(d)
            (p / 'room.c').write_text(room_source())
            for cpu, cl65, sim65, env in chains:
                env = {**os.environ, **env}
                exe = p / f'room-{cpu}'
                subprocess.run([cl65, '-t', cpu, '-O', '-Oirs', '-Cl', '-o', str(exe),
                                str(p / 'room.c')], check=True, env=env, capture_output=True)
                wrapped = 0
                for args, expected in ROOM_CASES:
                    with self.subTest(cpu=cpu, case=args):
                        out = subprocess.check_output([sim65, str(exe), *map(str, args)],
                                                      text=True, env=env, timeout=10)
                        fits, sum_refuses = (int(w) for w in out.split())
                        self.assertEqual(fits, expected)
                        wrapped += sum_refuses == fits      # the old test, saying yes to a no
                # the trap is real on this compiler: the sum accepted what does not fit
                self.assertGreaterEqual(wrapped, 5, cpu)


if __name__ == '__main__':
    unittest.main()
