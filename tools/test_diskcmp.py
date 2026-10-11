"""Run DISKCMP's actual entry point against mocked ProDOS units and images.

Two drives may carry the same volume name -- an original and its backup in
S6,D1 and S6,D2 -- and a comparison of a volume with itself must never be
reported as "Identical".
"""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_six_plugins import PREFIX, ROOT

HARNESS = PREFIX + r"""
#define ferror error_
static int error_(FILE*);
#include "src/plugins/diskcmp.c"
static FILE* disks[16];
static char names[16][16];
static unsigned int reads[16];
static const char* typed;
static const char* format;
static FILE* images[2], *errored;
static unsigned char image_mode, dir_index, opened, closed, single_mode, mounted=6;
static unsigned int swaps;
static int fault;
static unsigned int dir_calls,dir_closes,image_reads;
static unsigned char directory_error;
static struct DirEntry de;
static int error_(FILE* f){return f==errored;}
static FILE* open_(const char* p,const char* m){
    FILE* f=fopen(p,m);if(f)images[opened++]=f;return f;
}
static size_t read_(void* p,size_t s,size_t n,FILE* f){
    long at;size_t got;
    ++image_reads;
    if(f==errored)abort(); /* Comparison must stop at the first read error. */
    at=ftell(f);got=fread(p,s,n,f);
    if(n==64 && ((fault==31 && f==images[0]) || (fault==32 && f==images[1])))errored=f;
    if(n==512 && ((fault==3 && f==images[0] && at==0) ||
       (fault==4 && f==images[1] && at==0) ||
       (fault==5 && f==images[0] && at==279*512L) ||
       (fault==6 && f==images[1] && at==279*512L)))errored=f;
    if(n==1 && ((fault==7 && f==images[0]) || (fault==8 && f==images[1])))errored=f;
    return got;
}
static int close_(FILE* f){
    int fail=(fault==1 && f==images[0]) || (fault==2 && f==images[1]);
    int r;
    if(f==images[0])closed|=1;
    if(f==images[1])closed|=2;
    r=fclose(f);return fail ? -1:r;
}
static int seek_(FILE* f,long off,int origin){
    if(off==280*512L && ((fault==9 && f==images[0]) ||
                        (fault==10 && f==images[1])))return -1;
    return fseek(f,off,origin);
}
static unsigned char dir_open_(const char* p){
    ++dir_calls;dir_index=0;directory_error=0;
    return !((fault==27 && dir_calls==1) || (fault==28 && dir_calls==2));
}
static unsigned char dir_next_(void){
    if((fault==29 && dir_calls==1) || (fault==30 && dir_calls==2)){
        directory_error=0x27;return 0;
    }
    if(dir_index==2)return 0;
    if((fault==25 && dir_calls==1) || (fault==26 && dir_calls==2))directory_error=0x27;
    sprintf(de.name,"%s.%s",dir_index ? "dE":"d6",format);
    de.size=280*512L+(!strcmp(format,"2MG") ? 128:0);
    ++dir_index;return 1;
}
static unsigned char dir_close_(void){
    ++dir_closes;
    if((fault==21 && dir_calls==1) || (fault==22 && dir_calls==2))return 0x27;
    if((fault==23 && dir_calls==1) || (fault==24 && dir_calls==2))return 1;
    return directory_error;
}

static unsigned char mock_mli(unsigned char cmd, void* p)
{
    struct Online* o = p;
    struct Block* b = p;
    unsigned int i, n;
    if (cmd == 0xC5) {
        if(single_mode){
            memset(o->buffer,0,256);o->buffer[0]=0x61;
            o->buffer[1]=mounted==6 ? 'V':'W';return 0;
        }
        if (o->unit) abort();                    /* only ON_LINE of every unit here */
        memset(o->buffer, 0, 256);
        for (i = 1, n = 0; i < 16; ++i) if (names[i][0]) {
            o->buffer[n] = (unsigned char)(i << 4) | (unsigned char)strlen(names[i]);
            memcpy(o->buffer + n + 1, names[i], strlen(names[i]));
            n += 16;
        }
        return 0;
    }
    if (cmd != 0x80) abort();                    /* READ_BLOCK only: a write fails the test */
    i = single_mode ? mounted : b->unit >> 4;
    if (!disks[i]) return 0x28;
    ++reads[i];
    if(i==5 && b->block==2 && (fault==11 || (fault==12 && reads[i]==1)))return 0x27;
    if (fseek(disks[i], (long)b->block * 512, SEEK_SET)) return 0x27;
    if(fread(b->buffer,1,512,disks[i])!=512)return 0x27;
    if(single_mode && b->block==2 && swaps>=(i==6 ? 2:3)) {
        if((fault==13 && i==6) || (fault==14 && i==14))b->buffer[41]=25; /* 281 */
        if((fault==15 && i==6) || (fault==16 && i==14))b->buffer[4]=0xE1;
        if((fault==17 && i==6) || (fault==18 && i==14))return 0x27;
    }
    return 0;
}
static void message_(const char* s) {
    if(single_mode && strstr(s,"Insert /")) {
        ++swaps;mounted=strstr(s,"Insert /V ") ? 6:14;
    }
}
static char key_(void) {
    if(single_mode && ((fault==19 && swaps==1) || (fault==20 && swaps==2)))return KEY_ESC;
    return image_mode ? 'I':single_mode ? (swaps ? 13:'S'):'V';
}
static unsigned char prompt_(const char* label, const char* init, unsigned char hex)
{
    strcpy(a.input, typed); return 1;
}
static void clear_(void) {}
static int cprintf_(const char* f, ...) { return 0; }
static void bar_(const char* s, unsigned long d, unsigned long t) {}
/* argv: panel path ("" = the volume list), selected name, selected unit,
 * typed name, then unit=image pairs such as 6=/tmp/a.po */
int main(int argc, char** argv)
{
    static struct Panel panels[2];
    static struct Entry sel;
    static unsigned char scratch[512], active;
    static char input[17], note_[80], full[81], other[81];
    struct A2fcApi api;
    int i;
    for (i = 5; i < argc; ++i) {
        unsigned int u = strtoul(argv[i], 0, 16);
        disks[u] = fopen(strchr(argv[i], '=') + 1, "rb");
        strcpy(names[u], "V");
    }
    image_mode=!strcmp(argv[1],"images");single_mode=!strcmp(argv[1],"single");
    format=getenv("CMP_FORMAT");
    fault=getenv("CMP_FAULT") ? atoi(getenv("CMP_FAULT")):0;
    strcpy(panels[0].path, image_mode ? ".":single_mode ? "/V":argv[1]);
    strcpy(panels[1].path,".");
    if(image_mode)sprintf(full,"./d6.%s",format);
    strcpy(sel.name, argv[2]); sel.mdate = strtoul(argv[3], 0, 16);
    typed = argv[4];
    memset(&api, 0, sizeof api);
    api.panels = panels; api.active = &active; api.selected = &sel;
    api.copy_buf = scratch; api.input = input; api.note = note_;
    api.full = full; api.other_full = other;
    api.memcpy = memcpy; api.strcpy = strcpy; api.strcmp = strcmp; api.strlen = strlen;
    api.sprintf = sprintf; api.message = message_; api.cgetc = key_; api.prompt = prompt_;
    api.mli = mock_mli; api.clrscr = clear_; api.cprintf = cprintf_; api.progress_bar = bar_;
    api.fopen=open_;api.fread=read_;api.fseek=seek_;api.fclose=close_;
    api.dir_open=dir_open_;api.dir_next=dir_next_;api.dir_close=(void (*)(void))dir_close_;api.dir_entry=&de;
    plugin_entry(&api);
    if(image_mode && closed!=((1<<opened)-1))abort(); /* Close every opened image. */
    fprintf(stderr,"STATE %u %u %u %u %u\n",dir_calls,dir_closes,opened,closed,image_reads);
    printf("%s\n", note_);
    for (i = 1; i < 16; ++i) if (disks[i]) printf("%x %u\n", i, reads[i]);
    return 0;
}
"""


def volume(blocks=280, name=b'V', mark=0):
    d = bytearray(blocks * 512)
    d[1028] = 0xF0 | len(name)
    d[1029:1029 + len(name)] = name
    d[1065:1067] = blocks.to_bytes(2, 'little')
    d[5 * 512 + 7] = mark
    return bytes(d)


class Diskcmp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='diskcmp-')
        cls.p = Path(cls.tmp.name)
        (cls.p / 'test.c').write_text(HARNESS)
        cls.exe = cls.p / 'test'
        subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-I', str(ROOT),
                        str(cls.p / 'test.c'), '-o', str(cls.exe)],
                       check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_cmp(self, panel, name, unit, typed, disks, fault=0):
        fmt=name.rsplit('.',1)[-1] if panel=='images' else 'PO'
        args = [str(self.exe), panel, name, '%x' % unit, typed]
        for u, data in disks.items():
            f = self.p / ('d%X.%s' % (u,fmt))
            f.write_bytes(data)
            args.append('%x=%s' % (u, f))
        run = subprocess.run(args, text=True, timeout=20, cwd=self.p,capture_output=True,check=True,
                             env={**os.environ, "CMP_FAULT": str(fault), "CMP_FORMAT": fmt})
        out=run.stdout.splitlines()
        self.io_state=tuple(map(int,run.stderr.split()[1:]))
        for u, data in disks.items():
            self.assertEqual((self.p / ('d%X.%s' % (u,fmt))).read_bytes(), data, 'read only')
        return out[0], {int(u, 16): int(n) for u, n in (l.split() for l in out[1:])}

    def test_same_name_on_two_drives_from_inside_the_volume(self):
        """The panel shows /V (resolved to the first V); the second V must be
        the OTHER drive, whose block 5 differs."""
        note, reads = self.run_cmp('/V', 'FILE', 0, 'V', {0x6: volume(), 0xE: volume(mark=1)})
        self.assertEqual(note, '1 differing blocks; first at 5.')
        self.assertTrue(reads[0x6] and reads[0xE])

    def test_same_name_on_two_drives_from_the_volume_list(self):
        for sel, other in ((0x6, 0xE), (0xE, 0x6)):
            with self.subTest(selected=sel):
                note, reads = self.run_cmp('', '/V', sel, 'V', {0x6: volume(), 0xE: volume(mark=1)})
                self.assertEqual(note, '1 differing blocks; first at 5.')
                self.assertTrue(reads[sel] and reads[other])

    def test_identical_copies_on_two_drives(self):
        note, reads = self.run_cmp('/V', 'FILE', 0, 'V', {0x6: volume(), 0xE: volume()})
        self.assertEqual(note, 'Identical: 280 blocks compared.')
        self.assertGreaterEqual(min(reads[0x6], reads[0xE]), 280)

    def test_image_errors_never_produce_a_complete_verdict(self):
        for mark in (0,1):
            for fault in range(1,7):
                with self.subTest(fault=fault,mark=mark):
                    note,_=self.run_cmp('images','d6.PO',0,'dE.PO',
                                        {0x6:volume(),0xE:volume(mark=mark)},fault)
                    self.assertNotIn('Identical',note)
                    self.assertNotIn('differing blocks',note)
                    self.assertIn('incomplete',note)

    def test_stale_image_size_cannot_hide_a_tail(self):
        for fmt in ('PO','DO'):
            for size in (1,512):
                for side in (0,1,2):
                    with self.subTest(format=fmt,size=size,side=side):
                        tail=bytes([0xAB])*size
                        disks={0x6:volume()+(tail if side in (0,2) else b''),
                               0xE:volume()+(tail if side in (1,2) else b'')}
                        note,_=self.run_cmp('images','d6.'+fmt,0,'dE.'+fmt,disks)
                        self.assertNotIn('Identical',note)
                        self.assertIn('incomplete',note)

    def test_extent_probe_errors_are_incomplete(self):
        for fault in range(7,11):
            with self.subTest(fault=fault):
                note,_=self.run_cmp('images','d6.PO',0,'dE.PO',
                                    {0x6:volume(),0xE:volume()},fault)
                self.assertNotIn('Identical',note)
                self.assertIn('incomplete',note)

    def test_identical_images(self):
        note,_=self.run_cmp('images','d6.PO',0,'dE.PO',
                            {0x6:volume(),0xE:volume()})
        self.assertEqual(note,'Identical: 280 blocks compared.')

    def test_directory_errors_cannot_validate_image_sizes(self):
        header=bytearray(64);header[:4]=b'2IMG'
        header[8:10]=(64).to_bytes(2,'little');header[12:16]=(1).to_bytes(4,'little')
        header[20:24]=(280).to_bytes(4,'little');header[24:28]=(64).to_bytes(4,'little')
        header[28:32]=(280*512).to_bytes(4,'little')
        sentinel=self.p/'KEEP';sentinel.write_bytes(b'unrelated bytes')
        for fmt in ('PO','DO','2MG'):
            image=bytes(header)+volume()+b'container comment'.ljust(64,b' ') if fmt=='2MG' else volume()
            for fault in range(21,31):
                with self.subTest(format=fmt,fault=fault):
                    note,_=self.run_cmp('images','d6.'+fmt,0,'dE.'+fmt,{6:image,14:image},fault)
                    self.assertIn('Cannot compare',note)
                    self.assertNotIn('Identical',note)
                    self.assertEqual(sentinel.read_bytes(),b'unrelated bytes')
                    source_error=fault in (21,23,25,27,29)
                    opens=0 if source_error else 1
                    self.assertEqual(self.io_state[0],1 if source_error else 2)
                    self.assertEqual(self.io_state[1],self.io_state[0]-(fault in (27,28)))
                    self.assertEqual(self.io_state[2:],(opens,opens,opens if fmt=='2MG' else 0))

    def test_full_count_header_read_error_refuses_before_payload_read(self):
        header=bytearray(64);header[:4]=b'2IMG'
        header[8:10]=(64).to_bytes(2,'little');header[12:16]=(1).to_bytes(4,'little')
        header[20:24]=(280).to_bytes(4,'little');header[24:28]=(64).to_bytes(4,'little')
        header[28:32]=(280*512).to_bytes(4,'little')
        image=bytes(header)+volume()+bytes(64)
        for fault in (31,32):
            with self.subTest(fault=fault):
                note,_=self.run_cmp('images','d6.2MG',0,'dE.2MG',{6:image,14:image},fault)
                self.assertIn('Cannot compare',note)
                expected=(1,1,1,1,1) if fault==31 else (2,2,2,3,2)
                self.assertEqual(self.io_state,expected)

    def test_identical_do_images(self):
        note,_=self.run_cmp('images','d6.DO',0,'dE.DO',
                            {0x6:volume(),0xE:volume()})
        self.assertEqual(note,'Identical: 280 blocks compared.')

    def test_2mg_trailing_chunks_do_not_change_the_disk_verdict(self):
        header=bytearray(64);header[:4]=b'2IMG'
        header[8:10]=(64).to_bytes(2,'little')
        header[12:16]=(1).to_bytes(4,'little')
        header[20:24]=(280).to_bytes(4,'little')
        header[24:28]=(64).to_bytes(4,'little')
        header[28:32]=(280*512).to_bytes(4,'little')
        note,_=self.run_cmp('images','d6.2MG',0,'dE.2MG',
                            {0x6:header+volume()+b'A'*64,
                             0xE:header+volume()+b'B'*64})
        self.assertEqual(note,'Identical: 280 blocks compared.')

    def test_unreadable_or_malformed_volume_is_not_replaced_by_another(self):
        for side in ('source','destination'):
            for kind in ('read','transient-read','header','size'):
                with self.subTest(side=side,error=kind):
                    bad=bytearray(volume(mark=1));fault=0
                    if kind=='read': fault=11
                    if kind=='transient-read': fault=12
                    if kind=='header': bad[1028]=0xE1
                    if kind=='size': bad[1065:1067]=(2).to_bytes(2,'little')
                    disks={0x5:bad,0x6:volume(),0xE:volume()}
                    panel,name,unit=('/V','FILE',0) if side=='source' else ('','/V',6)
                    note,reads=self.run_cmp(panel,name,unit,'V',disks,fault)
                    self.assertNotIn('Identical',note)
                    self.assertIn('Cannot compare',note)
                    self.assertEqual(reads[5],1)
                    self.assertEqual(reads[0xE],0)

    def test_single_drive_detects_a_changed_or_unreadable_header(self):
        for fault in range(13,19):
            with self.subTest(fault=fault):
                note,reads=self.run_cmp('single','FILE',0,'W',
                    {6:volume(),14:volume(name=b'W')},fault)
                self.assertNotIn('Identical',note)
                self.assertNotIn('differing blocks',note)
                self.assertIn('incomplete',note)
                self.assertLessEqual(reads[6],4)
                self.assertLessEqual(reads[14],2)

    def test_single_drive_cancel_during_exchange(self):
        for fault in (19,20):
            with self.subTest(fault=fault):
                note,reads=self.run_cmp('single','FILE',0,'W',
                    {6:volume(),14:volume(name=b'W')},fault)
                self.assertEqual(note,'Comparison cancelled; no complete verdict.')
                self.assertEqual(reads[6],1)
                self.assertLessEqual(reads[14],1)

    def test_single_drive_valid_swaps(self):
        note,_=self.run_cmp('single','FILE',0,'W',
            {6:volume(),14:volume(name=b'W')})
        self.assertEqual(note,'1 differing blocks; first at 2.')

    def test_a_volume_is_never_compared_with_itself(self):
        for panel, name in (('/V', 'FILE'), ('', '/V')):
            with self.subTest(panel=panel):
                note, _ = self.run_cmp(panel, name, 0x6, 'V', {0x6: volume(mark=1)})
                self.assertNotIn('Identical', note)
                self.assertIn('Cannot compare', note)


if __name__ == '__main__':
    unittest.main(verbosity=2)
