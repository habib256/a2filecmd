"""Actual word processor C: paging, decoding, malformed data and I/O.

Read-only sources are byte-compared after each invocation. Deterministic
fixtures exercise chunk/record boundaries independently of decoder code.
"""
import os
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


class WordDocs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='retrotext-')
        cls.p = Path(cls.tmp.name)
        (cls.p / 'h.c').write_text(HARNESS)
        cls.executables = {}
        for name in ('multiscr', 'applewr'):
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

    def test_multiscribe_structure(self):
        header=b'\x80\x19\x01\x00\x01\x00\xb1\xe2\x02'+bytes(27)+b'\x02'
        data=header+b'\x01\x06\x00\x01\x01HELLO\rWORLD'
        rows,_,_=self.run_file('multiscr',data)
        self.assertEqual([r for r in rows if r],['HELLO','WORLD'])
        for n in list(range(len(header)))+list(range(len(header)+1,len(header)+5)):
            self.run_file('multiscr',data[:n],refused=True)
        for suffix in (b'\x01',b'\x01\x00\x00\x00\x02',b'\x02'+bytes(27),b'\x04'):
            self.run_file('multiscr',header+suffix,refused=True)

    def test_applewriter_layout_and_literal_commands(self):
        data=b'.lm2\r.rm20\r.pm+3\rHello world again today\r.cj\rTitle\r.inAddress\r'
        rows,_,_=self.run_file('applewr',data)
        self.assertEqual([r for r in rows if r],['     Hello world','  again today','          Title','       .inAddress'])
        rows2,_,_=self.run_file('applewr',bytes(c|128 for c in data))
        self.assertEqual(rows2,rows)
        self.run_file('applewr',b'A\x00B',refused=True)
        self.run_file('applewr',b'A\x01B',refused=True)
        rows,_,_=self.run_file('applewr',b'.rm999999999\r'+b'.'+b'Z'*200)
        self.assertIn('.rm999999999',rows)
        self.assertEqual(''.join(r for r in rows if r)[12:],'.'+'Z'*200)

    def test_corpus_and_io(self):
        corpus=Path(os.environ.get('A2FC_WORDPRO_CORPUS','/tmp/a2fc-wordpro-corpus'))/'extracted'
        if not corpus.is_dir():self.skipTest('real word processor corpus unavailable')
        found=0
        for path in sorted(corpus.glob('*')):
            data=path.read_bytes()
            if data[:2]==b'\x80\x19':
                rows,_,_=self.run_file('multiscr',data);self.assertTrue(any(rows));found+=1
        self.assertGreater(found,0,'real MultiScribe corpus required')
        beagle=Path.home()/'.cache/a2fc/asimov_corpus/raw/images/productivity/word_processing/beagle_write/BeagleWrite v3_2.2mg'
        if beagle.exists():
            from corpus_read import files
            _,entries=files(beagle.read_bytes())
            for name,typ,aux,data in entries:
                if name=='/FONT.EXAMPLE':self.run_file('multiscr',data)
        samples={'multiscr': next(p.read_bytes() for p in corpus.glob('*') if p.read_bytes()[:2]==b'\x80\x19'), 'applewr':b'Hello world\r'*100}
        for name,data in samples.items():
            for fault in (1,2,3):
                self.run_file(name,data,fault=fault,refused=True)
            for fault in (4,5):
                src=self.p/'source';src.write_bytes(data)
                r=subprocess.run([str(self.executables[name]),str(src),str(fault),'','1'],check=True,capture_output=True,text=True)
                self.assertIn('Read/open/close error.',r.stderr);self.assertEqual(src.read_bytes(),data)
            for size in (0,1,16777215):self.run_file(name,data,size=size)
            _,counts,_=self.run_file(name,data,keys='E');self.assertEqual(counts,(2,2))
        for p in corpus.glob('applewriterii_prodos__*'):
            if p.name.split('__')[1] in ('DEMOS','FORMLETTER','CONTRACT'):
                self.run_file('applewr',p.read_bytes())

    def test_cc65_on_both_processors(self):
        if not shutil.which('cl65') or not shutil.which('sim65'):
            self.skipTest('cc65/sim65 unavailable')
        samples = {'multiscr': b'\x80\x19\x01\x00\x01\x00\xb1\xe2\x02'+bytes(27)+b'\x02HELLO\r', 'applewr':b'.lm2\r.rm20\rHello world\r'}
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
