"""UNWRAP's real entry point on the host, against tools/unwrap_ref.py.

The overlay (src/plugins/unwrap.c) runs with the ProDOS calls and the C
library of the host behind its service table. Every extraction is compared
with the reference: the name, the ProDOS type and auxiliary type given to
CREATE, the bytes written, the note. Refusals must leave the destination
directory as it was; a failed write or read-back removes what was created.
Real files from CiderPress II's test data are added when at hand.
"""
import os
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import unwrap_ref as ref  # noqa: E402
import cp2_samples  # noqa: E402
from test_six_plugins import PREFIX, ROOT  # noqa: E402

HARNESS = PREFIX + r'''
#include <errno.h>
#include <sys/stat.h>
static int error_(FILE*);
#define ferror error_
#include "src/plugins/unwrap.c"
#undef ferror
static int fault, writes, reads_out, extracting;
static unsigned int create_calls, parser_reads;
static unsigned long output_bytes;
static FILE *reading_back, *source, *read_error;
static int error_(FILE* f) { return f == read_error || ferror(f); }
static unsigned char mli_(unsigned char cmd, void* params)
{
    char p[80];
    FILE* f;
    unsigned char* pas = create.path;
    if (cmd != 0xC0) abort();
    ++create_calls;
    memcpy(p, pas + 1, pas[0]); p[pas[0]] = 0;
    if (fault == 1) return 0x27;
    f = fopen(p, "wx");
    if (!f) return 0x47;
    fclose(f);
    printf("CREATE %s %02X %04X\n", strrchr(p, '/') + 1, create.type, create.aux);
    return 0;
}
static FILE* writing;
static FILE* open_(const char* p, const char* m)
{
    FILE* f = fopen(p, m);
    if (!strcmp(m, "wb")) writing = f;
    if (fault == 4 && !strcmp(m, "rb") && strstr(p, "/D/")) { if (f) fclose(f); return NULL; }
    if (!strcmp(m, "rb")) {
        if (strstr(p, "/D/")) reading_back = f;
        else source = f;
    }
    return f;
}
static size_t write_(const void* p, size_t s, size_t n, FILE* f)
{
    output_bytes+=s*n;
    if ((fault == 2 || fault == 5) && ++writes == 2) return n - 1;
    if (fault == 3) { unsigned char c[512]; memcpy(c, p, n); c[n - 1] ^= 1; return fwrite(c, s, n, f); }
    return fwrite(p, s, n, f);
}
static int remove_(const char* p) { printf("REMOVE %s\n", strrchr(p, '/') + 1); return fault == 5 || fault == 15 || fault == 16 || fault == 25 || (fault>=35 && fault<=38) ? -1 : remove(p); }
static int close_(FILE* f)
{
    int fail = ((fault == 8 || fault == 16) && f == source) ||
               (fault == 9 && f == reading_back) ||
               (fault == 10 && f == writing);
    int r;
    if (fault == 6 && f == writing) fputc('!', f);          /* one byte too many */
    if(((fault==22 || fault==25) && f==writing) ||
       (fault==23 && f==reading_back) || (fault==24 && f==source))cancelled=1;
    r = fclose(f);
    if(f==writing)writing=0;if(f==reading_back)reading_back=0;if(f==source)source=0;
    return fail ? EOF : r;
}
static size_t read_(void* p, size_t s, size_t n, FILE* f) {
    if(fault>=31 && fault<=38 && f==source && writing) {
        unsigned char mode=(fault-31)%4;
        unsigned long pos=ftell(f);
        if((!(mode&1) && pos==off) || ((mode&1) && pos+n==off+len)) {
            if(mode<2)read_error=f;else cancelled=1;
        }
    }
    if(f==source && !extracting && n==512) {
        if(fault==17){read_error=f;return 0;}
        if(fault==18 && ftell(f)>=512)read_error=f;
        if(fault==19){read_error=f;return fread(p,s,n-1,f);}
        if(fault==21)cancelled=1;
    }
    if(f==source && n==128)extracting=1;
    if(f==source && extracting) {
        if(n!=128)++parser_reads;
        if((fault==26 && n==128) || (fault==27 && n==12) ||
           (fault==28 && n==8) ||
           (fault==29 && n==12 && (unsigned long)ftell(f)==26+12UL*(be16(hdr+24)-1)))cancelled=1;
        if(fault==30 && n==12){cancelled=1;return fread(p,s,n-1,f);}
    }
    if ((fault == 7 || fault == 15) && f == reading_back && n == 1 &&
        (unsigned long)ftell(f) == len) { read_error = f; return 0; }
    if (fault == 11 && f == source && extracting && n == 512) { read_error = f; return fread(p, s, n - 1, f); }
    if ((fault == 12 && f == source && extracting && n == 512) ||
        (fault == 13 && f == source && n == 128) ||
        (fault == 14 && f == reading_back && n > 1)) read_error = f;
    return fread(p, s, n, f);
}
static int seek_(FILE* f, long o, int w) {
    if(fault==20 && f==source && !o && w==SEEK_SET)return -1;
    return fseek(f, o, w);
}
static unsigned long bars, overflows;
static void bar_(const char* n, unsigned long d, unsigned long t) { ++bars; if (d > t || !*n) ++overflows; }
int main(int argc, char** argv)
{
    static struct A2fcApi api;
    static struct Panel panels[2];
    static struct Entry sel;
    static char full[80], note[120];
    static unsigned char active, copy[512];
    FILE* s;
    strcpy(panels[0].path, argv[1]);
    strcpy(panels[1].path, argv[2]);
    strcpy(sel.name, argv[3]);
    sel.type = strtol(argv[4], 0, 16);
    fault = atoi(argv[5]);
    sprintf(full, "%s/%s", argv[1], argv[3]);
    s = fopen(full, "rb"); fseek(s, 0, SEEK_END); sel.size = ftell(s); fclose(s);
    if(argc>6)sel.size=strtoul(argv[6],0,10);
    api.panels = panels; api.active = &active; api.selected = &sel; api.full = full;
    api.note = note; api.copy_buf = copy;
    api.memcpy = memcpy; api.memset = memset; api.strcpy = strcpy; api.strlen = strlen;
    api.sprintf = sprintf; api.fopen = open_; api.fread = read_; api.fwrite = write_;
    api.fseek = seek_; api.fclose = close_; api.remove = remove_; api.mli = mli_;
    api.progress_bar = bar_;
    plugin_entry(&api);
    printf("BARS %lu %lu\n", bars, overflows);
    printf("CALLS %u %u\n",create_calls,parser_reads);
    printf("WRITTEN %lu\n",output_bytes);
    printf("NOTE %s\n", note);
    return 0;
}
'''


class Unwrap(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='unwrap-', dir='/tmp')
        cls.root = Path(cls.tmp.name)
        (cls.root / 'test.c').write_text(HARNESS)
        cls.exe = cls.root / 'test'
        subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-I', str(ROOT),
                        str(cls.root / 'test.c'), '-o', str(cls.exe)], check=True,
                       capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_unwrap(self, name, data, fault=0, typ='06', existing=(), cached_size=None):
        case = Path(tempfile.mkdtemp(dir=self.root))
        (case / 'S').mkdir()
        (case / 'D').mkdir()
        (case / 'S' / name).write_bytes(data)
        for e in existing:
            (case / 'D' / e).write_bytes(b'old')
        args=[str(self.exe),str(case/'S'),str(case/'D'),name,typ,str(fault)]
        if cached_size is not None:args.append(str(cached_size))
        out = subprocess.run(args, capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        lines = out.stdout.splitlines()
        note = [l[5:] for l in lines if l.startswith('NOTE ')][0]
        created = [l.split()[1:] for l in lines if l.startswith('CREATE ')]
        removed = [l.split()[1] for l in lines if l.startswith('REMOVE ')]
        self.bars = [int(v) for l in lines if l.startswith('BARS ') for v in l.split()[1:]]
        self.creates,self.parser_reads=map(int,next(l[6:] for l in lines if l.startswith('CALLS ')).split())
        self.output_bytes=int(next(l[8:] for l in lines if l.startswith('WRITTEN ')))
        files = {p.name: p.read_bytes() for p in (case / 'D').iterdir()}
        self.assertEqual((case / 'S' / name).read_bytes(), data, 'the source is untouched')
        return note, created, removed, files

    def check(self, name, data, typ='06'):
        want = ref.unwrap(data, name)
        note, created, removed, files = self.run_unwrap(name, data, typ=typ)
        if want is None:
            self.assertEqual(note, 'Not an AppleSingle or MacBinary file.')
            self.assertEqual((created, files), ([], {}))
            return
        wname, t, a, fork, rsrc = want
        self.assertEqual(created, [[wname, '%02X' % t, '%04X' % a]])
        self.assertEqual(files, {wname: fork})
        self.assertEqual(note, '%s: %d bytes, $%02X/$%04X.%s' % (
            wname, len(fork), t, a, ' Resource fork left out.' if rsrc else ''))
        self.assertEqual(removed, [])

    def test_synthetic_files(self):
        rng = random.Random(1)
        types = [b'TEXTttxt', b'p\x06\x20\x00pdos', b'FC  pdos', b'PSYSpdos', b'PS16pdos',
                 b'dImgdCpy', b'AIFCxxxx', b'MIDIxxxx', b'APPLMSWD', b'Z1  pdos', b'p\x0f\x00\x00pdos']
        for i in range(60):
            fork = bytes(rng.randrange(256) for _ in range(rng.choice([0, 1, 511, 512, 513, 3000])))
            rsrc = b'r' * rng.choice([0, 5])
            raw = bytes(rng.choice(b'abcXYZ019 .-_:/\x8a') for _ in range(rng.randint(0, 40)))
            if i % 2:
                entries = [(1, fork)]
                if raw:
                    entries.insert(0, (3, raw))
                if rsrc:
                    entries.append((2, rsrc))
                k = rng.random()
                if k < 0.3:
                    entries.append((11, bytes([0, 0xC3, 0, rng.randrange(256), 0, 0,
                                                rng.randrange(256), rng.randrange(256)])))
                elif k < 0.6:
                    entries.append((9, rng.choice(types) + bytes(24)))
                rng.shuffle(entries)
                v = rng.choice([1, 2])
                data = ref.make_as(entries, version=v, home=b'ProDOS' if v == 1 else b'')
                if v == 1 and rng.random() < 0.5:
                    data = ref.make_as(entries + [(7, bytes(8) + bytes([0, 0xE3, 0, 0x2A, 0, 0, 0x12, 0x34]))],
                                       version=1, home=b'ProDOS')
                name = 'FILE%d.AS' % i
            else:
                data = ref.make_mb(raw or b'x', rng.choice(types), fork, rsrc,
                                   version=rng.choice([1, 2]))
                name = 'FILE%d.BIN' % i
            with self.subTest(i=i):
                self.check(name, data)

    def test_real_files(self):
        v = cp2_samples.volume()
        real = [v[k][2] for k in sorted(v) if k.startswith('/ARCHIVES/') and k.endswith('.AS')]
        self.assertEqual(len(real), 3, 'data/CP2/ARCHIVES holds three AppleSingle files')
        for n in ('as/badmac-utf8name.as', 'as/illegal-chars.as'):
            p = cp2_samples.path(n)
            if p:
                real.append(p.read_bytes())
        for i, data in enumerate(real):
            with self.subTest(i=i):
                self.check('SAMPLE.AS', data, typ='E0')

    def test_progress(self):
        # A big fork is tens of seconds of floppy I/O: the bar moves on
        # every block of the copy and of the read-back.
        fork = bytes(range(256)) * 40
        self.check('BIG.AS', ref.make_as([(3, b'Big'), (1, fork)]))
        self.assertEqual(self.bars, [2 * ((len(fork) + 511) // 512), 0])

    def test_current_source_length_replaces_stale_panel_size(self):
        for fork in (b'',b'hello'*300):
            for fmt in ('as','mb'):
                data=ref.make_as([(3,b'Doc'),(1,fork)]) if fmt=='as' else ref.make_mb(b'Doc',b'TEXTttxt',fork)
                for cached in (0,1,len(data)-1,len(data)+4096):
                    with self.subTest(fmt=fmt,length=len(fork),cached=cached):
                        note,created,removed,files=self.run_unwrap('X.AS',data,existing=['KEEP'],cached_size=cached)
                        self.assertEqual(files,{'KEEP':b'old','DOC':fork})
                        self.assertEqual(removed,[])

    def test_stale_large_size_cannot_validate_empty_fork_past_actual_eof(self):
        data=bytearray(ref.make_as([(3,b'Doc'),(1,b'')]))
        for off in (len(data)+1,len(data)+4096):
            with self.subTest(off=off):
                data[42:46]=off.to_bytes(4,'big')
                note,created,removed,files=self.run_unwrap('X.AS',bytes(data),existing=['KEEP'],cached_size=off+512)
                self.assertEqual((created,removed,files),([],[],{'KEEP':b'old'}))

    def test_length_scan_errors_and_cancel_create_nothing(self):
        data=ref.make_as([(3,b'Doc'),(1,b'hello'*300)])
        for fault in range(17,22):
            with self.subTest(fault=fault):
                note,created,removed,files=self.run_unwrap('X.AS',data,fault=fault,existing=['KEEP'])
                self.assertEqual((created,removed,files),([],[],{'KEEP':b'old'}))

    def test_precedence_and_macbinary_i(self):
        prodos = (11, bytes([0, 0xC3, 0, 0x06, 0, 0, 0x20, 0x00]))
        finder = (9, b'TEXTttxt' + bytes(24))
        for order in ([prodos, finder], [finder, prodos]):
            data = ref.make_as([(3, b'P')] + order + [(1, b'x')])
            self.check('P.AS', data)
            self.assertEqual(ref.unwrap(data, 'P.AS')[1:3], (6, 0x2000))
        m = bytearray(ref.make_mb(b'Old', b'TEXTttxt', b'abc', version=1))
        m[99] = 1                       # neither a MacBinary I nor a valid CRC
        self.check('OLD.BIN', bytes(m))
        self.assertIsNone(ref.unwrap(bytes(m), 'OLD.BIN'))

    def test_refusals_and_failures(self):
        good = ref.make_as([(3, b'Doc'), (1, b'hello' * 300)])
        for data in (b'', b'\x00\x05\x16\x00' + bytes(10), b'\x00\x05\x16\x00\x00\x03' + bytes(30),
                     good[:40], good[:-1], ref.make_as([(3, b'No fork')]),
                     ref.make_mb(b'', b'TEXTttxt', b'x'),
                     ref.make_mb(b'x', b'TEXTttxt', b'x' * 200)[:200],
                     bytes(200)):
            note, created, removed, files = self.run_unwrap('BAD.AS', data)
            self.assertEqual((note, created, files), ('Not an AppleSingle or MacBinary file.', [], {}),
                             data[:12])
        note, created, removed, files = self.run_unwrap('X.AS', good, existing=['DOC'])
        self.assertEqual((note, files), ('DOC exists or cannot be created.', {'DOC': b'old'}))
        for fault in (2, 3, 4, 6):
            with self.subTest(fault=fault):
                note, created, removed, files = self.run_unwrap('X.AS', good, fault=fault)
                self.assertEqual((note, removed, files), ('Extraction failed: DOC removed.', ['DOC'], {}))
        # a removal that fails says the incomplete file stays
        note, created, removed, files = self.run_unwrap('X.AS', good, fault=5)
        self.assertEqual((note, removed, list(files)),
                         ('Cleanup failed: the incomplete file stays.', ['DOC'], ['DOC']))

    def test_final_verification_read_error_is_not_eof(self):
        for fork in (b'', b'x', b'hello' * 300):
            with self.subTest(size=len(fork)):
                data = ref.make_as([(3, b'Doc'), (1, fork)])
                note, created, removed, files = self.run_unwrap('X.AS', data, fault=7,
                    existing=['KEEP'])
                self.assertEqual((note, removed, files),
                    ('Extraction failed: DOC removed.', ['DOC'], {'KEEP': b'old'}))

    def test_every_close_failure_refuses_extraction(self):
        good = ref.make_as([(3, b'Doc'), (1, b'hello' * 300)])
        for fault in (8, 9, 10):
            with self.subTest(fault=fault):
                note, created, removed, files = self.run_unwrap('X.AS', good, fault=fault,
                    existing=['KEEP'])
                self.assertEqual((note, removed, files),
                    ('Extraction failed: DOC removed.', ['DOC'], {'KEEP': b'old'}))

    def test_source_and_output_read_errors_refuse_extraction(self):
        good = ref.make_as([(3, b'Doc'), (1, b'hello' * 300)])
        for fault in (11, 12, 14):
            with self.subTest(fault=fault):
                note, created, removed, files = self.run_unwrap('X.AS', good, fault=fault,
                    existing=['KEEP'])
                self.assertEqual((note, removed, files),
                    ('Extraction failed: DOC removed.', ['DOC'], {'KEEP': b'old'}))

    def test_cancellation_during_final_closes_never_reports_success(self):
        for fmt in ('as','mb'):
            for fork in (b'',b'hello'*300):
                data=ref.make_as([(3,b'Doc'),(1,fork)]) if fmt=='as' else ref.make_mb(b'Doc',b'TEXTttxt',fork)
                for fault in (22,23,24,25):
                    with self.subTest(fmt=fmt,size=len(fork),fault=fault):
                        note,created,removed,files=self.run_unwrap('X.AS',data,fault=fault,existing=['KEEP'])
                        self.assertEqual(removed,['DOC'])
                        self.assertEqual(files,{'KEEP':b'old',**({'DOC':fork} if fault==25 else {})})
                        self.assertIn('Cleanup failed' if fault==25 else 'Stopped',note)

    def test_cancel_during_header_or_metadata_never_creates_output(self):
        for fmt in ('as1','as2','mb1','mb2','mb3'):
            for fork in (b'',b'A',b'B'*513):
                for fault in ((26,27,28,29,30) if fmt.startswith('as') else (26,)):
                    for collision in (False,True):
                        with self.subTest(fmt=fmt,size=len(fork),fault=fault,collision=collision):
                            if fmt.startswith('as'):
                                data=ref.make_as([(3,b'Doc'),(11,b'\x00\xc3\x00\x06\x00\x00\x20\x00'),
                                                 (1,fork),(2,b'resource')],version=int(fmt[-1]))
                            else:data=ref.make_mb(b'Doc',b'TEXTttxt',fork,version=int(fmt[-1]))
                            existing=['KEEP','DOC'] if collision else ['KEEP']
                            note,created,removed,files=self.run_unwrap('X.AS',data,fault=fault,existing=existing)
                            self.assertEqual(self.creates,0)
                            self.assertEqual((created,removed,files),
                                             ([],[],{name:b'old' for name in existing}))
                            self.assertEqual(note,'Stopped: nothing extracted.')

    def test_faulted_source_block_is_never_written(self):
        for fmt in ('as1','as2','mb1','mb2','mb3'):
            for size in (1,513,1536):
                fork=bytes(i&255 for i in range(size))
                data=(ref.make_as([(3,b'Doc'),(1,fork)],version=int(fmt[-1])) if fmt.startswith('as')
                      else ref.make_mb(b'Doc',b'TEXTttxt',fork,version=int(fmt[-1])))
                for fault in range(31,39):
                    with self.subTest(fmt=fmt,size=size,fault=fault):
                        prefix=((size-1)//512)*512 if (fault-31)%2 else 0
                        note,created,removed,files=self.run_unwrap('X.AS',data,fault=fault,existing=['KEEP'])
                        self.assertEqual(self.output_bytes,prefix)
                        self.assertEqual(len(created),1)
                        self.assertEqual(removed,['DOC'])
                        self.assertEqual(files,{'KEEP':b'old',**({'DOC':fork[:prefix]} if fault>=35 else {})})
                        self.assertIn('Cleanup failed' if fault>=35 else 'removed',note)

    def test_cancel_stops_large_applesingle_catalogue_immediately(self):
        for version in (1,2):
            for count in (1000,65535):
                with self.subTest(version=version,count=count):
                    entries=[(3,b'Doc')]+[(4,b'')]*(count-2)+[(1,b'payload')]
                    data=ref.make_as(entries,version=version)
                    note,created,removed,files=self.run_unwrap('X.AS',data,fault=27,existing=['KEEP'])
                    self.assertEqual(self.parser_reads,1)
                    self.assertEqual(self.creates,0)
                    self.assertEqual((created,removed,files),([],[],{'KEEP':b'old'}))
                    self.assertEqual(note,'Stopped: nothing extracted.')

    def test_applesingle_payload_must_not_overlap_its_header_table(self):
        for version in (1,2):
            for eid in (1,2,3,4,11,0x80000001):
                entries=[(eid,b'x'*8)]
                if eid!=3:entries.append((3,b'Doc'))
                if eid!=1:entries.append((1,b'payload'))
                good=ref.make_as(entries,version=version)
                end=26+12*len(entries)
                for off in (0,25,26,end-1):
                    with self.subTest(version=version,eid=eid,off=off):
                        data=bytearray(good);data[30:34]=off.to_bytes(4,'big')
                        self.assertIsNone(ref.unwrap(bytes(data),'X.AS'))
                        note,created,removed,files=self.run_unwrap('X.AS',bytes(data),existing=['KEEP'])
                        self.assertEqual((created,removed,files),([],[],{'KEEP':b'old'}))

    def test_duplicate_applesingle_data_forks_refuse_before_create(self):
        for version in (1,2):
            for first,last in ((b'',b''),(b'',b'A'),(b'A',b''),(b'A',b'B'),
                               (b'A',b'A'),(b'A'*513,b'B'*3000)):
                for metadata in (False,True):
                    for collision in (False,True):
                        with self.subTest(version=version,first=len(first),last=len(last),
                                          metadata=metadata,collision=collision):
                            entries=[(3,b'Doc'),(1,first)]
                            if metadata:entries.append((11,b'\x00\xc3\x00\x06\x00\x00\x20\x00'))
                            entries.append((1,last))
                            data=ref.make_as(entries,version=version)
                            self.assertIsNone(ref.unwrap(data,'X.AS'))
                            note,created,removed,files=self.run_unwrap('X.AS',data,
                                existing=['KEEP','DOC'] if collision else ['KEEP'])
                            expected={'KEEP':b'old'}
                            if collision:expected['DOC']=b'old'
                            self.assertEqual(note,'Not an AppleSingle or MacBinary file.')
                            self.assertEqual((created,removed,files),([],[],expected))

    def test_duplicate_applesingle_prodos_metadata_refuses_before_create(self):
        good=b'\x00\xc3\x00\x06\x00\x00\x20\x00'
        legacy=bytes(8)+bytes([0,0xE3,0,0x2A,0,0,0x12,0x34])
        pairs=((good,good),(good,good[:3]+b'\x04'+good[4:]),
               (good,good[:6]+b'\x20\x01'),(b'',good),(good[:7],good),
               (good[:3]+b'\x0f'+good[4:],good))
        for version in (1,2):
            for first,last in pairs:
                for between in ([],[(9,b'TEXTttxt')],[(7,legacy)]):
                    for collision in (False,True):
                        with self.subTest(version=version,first=first,last=last,
                                          between=between,collision=collision):
                            data=ref.make_as([(3,b'Doc'),(11,first)]+between+
                                             [(1,b'payload'*100),(11,last)],
                                             version=version,home=b'ProDOS')
                            note,created,removed,files=self.run_unwrap('X.AS',data,
                                existing=['KEEP','DOC'] if collision else ['KEEP'])
                            self.assertEqual((created,removed,files),([],[],
                                {'KEEP':b'old',**({'DOC':b'old'} if collision else {})}))
                            self.assertEqual(note,'Not an AppleSingle or MacBinary file.')
                            self.assertIsNone(ref.unwrap(data,'X.AS'))

    def test_truncated_applesingle_prodos_metadata_refuses_before_create(self):
        metadata=b'\x00\xc3\x00\x06\x00\x00\x20\x00'
        for version in (1,2):
            for length in range(8):
                for fork in (b'',b'A',b'B'*513):
                    for collision in (False,True):
                        with self.subTest(version=version,length=length,size=len(fork),
                                          collision=collision):
                            data=ref.make_as([(3,b'Doc'),(9,b'TEXTttxt'),
                                             (11,metadata[:length]),(1,fork)],version=version)
                            note,created,removed,files=self.run_unwrap('X.AS',data,
                                existing=['KEEP','DOC'] if collision else ['KEEP'])
                            self.assertEqual((created,removed,files),([],[],
                                {'KEEP':b'old',**({'DOC':b'old'} if collision else {})}))
                            self.assertEqual(note,'Not an AppleSingle or MacBinary file.')
                            self.assertIsNone(ref.unwrap(data,'X.AS'))

    def test_complete_applesingle_prodos_metadata_preserves_type_and_aux(self):
        metadata=b'\x00\xc3\x00\x06\x00\x00\x20\x00'
        for version in (1,2):
            for length in (8,9,32):
                for fork in (b'',b'A',b'B'*513):
                    with self.subTest(version=version,length=length,size=len(fork)):
                        data=ref.make_as([(3,b'Doc'),(9,b'TEXTttxt'),
                                         (11,metadata.ljust(length,b'\0')),(1,fork)],version=version)
                        note,created,removed,files=self.run_unwrap('X.AS',data,existing=['KEEP'])
                        self.assertEqual(created,[['DOC','06','2000']])
                        self.assertEqual((removed,files),([],{'KEEP':b'old','DOC':fork}))
                        self.assertEqual(ref.unwrap(data,'X.AS')[1:4],(6,0x2000,fork))

    def test_single_prodos_metadata_with_legacy_and_finder_entries(self):
        good=b'\x00\xc3\x00\x06\x00\x00\x20\x00'
        legacy=bytes(8)+bytes([0,0xE3,0,0x2A,0,0,0x12,0x34])
        for version in (1,2):
            for position in (0,2,4):
                for fork in (b'',b'A',b'B'*513):
                    with self.subTest(version=version,position=position,size=len(fork)):
                        entries=[(3,b'Doc'),(7,legacy),(11,good),(9,b'TEXTttxt')]
                        entries.insert(position,(1,fork))
                        data=ref.make_as(entries,version=version,home=b'ProDOS')
                        note,created,removed,files=self.run_unwrap('X.AS',data,existing=['KEEP'])
                        self.assertEqual(created,[['DOC','06','2000']])
                        self.assertEqual((removed,files),([],{'KEEP':b'old','DOC':fork}))
                        self.assertEqual(ref.unwrap(data,'X.AS')[1:4],(6,0x2000,fork))

    def test_duplicate_applesingle_resources_refuse_before_create(self):
        prodos=(11,b'\x00\xc3\x00\x06\x00\x00\x20\x00')
        legacy=(7,bytes(8)+bytes([0,0xE3,0,0x06,0,0,0x20,0]))
        for version in (1,2):
            for first,last in ((b'R',b''),(b'',b'R'),(b'',b''),
                               (b'R',b'R'),(b'R',b'Other'),(b'R'*513,b'')):
                for between in ([],[prodos],[legacy,prodos]):
                    for collision in (False,True):
                        with self.subTest(version=version,first=len(first),last=len(last),
                                          between=between,collision=collision):
                            data=ref.make_as([(3,b'Doc'),(2,first)]+between+
                                             [(1,b'payload'*100),(2,last)],
                                             version=version,home=b'ProDOS')
                            note,created,removed,files=self.run_unwrap('X.AS',data,
                                existing=['KEEP','DOC'] if collision else ['KEEP'])
                            self.assertEqual((created,removed,files),([],[],
                                {'KEEP':b'old',**({'DOC':b'old'} if collision else {})}))
                            self.assertEqual(note,'Not an AppleSingle or MacBinary file.')
                            self.assertIsNone(ref.unwrap(data,'X.AS'))

    def test_unique_applesingle_resource_warning_survives_metadata_order(self):
        for version in (1,2):
            for resource in (b'',b'R',b'R'*513):
                for position in (0,2,4):
                    with self.subTest(version=version,resource=len(resource),position=position):
                        fork=b'payload'*100
                        entries=[(3,b'Doc'),(11,b'\x00\xc3\x00\x06\x00\x00\x20\x00'),
                                 (9,b'TEXTttxt'),(1,fork)]
                        entries.insert(position,(2,resource))
                        data=ref.make_as(entries,version=version)
                        note,created,removed,files=self.run_unwrap('X.AS',data,existing=['KEEP'])
                        self.assertEqual(created,[['DOC','06','2000']])
                        self.assertEqual((removed,files),([],{'KEEP':b'old','DOC':fork}))
                        self.assertEqual(note,'DOC: 700 bytes, $06/$2000.'+
                            (' Resource fork left out.' if resource else ''))
                        self.assertEqual(ref.unwrap(data,'X.AS')[3:],(fork,len(resource)))

    def test_duplicate_applesingle_names_refuse_before_create(self):
        metadata=(11,b'\x00\xc3\x00\x06\x00\x00\x20\x00')
        legacy=(7,bytes(8)+bytes([0,0xE3,0,0x06,0,0,0x20,0]))
        for version in (1,2):
            for first,last in ((b'Doc',b'Other'),(b'Other',b'Doc'),(b'Doc',b'Doc'),
                               (b'',b'Doc'),(b'Doc',b''),(b'',b'')):
                for between in ([],[metadata],[legacy,metadata]):
                    for collision in (False,True):
                        with self.subTest(version=version,first=first,last=last,
                                          between=between,collision=collision):
                            data=ref.make_as([(3,first)]+between+[(1,b'payload'*100),(3,last)],
                                             version=version,home=b'ProDOS')
                            existing=['KEEP','DOC','OTHER','X'] if collision else ['KEEP']
                            note,created,removed,files=self.run_unwrap('X.AS',data,existing=existing)
                            self.assertEqual((created,removed,files),
                                             ([],[],{name:b'old' for name in existing}))
                            self.assertEqual(note,'Not an AppleSingle or MacBinary file.')
                            self.assertIsNone(ref.unwrap(data,'X.AS'))

    def test_single_applesingle_name_and_wrapper_fallback_remain_valid(self):
        for version in (1,2):
            for raw,want in ((b'Doc','DOC'),(b'a-b','A.B'),(b'','X')):
                for position in (0,2,4):
                    with self.subTest(version=version,raw=raw,position=position):
                        fork=b'payload'*100
                        entries=[(11,b'\x00\xc3\x00\x06\x00\x00\x20\x00'),
                                 (9,b'TEXTttxt'),(1,fork),(2,b'resource')]
                        entries.insert(position,(3,raw))
                        data=ref.make_as(entries,version=version)
                        note,created,removed,files=self.run_unwrap('X.AS',data,existing=['KEEP'])
                        self.assertEqual(created,[[want,'06','2000']])
                        self.assertEqual((removed,files),([],{'KEEP':b'old',want:fork}))
                        self.assertEqual(note,f'{want}: 700 bytes, $06/$2000. Resource fork left out.')
                        self.assertEqual(ref.unwrap(data,'X.AS')[:4],(want,6,0x2000,fork))

    def test_duplicate_applesingle_finder_metadata_refuses_before_create(self):
        prodos=(11,b'\x00\xc3\x00\x06\x00\x00\x20\x00')
        legacy=(7,bytes(8)+bytes([0,0xE3,0,0x06,0,0,0x20,0]))
        for version in (1,2):
            for first,last in ((b'TEXTttxt',b'BINAxxxx'),(b'TEXTttxt',b'TEXTttxt'),
                               (b'p\x0f\0\0pdos',b'TEXTttxt'),(b'',b'TEXTttxt'),
                               (b'TEXTttxt',b''),(b'TEXT',b'TEXTttxt')):
                for between in ([],[prodos],[legacy,prodos]):
                    for collision in (False,True):
                        with self.subTest(version=version,first=first,last=last,
                                          between=between,collision=collision):
                            data=ref.make_as([(3,b'Doc'),(9,first)]+between+
                                             [(1,b'payload'*100),(9,last)],
                                             version=version,home=b'ProDOS')
                            existing=['KEEP','DOC'] if collision else ['KEEP']
                            note,created,removed,files=self.run_unwrap('X.AS',data,existing=existing)
                            self.assertEqual((created,removed,files),
                                             ([],[],{name:b'old' for name in existing}))
                            self.assertEqual(note,'Not an AppleSingle or MacBinary file.')
                            self.assertIsNone(ref.unwrap(data,'X.AS'))

    def test_short_applesingle_finder_type_and_creator_refuse_before_create(self):
        for version in (1,2):
            for length in range(8):
                for prodos in (False,True):
                    for collision in (False,True):
                        with self.subTest(version=version,length=length,prodos=prodos,collision=collision):
                            entries=[(3,b'Doc'),(1,b'payload'*100)]
                            if prodos:entries.append((11,b'\x00\xc3\x00\x06\x00\x00\x20\x00'))
                            entries.append((9,b'TEXTttxt'[:length]))
                            data=ref.make_as(entries,version=version)
                            existing=['KEEP','DOC'] if collision else ['KEEP']
                            note,created,removed,files=self.run_unwrap('X.AS',data,existing=existing)
                            self.assertEqual((created,removed,files),
                                             ([],[],{name:b'old' for name in existing}))
                            self.assertEqual(note,'Not an AppleSingle or MacBinary file.')
                            self.assertIsNone(ref.unwrap(data,'X.AS'))

    def test_unique_finder_metadata_keeps_prodos_precedence_and_fork_bytes(self):
        for version in (1,2):
            for finder,ftype,faux in ((b'TEXTttxt',4,0),(b'p\x06\x08\x00pdos',6,0x800),
                                     (b'APPLMSWD',0,0)):
                for prodos in (False,True):
                    for position in (0,3):
                        with self.subTest(version=version,finder=finder,prodos=prodos,position=position):
                            fork=b'payload'*100
                            entries=[(3,b'Doc'),(1,fork),(2,b'resource')]
                            if prodos:entries.insert(1,(11,b'\x00\xc3\x00\x06\x00\x00\x20\x00'))
                            entries.insert(position,(9,finder+bytes(24)))
                            data=ref.make_as(entries,version=version)
                            typ,aux=(6,0x2000) if prodos else (ftype,faux)
                            note,created,removed,files=self.run_unwrap('X.AS',data,existing=['KEEP'])
                            self.assertEqual(created,[['DOC',f'{typ:02X}',f'{aux:04X}']])
                            self.assertEqual((removed,files),([],{'KEEP':b'old','DOC':fork}))
                            self.assertEqual(note,f'DOC: 700 bytes, ${typ:02X}/${aux:04X}. Resource fork left out.')
                            self.assertEqual(ref.unwrap(data,'X.AS')[1:4],(typ,aux,fork))

    def test_duplicate_legacy_prodos_metadata_refuses_before_create(self):
        legacy=bytes(8)+bytes([0,0xE3,0,6,0,0,0x20,0])
        prodos=(11,b'\x00\xc3\x00\x06\x00\x00\x20\x00')
        pairs=((legacy,legacy),(legacy,legacy[:11]+b'\x04'+legacy[12:]),
               (legacy,legacy[:14]+b'\x20\x01'),(b'',legacy),(legacy[:15],legacy),
               (legacy[:11]+b'\x0f'+legacy[12:],legacy))
        for first,last in pairs:
            for between in ([],[(9,b'TEXTttxt')],[prodos]):
                for collision in (False,True):
                    with self.subTest(first=first,last=last,between=between,collision=collision):
                        data=ref.make_as([(3,b'Doc'),(7,first)]+between+
                                         [(1,b'payload'*100),(7,last)],version=1,home=b'ProDOS')
                        existing=['KEEP','DOC'] if collision else ['KEEP']
                        note,created,removed,files=self.run_unwrap('X.AS',data,existing=existing)
                        self.assertEqual((created,removed,files),
                                         ([],[],{name:b'old' for name in existing}))
                        self.assertEqual(note,'Not an AppleSingle or MacBinary file.')
                        self.assertIsNone(ref.unwrap(data,'X.AS'))

    def test_short_legacy_prodos_metadata_refuses_before_create(self):
        legacy=bytes(8)+bytes([0,0xE3,0,6,0,0,0x20,0])
        for length in range(16):
            for collision in (False,True):
                with self.subTest(length=length,collision=collision):
                    data=ref.make_as([(3,b'Doc'),(9,b'TEXTttxt'),(7,legacy[:length]),
                                     (1,b'payload'*100)],version=1,home=b'ProDOS')
                    existing=['KEEP','DOC'] if collision else ['KEEP']
                    note,created,removed,files=self.run_unwrap('X.AS',data,existing=existing)
                    self.assertEqual((created,removed,files),
                                     ([],[],{name:b'old' for name in existing}))
                    self.assertEqual(note,'Not an AppleSingle or MacBinary file.')
                    self.assertIsNone(ref.unwrap(data,'X.AS'))

    def test_legacy_metadata_versions_homes_and_complete_entries(self):
        legacy=bytes(8)+bytes([0,0xE3,0,6,0,0,0x20,0])
        for version,home in ((1,b'ProDOS'),(1,b'Macintosh'),(2,b'ProDOS')):
            for length in (16,17,32):
                for position in (0,3):
                    for fork in (b'',b'A'):
                        with self.subTest(version=version,home=home,length=length,
                                          position=position,size=len(fork)):
                            entries=[(3,b'Doc'),(9,b'TEXTttxt'),(1,fork)]
                            entries.insert(position,(7,legacy.ljust(length,b'\0')))
                            data=ref.make_as(entries,version=version,home=home)
                            typ,aux=(6,0x2000) if version==1 and home==b'ProDOS' else (4,0)
                            note,created,removed,files=self.run_unwrap('X.AS',data,existing=['KEEP'])
                            self.assertEqual(created,[['DOC',f'{typ:02X}',f'{aux:04X}']])
                            self.assertEqual((removed,files),([],{'KEEP':b'old','DOC':fork}))
                            self.assertEqual(ref.unwrap(data,'X.AS')[1:4],(typ,aux,fork))

        # ID 7 has no ProDOS meaning in another home system or in version 2.
        # Even short/repeated foreign entries must not acquire that meaning.
        for version,home in ((1,b'Macintosh'),(2,b'ProDOS'),(2,b'Macintosh')):
            for length in (0,15,16,32):
                for repeated in (False,True):
                    with self.subTest(version=version,home=home,length=length,repeated=repeated):
                        entries=[(3,b'Doc'),(9,b'TEXTttxt'),(7,legacy.ljust(length,b'\0')[:length]),
                                 (1,b'payload')]
                        if repeated:entries.append((7,b''))
                        data=ref.make_as(entries,version=version,home=home)
                        note,created,removed,files=self.run_unwrap('X.AS',data,existing=['KEEP'])
                        self.assertEqual(created,[['DOC','04','0000']])
                        self.assertEqual((removed,files),([],{'KEEP':b'old','DOC':b'payload'}))
                        self.assertEqual(ref.unwrap(data,'X.AS')[1:4],(4,0,b'payload'))

    def test_zero_applesingle_entry_id_refuses_before_create(self):
        for version in (1,2):
            for payload in (b'',b'X',b'X'*513):
                for position in (0,2,4):
                    for collision in (False,True):
                        with self.subTest(version=version,size=len(payload),position=position,
                                          collision=collision):
                            entries=[(3,b'Doc'),(11,b'\x00\xc3\x00\x06\x00\x00\x20\x00'),
                                     (9,b'TEXTttxt'),(1,b'payload'*100)]
                            entries.insert(position,(0,payload))
                            data=ref.make_as(entries,version=version)
                            existing=['KEEP','DOC'] if collision else ['KEEP']
                            note,created,removed,files=self.run_unwrap('X.AS',data,existing=existing)
                            self.assertEqual((created,removed,files),
                                             ([],[],{name:b'old' for name in existing}))
                            self.assertEqual(note,'Not an AppleSingle or MacBinary file.')
                            self.assertIsNone(ref.unwrap(data,'X.AS'))

    def test_unknown_nonzero_applesingle_entries_remain_opaque(self):
        for version in (1,2):
            for eid in (4,6,10,12,13,14,15,0x7FFFFFFF,0x80000000,0xFFFFFFFF):
                for payload in (b'',b'opaque!!!'):
                    for position in (0,4):
                        with self.subTest(version=version,eid=eid,size=len(payload),position=position):
                            fork=b'payload'*100
                            entries=[(3,b'Doc'),(11,b'\x00\xc3\x00\x06\x00\x00\x20\x00'),
                                     (9,b'TEXTttxt'),(1,fork)]
                            entries.insert(position,(eid,payload))
                            data=ref.make_as(entries,version=version)
                            note,created,removed,files=self.run_unwrap('X.AS',data,existing=['KEEP'])
                            self.assertEqual(created,[['DOC','06','2000']])
                            self.assertEqual((removed,files),([],{'KEEP':b'old','DOC':fork}))
                            self.assertEqual(ref.unwrap(data,'X.AS')[1:4],(6,0x2000,fork))

    def test_unique_applesingle_data_fork_survives_metadata_order(self):
        for version in (1,2):
            for fork in (b'',b'A',b'B'*513):
                for position in (0,2,4):
                    with self.subTest(version=version,size=len(fork),position=position):
                        entries=[(3,b'Doc'),(11,b'\x00\xc3\x00\x06\x00\x00\x20\x00'),
                                 (9,b'TEXTttxt'),(2,b'resource')]
                        entries.insert(position,(1,fork))
                        data=ref.make_as(entries,version=version)
                        note,created,removed,files=self.run_unwrap('X.AS',data,existing=['KEEP'])
                        self.assertEqual(created,[['DOC','06','2000']])
                        self.assertEqual((removed,files),([],{'KEEP':b'old','DOC':fork}))
                        self.assertEqual(note,f'DOC: {len(fork)} bytes, $06/$2000. Resource fork left out.')

    def test_applesingle_empty_entry_offset_and_table_boundary_remain_valid(self):
        for version in (1,2):
            data=bytearray(ref.make_as([(1,b'')],version=version))
            data[30:34]=bytes(4)
            self.check('EMPTY.AS',bytes(data))
            for payload in (b'x',b'payload'):
                self.check('X.AS',ref.make_as([(1,payload)],version=version))

    def test_rejected_applesingle_cannot_fall_back_to_macbinary(self):
        for version in (1,2):
            for payload in (b'',b'hello'*300):
                for malformed in ('overlap','version','past-eof','table'):
                    with self.subTest(version=version,size=len(payload),malformed=malformed):
                        # Also satisfies MacBinary I's permissive header checks.
                        data=bytearray(128)+payload
                        data[:8]=b'\x00\x05\x16\x00'+(version<<16).to_bytes(4,'big')
                        data[24:26]=(1).to_bytes(2,'big')
                        data[26:38]=(1).to_bytes(4,'big')+bytes(4)+(1).to_bytes(4,'big')
                        data[65:73]=b'TEXTttxt';data[83:87]=len(payload).to_bytes(4,'big')
                        if malformed=='version':data[4:8]=(3<<16).to_bytes(4,'big')
                        if malformed=='past-eof':data[30:34]=(len(data)+1).to_bytes(4,'big')
                        if malformed=='table':data[24:26]=(65535).to_bytes(2,'big')
                        self.assertIsNone(ref.unwrap(bytes(data),'X.AS'))
                        note,created,removed,files=self.run_unwrap('X.AS',bytes(data),existing=['KEEP'])
                        self.assertEqual((created,removed,files),([],[],{'KEEP':b'old'}))

    def test_macbinary_versions_still_dispatch_normally(self):
        for version in (1,2,3):
            for payload in (b'',b'hello'*300):
                self.check('X.BIN',ref.make_mb(b'Doc',b'TEXTttxt',payload,version=version))

    def test_macbinary_secondary_header_is_not_extracted_as_file_data(self):
        for version in (2,3):
            for secondary_size in (1,127,128,129,65535):
                for fork in (b'',b'D',b'payload'*100):
                    with self.subTest(version=version,secondary_size=secondary_size,size=len(fork)):
                        data=ref.make_mb(b'Doc',b'p\x06\x20\x00pdos',fork,b'resource',
                                         version=version,secondary=b'S'*secondary_size)
                        note,created,removed,files=self.run_unwrap('X.BIN',data,existing=['KEEP'])
                        self.assertEqual(created,[['DOC','06','2000']])
                        self.assertEqual((removed,files),([],{'KEEP':b'old','DOC':fork}))
                        self.assertEqual(note,f'DOC: {len(fork)} bytes, $06/$2000. Resource fork left out.')

    def test_macbinary_secondary_header_bounds_refuse_before_create(self):
        for version in (2,3):
            for secondary_size in (1,128,129,65535):
                for truncated in ('secondary','padding','data'):
                    for collision in (False,True):
                        with self.subTest(version=version,secondary_size=secondary_size,
                                          truncated=truncated,collision=collision):
                            data=ref.make_mb(b'Doc',b'TEXTttxt',b'payload',version=version,
                                             secondary=b'S'*secondary_size)
                            off=128+((secondary_size+127)//128)*128
                            length=(128+secondary_size-1 if truncated=='secondary' else
                                    off-1 if truncated=='padding' else off+6)
                            data=data[:length]
                            self.assertIsNone(ref.unwrap(data,'X.BIN'))
                            note,created,removed,files=self.run_unwrap('X.BIN',data,
                                existing=['KEEP','DOC'] if collision else ['KEEP'])
                            expected={'KEEP':b'old',**({'DOC':b'old'} if collision else {})}
                            self.assertEqual((created,removed,files),([],[],expected))
                            self.assertEqual(note,'Not an AppleSingle or MacBinary file.')

    def test_macbinary_truncated_resources_refuse_before_create(self):
        for version in (1,2,3):
            for size in (0,1,127,128,129,513):
                fork=b'D'*size
                data=ref.make_mb(b'Doc',b'TEXTttxt',fork,b'Rsrc!!',version=version)
                resource=128+((size+127)//128)*128
                for available in (0,5):
                    for collision in (False,True):
                        with self.subTest(version=version,size=size,available=available,collision=collision):
                            truncated=data[:resource+available]
                            self.assertIsNone(ref.unwrap(truncated,'X.BIN'))
                            note,created,removed,files=self.run_unwrap('X.BIN',truncated,
                                existing=['KEEP','DOC'] if collision else ['KEEP'])
                            self.assertEqual((created,removed,files),([],[],
                                {'KEEP':b'old',**({'DOC':b'old'} if collision else {})}))
                            self.assertEqual(note,'Not an AppleSingle or MacBinary file.')

    def test_macbinary_resource_lengths_cannot_wrap_past_eof(self):
        for version in (1,2,3):
            for size in (0,1,127,128,129,513):
                for resource_size in (0xFFFFFF,0xFFFFFFFF):
                    with self.subTest(version=version,size=size,resource_size=resource_size):
                        data=bytearray(ref.make_mb(b'Doc',b'TEXTttxt',b'D'*size,b'Rsrc!!',version=version))
                        data[87:91]=resource_size.to_bytes(4,'big')
                        if version>=2:data[124:126]=ref.crc16(data[:124]).to_bytes(2,'big')
                        self.assertIsNone(ref.unwrap(bytes(data),'X.BIN'))
                        note,created,removed,files=self.run_unwrap('X.BIN',bytes(data),existing=['KEEP'])
                        self.assertEqual((created,removed,files),([],[],{'KEEP':b'old'}))
                        self.assertEqual(note,'Not an AppleSingle or MacBinary file.')

    def test_macbinary_resources_need_no_final_padding(self):
        for version in (1,2,3):
            for secondary in ((b'',) if version==1 else (b'',b'S'*129)):
                for size in (0,1,127,128,129,513):
                    for resource_size in (1,129):
                        with self.subTest(version=version,secondary=len(secondary),size=size,resource_size=resource_size):
                            fork=b'D'*size
                            data=ref.make_mb(b'Doc',b'p\x06\x20\x00pdos',fork,b'R'*resource_size,
                                             version=version,secondary=secondary)
                            resource=128+((len(secondary)+127)//128)*128+((size+127)//128)*128
                            data=data[:resource+resource_size]
                            note,created,removed,files=self.run_unwrap('X.BIN',data,existing=['KEEP'])
                            self.assertEqual(created,[['DOC','06','2000']])
                            self.assertEqual((removed,files),([],{'KEEP':b'old','DOC':fork}))
                            self.assertEqual(note,f'DOC: {size} bytes, $06/$2000. Resource fork left out.')

    def test_secondary_header_offset_on_both_native_processors(self):
        from test_pascalw import toolchains
        chains=toolchains()
        self.assertEqual(len(chains),2,'both cc65 processors must be checked')
        source=(ROOT/'src/plugins/unwrap.c').read_text()
        functions=[]
        for signature in ('static unsigned long be32(', 'static unsigned int be16(',
                          'static unsigned int crc16(', 'static unsigned char mac_binary('):
            start=source.index(signature)
            end=(source.index('\n',start) if signature.endswith('be16(') else
                 source.index('\n}',start)+2)
            functions.append(source[start:end])
        harness='''#include <stdio.h>
#include <stdlib.h>
static unsigned char hdr[128],typed;
static unsigned long size,off,len,rsrc;
static void set_name(const unsigned char* p,unsigned char n){}
static void mac_type(const unsigned char* p){}
'''+ '\n'.join(functions)+'''
int main(int argc,char** argv){
 FILE* f;unsigned char ok;
 f=fopen(argv[1],"rb");if(!f)return 1;
 if(fread(hdr,1,128,f)!=128)return 2;
 fclose(f);size=strtoul(argv[2],0,10);ok=mac_binary();
 printf("%u %lu\\n",ok,off);return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix='mb-native-',dir='/tmp') as tmp:
            case=Path(tmp);c=case/'check.c';c.write_text(harness)
            for cpu,cl65,sim65,env in chains:
                exe=case/cpu
                subprocess.run([cl65,'-t',cpu,'-O',str(c),'-o',str(exe)],
                               env={**os.environ,**env},check=True,capture_output=True)
                for secondary_size in (1,127,128,129,65535):
                    data=ref.make_mb(b'Doc',b'TEXTttxt',b'payload',version=3,
                                     secondary=b'S'*secondary_size)
                    off=128+((secondary_size+127)//128)*128
                    for resources in (0,6,0xFFFFFF,0xFFFFFFFF):
                        raw=bytearray(data[:128]);raw[87:91]=resources.to_bytes(4,'big')
                        raw[124:126]=ref.crc16(raw[:124]).to_bytes(2,'big')
                        header=case/'header';header.write_bytes(raw)
                        sizes=(((off+7,1),(off-1,0),(off+6,0)) if not resources else
                               ((off+134,1),(off+133,0),(off+7,0)) if resources==6 else
                               ((off+134,0),))
                        for size,expected in sizes:
                            with self.subTest(cpu=cpu,secondary_size=secondary_size,size=size,resources=resources):
                                result=subprocess.check_output([sim65,str(exe),str(header),str(size)],
                                                               env={**os.environ,**env},text=True)
                                self.assertEqual(tuple(map(int,result.split())),(expected,off))

    def test_header_read_error_does_not_create_output(self):
        good = ref.make_as([(3, b'Doc'), (1, b'hello' * 300)])
        note, created, removed, files = self.run_unwrap('X.AS', good, fault=13,
            existing=['KEEP'])
        self.assertEqual((created, removed, files), ([], [], {'KEEP': b'old'}))

    def test_read_or_source_close_error_with_failed_cleanup_reports_retained_output(self):
        fork = b'hello' * 300
        good = ref.make_as([(3, b'Doc'), (1, fork)])
        for fault in (15, 16):
            with self.subTest(fault=fault):
                note, created, removed, files = self.run_unwrap('X.AS', good, fault=fault,
                    existing=['KEEP'])
                self.assertEqual((note, removed, files),
                    ('Cleanup failed: the incomplete file stays.', ['DOC'],
                     {'DOC': fork, 'KEEP': b'old'}))


if __name__ == '__main__':
    unittest.main()
