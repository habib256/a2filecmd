"""Execute production MCS C: exact AY bytes, faults, bounds and controls.

Sources are temporary, byte-compared after every run. AUX/file writes,
formatting and IRQ-vector services are absent from the harness.
"""
import os
import random
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_six_plugins import PREFIX, ROOT
import mcs_ref as M

HARNESS = PREFIX + r'''
static int fault, started, stopped, reads, closes, ticks, outputs, muted;
static int ferr(FILE* f){return fault==1 || (fault==4 && reads>=2) || ferror(f);}
static FILE* opn(const char* p,const char* m){
 if(strcmp(m,"rb"))abort();return fault==3?NULL:fopen(p,m);
}
static size_t rd(void* p,size_t z,size_t n,FILE* f){
 ++reads;
 if(fault==4 && reads==2)return 0;
 return fread(p,z,n,f);
}
static int cls(FILE* f){++closes;return fclose(f) || fault==2 ? EOF : 0;}
unsigned char host_song[2304];
#define ferror ferr
#include "src/plugins/mcs.c"
#undef ferror
unsigned char mc_regs[28];
static const char* keys;
void __fastcall__ mc_hw_start(unsigned char s){
 if(closes!=1 || s<1 || s>7 || s==3)abort();++started;
}
unsigned char mc_tick(void){if(++ticks>200000)abort();return 1;}
void mc_output(void){if(!started)abort();++outputs;fwrite(mc_regs,1,28,stdout);}
void mc_silence(void){if(!started)abort();++muted;}
void mc_hw_stop(void){if(!started)abort();++stopped;}
static char key(void){char k=*keys;if(k)++keys;return k=='.'?0:k=='E'?27:k;}
static void clear(void){}
static void text(const char* s){(void)s;}
int main(int argc,char** argv){
 static struct A2fcApi api;static struct Entry e;
 static unsigned char buf[512];static char note[80],sel[80];
 fault=atoi(argv[2]);api.arg=atoi(argv[3]);keys=argv[4];
 strcpy(e.name,"SONG.MCS");e.size=strtoul(argv[5],0,10);e.type=6;
 api.full=argv[1];api.selected=&e;api.note=note;api.reselect=sel;api.copy_buf=buf;
 api.fopen=opn;api.fread=rd;api.fclose=cls;api.strcpy=strcpy;
 api.cgetc=key;api.clrscr=clear;api.cputs=text;
 plugin_entry(&api);
 fprintf(stderr,"%d %d %d %d %d %d %d %s\n",started,stopped,reads,closes,ticks,outputs,muted,note);
 return 0;
}
'''


class MCS(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='mcs-host-')
        cls.p = Path(cls.tmp.name)
        (cls.p / 'h.c').write_text(HARNESS)
        cls.exe = cls.p / 'test'
        subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-I', str(ROOT),
                        str(cls.p / 'h.c'), '-o', str(cls.exe)], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_song(self, data, good=False, fault=0, slot=4, keys='', size=1):
        src = self.p / 'song'
        src.write_bytes(data)
        r = subprocess.run([str(self.exe), str(src), str(fault), str(slot), keys, str(size)],
                           check=True, capture_output=True, timeout=10)
        self.assertEqual(src.read_bytes(), data)
        fields = r.stderr.decode().split(maxsplit=7)
        counts = [int(v) for v in fields[:7]]
        self.assertEqual(counts[:2], [1, 1] if good else [0, 0], r.stderr)
        if not good:
            self.assertEqual(r.stdout, b'')
        return r.stdout, counts, fields[7] if len(fields) > 7 else ''

    def test_exact_bytes_rest_chord_tie_decay_and_stale_sizes(self):
        data = M.fixture()
        expected = b''.join(M.frames(data))
        for size in (0, 1, 2304, 65535, 16777215):
            out, _, _ = self.run_song(data, True, size=size)
            self.assertEqual(out, expected)

    def test_io_failure_before_any_card_write(self):
        for fault in (1, 2, 3, 4):
            self.run_song(M.fixture(), fault=fault)
        for slot in (0, 3, 8):
            _, counts, _ = self.run_song(M.fixture(), slot=slot)
            self.assertEqual(counts[2:4], [0, 0])

    def test_space_pause_matches_p(self):
        data = M.fixture()
        p, counts, _ = self.run_song(data, True, keys='P....P')
        space, other, _ = self.run_song(data, True, keys=' .... ')
        self.assertEqual(space, p)
        self.assertEqual(other, counts)

    def test_every_truncation_and_trailing_byte(self):
        data = M.fixture()
        for n in range(len(data)):
            self.run_song(data[:n])
        for tail in (b'X', bytes(512)):
            self.run_song(data + tail)

    def test_malformed_records_and_unterminated_chords(self):
        data = M.fixture()
        for p in (0, M.STAFF):
            for pair in (b'\x80\x01', b'\xfe\x01', b'\x20\x00', b'\x20\x40', b'\x20\x80'):
                b = bytearray(data);b[p:p+2] = pair;self.run_song(bytes(b))
            b = bytearray(data);b[p:p+M.STAFF] = bytes([60, 1]) * (M.STAFF // 2)
            self.run_song(bytes(b))
            self.run_song(M.fixture([(60, 0x81)], [(80, 1)]))
        self.run_song(M.fixture([], [(60, 1)]))

    def test_unused_tail_is_not_mistaken_for_more_music(self):
        rng = random.Random(85)
        data = bytearray(M.fixture())
        for p in M.validate(data):
            base = p // M.STAFF * M.STAFF
            data[p+2:base+M.STAFF] = rng.randbytes(base+M.STAFF-p-2)
        out, _, _ = self.run_song(bytes(data), True)
        self.assertEqual(out, b''.join(M.frames(bytes(data))))

    def test_polyphony_overflow_matches_original_voice_stealing(self):
        staff = [(p*2, 0x83) for p in range(8)] + [(30, 3)]
        data = M.fixture(staff, [(p*2, 0x83) for p in range(10, 18)] + [(50, 3)])
        out, _, _ = self.run_song(data, True)
        self.assertEqual(out, b''.join(M.frames(data)))

    def test_pause_resume_escape_restart_and_tempo(self):
        data = M.fixture()
        baseline, base, _ = self.run_song(data, True)
        out, paused, _ = self.run_song(data, True, keys='P...P')
        self.assertEqual(out, baseline[:28] + baseline)
        self.assertEqual(paused[4], base[4] + 4)
        self.assertEqual(paused[6], 1)
        _, cancelled, _ = self.run_song(data, True, keys='E')
        self.assertEqual(cancelled[4], 0)
        out, _, _ = self.run_song(data, True, keys='+')
        self.assertEqual(out, b''.join(M.frames(data, 3)))
        out, _, _ = self.run_song(data, True, keys='-')
        self.assertEqual(out, b''.join(M.frames(data, 5)))
        out, _, _ = self.run_song(data, True, keys='....R')
        self.assertEqual(out, baseline[:5*28] + baseline)

    def test_random_valid_streams(self):
        rng = random.Random(1983)
        for _ in range(50):
            staffs = []
            for s in range(2):
                staff = []
                for i in range(rng.randrange(1, 30)):
                    chord = rng.randrange(1, 10)
                    for v in range(chord):
                        staff.append((rng.randrange(64)*2, rng.randrange(1, 64) |
                                      rng.choice((0, 64)) | (128 if v+1<chord else 0)))
                staffs.append(staff)
            data = M.fixture(*staffs)
            out, _, _ = self.run_song(data, True)
            self.assertEqual(out, b''.join(M.frames(data)))

    def test_real_toolkit_exports_when_available(self):
        disk = Path(os.environ.get('A2FC_MCS_DISK',
                                   '/tmp/a2fc-mcs-player/dsk/mcs-player.dsk'))
        if not disk.exists():
            self.skipTest('reference toolkit disk unavailable; deterministic fixtures still run')
        exports = list(M.disk_exports(disk))
        self.assertGreaterEqual(len(exports), 10)
        from take1_ref import DosImage
        image = DosImage(disk.read_bytes())
        ts = image.find(b'MCS-MB')
        self.assertIsNotNone(ts)
        player = image.read_file(*ts)
        for name, data in exports:
            with self.subTest(song=name):
                out, _, _ = self.run_song(data, True)
                self.assertEqual(out, b''.join(M.frames(data)))
                self.assertEqual(out, b''.join(M.original_frames(data, player)))

    def test_production_c_on_both_6502_processors(self):
        """Actual cc65 code, with file callbacks and AY output capture."""
        if not shutil.which('cl65') or not shutil.which('sim65'):
            self.skipTest('cc65/sim65 unavailable')
        data = M.fixture()
        source = self.p / 'native-song'
        source.write_bytes(data)
        target_path = Path(subprocess.check_output(['cl65', '--print-target-path'], text=True).strip())
        for cpu, target in [('6502', 'sim6502'), ('65c02', 'sim65c02')]:
            with self.subTest(cpu=cpu):
                exe = self.p / ('native-' + cpu)
                cfg = (target_path.parent / 'cfg' / (target + '.cfg')).read_text()
                cfg = cfg.replace('\n    CODE:', '\n    OVLHDR: load = MAIN, type = ro;\n    CODE:', 1)
                config = self.p / (cpu + '.cfg');config.write_text(cfg)
                subprocess.run(['cl65', '-t', target, '--cpu', cpu, '-O', '-Cl',
                                '-C', str(config),
                                '-I', str(ROOT), '-o', str(exe), str(self.p / 'h.c')],
                               check=True, capture_output=True)
                r = subprocess.run(['sim65', str(exe), str(source), '0', '4', '', '1'],
                                   check=True, capture_output=True, timeout=20)
                self.assertEqual(r.stdout, b''.join(M.frames(data)))
                self.assertEqual(source.read_bytes(), data)


class Hardware(unittest.TestCase):
    def test_real_driver_preserves_configuration_silences_and_has_no_aux_writes(self):
        from mos6502 import CPU
        for build in ('build', 'build-6502'):
            subprocess.run(['make', 'ARCH=' + ('6502' if build == 'build-6502' else 'enh'),
                            build + '/mcs.PLG'], cwd=ROOT, check=True, capture_output=True)
            path = ROOT / build / 'mcs.PLG'
            if not path.exists():
                self.fail('build MCS for both CPUs before running hardware tests')
            labels = dict((n, int(a, 16)) for a, n in re.findall(
                r'^al ([0-9A-Fa-f]+) \.([^\s]+)', path.with_suffix('.lbl').read_text(), re.M))

            class Via(CPU):
                def __init__(self):
                    super().__init__()
                    self.ay = [bytearray(14), bytearray(14)]
                    self.latch = [0, 0]
                    self.ticks = 0

                def wr(self, addr, value):
                    if addr == 0xc40e:
                        bits = self.m[addr] & 127
                        bits = bits | (value & 127) if value & 128 else bits & ~(value & 127)
                        super().wr(addr, bits | 128)
                    else:
                        super().wr(addr, value)
                    if addr in (0xc400, 0xc480):
                        chip = int(addr == 0xc480)
                        if value == 7:
                            self.latch[chip] = self.m[addr + 1]
                        elif value == 6:
                            reg = self.latch[chip]
                            if reg >= 14:
                                raise AssertionError('write outside AY register set')
                            self.ay[chip][reg] = self.m[addr + 1]

                def rd(self, addr):
                    value = super().rd(addr)
                    if addr == 0xc404:
                        self.m[0xc40d] &= ~64
                    return value

            c = Via()
            binary = path.read_bytes()
            c.m[0x1b00:0x1b00+len(binary)] = binary
            old = {0xc40b: 0xa3, 0xc40e: 0x95, 0xc406: 0x34, 0xc407: 0x12,
                   0xc402: 0x67, 0xc403: 0x89, 0xc482: 0xab, 0xc483: 0xcd}
            for addr, value in old.items():
                c.m[addr] = value
            before = bytes(c.m)
            c.call(labels['_mc_hw_start'], 4)
            r = labels['_mc_regs']
            c.m[r:r+28] = bytes(range(28))
            c.call(labels['_mc_output'])
            self.assertEqual(c.ay, [bytearray(range(14)), bytearray(range(14, 28))])
            c.m[0xc40d] = 64
            self.assertEqual(c.call(labels['_mc_tick']), 1)
            self.assertEqual(c.call(labels['_mc_tick']), 0)
            c.call(labels['_mc_hw_stop'])
            for chip in c.ay:
                self.assertEqual(chip[7:11], b'\x3f\0\0\0')
            for addr, value in old.items():
                self.assertEqual(c.m[addr], value, (build, hex(addr)))
            allowed = lambda a: (0x80 <= a < 0x9a or 0x100 <= a < 0x200 or
                                 0x1b00 <= a < 0x3000 or 0xc400 <= a < 0xc490)
            self.assertTrue(all(allowed(a) for a in c.writes),
                            [hex(a) for a in c.writes if not allowed(a)])
            for start, end in ((0, 0x80), (0x3000, 0xc000), (0xc000, 0xc100), (0xd000, 0x10000)):
                self.assertEqual(bytes(c.m[start:end]), before[start:end])


if __name__ == '__main__':
    unittest.main()
