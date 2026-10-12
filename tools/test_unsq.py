"""UNSQ's real entry point on the host, against tools/squeeze_ref.py.

The overlay (src/plugins/unsq.c) runs with the host's files and a CREATE
stand-in behind its service table. Every extraction is compared with the
reference -- names, types, bytes, the note -- for synthetic SQueezed files
and ACU archives, and for CiderPress II's real ones when at hand: the .QQ
inside its Binary II sample (whose plain original sits next to it) and
IconEd.ACU. Damaged input and failed writes leave nothing behind.
"""
import random
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import squeeze_ref as ref  # noqa: E402
import cp2_samples  # noqa: E402
from test_six_plugins import PREFIX, ROOT  # noqa: E402

HARNESS = PREFIX + r'''
static int error_(FILE*);
#define ferror error_
#include "src/plugins/unsq.c"
#undef ferror
static int fault, writes;
static unsigned int create_calls,create_at=1;
static FILE *writing, *read_error;
static FILE* source_stream;
static FILE* verifying;
static unsigned int verifications,outputs;
static unsigned int verify_reads,verify_closes;
static unsigned int source_closes;
static int extracting;
static unsigned int data_reads;
static unsigned long output_bytes;
static unsigned int output_calls,cancel_refills,cancel_injected,writes_after_cancel;
static unsigned long bytes_before_cancel;
static int error_(FILE* f) { return f == read_error || ferror(f); }
static unsigned char mli_(unsigned char cmd, void* params)
{
    char p[80];
    FILE* f;
    unsigned char* pas = create.path;
    if (cmd != 0xC0) abort();
    memcpy(p, pas + 1, pas[0]); p[pas[0]] = 0;
    ++create_calls;
    if(fault>=19 && fault<=22 && create_calls==create_at){
        if(fault==22){
            f=fopen(p,"wx");if(!f)abort();fputs("new arrival",f);fclose(f);
        }
        return fault==20?0x48:fault==21?0x4E:0x27;
    }
    f = fopen(p, "wx");
    if (!f) return 0x47;
    fclose(f);
    printf("CREATE %s %02X %04X\n", strrchr(p, '/') + 1, create.type, create.aux);
    return 0;
}
static FILE* open_(const char* p, const char* m)
{
    FILE* f = fopen(p, m);
    if(!strcmp(m,"rb") && !source_stream)source_stream=f;
    if (!strcmp(m, "wb")){writing = f;++outputs;}
    if (!strcmp(m,"rb") && strstr(p,"/D/")){verifying=f;++verifications;}
    return f;
}
static size_t write_(const void* p, size_t s, size_t n, FILE* f)
{
    size_t result;
    if(cancel_injected)++writes_after_cancel;
    unsigned char injected=fault>=40 && fault<=47 && ++output_calls==create_at;
    output_bytes += s*n;
    if ((fault == 1 || fault == 4) && ++writes == 2) return n - 1;
    if((fault==28 || fault==30) && ++writes==1){
        unsigned char changed[512];memcpy(changed,p,n);
        if(n>=2){unsigned char tmp=changed[0];changed[0]=changed[1];changed[1]=tmp;}
        return fwrite(changed,s,n,f);
    }
    if (fault == 3 && ++writes == 1) {  /* a byte lands wrong: only the read-back sees it */
        unsigned char c[512];
        memcpy(c, p, n); c[0] ^= 1;
        return fwrite(c, s, n, f);
    }
    result=fwrite(p,s,injected && (fault-40)%4==3 && n ? n-1 : n,f);
    if(injected){
        if((fault-40)%4==0 || (fault-40)%4==2)cancelled=1;
        if((fault-40)%4!=0)read_error=f;
    }
    return result;
}
static int close_(FILE* f)
{
    int result;
    if (fault == 2 && f == writing) fputc('!', f);
    result=fclose(f);
    if(f==writing){if(fault==15 && outputs==2)cancelled=1;writing=0;}
    if(f==verifying){
        if(verifications==2){
            ++verify_closes;
            if(fault==17 || fault==18)cancelled=1;
        }
        verifying=0;
    }
    if(f==source_stream){
        ++source_closes;
        if(fault==23 || fault==24)cancelled=1;
        if(fault==11 || fault==24)result=EOF;
        source_stream=NULL;
    }
    return result;
}
static int remove_(const char* p) { printf("REMOVE %s\n", strrchr(p, '/') + 1); return fault == 4 || fault==16 || fault==18 || fault==30 || fault==31 || (fault>=36 && fault<=39) || (fault>=44 && fault<=47) || fault==49 ? -1 : remove(p); }
static size_t read_(void* p, size_t s, size_t n, FILE* f) {
    size_t result;
    if(f==verifying && verifications==2)++verify_reads;
    long position=ftell(f);
    if (fault == 6 || fault == 9) read_error = f;
    if (fault == 8) cancelled = 1;
    int data_fault = fault>=32 && fault<=39 && f==source_stream && writing && ++data_reads==create_at;
    result=fread(p, s, (fault == 9 || (data_fault && (fault-32)%4==3)) && n ? n - 1 : n, f);
    if((fault==48 || fault==49) && f==source_stream && writing && ++cancel_refills==create_at){
        bytes_before_cancel=output_bytes;cancel_injected=1;cancelled=1;
    }
    if(data_fault){
        if((fault-32)%4==0 || (fault-32)%4==2)cancelled=1;
        if((fault-32)%4!=0)read_error=f;
    }
    if(fault==29 && f==verifying && !position && result>=2){
        unsigned char* bytes=p;unsigned char tmp=bytes[0];bytes[0]=bytes[1];bytes[1]=tmp;
    }
    if((fault==10 || (fault==12 && position>=512)) && f==source_stream && extracting)read_error=f;
    if(fault==26 && f==source_stream && extracting)cancelled=1;
    return result;
}
static int seek_(FILE* f, long o, int w) {
    if (fault == 5 && w == SEEK_SET && o) return -1;
    if (fault == 7 && w == SEEK_SET && !o) return -1;
    if(f==source_stream && w==SEEK_SET && !o)extracting=1;
    if(f==source_stream && w==SEEK_SET &&
       ((fault==25 && !o) || (fault==27 && o && outputs==1 && verifications==1)))cancelled=1;
    return fseek(f, o, w);
}
static unsigned long bars, overflows;
static void bar_(const char* n, unsigned long d, unsigned long t) {
    ++bars; if (d > t || !*n) ++overflows;
    if(verifying && verifications==2 &&
       (fault==13 || fault==16 || (fault==14 && d==t)))cancelled=1;
}
int main(int argc, char** argv)
{
    static struct A2fcApi api;
    static struct Panel panels[2];
    static struct Entry sel;
    static char full[80], note[120];
    static unsigned char active, copy[512];
    strcpy(panels[0].path, argv[1]);
    strcpy(panels[1].path, argv[2]);
    strcpy(sel.name, argv[3]);
    sel.type = strtol(argv[4], 0, 16);
    sel.aux = strtol(argv[5], 0, 16);
    fault = atoi(argv[6]);
    sprintf(full, "%s/%s", argv[1], argv[3]);
    api.panels = panels; api.active = &active; api.selected = &sel; api.full = full;
    api.note = note; api.copy_buf = copy;
    api.memcpy = memcpy; api.memset = memset; api.strcpy = strcpy; api.strlen = strlen;
    api.strcmp = strcmp; api.sprintf = sprintf; api.fopen = open_; api.fread = read_;
    api.fwrite = write_; api.fseek = seek_; api.fclose = close_; api.remove = remove_;
    api.mli = mli_; api.progress_bar = bar_;
    {
        FILE* f = fopen(full, "rb");
        if (f) { fseek(f, 0, SEEK_END); sel.size = ftell(f); fclose(f); }
    }
    if (argc > 7) sel.size = strtoul(argv[7], 0, 10);
    if (argc > 8) create_at = atoi(argv[8]);
    plugin_entry(&api);
    printf("BARS %lu %lu\n", bars, overflows);
    printf("CHECK %u %u\n",verify_reads,verify_closes);
    printf("ATTEMPTS %u\n",create_calls);
    printf("SOURCE-CLOSE %u\n",source_closes);
    printf("OUTPUT-BYTES %lu\n",output_bytes);
    printf("OUTPUT-CALLS %u\n",output_calls);
    printf("CANCEL-WRITES %u %lu %u\n",cancel_injected,bytes_before_cancel,writes_after_cancel);
    printf("NOTE %s\n", note);
    return 0;
}
'''


def bqy_members(data):
    out, pos = {}, 0
    while pos + 128 <= len(data):
        h = data[pos:pos + 128]
        if h[0:3] != b'\x0aGL':
            pos += 128
            continue
        eof = int.from_bytes(h[0x14:0x17], 'little')
        name = h[0x18:0x18 + h[0x17]].decode('latin-1')
        out[name] = data[pos + 128:pos + 128 + eof]
        pos += 128 + (eof + 127) // 128 * 128
    return out


class Unsq(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='unsq-', dir='/tmp')
        cls.root = Path(cls.tmp.name)
        (cls.root / 'test.c').write_text(HARNESS)
        cls.exe = cls.root / 'test'
        subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-I', str(ROOT),
                        str(cls.root / 'test.c'), '-o', str(cls.exe)], check=True,
                       capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_unsq(self, name, data, typ=4, aux=0, fault=0, existing=(), cached_size=None,
                 create_at=None, dest_len=None):
        case = Path(tempfile.mkdtemp(dir=self.root))
        (case / 'S').mkdir()
        (case / 'D').mkdir()
        destination=case/'D'
        if dest_len is not None:
            padding=dest_len-len(str(destination))-1
            self.assertGreater(padding,0)
            destination=destination/('A'*padding)
            destination.mkdir()
        (case / 'S' / name).write_bytes(data)
        for e in existing:
            (destination / e).write_bytes(b'old')
        args = [str(self.exe), str(case / 'S'), str(destination), name,
                '%02X' % typ, '%04X' % aux, str(fault)]
        if cached_size is not None or create_at is not None:
            args.append(str(len(data) if cached_size is None else cached_size))
        if create_at is not None:args.append(str(create_at))
        out = subprocess.run(args,
                             capture_output=True, text=True, timeout=120)
        self.assertEqual(out.returncode, 0, out.stderr)
        lines = out.stdout.splitlines()
        note = [l[5:] for l in lines if l.startswith('NOTE ')][0]
        created = [l.split()[1:] for l in lines if l.startswith('CREATE ')]
        removed = [l.split()[1] for l in lines if l.startswith('REMOVE ')]
        self.bars = [int(v) for l in lines if l.startswith('BARS ') for v in l.split()[1:]]
        self.verification = [int(v) for l in lines if l.startswith('CHECK ') for v in l.split()[1:]]
        self.create_calls = next(int(l.split()[1]) for l in lines if l.startswith('ATTEMPTS '))
        self.source_closes = next(int(l.split()[1]) for l in lines if l.startswith('SOURCE-CLOSE '))
        self.output_bytes = next(int(l.split()[1]) for l in lines if l.startswith('OUTPUT-BYTES '))
        self.output_calls = next(int(l.split()[1]) for l in lines if l.startswith('OUTPUT-CALLS '))
        self.cancel_injected,self.bytes_before_cancel,self.writes_after_cancel=map(int,next(l for l in lines if l.startswith('CANCEL-WRITES ')).split()[1:])
        made = {p.name: p.read_bytes() for p in destination.iterdir()}
        self.assertEqual((case / 'S' / name).read_bytes(), data, 'source must remain untouched')
        return note, created, removed, made

    def check(self, name, data, typ=4, aux=0):
        files = ref.unsqueeze(data, name)
        note, created, removed, made = self.run_unsq(name, data, typ, aux)
        want_created = [[n, '%02X' % (typ if t is None else t), '%04X' % (aux if a is None else a)]
                        for n, t, a, _ in files]
        self.assertEqual(created, want_created, note)
        self.assertEqual(made, {n: b for n, _, _, b in files})
        self.assertEqual(note, '%d extracted, 0 skipped (name taken).' % len(files))

    def test_long_qq_paths_use_the_complete_last_component(self):
        payload=bytes(i%251 for i in range(513))
        for length in (64,65,511,512,1024):
            for separator in (b'/',b':'):
                for leaf in (b'DOC',b'1'*80+b'DOC',b''):
                    raw=b'P'*length+separator+leaf
                    archive=ref.squeeze(payload,raw)
                    target=ref.unsqueeze(archive,'ARCH.QQ')[0][0]
                    for collision in (False,True):
                        with self.subTest(length=length,separator=separator,leaf=leaf,collision=collision):
                            old={'KEEP':b'old','P'*15:b'old'}
                            if collision:old[target]=b'old'
                            note,created,removed,made=self.run_unsq('ARCH.QQ',archive,existing=tuple(old))
                            self.assertEqual(made,old if collision else {**old,target:payload},note)
                            self.assertEqual([c[0] for c in created],[] if collision else [target],note)
                            self.assertEqual(removed,[],note)
                            self.assertEqual(note,'%d extracted, %d skipped (name taken).'%(not collision,collision))

    def test_failed_output_stops_inside_rle_and_before_final_flush(self):
        for kind in ('QQ-rle','QQ-literal','stored','ACU-rle','ACU-literal'):
            for size in (513,2000):
                payload=b'A'*size if kind.endswith('rle') else bytes(i%251 for i in range(size))
                filename='X.QQ' if kind.startswith('QQ') else 'X.ACU'
                archive=ref.squeeze(payload,b'DOC') if kind.startswith('QQ') else ref.make_acu([(b'DOC',4,0,payload,kind!='stored',False)])
                for target in sorted({1,2,(size+511)//512}):
                    for fault in range(40,48):
                        with self.subTest(kind=kind,size=size,target=target,fault=fault):
                            length=min(target*512,size)
                            prefix=payload[:length-int((fault-40)%4==3)]
                            note,created,removed,made=self.run_unsq(filename,archive,fault=fault,create_at=target,existing=('KEEP',))
                            expected={'KEEP':b'old'}
                            if fault>=44:expected['DOC']=prefix
                            self.assertEqual(made,expected,note)
                            self.assertEqual(self.output_calls,target,note)
                            self.assertEqual(self.output_bytes,length,note)
                            self.assertEqual(self.verification,[0,0],note)
                            self.assertEqual(self.source_closes,1)
                            self.assertEqual([c[0] for c in created],['DOC'],note)
                            self.assertEqual(removed,['DOC'],note)
                            self.assertIn('Cleanup failed' if fault>=44 else 'stopped',note)

    def test_cancelled_source_refill_never_flushes_pending_output(self):
        for kind in ('QQ','QQ-RLE','stored','squeezed','squeezed-RLE'):
            for size in (513,1536,4097):
                payload=(b'A'*size if kind.endswith('RLE') else
                         bytes((i*73+i//13)&255 for i in range(size)))
                filename='X.QQ' if kind.startswith('QQ') else 'X.ACU'
                archive=(ref.squeeze(payload,b'DOC') if kind.startswith('QQ') else
                         ref.make_acu([(b'DOC',4,0,payload,kind!='stored',False)]))
                for target in (1,2,3,4,5,8,16):
                    for fault in (48,49):
                        with self.subTest(kind=kind,size=size,target=target,fault=fault):
                            note,created,removed,made=self.run_unsq(filename,archive,
                                fault=fault,create_at=target,existing=('KEEP',))
                            self.assertEqual([c[0] for c in created],['DOC'])
                            self.assertEqual(self.source_closes,1)
                            expected={'KEEP':b'old'}
                            if self.cancel_injected:
                                self.assertEqual(removed,['DOC'])
                                if fault==49:
                                    expected['DOC']=payload[:self.bytes_before_cancel]
                                    self.assertIn('Cleanup failed',note)
                                else:self.assertIn('stopped',note)
                                self.assertEqual(self.output_bytes,self.bytes_before_cancel)
                                self.assertEqual(self.writes_after_cancel,0)
                            else:
                                self.assertEqual(removed,[])
                                expected['DOC']=payload
                                self.assertIn('1 extracted',note)
                            self.assertEqual(made,expected)

    def test_stored_acu_failed_refill_never_writes_an_unread_byte(self):
        for size in (1,513,1536):
            payload=bytes((i%250)+1 for i in range(size))
            archive=ref.make_acu([(b'DOC',4,0,payload,False,False)])
            for refill in range(1,(size+511)//512+1):
                for fault in range(32,40):
                    with self.subTest(size=size,refill=refill,fault=fault):
                        prefix=payload[:(refill-1)*512]
                        note,created,removed,made=self.run_unsq('X.ACU',archive,fault=fault,create_at=refill,existing=('KEEP',))
                        expected={'KEEP':b'old'}
                        if fault>=36:expected['DOC']=prefix
                        self.assertEqual(made,expected,note)
                        self.assertEqual(self.output_bytes,len(prefix),note)
                        self.assertEqual([c[0] for c in created],['DOC'],note)
                        self.assertEqual(removed,['DOC'],note)
                        self.assertEqual(self.source_closes,1)
                        self.assertIn('Cleanup failed' if fault>=36 else 'stopped',note)

    def test_acu_impossible_lengths_are_refused_before_create(self):
        for size in (1,513,1536):
            payload=bytes(i%251 for i in range(size))
            for squeezed in (False,True):
                lengths=(0,size+1,0x1000000,0xFFFFFFFF) if not squeezed else (0x1000000,0xFFFFFFFF)
                for declared in lengths:
                    for prior in (False,True):
                        for collision in (False,True):
                            with self.subTest(size=size,squeezed=squeezed,declared=declared,prior=prior,collision=collision):
                                entries=[(b'FIRST',4,0,b'verified',False,False)] if prior else []
                                prefix=ref.make_acu(entries)
                                data=bytearray(ref.make_acu(entries+[(b'DOC',4,0,payload,squeezed,False)]))
                                record=len(prefix)
                                data[record+0x26:record+0x2A]=struct.pack('<I',declared)
                                with self.assertRaises(ref.Bad):ref.unsqueeze(bytes(data),'X.ACU')
                                note,created,removed,made=self.run_unsq('X.ACU',bytes(data),existing=('KEEP','DOC') if collision else ('KEEP',))
                                expected={'KEEP':b'old'}
                                if prior:expected['FIRST']=b'verified'
                                if collision:expected['DOC']=b'old'
                                self.assertEqual(made,expected,note)
                                self.assertEqual(self.create_calls,int(prior),note)
                                self.assertEqual([c[0] for c in created],['FIRST'] if prior else [],note)
                                self.assertEqual(removed,[],note)
                                self.assertNotIn('name taken).',note)

    def test_acu_squeezed_output_cannot_exceed_declared_length(self):
        for size in (1,513,1536):
            # Includes long RLE runs, so the bound must apply inside a run.
            payload=b'A'*size
            for declared in sorted({0,size-1}):
                for prior in (False,True):
                    for fault in (0,31):
                        with self.subTest(size=size,declared=declared,prior=prior,fault=fault):
                            entries=[(b'FIRST',4,0,b'verified',False,False)] if prior else []
                            record=len(ref.make_acu(entries))
                            data=bytearray(ref.make_acu(entries+[(b'DOC',4,0,payload,True,False)]))
                            data[record+0x26:record+0x2A]=struct.pack('<I',declared)
                            note,created,removed,made=self.run_unsq('X.ACU',bytes(data),fault=fault,existing=('KEEP',))
                            expected={'KEEP':b'old'}
                            if prior:expected['FIRST']=b'verified'
                            if fault:expected['DOC']=payload[:declared]
                            self.assertEqual(made,expected,note)
                            self.assertEqual([c[0] for c in created],(['FIRST'] if prior else [])+['DOC'],note)
                            self.assertEqual(removed,['DOC'],note)
                            self.assertIn('Cleanup failed' if fault else 'damaged',note)

    def test_same_sum_corruption_is_not_accepted_as_verified(self):
        for size in (2,513,2000):
            payload=bytes(i%251 for i in range(size))
            for kind in ('QQ','stored','squeezed'):
                name='X.QQ' if kind=='QQ' else 'X.ACU'
                archive=ref.squeeze(payload,b'DOC') if kind=='QQ' else ref.make_acu([(b'DOC',4,0,payload,kind=='squeezed',False)])
                for fault in (0,28,29,30):
                    with self.subTest(size=size,kind=kind,fault=fault):
                        note,created,removed,made=self.run_unsq(name,archive,fault=fault,existing=('KEEP',))
                        self.assertEqual(made['KEEP'],b'old')
                        self.assertEqual(self.source_closes,1)
                        if not fault:
                            self.assertEqual(made['DOC'],payload)
                            self.assertEqual(removed,[])
                            self.assertIn('1 extracted',note)
                        elif fault in (28,29):
                            self.assertEqual(made,{'KEEP':b'old'})
                            self.assertEqual(removed,['DOC'])
                            self.assertIn('damaged, stopped',note)
                        else:
                            self.assertEqual(made['DOC'],payload[1:2]+payload[:1]+payload[2:])
                            self.assertEqual(removed,['DOC'])
                            self.assertIn('Cleanup failed',note)

    def test_squeezed_files(self):
        rng = random.Random(1)
        for i in range(30):
            size = rng.choice([0, 1, 2, 3, 200, 513, 4000])
            alphabet = rng.choice([b'ab', b'\x90\x90\x90a', bytes(range(256)), b'zzzzzzzzzy'])
            data = bytes(rng.choice(alphabet) for _ in range(size))
            name = rng.choice([b'NOTES.TXT', b'/usr/src/Read Me', b'', b'1.2.3', b'Mac:Folder:File'])
            with self.subTest(i=i):
                self.check('F%d.QQ' % i, ref.squeeze(data, name), typ=rng.choice([4, 6]),
                           aux=rng.randrange(0x10000))

    def test_cancelled_header_never_creates_or_skips_a_destination(self):
        for payload in (b'',b'A',bytes(range(256))*3):
            for filename,data in (
                    ('X.QQ',ref.squeeze(payload,b'DOC')),
                    ('X.ACU',ref.make_acu([(b'DOC',4,0,payload,False,False)]))):
                for fault in (25,26):
                    for collision in (False,True):
                        with self.subTest(filename=filename,size=len(payload),fault=fault,collision=collision):
                            old={'KEEP':b'old',**({'DOC':b'old'} if collision else {})}
                            note,created,removed,made=self.run_unsq(filename,data,fault=fault,existing=tuple(old))
                            self.assertEqual(self.create_calls,0)
                            self.assertEqual(created,[])
                            self.assertEqual(removed,[])
                            self.assertEqual(made,old)
                            self.assertEqual(self.source_closes,1)
                            self.assertEqual(note,'0 extracted, 0 skipped (name taken); stopped.')

    def test_cancel_between_acu_records_preserves_verified_outputs(self):
        first=b'verified first file'
        for squeezed in (False,True):
            archive=ref.make_acu([(b'FIRST',4,0,first,False,False),
                                  (b'SECOND',4,0,b'second data',squeezed,False)])
            for collision in (False,True):
                with self.subTest(squeezed=squeezed,collision=collision):
                    old={'KEEP':b'old',**({'SECOND':b'old'} if collision else {})}
                    note,created,removed,made=self.run_unsq('X.ACU',archive,fault=27,existing=tuple(old))
                    self.assertEqual(self.create_calls,1)
                    self.assertEqual(created,[['FIRST','04','0000']])
                    self.assertEqual(removed,[])
                    self.assertEqual(made,{'FIRST':first,**old})
                    self.assertEqual(self.source_closes,1)
                    self.assertEqual(note,'1 extracted, 0 skipped (name taken); stopped.')

    def test_create_errors_stop_without_owning_or_removing_the_failed_target(self):
        payload=b'verified first file'
        archive=ref.make_acu([(b'FIRST',4,0,payload,False,False),
                              (b'SECOND',4,0,b'squeezed data'*100,True,False),
                              (b'THIRD',4,0,b'must not be created',False,False)])
        for name,data,at,target in (('X.QQ',ref.squeeze(payload,b'FIRST'),1,'FIRST'),
                                    ('X.ACU',archive,1,'FIRST'),('X.ACU',archive,2,'SECOND')):
            for fault in (19,20,21,22):
                with self.subTest(name=name,at=at,fault=fault):
                    note,created,removed,made=self.run_unsq(
                        name,data,fault=fault,create_at=at,existing=['KEEP'])
                    expected={'KEEP':b'old'}
                    if at==2:expected['FIRST']=payload
                    if fault==22:expected[target]=b'new arrival'
                    self.assertEqual(made,expected)
                    self.assertEqual(removed,[])
                    self.assertEqual(self.create_calls,at)
                    self.assertEqual([c[0] for c in created],['FIRST'] if at==2 else [])
                    self.assertIn('stopped',note)
                    self.assertIn('create failed',note)
                    self.assertNotIn('damaged',note)
                    self.assertIn('0 skipped',note)

    def test_only_duplicate_name_skips_and_allows_the_next_record(self):
        data=ref.make_acu([(b'FIRST',4,0,b'must remain old',False,False),
                           (b'SECOND',4,0,b'new',False,False),
                           (b'THIRD',4,0,b'must remain old',False,False)])
        note,created,removed,made=self.run_unsq('X.ACU',data,existing=['KEEP','FIRST','THIRD'])
        self.assertEqual(made,{'KEEP':b'old','FIRST':b'old','SECOND':b'new','THIRD':b'old'})
        self.assertEqual(self.create_calls,3)
        self.assertEqual(removed,[])
        self.assertEqual(note,'1 extracted, 2 skipped (name taken).')

    def test_unrepresentable_acu_names_stop_without_a_collision_skip(self):
        for raw in (b'',b'123...',b'folder/'):
            for squeezed in (False,True):
                for prior in (False,True):
                    with self.subTest(raw=raw,squeezed=squeezed,prior=prior):
                        entries=[(raw,4,0,b'invalid name',squeezed,False),
                                 (b'LATER',4,0,b'later',False,False)]
                        if prior:entries.insert(0,(b'FIRST',4,0,b'first',False,False))
                        note,created,removed,made=self.run_unsq('X.ACU',ref.make_acu(entries),
                                                              existing=['KEEP','LATER'])
                        expected={'KEEP':b'old','LATER':b'old'}
                        if prior:expected['FIRST']=b'first'
                        self.assertEqual(made,expected)
                        self.assertEqual(removed,[])
                        self.assertEqual(self.create_calls,int(prior))
                        self.assertIn('0 skipped',note)
                        self.assertIn('name/path invalid, stopped',note)

    def test_destination_path_boundary_refuses_before_create(self):
        target=b'LONGFILENAME123'
        for format in ('qq','stored','squeezed'):
            for dest_len in (47,48,49):
                for collision in (False,True):
                    with self.subTest(format=format,dest_len=dest_len,collision=collision):
                        if format=='qq':
                            name='X.QQ';data=ref.squeeze(b'payload',target)
                        else:
                            name='X.ACU';data=ref.make_acu([
                                (b'FIRST',4,0,b'first',False,False),
                                (target,4,0,b'payload',format=='squeezed',False),
                                (b'LATER',4,0,b'later',False,False)])
                        existing=['KEEP']+([target.decode()] if collision else [])
                        note,created,removed,made=self.run_unsq(name,data,existing=existing,
                                                              dest_len=dest_len)
                        expected={'KEEP':b'old'}
                        if collision:expected[target.decode()]=b'old'
                        if format!='qq':expected['FIRST']=b'first'
                        if dest_len==47:
                            if not collision:expected[target.decode()]=b'payload'
                            if format!='qq':expected['LATER']=b'later'
                            self.assertEqual(self.create_calls,1 if format=='qq' else 3)
                            self.assertIn(f'{int(collision)} skipped',note)
                            self.assertNotIn('stopped',note)
                        else:
                            self.assertEqual(self.create_calls,int(format!='qq'))
                            self.assertIn('0 skipped',note)
                            self.assertIn('name/path invalid, stopped',note)
                        self.assertEqual((removed,made),([],expected))

    def test_extraction_read_error_is_not_accepted_as_valid_input(self):
        data=ref.squeeze(b'hello'*100,b'DATA')
        note,created,removed,made=self.run_unsq('X.QQ',data,fault=10,existing=['KEEP'])
        self.assertEqual(made,{'KEEP':b'old'})
        self.assertEqual(created,[])
        self.assertNotIn('1 extracted',note)

    def test_cancel_during_read_back_does_not_count_unverified_output(self):
        for fault in (13,14,15,16):
            payload=b'' if fault==15 else bytes(range(256))*6
            data=ref.make_acu([(b'FIRST',4,0,b'verified',False,False),
                               (b'SECOND',4,0,payload,False,False)])
            with self.subTest(fault=fault):
                note,created,removed,made=self.run_unsq('X.ACU',data,fault=fault,existing=['KEEP'])
                self.assertEqual([c[0] for c in created],['FIRST','SECOND'])
                self.assertEqual(removed,['SECOND'])
                self.assertEqual(self.verification,[0,0] if fault==15 else [3 if fault==14 else 1,1])
                if fault==16:
                    self.assertIn('Cleanup failed',note)
                    self.assertEqual(made,{'KEEP':b'old','FIRST':b'verified','SECOND':payload})
                else:
                    self.assertIn('1 extracted',note)
                    self.assertIn('stopped',note)
                    self.assertEqual(made,{'KEEP':b'old','FIRST':b'verified'})
    def test_cancel_at_verification_close_does_not_publish_or_continue(self):
        for payload in (b'',bytes(range(256))*6):
            for fault in (17,18):
                with self.subTest(size=len(payload),fault=fault):
                    data=ref.make_acu([(b'FIRST',4,0,b'verified',False,False),
                                       (b'SECOND',4,0,payload,False,False),
                                       (b'THIRD',4,0,b'not reached',False,False)])
                    note,created,removed,made=self.run_unsq('X.ACU',data,fault=fault,existing=['KEEP'])
                    self.assertEqual([c[0] for c in created],['FIRST','SECOND'])
                    self.assertEqual(removed,['SECOND'])
                    self.assertEqual(self.verification,[len(payload)//512+1,1])
                    self.assertEqual(made,{'KEEP':b'old','FIRST':b'verified',
                                          **({'SECOND':payload} if fault==18 else {})})
                    if fault==18:self.assertIn('Cleanup failed',note)
                    else:
                        self.assertIn('1 extracted',note)
                        self.assertIn('stopped',note)

    def test_source_close_error_reports_incomplete_but_keeps_verified_outputs(self):
        for data,name in ((ref.squeeze(b'hello'*100,b'DATA'),'X.QQ'),
                          (ref.make_acu([(b'DATA',4,0,b'hello'*100,False,False)]),'X.ACU'),
                          (ref.make_acu([]),'EMPTY.ACU')):
            with self.subTest(name=name):
                note,created,removed,made=self.run_unsq(name,data,fault=11,existing=['KEEP'])
                self.assertIn('I/O error',note)
                expected={'KEEP':b'old'}
                if name!='EMPTY.ACU':expected['DATA']=b'hello'*100
                self.assertEqual(made,expected)
                self.assertEqual(removed,[])

    def test_cancel_during_final_source_close_keeps_verified_and_existing_files(self):
        payload=b'hello'*100
        cases=(('X.QQ',ref.squeeze(payload,b'DATA'),[],{'DATA':payload}),
               ('X.ACU',ref.make_acu([(b'DATA',4,0,payload,False,False),
                                     (b'EMPTY',6,0,b'',False,False)]),[],{'DATA':payload,'EMPTY':b''}),
               ('EMPTY.ACU',ref.make_acu([]),[],{}),
               ('TAKEN.ACU',ref.make_acu([(b'DATA',4,0,payload,False,False)]),['DATA'],{'DATA':b'old'}),
               ('DIR.ACU',ref.make_acu([(b'DIR',0x0F,0,b'',False,False)]),[],{}))
        for name,data,existing,expected in cases:
            for fault in (23,24):
                with self.subTest(name=name,fault=fault):
                    note,created,removed,made=self.run_unsq(name,data,fault=fault,existing=['KEEP',*existing])
                    self.assertEqual(made,{'KEEP':b'old',**expected})
                    self.assertEqual(removed,[])
                    self.assertEqual(self.source_closes,1)
                    self.assertEqual([c[0] for c in created],[n for n in expected if n not in existing])
                    self.assertIn('stopped',note)
                    self.assertNotIn('Damaged',note)
                    if fault==24:self.assertIn('I/O error',note)

    def test_late_source_read_error_removes_only_the_current_output(self):
        data=ref.make_acu([(b'FIRST',4,0,b'first',False,False),
                           (b'SECOND',4,0,bytes(range(256))*8,False,False)])
        note,created,removed,made=self.run_unsq('X.ACU',data,fault=12,existing=['KEEP'])
        self.assertIn('I/O error',note)
        self.assertEqual(made,{'FIRST':b'first','KEEP':b'old'})
        self.assertEqual(removed,['SECOND'])

    def test_acu_archives(self):
        rng = random.Random(2)
        for i in range(10):
            files = []
            for k in range(rng.randint(1, 6)):
                data = bytes(rng.choice(b'hello \x90\r') for _ in range(rng.choice([0, 5, 300, 2000])))
                if rng.random() < 0.2:
                    files.append((b'DIR%d' % k, 0x0F, 0, b'', False, True))
                files.append((b'DIR/FILE%d' % k, rng.choice([4, 6, 0xB3]), rng.randrange(65536),
                              data, rng.random() < 0.6, False))
            with self.subTest(i=i):
                self.check('A%d.ACU' % i, ref.make_acu(files), typ=0xE0, aux=0x8001)

    def test_type_0f_record_skipped(self):
        """An ACU record typed $0F that is not a directory record is skipped.

        Before: only storage type $0D was skipped, so a record with file
        type $0F and storage type 1 went to newfile(dest, $0F, ...):
        `CREATE FAKEDIR 0F 0000`, note `1 extracted` -- a plain file
        typed as a folder, which the panels then walk as directory
        entries. BINARY2, SCIIBIN and UNWRAP refuse $0F; so does UNSQ now,
        counted with the skipped files and named in the note."""
        for squeezed in (False, True):
            with self.subTest(squeezed=squeezed):
                acu = ref.make_acu([(b'FAKEDIR', 0x0F, 0, b'\0' * 600, squeezed, False),
                                    (b'REAL', 4, 0x1234, b'kept\r' * 50, squeezed, False)])
                self.assertEqual([f[0] for f in ref.unsqueeze(acu, 'X')], ['REAL'])
                note, created, removed, made = self.run_unsq('X.ACU', acu, typ=0xE0, aux=0x8001)
                self.assertEqual(created, [['REAL', '04', '1234']], note)
                self.assertEqual(made, {'REAL': b'kept\r' * 50})
                self.assertEqual(removed, [])
                self.assertEqual(note, '1 extracted, 1 skipped (name taken or type $0F).')
        acu = ref.make_acu([(b'ONLY', 0x0F, 0, b'x' * 10, False, False)])
        note, created, removed, made = self.run_unsq('X.ACU', acu, typ=0xE0, aux=0x8001)
        self.assertEqual((created, made), ([], {}), note)
        self.assertEqual(note, '0 extracted, 1 skipped (name taken or type $0F).')

    def test_counts_past_255(self):
        """The counts of the note are 16 bits, like ACU's record count.

        Before: `made` and `skipped` were unsigned char -- 300 records
        said "44 extracted", 256 said "0 extracted", and a damaged record
        after 256 good files said "Damaged archive: nothing extracted."
        although 256 files had been written."""
        files = [(b'F%d' % i, 4, i, b'r%d\r' % i, i % 2 == 0, False) for i in range(300)]
        acu = ref.make_acu(files)
        note, created, removed, made = self.run_unsq('X.ACU', acu, typ=0xE0, aux=0x8001)
        self.assertEqual(note, '300 extracted, 0 skipped (name taken).')
        self.assertEqual(made, {'F%d' % i: b'r%d\r' % i for i in range(300)})
        self.assertEqual(len(created), 300)
        # 260 taken names: the skipped count goes past 255 too
        note, created, removed, made = self.run_unsq('X.ACU', acu, typ=0xE0, aux=0x8001,
                                                     existing=['F%d' % i for i in range(260)])
        self.assertEqual(note, '40 extracted, 260 skipped (name taken).')
        self.assertEqual(made['F0'], b'old')
        self.assertEqual(made['F299'], b'r299\r')
        # 256 good files, then a record cut short: the good ones stay, the
        # cut one's bounds are refused before creation; the note counts
        # what was written
        acu = ref.make_acu(files[:257])
        note, created, removed, made = self.run_unsq('X.ACU', acu[:-2], typ=0xE0, aux=0x8001)
        self.assertEqual(note, '256 extracted, 0 skipped (name taken); damaged, stopped.')
        self.assertEqual(made, {'F%d' % i: b'r%d\r' % i for i in range(256)})
        self.assertEqual(removed, [])
        self.assertEqual(len(created), 256)

    def test_real_files(self):
        found = 0
        bqy = cp2_samples.path('bny/SAMPLE.BQY')
        if bqy:
            found += 1
            members = bqy_members(bqy.read_bytes())
            qq = members['SQUEEZE/BNYARCHIVE.H.QQ']
            self.check('BNYARCHIVE.H.QQ', qq)
            self.assertEqual(ref.unsqueeze(qq, 'X')[0][3], members['BNYARCHIVE.H'])
        acu = cp2_samples.path('acu/IconEd.ACU')
        if acu:
            found += 1
            self.check('ICONED.ACU', acu.read_bytes(), typ=0xE0, aux=0x8001)
        if not found:
            self.skipTest('no CiderPress II samples')

    def test_progress(self):
        # Minutes at 1 MHz for a big file: the bar must move during the
        # decoding (every KB written) and the read-back (every block).
        rng = random.Random(3)
        data = bytes(rng.choice(b'abcdefgh \r') for _ in range(20000))
        self.check('BIG.QQ', ref.squeeze(data, b'BIG'))
        calls, bad = self.bars
        self.assertGreaterEqual(calls, 20000 // 1024 + 20000 // 512)
        self.assertEqual(bad, 0)
        acu = ref.make_acu([(b'A', 4, 0, data, True, False), (b'B', 4, 0, data[:3000], False, False)])
        self.check('BIG.ACU', acu, typ=0xE0, aux=0x8001)
        calls, bad = self.bars
        self.assertGreaterEqual(calls, 23000 // 1024 + 23000 // 512)
        self.assertEqual(bad, 0)

    def test_damage_and_failures(self):
        good = ref.squeeze(b'the same text, the same text, the same text\r' * 40, b'TEXT')
        cases = [good[:-3], good[:30], good[:2] + bytes([good[2] ^ 1]) + good[3:],
                 good[:18] + b'\x01\x02' + good[20:], b'\x76\xff\x00\x00NAME',
                 b'plain text, neither format' * 3]
        for data in cases:
            with self.subTest(data=data[:12]):
                note, created, removed, made = self.run_unsq('BAD.QQ', data)
                self.assertEqual(made, {}, note)
        acu = ref.make_acu([(b'A', 4, 0, b'first\r' * 30, True, False), (b'B', 4, 0, b'x' * 99, False, False)])
        note, created, removed, made = self.run_unsq('X.ACU', acu[:-10])
        self.assertEqual(list(made), ['A'], note)
        self.assertTrue(note.endswith('damaged, stopped.'), note)
        bad_len = bytearray(acu)
        bad_len[20 + 0x26] ^= 1
        note, created, removed, made = self.run_unsq('X.ACU', bytes(bad_len))
        self.assertEqual((made, removed), ({}, ['A']), note)
        # a squeezed fork one byte shorter than its stream, the byte after it
        short = bytearray(ref.make_acu([(b'A', 4, 0, b'first\r' * 30, True, False)]))
        short[20 + 0x12] -= 1
        self.assertRaises(ref.Bad, ref.unsqueeze, bytes(short), 'X')
        note, created, removed, made = self.run_unsq('X.ACU', bytes(short))
        self.assertEqual(made, {}, note)
        note, created, removed, made = self.run_unsq('X.ACU', acu, existing=['A'])
        self.assertEqual((note, made['B']), ('1 extracted, 1 skipped (name taken).', b'x' * 99))
        for fault in (1, 2, 3):
            with self.subTest(fault=fault):
                note, created, removed, made = self.run_unsq('T.QQ', good, fault=fault)
                self.assertEqual((made, removed), ({}, ['TEXT']), note)
        note, created, removed, made = self.run_unsq('T.QQ', good, fault=4)
        self.assertIn('Cleanup failed', note)

    def test_acu_forks_outside_input_are_refused_before_creation(self):
        for squeezed, directory in ((False, False), (True, False), (False, True)):
            for offset, length in ((0x0E, 0xFFFFFFFF), (0x12, 0xFFFFFFFF),
                                   (0x0E, 1000), (0x12, 1000)):
                with self.subTest(squeezed=squeezed, directory=directory,
                                  offset=offset, length=length):
                    data = bytearray(ref.make_acu([(b'BAD', 4, 0, b'', squeezed, directory)]))
                    struct.pack_into('<I', data, 20 + offset, length)
                    self.assertRaises(ref.Bad, ref.unsqueeze, bytes(data), 'X')
                    note, created, removed, made = self.run_unsq('X.ACU', bytes(data),
                        existing=['KEEP'])
                    self.assertEqual((created, removed, made), ([], [], {'KEEP': b'old'}), note)
                    self.assertIn('Damaged archive', note)

    def test_failed_seek_to_empty_acu_fork_does_not_publish_file(self):
        data = ref.make_acu([(b'EMPTY', 4, 0, b'', False, False)])
        note, created, removed, made = self.run_unsq('X.ACU', data, fault=5,
            existing=['KEEP'])
        self.assertEqual((created, removed, made), ([], [], {'KEEP': b'old'}), note)
        self.assertIn('Damaged archive', note)

    def test_actual_input_length_overrides_stale_panel_size(self):
        data = ref.make_acu([(b'GOOD', 4, 0, b'preserved', False, False)])
        for cached_size in (0, 1, len(data) - 1, len(data) + 1000):
            with self.subTest(cached_size=cached_size):
                note, created, removed, made = self.run_unsq('X.ACU', data,
                    cached_size=cached_size)
                self.assertEqual(made, {'GOOD': b'preserved'}, note)

    def test_size_scan_read_errors_reset_failure_and_cancel_create_nothing(self):
        data = ref.make_acu([(b'GOOD', 4, 0, bytes(range(256)) * 8, False, False)])
        for fault in (6, 7, 8, 9):
            with self.subTest(fault=fault):
                note, created, removed, made = self.run_unsq('X.ACU', data,
                    fault=fault, existing=['KEEP'])
                self.assertEqual((created, removed, made), ([], [], {'KEEP': b'old'}), note)
                self.assertIn('nothing extracted', note)

    def test_invalid_fork_after_valid_record_preserves_prior_extraction(self):
        data = bytearray(ref.make_acu([(b'GOOD', 4, 0, b'kept', False, False),
                                       (b'BAD', 4, 0, b'', False, False)]))
        second = 20 + 0x36 + len(b'GOOD') + len(b'kept')
        struct.pack_into('<I', data, second + 0x0E, 0xFFFFFFFF)
        note, created, removed, made = self.run_unsq('X.ACU', bytes(data), existing=['KEEP'])
        self.assertEqual((created, removed, made),
            ([['GOOD', '04', '0000']], [], {'GOOD': b'kept', 'KEEP': b'old'}))
        self.assertEqual(note, '1 extracted, 0 skipped (name taken); damaged, stopped.')


if __name__ == '__main__':
    unittest.main()
