"""Actual legacy text reader C: paging, decoding, malformed data and I/O.

Read-only sources are byte-compared after each invocation. Deterministic
fixtures exercise chunk/record boundaries independently of decoder code.
"""
import gzip
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_six_plugins import PREFIX, ROOT

HARNESS = PREFIX + r'''
static int fault, reads, opens, closes, ioerr;
static int ferr(FILE* f){return ioerr || ferror(f);}
#define ferror ferr
#include RT_SOURCE
#undef ferror
static unsigned char x,y;
static char screen[24][80];
static unsigned int pages;
static const char* keys;
static void flush(void){
 unsigned char i,j;int any=0;
 for(i=1;i<22;++i)for(j=0;j<80;++j)if(screen[i][j]!=' ')any=1;
 if(!any)return;
 puts("PAGE");
 for(i=1;i<22;++i){fputc('|',stdout);fwrite(screen[i],1,80,stdout);fputc('\n',stdout);}
 memset(screen,' ',sizeof screen);
}
static void clear(void){flush();memset(screen,' ',sizeof screen);}
static void xy(unsigned char a,unsigned char b){x=a;y=b;}
static void put(char c){if(x>=79 || y<1 || y>21)abort();screen[y][x++]=c;}
static void message(const char* s){(void)s;}
static char key(void){char k=*keys;++pages;if(pages>5000)abort();flush();if(k)++keys;return k=='E'?27:' ';}
static FILE* opn(const char* p,const char* m){
 ++opens;ioerr=0;if(strcmp(m,"rb"))abort();if(fault==1)return NULL;
 return fopen(p,m);
}
static size_t rd(void* p,size_t z,size_t n,FILE* f){
 ++reads;
 if((fault==2 && reads==2)||(fault==5 && opens==2)){ioerr=1;return 0;}
 return fread(p,z,n,f);
}
static int close_(FILE* f){++closes;return fclose(f) || fault==3 || (fault==4 && closes==2)?EOF:0;}
int main(int argc,char**argv){
 static struct A2fcApi api;static struct Entry e;static unsigned char buf[512];
 static char note[80],reselect[80];fault=atoi(argv[2]);keys=argv[3];
 memset(screen,' ',sizeof screen);strcpy(e.name,"SAMPLE");e.size=strtoul(argv[4],0,10);
 api.full=argv[1];api.selected=&e;api.copy_buf=buf;api.note=note;api.reselect=reselect;
 api.fopen=opn;api.fread=rd;api.fclose=close_;api.strcpy=strcpy;api.sprintf=sprintf;
 api.gotoxy=xy;api.cputc=put;api.clrscr=clear;api.message=message;api.wait_key=key;
 plugin_entry(&api);flush();fprintf(stderr,"%d %d %s\n",opens,closes,note);return 0;
}
'''


def pascal(*chunks):
    return bytes(1024) + b''.join(c.ljust(1024, b'\0') for c in chunks)


def sc_line(number, content):
    return bytes([len(content) + 4]) + number.to_bytes(2, 'little') + content + b'\0'


def lisa(*lines):
    body = b''.join(bytes([len(line)]) + line for line in lines) + b'\xff\xff\xff'
    return b'\0\x18' + (len(body) - 1).to_bytes(2, 'little') + body


class RetroText(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='retrotext-')
        cls.p = Path(cls.tmp.name)
        (cls.p / 'h.c').write_text(HARNESS)
        cls.executables = {}
        for name in ('pastext', 'scasm', 'merlin', 'lisav2', 'guttext', 'teachtxt'):
            exe = cls.p / name
            subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-I', str(ROOT),
                            '-DRT_SOURCE="src/plugins/' + name + '.c"',
                            str(cls.p / 'h.c'), '-o', str(exe)], check=True, capture_output=True)
            cls.executables[name] = exe

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_file(self, name, data, fault=0, keys='', size=1, refused=False):
        src = self.p / 'source';src.write_bytes(data)
        r = subprocess.run([str(self.executables[name]), str(src), str(fault), keys, str(size)],
                           check=True, capture_output=True, text=True, timeout=10)
        self.assertEqual(src.read_bytes(), data)
        opens, closes, note = r.stderr.rstrip('\n').split(' ', 2)
        rows = [row[1:].rstrip() for row in r.stdout.splitlines() if row.startswith('|')]
        if refused:
            self.assertNotEqual(note, '')
            self.assertEqual(rows, [])
        else:
            self.assertEqual(note, '', r.stderr)
        return rows, (int(opens), int(closes)), note

    def test_pascal_pages_and_zero_space_indentation(self):
        data = pascal(b'\x10\x23PROGRAM HELLO;\r\x10\x20BEGIN\r', b'END.\r')
        rows, _, _ = self.run_file('pastext', data)
        self.assertEqual([r for r in rows if r], ['   PROGRAM HELLO;', 'BEGIN', 'END.'])
        data = pascal((b'X\r' * 40), (b'Y\r' * 40))
        rows, _, _ = self.run_file('pastext', data)
        self.assertEqual([r for r in rows if r], ['X']*40 + ['Y']*40)

    def test_pascal_boundaries_and_malformed_indentation(self):
        for data in (bytes(1023), pascal(b'\x10\x1fX\r'), pascal(b'X\x10\x21\r'),
                     pascal(b'X\0'), pascal(b'\0X'),
                     bytes(1024) + b'\r'*1023 + b'\x10' + b'\x21X\r',
                     bytes(1024) + b'\r'*1022 + b'XX'):
            self.run_file('pastext', data, refused=True)
        self.run_file('pastext', bytes(1024) + b'X\r')  # final partial chunk
        data = pascal(b'\x10\xffX\r')
        rows, _, _ = self.run_file('pastext', data)
        self.assertEqual(sum(len(r) for r in rows), 66)  # trailing spaces omitted from wrapped rows

    def test_sc_assembler_line_numbers_spaces_and_rle(self):
        data = sc_line(100, b'\x89LDA\x83#0') + sc_line(65535, b'\xc0\x05*')
        rows, _, _ = self.run_file('scasm', data)
        self.assertEqual([r for r in rows if r], ['0100          LDA   #0', '65535 *****'])
        for content in (b'\0X', b'\xc0', b'\xc0\x04', b'\xc1', b'\xc0\xff\0'):
            self.run_file('scasm', sc_line(1, content), refused=True)
        for n in range(len(data)):
            if n == len(sc_line(100, b'\x89LDA\x83#0')):
                continue  # a shorter complete source remains valid
            self.run_file('scasm', data[:n], refused=True)

    def test_merlin_columns_quotes_and_comments(self):
        high = lambda b: bytes(c | 128 for c in b)
        data = (high(b'LABEL LDA #$20 ;note\r') +
                high(b' ASC "A B" ;quoted space\r') +
                high(b'* Whole line comment\r') + high(b' ; Comment\r'))
        rows, _, _ = self.run_file('merlin', data)
        self.assertEqual([r for r in rows if r], [
            'LABEL    LDA   #$20       ;note',
            '         ASC   "A B"      ;quoted space',
            '* Whole line comment', '                          ; Comment'])
        self.run_file('merlin', b'ordinary text\r', refused=True)
        rows, _, _ = self.run_file('merlin', high(b' IF "=]1\r'))
        self.assertEqual([r for r in rows if r], ['         IF    "=]1'])

    def test_lisa_v2_labels_mnemonics_operands_and_comments(self):
        data = lisa(b'*comment\r', b'LABEL   \xcd\x02#$20\xbbnote\r',
                    b' \xa0\0\r', b'ONLY    \r')
        rows, _, _ = self.run_file('lisav2', data)
        self.assertEqual([r for r in rows if r], [
            '*comment', 'LABEL    LDA #$20            ;note', '         NOP', 'ONLY'])
        for n in range(len(data)):
            self.run_file('lisav2', data[:n], refused=True)
        for line in (b'\xcd\r', b'\xcd\0', b'LABEL   \x01\r', b' \xcd\x21\r', b' \xa0\0X\r'):
            self.run_file('lisav2', lisa(line), refused=True)
        rows, _, _ = self.run_file('lisav2', lisa(b'; "\0a"\r'))
        self.assertEqual([r for r in rows if r], ['; "?a"'])

    def test_gutenberg_eof_and_missing_external_glyphs(self):
        data = bytes(c | 128 for c in b'HELLO\rWORLD') + b'\x01\0IGNORED'
        rows, _, _ = self.run_file('guttext', data)
        self.assertEqual([r for r in rows if r], ['HELLO', 'WORLD?'])

    def test_teach_data_fork_macroman_and_line_ends(self):
        rows, _, _ = self.run_file('teachtxt', b'A\r\nB\nC\r\x80\x8e\x96\xff')
        self.assertEqual([r for r in rows if r], ['A', 'B', 'C', 'Aen?'])

    def test_read_open_and_close_failures_before_display(self):
        samples = {'pastext': pascal(b'HI\r'), 'scasm': sc_line(1, b'A')*120,
                   'merlin': bytes(c | 128 for c in b' LDA #0\r')*120,
                   'lisav2': lisa(*([b' \xa0\0\r']*200)),
                   'guttext': b'\xc1'*600, 'teachtxt': b'A'*600}
        for name, data in samples.items():
            for fault in (1, 2, 3):
                with self.subTest(format=name, fault=fault):
                    _, _, note = self.run_file(name, data, fault=fault, refused=True)
                    self.assertIn('error', note)

    def test_paging_cancellation_and_stale_panel_sizes(self):
        data = pascal(b'ABC\r'*100)
        for size in (0, 1, 65535, 16777215):
            rows, _, _ = self.run_file('pastext', data, size=size)
            self.assertEqual([r for r in rows if r], ['ABC']*100)
        rows, counts, _ = self.run_file('pastext', data, keys='E')
        self.assertEqual([r for r in rows if r], ['ABC']*21)
        self.assertEqual(counts, (2, 2))

    def test_render_pass_io_and_close_errors(self):
        data = pascal(b'ABC\r')
        for fault in (4, 5):
            src = self.p / 'source';src.write_bytes(data)
            r = subprocess.run([str(self.executables['pastext']), str(src), str(fault), '', '0'],
                               check=True, capture_output=True, text=True)
            self.assertIn('Read/open/close error.', r.stderr)
            self.assertEqual(src.read_bytes(), data)

    def test_real_lisa_and_merlin_sources_when_available(self):
        from legacy_corpus import dos_files
        root = Path.home() / '.cache/a2fc/asimov_corpus/raw/images/programming/assembler'
        disks = [('lisav2', Path.home() / '.cache/a2fc/cp2/fileconv_dos-files.do.gz', 0xf4),
                 ('merlin', root / 'merlin/MERLIN-8_DOS33.dsk', 4)]
        found = 0
        for plugin, disk, kind in disks:
            if not disk.exists():
                continue
            image = disk.read_bytes()
            if disk.suffix == '.gz':
                image = gzip.decompress(image)
            for name, typ, aux, data in dos_files(image):
                if typ == kind:
                    with self.subTest(plugin=plugin, name=name):
                        rows, _, _ = self.run_file(plugin, data)
                        self.assertTrue(rows)
                        found += 1
        if not found:
            self.skipTest('local LISA/Merlin corpus unavailable')

    def test_cc65_on_both_processors(self):
        if not shutil.which('cl65') or not shutil.which('sim65'):
            self.skipTest('cc65/sim65 unavailable')
        samples = {'pastext': pascal(b'HELLO\r'), 'scasm': sc_line(12, b'\x83LDA'),
                   'merlin': bytes(c | 128 for c in b' LDA #0\r'),
                   'lisav2': lisa(b' \xa0\0\r'), 'guttext': b'\xc1\xc2\0',
                   'teachtxt': b'Hello\r\x80'}
        target_path = Path(subprocess.check_output(['cl65', '--print-target-path'], text=True).strip())
        for cpu, target in (('6502', 'sim6502'), ('65c02', 'sim65c02')):
            cfg = (target_path.parent / 'cfg' / (target + '.cfg')).read_text()
            config = self.p / (target + '.cfg')
            config.write_text(cfg.replace('\n    CODE:', '\n    OVLHDR: load = MAIN, type = ro;\n    CODE:', 1))
            for name, data in samples.items():
                with self.subTest(cpu=cpu, format=name):
                    exe = self.p / (target + '-' + name)
                    subprocess.run(['cl65', '-t', target, '--cpu', cpu, '-O', '-Cl',
                                    '-C', str(config), '-I', str(ROOT),
                                    '-DRT_SOURCE="src/plugins/' + name + '.c"',
                                    '-o', str(exe), str(self.p / 'h.c')], check=True, capture_output=True)
                    src = self.p / 'native-source';src.write_bytes(data)
                    args = [str(src), '0', '', '0']
                    expected = subprocess.run([str(self.executables[name])] + args, check=True, capture_output=True)
                    actual = subprocess.run(['sim65', str(exe)] + args, check=True, capture_output=True, timeout=20)
                    self.assertEqual(actual.stdout, expected.stdout)
                    self.assertEqual(actual.stderr, expected.stderr)
                    self.assertEqual(src.read_bytes(), data)


if __name__ == '__main__':
    unittest.main()
