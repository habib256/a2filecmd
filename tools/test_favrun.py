"""Real FAVRUN C: UI requests, bounded lists, and byte-preserving save faults."""
import subprocess
import tempfile
import unittest
from pathlib import Path

import test_goto_safety as goto

ROOT = goto.ROOT

FAV_HARNESS = goto.HARNESS.replace('src/plugins/goto.c', 'src/plugins/favrun.c').replace('GOTO', 'FAVRUN')
FAV_HARNESS = FAV_HARNESS.replace('static char list_mem[585], text_mem[2001];',
                               'static char list_mem[585], text_mem[2001], current_mem[64];\n#define CURRENT current_mem')


class FavrunSafety(goto.GotoSafety):
    stem = 'FAVRUN'
    harness = FAV_HARNESS


UI = FAV_HARNESS[:FAV_HARNESS.index('int main(')] + r'''
static const char* keys;
static unsigned char program_call(unsigned char cmd,void* p) {
    char path[81];decode(path,info.path);
    if(cmd==0xC4 && path[0]=='/' && !strncmp(path,"/WORK/",6)) {
        if(fault==40)return 0x46;
        if(fault==41)return 0x27;
        memset(info.fields,0,15);
        info.fields[0]=fault==42?0:0xE3;
        info.fields[1]=fault==44?4:fault==47?0xFF:fault==48?0xFC:fault==49?0xFA:6;
        info.fields[2]=0;info.fields[3]=0x20;
        info.fields[4]=fault==43?5:fault==45?0:fault==46?13:1;
        return 0;
    }
    return file_call(cmd,p);
}
static char key(void) {return *keys ? *keys++ : KEY_ESC;}
static void clear(void) {}
static void at_xy(unsigned char x,unsigned char y) {}
static void put_text(const char* p) {}
static void bar(unsigned char x,const char* p) {}
int main(int argc,char** argv) {
    static struct A2fcApi api;
    static struct Panel panels[2];static struct Entry selected;
    static char full[81],other[81],note[80],cfgpath[64],reselect[17];
    static unsigned char buffer[512],type,active;static unsigned int aux;
    keys=argv[2];fault=atoi(argv[3]);strcpy(full,argv[4]);
    strcpy(selected.name,"STALE");selected.type=4;
    strcpy(panels[0].path,"/OLD");panels[0].count=5;panels[0].cursor=2;
    panels[0].fs=argc>5?atoi(argv[5]):FS_PRODOS;
    sprintf(cfgpath,"%s/A2FILE.CFG",argv[1]);
    if(argc>6)strcpy(cfgpath,argv[6]);
    api.full=full;api.other_full=other;api.note=note;api.copy_buf=buffer;
    api.selected=&selected;api.panels=panels;api.active=&active;
    api.cfg_path=cfgpath;api.reselect=reselect;
    api.filetype=&type;api.auxtype=&aux;
    api.fopen=open_file;api.fread=read_file;api.fwrite=write_file;api.fclose=close_file;
    api.strcpy=strcpy;api.strcmp=strcmp;api.strlen=strlen;api.mli=program_call;
    api.cgetc=key;api.clrscr=clear;api.gotoxy=at_xy;api.cputs=put_text;
    api.keys_bar=bar;api.message=put_text;
    plugin_entry(&api);
    printf("%u|%s|%s|%u|%u|%u|%u|%u|%s\n",(unsigned char)note[0],
           panels[0].path,selected.name,selected.type,selected.aux,
           panels[0].fs,panels[0].count,renames,note);
    return 0;
}
'''


class FavrunUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory(prefix='favrun-build-', dir='/tmp')
        p = Path(cls.build.name); (p/'test.c').write_text(UI); cls.exe = p/'test'
        subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-I', str(ROOT),
                        str(p/'test.c'), '-o', str(cls.exe)], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def setUp(self):
        self.case = tempfile.TemporaryDirectory(prefix='fr-', dir='/tmp')
        self.addCleanup(self.case.cleanup)
        self.p = Path(self.case.name); self.cfg = self.p/'FAVRUN.CFG'

    def run_keys(self, keys, fault=0, path='/WORK/TOOLS/APP', fs=0, home=None):
        args=[self.exe, self.p, keys, str(fault), path, str(fs)]
        if home is not None: args.append(home)
        return subprocess.check_output(args,
                                       text=True).strip().split('|')

    def test_add_selected_program_persists_path_across_load(self):
        self.run_keys('a')
        self.assertEqual(self.cfg.read_bytes(), b'/WORK/TOOLS/APP\r')
        self.assertFalse((self.p/'FAVRUN.TMP').exists())
        self.assertFalse((self.p/'FAVRUN.BAK').exists())
        before = self.cfg.read_bytes(); self.run_keys('A')
        self.assertEqual(self.cfg.read_bytes(), before)

    def test_launch_exact_favourite_uses_fresh_metadata_without_writes(self):
        self.cfg.write_bytes(b'/WORK/OTHER/ONE\r/WORK/TOOLS/APP\r')
        before = self.cfg.read_bytes()
        for fault, kind in ((0,6),(47,255),(48,252),(49,250)):
            with self.subTest(kind=kind):
                out = self.run_keys('2', fault=fault)
                self.assertEqual(out[:8], ['7','/WORK/TOOLS','APP',str(kind),'8192','0','0','0'])
                self.assertEqual(self.cfg.read_bytes(), before)

    def test_missing_protected_invalid_or_unreadable_program_is_not_requested(self):
        self.cfg.write_bytes(b'/WORK/TOOLS/APP\r'); before = self.cfg.read_bytes()
        for keys in ('A','1'):
            for fault in range(40,47):
                with self.subTest(keys=keys, fault=fault):
                    out = self.run_keys(keys, fault=fault)
                    self.assertNotEqual(out[0], '7')
                    self.assertEqual(out[1:3], ['/OLD','STALE'])
                    self.assertEqual(self.cfg.read_bytes(), before)
                    self.assertEqual(list(self.p.iterdir()), [self.cfg])

    def test_add_refuses_foreign_panel_empty_selection_and_full_list(self):
        for fs in (1,2):
            self.run_keys('A', fs=fs); self.assertFalse(self.cfg.exists())
        self.run_keys('A', path=''); self.assertFalse(self.cfg.exists())
        before = b''.join(f'/WORK/P{i}\r'.encode() for i in range(9))
        self.cfg.write_bytes(before); self.run_keys('A')
        self.assertEqual(self.cfg.read_bytes(), before)

    def test_delete_and_reorder(self):
        self.cfg.write_bytes(b'/WORK/ONE\r/WORK/TWO\r/WORK/THREE\r')
        self.run_keys('M13')
        self.assertEqual(self.cfg.read_bytes(), b'/WORK/TWO\r/WORK/THREE\r/WORK/ONE\r')
        self.run_keys('D2')
        self.assertEqual(self.cfg.read_bytes(), b'/WORK/TWO\r/WORK/ONE\r')

    def test_escape_invalid_digits_and_cancelled_edits_leave_bytes_intact(self):
        before = b'/WORK/ONE\r/WORK/TWO\r'; self.cfg.write_bytes(before)
        for keys in ('\x1b','9','D9','D\x1b','M\x1b','M1\x1b','M11'):
            with self.subTest(keys=keys):
                self.assertNotEqual(self.run_keys(keys)[0], '7')
                self.assertEqual(self.cfg.read_bytes(), before)
                self.assertEqual(list(self.p.iterdir()), [self.cfg])

    def test_malformed_lists_are_never_partly_rewritten_or_launched(self):
        for before in (b'/WORK/../APP\r', b'/WORK/A\x00B\r', b'/WORK/APP/\r',
                       b'/WORK/'+b'A'*16+b'\r', b'/WORK/1BAD\r',
                       b'/WORK/APP\r'*10, b'X'*2001):
            with self.subTest(before=before[:30]):
                self.cfg.write_bytes(before)
                for keys in ('A','D1','1'):
                    self.assertNotEqual(self.run_keys(keys)[0], '7')
                    self.assertEqual(self.cfg.read_bytes(), before)

    def test_longest_absolute_program_path(self):
        path='/WORK/'+ '/'.join(('A'*15,'B'*15,'C'*15,'D'*9))
        self.assertEqual(len(path),63)
        self.run_keys('A',path=path)
        self.assertEqual(self.cfg.read_bytes(),path.encode()+b'\r')
        out=self.run_keys('1')
        self.assertEqual(out[0],'7');self.assertEqual(out[2],'D'*9)

    def test_missing_home_and_overlong_configuration_names_refuse_before_io(self):
        before=b'/WORK/TOOLS/APP\r';self.cfg.write_bytes(before)
        home='/WORK/'+'/'.join(('A'*15,'B'*15,'C'*15,'D'*7))+'/C'
        self.assertEqual(len(home),63)
        for home in ('A2FILE.CFG',home):
            with self.subTest(home=home):
                out=self.run_keys('A',home=home)
                self.assertIn('cannot be written',out[-1])
                self.assertEqual(self.cfg.read_bytes(),before)
                self.assertEqual(list(self.p.iterdir()),[self.cfg])


if __name__ == '__main__':
    unittest.main()
