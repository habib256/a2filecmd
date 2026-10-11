"""Execute the shipped CPMW C: ProDOS files written into an Apple II CP/M
volume, on disposable images only, and through I/O faults.

The volume is built and read back by tools/cpm_ref.py, which knows nothing
of the overlay.

Two things matter here and nowhere else. A CP/M sector is HALF a ProDOS
block, so every write is a read-modify-write and the other half belongs to
someone else -- a test writes a file next to another and checks the
neighbour survived. And CP/M has no bitmap: what is in use is whatever the
live directory entries claim. A reported failure restores the full shared
block and preserves existing entries; physical writes are not atomic on a cut.
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import cpm_ref
from po22mg import to_2mg
from po2dsk import to_dsk

ROOT = Path(__file__).resolve().parents[1]

C = r'''
#define __fastcall__
#define PLUGIN_HOST
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
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
#include "src/plugins/cpmw.c"
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
static int source_reads,source_closes,image_reads,image_seeks,image_closes;
static int h_error(FILE* f){return f==flagged || ferror(f);}
static void h_clear(FILE* f){if(f==flagged)flagged=NULL;clearerr(f);}
static FILE* h_open(const char* p,const char* m){
    if(!strcmp(p,img_path) && !strcmp(m,"r+b"))++image_updates;
    FILE* f=fopen(p,m);
    if(f && strcmp(p,img_path)){source_stream=f;source_reads=0;}
    else if(f)image_stream=f;
    return f;
}
static size_t h_read(void* p,size_t s,size_t n,FILE* f){
    size_t result=fread(p,s,n,f);
    if(f==image_stream && (mode==28 || mode==30)){
        ++image_reads;
        if((mode==28 && image_reads==fail_at) || (mode==30 && image_reads>=fail_at))flagged=f;
    }
    if(f==image_stream && mode==27 && writes>fail_at)return 0;
    if(f==image_stream && (mode==23 || mode==25) && ++image_reads==fail_at)return 0;
    if(f==source_stream){
        ++source_reads;
        if((mode==5 && source_reads==fail_at) || (mode==6 && n==1) ||
           (mode==19 && source_reads==1))flagged=f;
    }
    return result;
}
static int h_seek(FILE* f,long off,int whence){
    if(f==image_stream && mode==24 && ++image_seeks==fail_at)return -1;
    return fseek(f,off,whence);
}
static int h_close(FILE* f){
    int failed=0,result;
    if(f==image_stream){
        ++image_closes;image_stream=NULL;
        if(mode==16 || mode==18 || mode==19 || mode==25)failed=1;
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
    if(mode==33 && !(fail_at&2))return 0; /* ProDOS rejects WRITE, not OPEN. */
    if((mode==29 && writes==fail_at) || (mode==31 && writes>=fail_at))flagged=f;
    if((mode==2 || mode==3 || mode==4 || mode==26 || mode==27) && writes==fail_at){
        unsigned char before[512];unsigned int i;long off=ftell(f);
        fread(before,1,512,f);fseek(f,off,SEEK_SET);
        fprintf(stderr,"BEFORE %ld ",off);
        for(i=0;i<512;++i)fprintf(stderr,"%02x",before[i]);
        fprintf(stderr,"\n");
    }
    if(mode==26 && writes>fail_at)return 0;
    if (mode == 2 && writes == fail_at) return 0;
    if (mode == 3 && writes == fail_at) { fwrite(p, 1, 128, f); fflush(f); return 0; }
    if ((mode == 4 || mode==26 || mode==27) && writes == fail_at) {
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
    de.access=(mode==33 && !strcmp(path,img_path))?fail_at:0xE3;
    de.aux = 0;
    de.size = 0;
    f = fopen(path, "rb");
    if (f) { fseek(f, 0, SEEK_END); de.size = ftell(f); fclose(f); }
    if(!strcmp(de.name,"NEWFILE")){
        if(mode==9 && de.size)--de.size;
        if(mode==10)++de.size;
    }
    ++nat;
    return 1;
}
static unsigned char h_dir_close(void) {
    if(mode==32 && strcmp(open_dir,dir_path))return fail_at;
    return listing_error || (mode==22 && !strcmp(open_dir,dir_path) && source_passes==fail_at);
}

int main(int argc, char** argv) {
    struct A2fcApi api;
    memset(&api, 0, sizeof api);
    strcpy(img_path, argv[1]);
    strcpy(dir_path, argv[2]);
    mode = atoi(argv[3]); fail_at = atoi(argv[4]);
    strcpy(full_path, img_path);
    { const char* s = strrchr(img_path, '/'); strcpy(sel.name, s ? s + 1 : img_path); }
    sel.type = 6;sel.access=(mode==33 && (fail_at&2))?1:0xE3;
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
    api.fclose = h_close; api.fseek = h_seek;
    api.confirm = h_confirm; api.message = h_message; api.progress_bar = h_progress;
    plugin_entry(&api);
    fprintf(stderr,"SOURCE-PASSES %d\n",source_passes);
    fprintf(stderr,"SOURCE-CLOSE %d\n",source_closes);
    fprintf(stderr,"IMAGE-CLOSE %d\n",image_closes);
    fprintf(stderr,"IMAGE-UPDATE %d\n",image_updates);
    printf("%d %s\n", writes, note_text);
    return 0;
}
'''

WAS_THERE = [('KEEP.TXT', b'this one was in the volume\r\n' * 30),
             ('OTHER.COM', bytes(range(256)) * 3)]


class CpmW(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='cw-build-')
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
        self.case = tempfile.TemporaryDirectory(prefix='cw', dir='/tmp')
        self.addCleanup(self.case.cleanup)
        self.dir = Path(self.case.name)
        self.img = self.dir / 'VOL.PO'
        self.original = cpm_ref.make(WAS_THERE, skew='apple')
        self.img.write_bytes(self.original)
        self.src = self.dir / 'src'
        self.src.mkdir()
        self.files = {}

    def give(self, name, data):
        self.files[name] = data
        (self.src / name).write_bytes(data)

    def run_op(self, mode=0, at=1, wrong=0):
        run = subprocess.run(
            [str(self.exe), str(self.img), str(self.src), str(mode), str(at), str(wrong)],
            text=True, capture_output=True, check=True)
        out = run.stdout.strip()
        self.trace = run.stderr.splitlines()
        n, _, note = out.partition(' ')
        return int(n), note

    def volume(self):
        return cpm_ref.volume(self.img.read_bytes())

    def contents(self, name):
        raw = self.img.read_bytes()
        v = cpm_ref.volume(raw)
        e = next(f for f in v['files'] if f['name'] == name)
        return cpm_ref.contents(raw, e, v['skew'])

    # -- what must happen ---------------------------------------------------

    def test_every_file_shows_its_name_then_its_blocks(self):
        # `name` is one buffer for every file: 0 redraws it, so the bar
        # names each file -- a skipped one too -- then fills to the end.
        self.give('HELLO.TXT', b'hello, CP/M\r\n' * 100)      # 1,400 bytes: 2 blocks
        self.give('EMPTY', b'')                                  # skipped
        writes, note = self.run_op()
        self.assertIn('1 put', note)
        bars = [tuple(l.split()[1:]) for l in self.trace if l.startswith('BAR ')]
        self.assertEqual(sorted(set(bars)), sorted({('EMPTY', '0', '1'), ('HELLO.TXT', '0', '1'),
                                                    ('HELLO.TXT', '1', '2'), ('HELLO.TXT', '2', '2')}))

    def test_source_listing_errors_stop_and_keep_previously_imported_files(self):
        self.give('ALPHA',b'A'*300);self.give('ZULU',b'Z'*300)
        sources={p.name:p.read_bytes() for p in self.src.iterdir()}
        old=cpm_ref.volume(self.original)
        existing={e['name']:cpm_ref.contents(self.original,e,old['skew']) for e in old['files']}
        for mode in (21,22):
            for at in (1,2,3):
                with self.subTest(mode=mode,at=at):
                    self.img.write_bytes(self.original)
                    writes,note=self.run_op(mode,at)
                    volume=self.volume();data=self.img.read_bytes()
                    self.assertEqual(len(volume['files']),len(existing)+at-1)
                    for e in volume['files']:
                        expected=existing.get(e['name'])
                        if expected is None:expected=sources[e['name']].ljust(384,b'\x1a')
                        self.assertEqual(cpm_ref.contents(data,e,volume['skew']),expected)
                    self.assertEqual({p.name:p.read_bytes() for p in self.src.iterdir()},sources)
                    self.assertIn(f'SOURCE-PASSES {at}',self.trace)
                    if at==1:
                        self.assertEqual(writes,0)
                        self.assertEqual(data,self.original)
                    self.assertEqual(note,'Cannot read the other panel.')

    def test_source_errors_and_stale_sizes_never_publish_the_file(self):
        self.give('NEWFILE',bytes(range(256))*4)
        sources={p.name:p.read_bytes() for p in self.src.iterdir()}
        old=cpm_ref.volume(self.original)
        directory=cpm_ref.directory_of(self.original,cpm_ref.SKEWS[old['skew']])
        existing={e['name']:cpm_ref.contents(self.original,e,old['skew']) for e in old['files']}
        for mode,at in ((5,1),(5,4),(6,1),(7,1),(8,1),(9,1),(10,1)):
            with self.subTest(mode=mode,at=at):
                self.img.write_bytes(self.original)
                writes,note=self.run_op(mode,at)
                raw=self.img.read_bytes();volume=self.volume()
                self.assertEqual({e['name']:cpm_ref.contents(raw,e,volume['skew'])
                                  for e in volume['files']},existing)
                self.assertEqual(cpm_ref.directory_of(raw,cpm_ref.SKEWS[old['skew']]),directory)
                self.assertEqual({p.name:p.read_bytes() for p in self.src.iterdir()},sources)
                self.assertIn('SOURCE-CLOSE 1',self.trace)
                self.assertNotIn('1 put',note)
                if mode==5 and at==1:
                    self.assertEqual(writes,0)
                    self.assertEqual(raw,self.original)
                self.assertEqual(note,'Stopped; the volume is whole.' if mode==8
                                 else 'Cannot read a file opposite.')

    def test_name_survey_read_and_seek_errors_stop_without_a_collision(self):
        self.give('NEWFILE',b'new contents');self.give('LATER',b'must not be imported')
        sources={p.name:p.read_bytes() for p in self.src.iterdir()}
        # Two eight-sector validations precede the first name survey.
        for mode in (23,24):
            for at in range(17,25):
                with self.subTest(mode=mode,at=at):
                    self.img.write_bytes(self.original)
                    writes,note=self.run_op(mode,at)
                    self.assertEqual(writes,0)
                    self.assertEqual(self.img.read_bytes(),self.original)
                    self.assertEqual({p.name:p.read_bytes() for p in self.src.iterdir()},sources)
                    self.assertIn('SOURCE-CLOSE 0',self.trace)
                    self.assertIn('SOURCE-PASSES 1',self.trace)
                    self.assertEqual(note,'Cannot read the CP/M directory.')

    def test_final_image_close_failure_or_cancel_keeps_published_files(self):
        old=cpm_ref.volume(self.original)
        existing={e['name']:cpm_ref.contents(self.original,e,old['skew']) for e in old['files']}
        for with_source,mode in ([(s,m) for s in (False,True) for m in (16,17,18)]+
                                 [(True,19),(True,25)]):
            with self.subTest(with_source=with_source,mode=mode):
                self.img.write_bytes(self.original)
                for p in self.src.iterdir():p.unlink()
                if with_source:self.give('NEWFILE',bytes(range(256))*4)
                sources={p.name:p.read_bytes() for p in self.src.iterdir()}
                writes,note=self.run_op(mode,17 if mode==25 else 1)
                raw=self.img.read_bytes();volume=self.volume()
                expected=dict(existing)
                if with_source and mode in (16,17,18):expected['NEWFILE']=sources['NEWFILE']
                self.assertEqual({e['name']:cpm_ref.contents(raw,e,volume['skew'])
                                  for e in volume['files']},expected)
                self.assertEqual({p.name:p.read_bytes() for p in self.src.iterdir()},sources)
                self.assertIn('IMAGE-CLOSE 1',self.trace)
                self.assertIn(f'SOURCE-CLOSE {int(with_source and mode!=25)}',self.trace)
                if not with_source or mode==25:
                    self.assertEqual(writes,0)
                    self.assertEqual(raw,self.original)
                self.assertEqual(note,'Stopped; imported files kept.' if mode==17
                                 else 'Image close failed; check the volume.')

    def test_failed_sector_write_restores_the_entire_shared_block(self):
        self.give('NEWFILE',bytes(range(256))*4)
        sources={p.name:p.read_bytes() for p in self.src.iterdir()}
        old=cpm_ref.volume(self.original)
        directory=cpm_ref.directory_of(self.original,cpm_ref.SKEWS[old['skew']])
        existing={e['name']:cpm_ref.contents(self.original,e,old['skew']) for e in old['files']}
        for mode in (2,3,4):
            for at in range(1,6):
                with self.subTest(mode=mode,at=at):
                    self.img.write_bytes(self.original)
                    writes,note=self.run_op(mode,at)
                    before=next(l.split() for l in self.trace if l.startswith('BEFORE '))
                    off=int(before[1]);raw=self.img.read_bytes()
                    self.assertEqual(raw[off:off+512],bytes.fromhex(before[2]))
                    self.assertEqual(cpm_ref.directory_of(raw,cpm_ref.SKEWS[old['skew']]),directory)
                    volume=self.volume()
                    self.assertEqual({e['name']:cpm_ref.contents(raw,e,volume['skew'])
                                      for e in volume['files']},existing)
                    self.assertEqual({p.name:p.read_bytes() for p in self.src.iterdir()},sources)
                    self.assertEqual(note,'Entry not written; the volume is whole.' if at==5
                                     else 'Write failed; the volume is whole.')

    def test_failed_restoration_is_reported_without_claiming_the_volume_whole(self):
        self.give('NEWFILE',bytes(range(256))*4)
        sources={p.name:p.read_bytes() for p in self.src.iterdir()}
        for mode in (26,27):
            for at in (1,5):
                with self.subTest(mode=mode,at=at):
                    self.img.write_bytes(self.original)
                    writes,note=self.run_op(mode,at)
                    self.assertGreater(writes,at)
                    self.assertIn('check the volume',note)
                    self.assertNotIn('whole',note)
                    self.assertEqual({p.name:p.read_bytes() for p in self.src.iterdir()},sources)
                    if mode==27:
                        before=next(l.split() for l in self.trace if l.startswith('BEFORE '))
                        off=int(before[1])
                        self.assertEqual(self.img.read_bytes()[off:off+512],bytes.fromhex(before[2]))

    def test_directory_restoration_in_dos_and_2mg_containers(self):
        self.give('NEWFILE',bytes(range(256))*4)
        old=cpm_ref.volume(self.original)
        directory=cpm_ref.directory_of(self.original,cpm_ref.SKEWS[old['skew']])
        for suffix,wrap,unwrap,at in (('.2MG',to_2mg,lambda d:d[64:],5),
                                      ('.DSK',to_dsk,to_dsk,9),('.DSK',to_dsk,to_dsk,10)):
            with self.subTest(suffix=suffix,at=at):
                self.img=self.dir/('VOL'+suffix);self.img.write_bytes(wrap(self.original))
                writes,note=self.run_op(4,at)
                raw=unwrap(self.img.read_bytes())
                self.assertEqual(cpm_ref.directory_of(raw,cpm_ref.SKEWS[old['skew']]),directory)
                volume=cpm_ref.volume(raw)
                for e in old['files']:
                    actual=next(f for f in volume['files'] if f['name']==e['name'])
                    self.assertEqual(cpm_ref.contents(raw,actual,volume['skew']),
                                     cpm_ref.contents(self.original,e,old['skew']))
                self.assertEqual(len(volume['files']),len(old['files']))
                self.assertEqual((self.src/'NEWFILE').read_bytes(),bytes(range(256))*4)
                self.assertEqual(note,'Entry not written; the volume is whole.')

    def test_full_count_image_errors_never_validate_or_publish(self):
        self.give('NEWFILE',bytes(range(256))*4)
        old=cpm_ref.volume(self.original)
        directory=cpm_ref.directory_of(self.original,cpm_ref.SKEWS[old['skew']])
        existing={e['name']:cpm_ref.contents(self.original,e,old['skew']) for e in old['files']}
        sources={p.name:p.read_bytes() for p in self.src.iterdir()}
        # 16 validation reads, 8 survey reads, 8 data backup/verify reads,
        # then 3 reads to load, save and verify the publication block.
        cases=[(28,at) for at in range(1,36)]+[(29,at) for at in range(1,6)]
        cases += [(30,35),(31,5)]
        for mode,at in cases:
            with self.subTest(mode=mode,at=at):
                self.img.write_bytes(self.original)
                writes,note=self.run_op(mode,at)
                raw=self.img.read_bytes();volume=self.volume()
                self.assertEqual(cpm_ref.directory_of(raw,cpm_ref.SKEWS[old['skew']]),directory)
                self.assertEqual({e['name']:cpm_ref.contents(raw,e,volume['skew'])
                                  for e in volume['files']},existing)
                self.assertEqual({p.name:p.read_bytes() for p in self.src.iterdir()},sources)
                self.assertNotIn('1 put',note)
                if mode==28 and at<=25:
                    self.assertEqual(writes,0)
                    self.assertEqual(raw,self.original)
                if mode in (30,31):
                    self.assertIn('check the volume',note)
                    self.assertNotIn('whole',note)

    def test_container_full_count_read_errors_refuse_every_write(self):
        self.give('NEWFILE',b'new contents')
        for suffix,wrap,at in (('.2MG',to_2mg,1),('.DSK',to_dsk,1),('.DSK',to_dsk,2)):
            with self.subTest(suffix=suffix,at=at):
                self.img=self.dir/('VOL'+suffix)
                original=wrap(self.original);self.img.write_bytes(original)
                writes,note=self.run_op(28,at)
                self.assertEqual(writes,0)
                self.assertEqual(self.img.read_bytes(),original)
                self.assertEqual((self.src/'NEWFILE').read_bytes(),b'new contents')
                self.assertIn('SOURCE-CLOSE 0',self.trace)
                self.assertIn('IMAGE-CLOSE 1',self.trace)
                self.assertNotIn('1 put',note)

    def test_files_land_in_the_volume_with_their_bytes(self):
        self.give('HELLO.TXT', b'hello, CP/M\r\n' * 40)
        self.give('TINY.COM', b'\xc9' * 300)
        writes, note = self.run_op()
        self.assertIn('2 put', note)
        v = self.volume()
        self.assertEqual(sorted(f['name'] for f in v['files']),
                         ['HELLO.TXT', 'KEEP.TXT', 'OTHER.COM', 'TINY.COM'])
        for name in ('HELLO.TXT', 'TINY.COM'):
            got = self.contents(name)
            self.assertEqual(got[:len(self.files[name])], self.files[name], name)
            self.assertTrue(set(got[len(self.files[name]):]) <= {0x1A}, name)

    def test_the_neighbour_sharing_a_prodos_block_survives(self):
        """A CP/M sector is half a ProDOS block: every write is a
        read-modify-write, and losing the other half would eat a file that
        has nothing to do with this one."""
        self.give('NEW.DAT', b'N' * 2000)
        self.run_op()
        for name, data in WAS_THERE:
            self.assertEqual(self.contents(name)[:len(data)], data, name)

    def test_the_blocks_it_took_belong_to_it_alone(self):
        self.give('ONE.DAT', b'1' * 1500)
        self.give('TWO.DAT', b'2' * 1500)
        self.run_op()
        v = self.volume()
        seen = set()
        for f in v['files']:
            for b in f['blocks']:
                self.assertNotIn(b, seen, (f['name'], b))
                seen.add(b)

    def test_a_dos_order_container_writes_the_same(self):
        """CP/M has a skew of its own on top of the container's order, so
        the two undo each other here and nowhere else. Nothing exercised a
        DOS-order container for writing."""
        img = self.dir / 'VOL.DSK'
        img.write_bytes(to_dsk(self.original))     # the order is its own inverse
        self.give('NEW.TXT', b'new bytes\r\n' * 30)
        out = subprocess.check_output(
            [str(self.exe), str(img), str(self.src), '0', '1', '0'], text=True).strip()
        self.assertIn('1 put', out)
        raw = to_dsk(img.read_bytes())
        v = cpm_ref.volume(raw)
        self.assertIsNotNone(v, out)
        e = next(f for f in v['files'] if f['name'] == 'NEW.TXT')
        self.assertEqual(cpm_ref.contents(raw, e, v['skew'])[:330], b'new bytes\r\n' * 30)

    # -- what must not ------------------------------------------------------

    def test_a_write_protected_2mg_is_refused_untouched(self):
        """Bit 31 of the 2IMG flags (header byte 19, $80) says the disk is
        write protected. Measured before image_open looked at it: "1 put",
        and the volume inside changed."""
        image = bytearray(to_2mg(self.original))
        image[0x13] |= 0x80
        self.img = self.dir / 'VOL.2MG'
        self.img.write_bytes(bytes(image))
        self.give('NEW.TXT', b'new bytes\r\n' * 30)
        writes, note = self.run_op()
        self.assertIn('read-only', note)
        self.assertEqual(writes, 0, note)
        self.assertEqual(self.img.read_bytes(), bytes(image))
        image[0x13] &= 0x7F                        # the same container, unlocked
        self.img.write_bytes(bytes(image))
        writes, note = self.run_op()
        self.assertIn('1 put', note)
        raw = self.img.read_bytes()[64:]
        v = cpm_ref.volume(raw)
        e = next(f for f in v['files'] if f['name'] == 'NEW.TXT')
        self.assertEqual(cpm_ref.contents(raw, e, v['skew'])[:330], b'new bytes\r\n' * 30)

    def test_image_metadata_close_error_refuses_before_open_or_write(self):
        self.give('NEW.TXT',b'new bytes'*80)
        for suffix,wrap in (('.PO',bytes),('.2MG',to_2mg),('.DSK',to_dsk)):
            for error in (1,27):
                with self.subTest(suffix=suffix,error=error):
                    self.img=self.dir/('VOL'+suffix)
                    original=wrap(self.original);self.img.write_bytes(original)
                    writes,note=self.run_op(32,error)
                    self.assertEqual(writes,0)
                    self.assertEqual(self.img.read_bytes(),original)
                    self.assertEqual((self.src/'NEW.TXT').read_bytes(),self.files['NEW.TXT'])
                    self.assertIn('SOURCE-CLOSE 0',self.trace)
                    self.assertIn('IMAGE-CLOSE 0',self.trace)
                    self.assertEqual(note,'Not a disk image this can open.')

    def test_fresh_image_write_protection_is_respected(self):
        self.give('NEW.TXT',b'new bytes'*80)
        for suffix,wrap in (('.PO',bytes),('.2MG',to_2mg),('.DSK',to_dsk)):
            for access in (1,0x21,0x41,0x81,0xC1):
                with self.subTest(suffix=suffix,access=access):
                    self.img=self.dir/('VOL'+suffix)
                    original=wrap(self.original);self.img.write_bytes(original)
                    writes,note=self.run_op(33,access)
                    self.assertEqual(writes,0)
                    self.assertEqual(self.img.read_bytes(),original)
                    self.assertEqual((self.src/'NEW.TXT').read_bytes(),self.files['NEW.TXT'])
                    self.assertIn('IMAGE-UPDATE 0',self.trace)
                    self.assertIn('SOURCE-CLOSE 0',self.trace)
                    self.assertEqual(note,'The image is read-only.')

    def test_image_write_permission_does_not_require_destroy_permission(self):
        self.give('NEW.TXT',b'new bytes'*80)
        for access in (3,0x43,0xC3):
            with self.subTest(access=access):
                self.img.write_bytes(self.original)
                writes,note=self.run_op(33,access)
                self.assertGreater(writes,0)
                self.assertIn('1 put',note)
                for name,data in self.files.items():
                    self.assertEqual((self.src/name).read_bytes(),data)
                raw=self.img.read_bytes();v=cpm_ref.volume(raw)
                for name,data in [('NEW.TXT',self.files['NEW.TXT'])]+WAS_THERE:
                    e=next(f for f in v['files'] if f['name']==name)
                    self.assertEqual(cpm_ref.contents(raw,e,v['skew'])[:len(data)],data)

    def test_a_name_already_there_is_skipped(self):
        self.give('KEEP.TXT', b'completely different bytes\r\n')
        writes, note = self.run_op()
        self.assertIn('0 put', note)
        self.assertEqual(self.contents('KEEP.TXT')[:len(WAS_THERE[0][1])], WAS_THERE[0][1])
        self.assertEqual(self.img.read_bytes(), self.original)

    def test_a_file_too_big_for_one_extent_is_skipped(self):
        self.give('BIG.DAT', b'B' * 20000)
        writes, note = self.run_op()
        self.assertIn('0 put', note)
        self.assertEqual(self.img.read_bytes(), self.original)

    def test_a_name_cp_m_cannot_carry_is_skipped(self):
        for name in ('TOOLONGNAME.TXT', 'A.B.C', 'WITH:COLON'):
            with self.subTest(name=name):
                self.setUp()
                self.give(name, b'x' * 300)
                writes, note = self.run_op()
                self.assertIn('0 put', note)
                self.assertEqual(self.img.read_bytes(), self.original)

    def test_answering_no_writes_nothing(self):
        self.give('HELLO.TXT', b'x' * 600)
        writes, note = self.run_op(mode=1)
        self.assertEqual(writes, 0, note)
        self.assertEqual(self.img.read_bytes(), self.original)

    def test_an_empty_volume_is_refused_because_the_skew_cannot_be_known(self):
        self.original = cpm_ref.make([], skew='apple')
        self.img.write_bytes(self.original)
        self.give('HELLO.TXT', b'x' * 600)
        writes, note = self.run_op()
        self.assertEqual(writes, 0, note)
        self.assertIn('Not a CP/M volume', note)
        self.assertEqual(self.img.read_bytes(), self.original)

    def test_a_failure_before_the_entry_leaves_the_volume_as_it_was(self):
        """The data goes into blocks no live entry claims, and CP/M has no
        bitmap: until the entry lands, nothing in the volume changed."""
        self.give('HELLO.TXT', b'h' * 1500)
        for mode in (2, 3, 4):
            for at in range(1, 8):
                with self.subTest(mode=mode, at=at):
                    self.img.write_bytes(self.original)
                    writes, note = self.run_op(mode=mode, at=at)
                    v = self.volume()
                    self.assertIsNotNone(v, (mode, at, note))
                    names = sorted(f['name'] for f in v['files'])
                    if 'HELLO.TXT' in names:
                        self.assertEqual(self.contents('HELLO.TXT')[:1500], b'h' * 1500)
                    else:
                        self.assertEqual(names, ['KEEP.TXT', 'OTHER.COM'])
                    for name, data in WAS_THERE:
                        self.assertEqual(self.contents(name)[:len(data)], data, name)


if __name__ == '__main__':
    unittest.main()
