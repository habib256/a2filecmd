"""SCIIBIN's real entry point on the host, against tools/binscii_ref.py.

The overlay (src/plugins/sciibin.c) runs with the host's files behind its
service table; the directory it walks for later parts is the order given
on the command line. Every decoded file is compared with the reference --
name, type, bytes, note -- and every refusal or failure must leave the
destination as it was. The table CRC of src/plugins/sciibin.s runs under
sim65 on both processors against the reference's bitwise one. Real
BinSCII posts from CiderPress II's test data are decoded when at hand.
"""
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import binscii_ref as ref  # noqa: E402
import cp2_samples  # noqa: E402
from test_six_plugins import PREFIX, ROOT  # noqa: E402

HARNESS = PREFIX + r'''
static int error_(FILE*);
#define ferror error_
#include "src/plugins/sciibin.c"
#undef ferror
static FILE *errored,*verifying,*reading;
static int error_(FILE* f){return f==errored || ferror(f);}
static int fault, writes, argn;
static unsigned long output_bytes;
static unsigned int verify_closes;
static unsigned long verify_end;
static char** args;
static struct DirEntry dirent;
static int dir_i;
static unsigned int opens,dir_closes,create_calls;
static unsigned char directory_error;
static unsigned char mli_(unsigned char cmd, void* params)
{
    char p[80];
    FILE* f;
    unsigned char* pas = create.path;
    if (cmd != 0xC0) abort();
    ++create_calls;
    memcpy(p, pas + 1, pas[0]); p[pas[0]] = 0;
    f = fopen(p, "wx");
    if (!f) return 0x47;
    fclose(f);
    printf("CREATE %s %02X %04X\n", strrchr(p, '/') + 1, create.type, create.aux);
    return 0;
}
static FILE* writing;
static FILE* open_(const char* p, const char* m)
{
    ++opens;
    FILE* f = fopen(p, m);
    if (!strcmp(m, "wb")) writing = f;
    else if(!strcmp(p,path))verifying=f;
    else reading=f;
    return f;
}
static size_t write_(const void* p, size_t s, size_t n, FILE* f)
{
    output_bytes+=s*n;
    if ((fault == 1 || fault == 4) && ++writes == 3) return n - 1;
    if (fault == 2 && ++writes == 3) { unsigned char c[64]; memcpy(c, p, n); c[0] ^= 1; return fwrite(c, s, n, f); }
    if(fault==5)errored=f;
    return fwrite(p, s, n, f);
}
static int close_(FILE* f)
{
    if (fault == 3 && f == writing) fputc('!', f);
    {
        int bad=((fault==9 || fault==19) && f==verifying) || (fault==10 && f==reading) || (fault==11 && f==writing);
        if(f==verifying){++verify_closes;verify_end=ftell(f);}
        if(f==verifying && fault>=17 && fault<=19)cancelled=1;
        if(fault==15 && f==writing)cancelled=1;
        int r=fclose(f);if(f==errored)errored=NULL;
        if(f==writing)writing=NULL;if(f==verifying)verifying=NULL;if(f==reading)reading=NULL;
        return bad?-1:r;
    }
}
static int remove_(const char* p) { printf("REMOVE %s\n", strrchr(p, '/') + 1); return fault == 4 || fault==12 || fault==16 || fault==18 || fault==29 || fault==31 || fault==33 || fault==38 || fault==40 || fault==42 ? -1 : remove(p); }
static size_t read_(void* p, size_t s, size_t n, FILE* f) {
 if(f==reading && created && fault>=37 && fault<=45){
  unsigned char refill=fault>=43?fault-42:(fault-37)/2+1;
  if((unsigned long)ftell(f)==512UL*refill){errored=f;if(fault>=43)return fread(p,s,n-1,f);}
 }
 if(f==reading && created && fault>=28 && fault<=36){
  unsigned char refill=fault>=34?fault-33:(fault-28)/2+1;
  if((unsigned long)ftell(f)==512UL*refill){cancelled=1;if(fault>=34)errored=f;}
 }
 if(f==verifying){
  if((fault==7 || fault==12) && n==1 && (unsigned long)ftell(f)>=written){errored=f;return 0;}
  if(fault==6 && (unsigned long)ftell(f)<written)errored=f;
 }
 if(fault==8 && f==reading)errored=f;
 if(fault==27 && f==reading)cancelled=1;
 return fread(p, s, n, f);
}
static int seek_(FILE* f, long o, int w) { return fseek(f, o, w); }
static unsigned long bars, overflows;
static void bar_(const char* n, unsigned long d, unsigned long t) {
    ++bars; if (d > t || !*n) ++overflows;
    if(verifying && (fault==13 || fault==16 || (fault==14 && d==t)))cancelled=1;
}
static unsigned char dopen_(const char* p) { dir_i = 5; return fault!=20; }
static unsigned char dnext_(void)
{
    if((fault==21 && dir_i==5) || (fault==22 && dir_i==6) || (fault==23 && dir_i==7)){
        directory_error=0x27;return 0;
    }
    if(fault==26 && dir_i<argn && !strcmp(args[dir_i],args[3]))++dir_i;
    if (dir_i >= argn) return 0;
    strcpy(dirent.name, args[dir_i++]);
    dirent.type = 4;
    return 1;
}
static unsigned char dclose_(void) { ++dir_closes;return fault==24?0x27:fault==25?1:directory_error; }
int main(int argc, char** argv)
{
    static struct A2fcApi api;
    static struct Panel panels[2];
    static struct Entry sel;
    static char full[80], note[120];
    static unsigned char active, copy[512];
    args = argv; argn = argc;
    strcpy(panels[0].path, argv[1]);
    strcpy(panels[1].path, argv[2]);
    strcpy(sel.name, argv[3]);
    sel.type = 4;
    fault = atoi(argv[4]);
    sprintf(full, "%s/%s", argv[1], argv[3]);
    api.panels = panels; api.active = &active; api.selected = &sel; api.full = full;
    api.note = note; api.copy_buf = copy; api.dir_entry = &dirent;
    api.memcpy = memcpy; api.memset = memset; api.strcpy = strcpy; api.strlen = strlen;
    api.strcmp = strcmp; api.sprintf = sprintf; api.fopen = open_; api.fread = read_;
    api.fwrite = write_; api.fseek = seek_; api.fclose = close_; api.remove = remove_;
    api.mli = mli_; api.dir_open = dopen_; api.dir_next = dnext_; api.dir_close = (void (*)(void))dclose_;
    api.progress_bar = bar_;
    plugin_entry(&api);
    printf("BARS %lu %lu\n", bars, overflows);
    printf("CHECK %u %lu\n",verify_closes,verify_end);
    printf("LIST %u %u\n",opens,dir_closes);
    printf("CALLS %u\n",create_calls);
    printf("WRITTEN %lu\n",output_bytes);
    printf("NOTE %s\n", note);
    return 0;
}
'''

SIM = r'''
#include <fcntl.h>
#include <unistd.h>
void bs_init(void);
void __fastcall__ bs_crc(const unsigned char* p);
extern unsigned int bs_sum;
static unsigned char line[48];
int main(void)
{
    int in = open("data.bin", O_RDONLY);
    bs_init();
    bs_sum = 0;
    while (read(in, line, 48) == 48) bs_crc(line);
    write(1, &bs_sum, 2);
    return 0;
}
'''


class Sciibin(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='sciibin-', dir='/tmp')
        cls.root = Path(cls.tmp.name)
        (cls.root / 'test.c').write_text(HARNESS)
        cls.exe = cls.root / 'test'
        subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-D_POSIX_C_SOURCE=0', '-I', str(ROOT),
                        str(cls.root / 'test.c'), '-o', str(cls.exe)], check=True,
                       capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_sb(self, files, selected, fault=0, existing=(), subdirs=()):
        """files: [(name, bytes)] in directory order; the ones after `selected` are its successors."""
        case = Path(tempfile.mkdtemp(dir=self.root))
        (case / 'S').mkdir()
        (case / 'D').mkdir()
        for d in subdirs:
            (case / 'D' / d).mkdir()
        for n, data in files:
            (case / 'S' / n).write_bytes(data)
        for e in existing:
            (case / 'D' / e).write_bytes(b'old')
        names = [n for n, _ in files]
        out = subprocess.run([str(self.exe), str(case / 'S'), str(case / 'D'), selected,
                              str(fault)] + names, capture_output=True, text=True, timeout=120)
        self.assertEqual(out.returncode, 0, out.stderr)
        for n,data in files:self.assertEqual((case/'S'/n).read_bytes(),data)
        lines = out.stdout.splitlines()
        note = [l[5:] for l in lines if l.startswith('NOTE ')][0]
        created = [l.split()[1:] for l in lines if l.startswith('CREATE ')]
        removed = [l.split()[1] for l in lines if l.startswith('REMOVE ')]
        self.bars = [int(v) for l in lines if l.startswith('BARS ') for v in l.split()[1:]]
        self.verification = [int(v) for l in lines if l.startswith('CHECK ') for v in l.split()[1:]]
        self.output_bytes=int(next(l[8:] for l in lines if l.startswith('WRITTEN ')))
        self.list_state = [int(v) for l in lines if l.startswith('LIST ') for v in l.split()[1:]]
        self.create_calls = [int(l.split()[1]) for l in lines if l.startswith('CALLS ')][0]
        made = {p.name: p.read_bytes() for p in (case / 'D').iterdir() if p.is_file()}
        self.sub_files = sorted(str(p.relative_to(case / 'D')) for d in subdirs
                                for p in (case / 'D' / d).rglob('*'))
        return note, created, removed, made

    def check(self, files, selected):
        names = [n for n, _ in files]
        texts = [d for n, d in files[names.index(selected):]]
        note, created, removed, made = self.run_sb(files, selected)
        try:
            name, access, t, a, data = ref.decode(texts)
        except ref.Bad as e:
            self.assertEqual(made, {}, (str(e), note))
            return note
        self.assertEqual(created, [[name, '%02X' % t, '%04X' % a]], note)
        self.assertEqual(made, {name: data})
        self.assertEqual(note, '%s: %d bytes, $%02X/$%04X, %d chunks.' % (
            name, len(data), t, a, (len(data) + ref.SEGMENT - 1) // ref.SEGMENT))
        return note

    def test_stream_errors_and_closes_never_validate_decoded_output(self):
        for size in (1,2560):
            payload=bytes(i&255 for i in range(size))
            text=ref.encode('DOC',payload)
            for fault in (5,6,7,9,10,11,12):
                with self.subTest(size=size,fault=fault):
                    note,created,removed,made=self.run_sb([('D.BSC',text)],'D.BSC',fault,existing=('KEEP',))
                    self.assertEqual(created,[['DOC','06','0000']])
                    self.assertEqual(removed,['DOC'])
                    self.assertEqual(made,{'KEEP':b'old',**({'DOC':payload} if fault==12 else {})})
                    self.assertIn('Cleanup failed' if fault==12 else 'removed',note)

    def test_cancel_during_data_refill_precedes_appending_decoded_bytes(self):
        for size in (768,1536,ref.SEGMENT+48):
            payload=bytes(i&255 for i in range(size))
            encoded=ref.encode('DOC',payload)
            for fault in range(28,37):
                refill=fault-33 if fault>=34 else (fault-28)//2+1
                if size==768 and refill==3:continue
                prefix=position=0
                for i,line in enumerate(encoded.split(b'\r')):
                    position+=len(line)+1
                    if position>refill*512:break
                    if i>=4 and len(line)==64:prefix+=48
                with self.subTest(size=size,fault=fault,refill=refill):
                    note,created,removed,made=self.run_sb([('D.BSC',encoded)],'D.BSC',fault,existing=('KEEP',))
                    self.assertEqual(self.output_bytes,prefix)
                    self.assertEqual(created,[['DOC','06','0000']])
                    self.assertEqual(removed,['DOC'])
                    kept=fault in (29,31,33)
                    self.assertEqual(made,{'KEEP':b'old',**({'DOC':payload[:prefix]} if kept else {})})
                    self.assertIn('Cleanup failed' if kept else 'removed',note)

    def test_data_refill_error_refuses_its_bytes_before_decoding(self):
        for size in (768,1536,ref.SEGMENT+48):
            payload=bytes(i&255 for i in range(size))
            encoded=ref.encode('DOC',payload)
            for fault in range(37,46):
                refill=fault-42 if fault>=43 else (fault-37)//2+1
                if size==768 and refill==3:continue
                prefix=position=0
                for i,line in enumerate(encoded.split(b'\r')):
                    position+=len(line)+1
                    if position>refill*512:break
                    if i>=4 and len(line)==64:prefix+=48
                with self.subTest(size=size,fault=fault,refill=refill):
                    note,created,removed,made=self.run_sb([('D.BSC',encoded)],'D.BSC',fault,existing=('KEEP',))
                    self.assertEqual(self.output_bytes,prefix)
                    self.assertEqual(created,[['DOC','06','0000']])
                    self.assertEqual(removed,['DOC'])
                    kept=fault in (38,40,42)
                    self.assertEqual(made,{'KEEP':b'old',**({'DOC':payload[:prefix]} if kept else {})})
                    self.assertIn('Cleanup failed' if kept else 'Read:',note)

    def test_chunks_cannot_exceed_declared_total_before_create_or_append(self):
        for size in (2,48,513):
            payload=bytes(i&255 for i in range(size))
            for total in set((0,size-1)):
                text=ref.encode('DOC',payload,total_size=total)
                for collision in (False,True):
                    with self.subTest(size=size,total=total,collision=collision):
                        old={'KEEP':b'old',**({'DOC':b'old'} if collision else {})}
                        note,created,removed,made=self.run_sb([('D.BSC',text)],'D.BSC',existing=tuple(old))
                        self.assertEqual(self.create_calls,0)
                        self.assertEqual(self.output_bytes,0)
                        self.assertEqual((created,removed,made),([],[],old))
                        self.assertEqual(note,'BinSCII damaged')
        for tail in (2,49,ref.SEGMENT):
            payload=b'A'*ref.SEGMENT+b'B'*tail
            text=ref.encode('DOC',payload,total_size=len(payload)-1)
            for multipart in (False,True):
                for fault in (0,18):
                    with self.subTest(tail=tail,multipart=multipart,fault=fault):
                        files=([('P.%02d'%i,part) for i,part in enumerate(self.split(text))]
                               if multipart else [('P.00',text)])
                        note,created,removed,made=self.run_sb(files,'P.00',fault,existing=('KEEP',))
                        self.assertEqual(self.output_bytes,ref.SEGMENT)
                        self.assertEqual(created,[['DOC','06','0000']])
                        self.assertEqual(removed,['DOC'])
                        self.assertEqual(made,{'KEEP':b'old',**({'DOC':payload[:ref.SEGMENT]} if fault else {})})
                        self.assertIn('Cleanup failed' if fault else 'removed',note)

    def test_bad_header_read_or_cancel_refuses_before_create(self):
        for size in (1,48,ref.SEGMENT+48):
            text=ref.encode('DOC',bytes(i&255 for i in range(size)))
            for fault in (8,27):
                for collision in (False,True):
                    with self.subTest(size=size,fault=fault,collision=collision):
                        old={'KEEP':b'old',**({'DOC':b'old'} if collision else {})}
                        note,created,removed,made=self.run_sb([('D.BSC',text)],'D.BSC',fault,existing=tuple(old))
                        self.assertEqual(self.create_calls,0)
                        self.assertEqual(created,[])
                        self.assertEqual(removed,[])
                        self.assertEqual(made,old)
                        self.assertEqual(note,'Read' if fault==8 else 'Stopped')

    def test_uncertain_directory_list_refuses_before_open_or_create(self):
        for size in (48,ref.SEGMENT+48):
            payload=bytes(i&255 for i in range(size))
            parts=self.split(ref.encode('DOC',payload))
            files=[('P.%02d'%i,p) for i,p in enumerate(parts)]+[('LAST',b'other text')]
            for fault in range(20,27):
                with self.subTest(size=size,fault=fault):
                    note,created,removed,made=self.run_sb(files,'P.00',fault,existing=('KEEP',))
                    self.assertEqual(created,[])
                    self.assertEqual(removed,[])
                    self.assertEqual(made,{'KEEP':b'old'})
                    self.assertEqual(self.list_state,[0,0 if fault==20 else 1])
                    self.assertEqual(note,'Directory unreadable.')

    def test_normalized_alphabet_accepts_del_and_high_bit_input(self):
        payload=bytes(range(256))*100
        for alphabet in (ref.ALPHABET,ref.ALPHABET[:-1]+'\x7f'):
            text=ref.encode('DOC',payload,alphabet=alphabet)
            for high in (False,True):
                with self.subTest(del_char=alphabet.endswith('\x7f'),high=high):
                    encoded=bytes(c|0x80 for c in text) if high else text
                    # The reference splits CR/LF before stripping bit 7;
                    # the shipped C also supports high-bit line endings.
                    note,created,removed,made=self.run_sb([('D.BSC',encoded)],'D.BSC')
                    self.assertEqual(made,{'DOC':payload})
                    self.assertEqual(created,[['DOC','06','0000']])
                    self.assertEqual(removed,[])
                    self.assertEqual(note,'DOC: 25600 bytes, $06/$0000, 3 chunks.')

    def test_cancelled_verification_never_reports_a_decoded_file(self):
        for fault in (13,14,15,16):
            payload=bytes(i&255 for i in range(1 if fault==15 else 1536))
            with self.subTest(fault=fault):
                note,created,removed,made=self.run_sb([('D.BSC',ref.encode('DOC',payload))],'D.BSC',fault,existing=('KEEP',))
                self.assertEqual(created,[['DOC','06','0000']])
                self.assertEqual(removed,['DOC'])
                self.assertEqual(made,{'KEEP':b'old',**({'DOC':payload} if fault==16 else {})})
                self.assertIn('Cleanup failed' if fault==16 else 'removed',note)
                self.assertEqual(self.verification,[1,0 if fault==15 else (1536 if fault==14 else 768)])

    def test_cancel_during_final_verification_close_cleans_only_owned_output(self):
        for size in (1,1536,ref.SEGMENT+48):
            payload=bytes(i&255 for i in range(size))
            for fault in (17,18,19):
                with self.subTest(size=size,fault=fault):
                    note,created,removed,made=self.run_sb(
                        [('D.BSC',ref.encode('DOC',payload))],'D.BSC',fault,existing=('KEEP',))
                    self.assertEqual(created,[['DOC','06','0000']])
                    self.assertEqual(removed,['DOC'])
                    self.assertEqual(made,{'KEEP':b'old',**({'DOC':payload} if fault==18 else {})})
                    self.assertIn('Cleanup failed' if fault==18 else 'removed',note)
                    self.assertNotIn(' chunks.',note)
                    self.assertEqual(self.verification,[1,size])

    def split(self, text):
        parts = text.split(b'FiLeStArTfIlEsTaRt')
        head = parts[0] + b'FiLeStArTfIlEsTaRt' + parts[1]
        return [head] + [b'FiLeStArTfIlEsTaRt' + p for p in parts[2:]]

    def test_single_and_multi_part(self):
        rng = random.Random(2)
        for size in (1, 48, 12288, 12289, 40000):
            data = bytes(rng.randrange(256) for _ in range(size))
            text = ref.encode('PROG.NAME', data, ftype=0xFF, aux=0x2000,
                              eol=rng.choice([b'\r', b'\n', b'\r\n']))
            with self.subTest(size=size):
                self.check([('P.BSC', text), ('OTHER', b'hello')], 'P.BSC')
                if size > ref.SEGMENT:
                    parts = self.split(text)
                    files = [('P.%02d' % i, p) for i, p in enumerate(parts)] + [('LAST', b'x')]
                    self.check(files, 'P.00')
                    # a missing part, parts out of order, an unrelated file between
                    note = self.check([files[0]] + files[2:], 'P.00')
                    self.assertTrue(note.endswith('removed.'), note)
                    note = self.check([files[1], files[0]] + files[2:], 'P.01')
                    self.assertTrue(note.startswith('Parts out of order') or note.endswith('removed.'), note)
                    note = self.check([files[0], ('NOTE', b'text'), *files[1:]], 'P.00')
                    self.assertEqual(note, 'Parts missing: PROG.NAME removed.')

    def test_conflicting_chunk_types_refuse_before_appending_data(self):
        for tail in (1,49,ref.SEGMENT):
            payload=b'A'*ref.SEGMENT+b'B'*tail
            original=self.split(ref.encode('DOC',payload,ftype=6,aux=0x2000))
            for ftype,aux in ((4,0x2000),(6,0x2001),(6,0x2100),(0x0F,0x2000)):
                changed=self.split(ref.encode('DOC',payload,ftype=ftype,aux=aux))
                for multipart in (False,True):
                    for fault in (0,18):
                        with self.subTest(tail=tail,ftype=ftype,aux=aux,multipart=multipart,fault=fault):
                            texts=[original[0],changed[1]]
                            self.assertRaises(ref.Bad,ref.decode,texts)
                            files=([('P.00',texts[0]),('P.01',texts[1])] if multipart else
                                   [('P.00',b''.join(texts))])
                            note,created,removed,made=self.run_sb(files,'P.00',fault,existing=('KEEP',))
                            self.assertEqual(created,[['DOC','06','2000']])
                            self.assertEqual(removed,['DOC'])
                            self.assertEqual(made,{'KEEP':b'old',**({'DOC':payload[:ref.SEGMENT]} if fault else {})})
                            self.assertIn('Cleanup failed' if fault else 'removed',note)

    def test_later_non_plain_chunks_refuse_before_appending_data(self):
        for tail in (1,49,ref.SEGMENT):
            payload=b'A'*ref.SEGMENT+b'B'*tail
            original=self.split(ref.encode('DOC',payload))
            for storage in (5,0x0D):
                changed=self.split(ref.encode('DOC',payload,storage=storage))
                for multipart in (False,True):
                    for fault in (0,18):
                        with self.subTest(tail=tail,storage=storage,multipart=multipart,fault=fault):
                            texts=[original[0],changed[1]]
                            self.assertRaises(ref.Bad,ref.decode,texts)
                            files=([('P.00',texts[0]),('P.01',texts[1])] if multipart else
                                   [('P.00',b''.join(texts))])
                            note,created,removed,made=self.run_sb(files,'P.00',fault,existing=('KEEP',))
                            self.assertEqual(created,[['DOC','06','0000']])
                            self.assertEqual(removed,['DOC'])
                            self.assertEqual(made,{'KEEP':b'old',**({'DOC':payload[:ref.SEGMENT]} if fault else {})})
                            self.assertIn('Cleanup failed' if fault else 'removed',note)

    def test_later_plain_storage_types_preserve_all_bytes(self):
        for tail in (1,49,ref.SEGMENT):
            payload=b'A'*ref.SEGMENT+b'B'*tail
            original=self.split(ref.encode('DOC',payload))
            for storage in (1,2,3):
                changed=self.split(ref.encode('DOC',payload,storage=storage))
                for multipart in (False,True):
                    with self.subTest(tail=tail,storage=storage,multipart=multipart):
                        texts=[original[0],changed[1]]
                        files=([('P.00',texts[0]),('P.01',texts[1])] if multipart else
                               [('P.00',b''.join(texts))])
                        note,created,removed,made=self.run_sb(files,'P.00',existing=('KEEP',))
                        self.assertEqual(created,[['DOC','06','0000']])
                        self.assertEqual((removed,made),([],{'KEEP':b'old','DOC':payload}))
                        self.assertEqual(note,f'DOC: {len(payload)} bytes, $06/$0000, 2 chunks.')

    def test_matching_chunk_types_preserve_all_bytes(self):
        for ftype,aux in ((6,0x2000),(0xFF,0xFFFF),(0xB3,0xDB07)):
            for tail in (1,49,ref.SEGMENT):
                payload=b'A'*ref.SEGMENT+b'B'*tail
                text=ref.encode('DOC',payload,ftype=ftype,aux=aux)
                for multipart in (False,True):
                    with self.subTest(ftype=ftype,aux=aux,tail=tail,multipart=multipart):
                        files=([('P.%02d'%i,part) for i,part in enumerate(self.split(text))]
                               if multipart else [('P.00',text)])
                        note,created,removed,made=self.run_sb(files,'P.00',existing=('KEEP',))
                        self.assertEqual(created,[['DOC',f'{ftype:02X}',f'{aux:04X}']])
                        self.assertEqual((removed,made),([],{'KEEP':b'old','DOC':payload}))
                        self.assertEqual(note,f'DOC: {len(payload)} bytes, ${ftype:02X}/${aux:04X}, 2 chunks.')

    def test_progress(self):
        # About 15 ms a line at 1 MHz: a 40,000-byte file is 834 lines to
        # decode and 834 to read back, the bar moving every 16 of them.
        data = bytes(range(256)) * 157
        self.check([('P.BSC', ref.encode('BIG', data))], 'P.BSC')
        lines = (len(data) + 47) // 48
        self.assertGreaterEqual(self.bars[0], 2 * (lines // 16) - 2)
        self.assertEqual(self.bars[1], 0)

    def test_damage_is_refused(self):
        text = ref.encode('DOC', bytes(range(256)) * 10)
        lines = text.split(b'\r')
        for k, pos, what in ((2, 10, 'alphabet'), (3, 20, 'header'), (4, 10, 'data line'),
                             (-3, 1, 'crc line')):
            bad = list(lines)
            i = k if k > 0 else len(bad) + k
            j = pos
            bad[i] = bad[i][:j] + (b'!' if bad[i][j:j + 1] != b'!' else b'#') + bad[i][j + 1:]
            with self.subTest(what):
                note = self.check([('D.BSC', b'\r'.join(bad))], 'D.BSC')
                self.assertIn(note, ('BinSCII damaged', 'BinSCII damaged: DOC removed.'))
        # a character swapped for another of the alphabet: only the CRCs see it
        for k, pos, what in ((3, 20, 'header'), (4, 10, 'data line'), (2, 5, 'alphabet twice')):
            bad = list(lines)
            c = bad[k][pos:pos + 1]
            bad[k] = bad[k][:pos] + (b'A' if c != b'A' else b'B') + bad[k][pos + 1:]
            with self.subTest(what):
                note = self.check([('D.BSC', b'\r'.join(bad))], 'D.BSC')
                self.assertIn(note, ('BinSCII damaged', 'BinSCII damaged: DOC removed.'))
        blanks = text.replace(b'FiLeStArTfIlEsTaRt', b'  FiLeStArTfIlEsTaRt \t')
        self.assertEqual(self.check([('B.BSC', blanks)], 'B.BSC'), 'DOC: 2560 bytes, $06/$0000, 1 chunks.')
        self.assertEqual(self.check([('N.TXT', b'just text\r')], 'N.TXT'), 'Not BinSCII text')

    def test_failures_remove_the_output(self):
        text = ref.encode('DOC', bytes(range(256)) * 10)
        for fault in (1, 2, 3):
            with self.subTest(fault=fault):
                note, created, removed, made = self.run_sb([('D.BSC', text)], 'D.BSC', fault)
                self.assertEqual((removed, made), (['DOC'], {}), note)
                self.assertTrue(note.endswith('DOC removed.'), note)
        note, created, removed, made = self.run_sb([('D.BSC', text)], 'D.BSC', 4)
        self.assertEqual((note, list(made)), ('Cleanup failed: the incomplete file stays.', ['DOC']))
        note, created, removed, made = self.run_sb([('D.BSC', text)], 'D.BSC', existing=['DOC'])
        self.assertEqual((note, made), ('DOC exists or cannot be created.', {'DOC': b'old'}))

    def test_names_made_legal(self):
        """The name in a chunk header becomes a legal ProDOS name.

        Before: the header's 1-15 characters were memcpy'd and joined to
        the destination as they were: a header named "SUB/EVIL" created
        DEST/SUB/EVIL (a file in a subfolder of the destination, never
        confirmed), "evil name" a name ProDOS would refuse. Now: upper
        case, anything but letters, digits and periods a period, leading
        non-letters dropped, as UNWRAP and UNSQ do; no letter at all is
        refused before anything is created."""
        data = b'hello world' * 10
        for raw, legal in (('SUB/EVIL', 'SUB.EVIL'), ('evil name', 'EVIL.NAME'), ('../X', 'X'),
                           ('1st:file', 'ST.FILE'), ('A' * 15, 'A' * 15), ('Ok.Name.2', 'OK.NAME.2')):
            with self.subTest(raw=raw):
                note, created, removed, made = self.run_sb([('X.BSC', ref.encode(raw, data))], 'X.BSC',
                                                           subdirs=['SUB'])
                self.assertEqual(created, [[legal, '06', '0000']], note)
                self.assertEqual(made, {legal: data})
                self.assertEqual(self.sub_files, [])
                self.assertEqual(ref.decode([ref.encode(raw, data)])[0], legal)
        for raw in ('123', '/', '..', '#$%'):
            with self.subTest(raw=raw):
                note, created, removed, made = self.run_sb([('X.BSC', ref.encode(raw, data))], 'X.BSC',
                                                           subdirs=['SUB'])
                self.assertEqual((created, made, self.sub_files), ([], {}, []), note)
                self.assertEqual(note, 'BinSCII damaged')
                self.assertRaises(ref.Bad, ref.decode, [ref.encode(raw, data)])
        # the parts of one file are matched on the name made legal
        big = bytes(range(256)) * 60
        parts = self.split(ref.encode('two parts', big))
        note = self.check([('P.%02d' % i, p) for i, p in enumerate(parts)], 'P.00')
        self.assertEqual(note, 'TWO.PARTS: 15360 bytes, $06/$0000, 2 chunks.')

    def test_padding_as_sent(self):
        """A last line padded with non-zero bytes decodes and is kept.

        Before: the decode checked the data CRC over the padding as sent,
        but the read-back recomputed it over zeros, so a file from an
        encoder that pads with anything else was written, then removed
        with "Read-back". (The real posts at hand pad with zeros.) The
        read-back now compares with the CRC of the zero-padded bytes."""
        for size in (1, 47, 49, 12288 + 5, 30000):
            rng = random.Random(size)
            data = bytes(rng.randrange(256) for _ in range(size))
            with self.subTest(size=size):
                for pad in (0, 0xFF, 0x41):
                    note = self.check([('P.BSC', ref.encode('PADDED', data, pad=pad))], 'P.BSC')
                    self.assertTrue(note.startswith('PADDED: %d bytes' % size), note)
        # the CRC line still guards the padding as sent
        text = ref.encode('PADDED', b'abc', pad=0xFF)
        good = ref.encode('PADDED', b'abc', pad=0xFE)
        lines = text.split(b'\r')
        lines[-3] = good.split(b'\r')[-3]          # the CRC of another padding
        note, created, removed, made = self.run_sb([('P.BSC', b'\r'.join(lines))], 'P.BSC')
        self.assertEqual(made, {}, note)

    def test_real_posts(self):
        v = cp2_samples.volume()
        self.check([('SHRINKIT.BSC', v['/ARCHIVES/SHRINKIT.BSC'][2])], 'SHRINKIT.BSC')
        files = [('ZLINK.%02d.BSQ' % i, v['/ARCHIVES/ZLINK.%02d.BSQ' % i][2]) for i in range(1, 6)]
        note = self.check(files, 'ZLINK.01.BSQ')
        self.assertEqual(note, 'Z.LINK.SHK: 54568 bytes, $E0/$8002, 5 chunks.')

    def test_table_crc_under_sim65(self):
        rng = random.Random(3)
        data = bytes(rng.randrange(256) for _ in range(48 * 300))
        (self.root / 'data.bin').write_bytes(data)
        shutil.copyfile(ROOT / 'src/plugins/sciibin.s', self.root / 'sciibin.s')
        (self.root / 'sim.c').write_text(SIM)
        for cpu in ('sim6502', 'sim65c02'):
            exe = self.root / cpu
            subprocess.run(['cl65', '-t', cpu, '-O', '-o', str(exe), str(self.root / 'sim.c'),
                            str(self.root / 'sciibin.s')], check=True, cwd=self.root,
                           capture_output=True)
            out = subprocess.run(['sim65', str(exe)], cwd=self.root, capture_output=True, timeout=60)
            self.assertEqual(int.from_bytes(out.stdout, 'little'), ref.crc16(data), cpu)


if __name__ == '__main__':
    unittest.main()
