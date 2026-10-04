"""Run the real GROUiK driver (src/plugins/ppt3/hook.s + driver.s) and engine under sim65.

The harness is the service table: fopen/fread/fclose/fseek over real files
with injected faults, aux_consent with a scripted answer, ram_format, the
credit row. sim65 has one flat bank, so "AUX" is ordinary memory at the
engine's addresses ($0800-$1FFF, $4000-$BFFF): the harness fills it with a
pattern first and checks that NOTHING there changes before the consent, nor
at all when the answer is no or the module is not eligible. pg_call runs the
real engine image (the same bytes as A2FILE/PPT3.BIN) through the trampoline.

What a refusal must leave: pg_setup 0 = pt3_lib plays, AUX untouched, the
source still open; 2 = stop, io_bad or r set, the source closed exactly once;
from the first AUX write on, aux = 1, so pt3.c calls pg_end, which rebuilds
/RAM once and appends " /RAM rebuilt." to the note. Host zero page $60-$7F
is checked around every call. Both CPUs.

aux_consent clobbers copy_buf like the core's (ram_empty reads /RAM's
directory there): on 2026-10-03 POM2 caught the first version of the driver
staging the engine's first chunk in copy_buf across the question -- AUX $0800
received /RAM's directory block instead and INIT ran into it.
"""
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ppt3_sim
from pt3_fixture import module

ROOT = Path(__file__).resolve().parents[1]
PPT3 = ROOT / 'src/plugins/ppt3'

HARNESS = r'''
#include <stdio.h>
#include <string.h>
#include "a2fc_plugin.h"
unsigned char pt_regs[14];
const struct A2fcApi* A;
FILE* source;
unsigned int n;
unsigned char io_bad, r, aux;
unsigned char pg_setup(void), __fastcall__ pg_call(unsigned char);
void pg_end(void);
static struct A2fcApi api;
static unsigned char cfg[8], copy[512], consents, formats, pre_ok = 1, zp_ok = 1;
static unsigned char eng_reads, mod_reads, opens, closes;
static FILE *engf, *modf;
static char note[80], credit[80], cfgpath[] = "/VOL/A2FILE/A2FILE.CFG", opened[80];
static unsigned char row, col;
#define SONG ((unsigned char*)0x3700)
static unsigned char pattern(unsigned a) { return (unsigned char)(a ^ (a >> 8) ^ 0x5A); }
/* "AUX" here: $0800-$36FF and $4000-$BFFF. $3700-$3AFF is pt3.c's SONG
 * and SECOND in MAIN, which one flat bank cannot tell from AUX. */
static void fill(void) {
    unsigned a;
    for (a = 0x0800; a < 0x3700; ++a) *(unsigned char*)a = pattern(a);
    for (a = 0x4000; a < 0xC000; ++a) *(unsigned char*)a = pattern(a);
}
static unsigned char intact_from(unsigned from, unsigned to) {
    unsigned a;
    for (a = from; a < to; ++a) if (*(unsigned char*)a != pattern(a)) return 0;
    return 1;
}
static unsigned char intact(void) { return intact_from(0x0800, 0x3700) && intact_from(0x4000, 0xC000); }
static void zp_set(void) { unsigned char k; for (k = 0; k < 32; ++k) ((unsigned char*)0x60)[k] = k * 11 + 3; }
static void zp_check(void) { unsigned char k; for (k = 0; k < 32; ++k) if (((unsigned char*)0x60)[k] != (unsigned char)(k * 11 + 3)) zp_ok = 0; }
static FILE* my_fopen(const char* p, const char* m) {
    FILE* f;
    strcpy(opened, p);
    if (!strcmp(p, "/VOL/A2FILE/PPT3.BIN")) {
        if (cfg[2] == 1) return 0;
        f = fopen("eng.bin", m); engf = f;
    } else f = fopen(p, m);
    if (f) ++opens;
    return f;
}
static size_t my_fread(void* b, size_t s, size_t k, FILE* f) {
    size_t c = fread(b, s, k, f);
    if (f == engf) {
        ++eng_reads;
        if ((cfg[2] == 2 && eng_reads == 2) || (cfg[2] == 7 && eng_reads == 1)) { ((unsigned char*)f)[1] |= 4; return c / 2; }
    } else {
        ++mod_reads;
        if (cfg[2] == 5 && mod_reads == 2) { ((unsigned char*)f)[1] |= 4; return 0; }
    }
    return c;
}
static int my_fclose(FILE* f) {
    int e = fclose(f);
    ++closes;
    if (cfg[2] == 3 && f == engf) return EOF;
    if (cfg[2] == 6 && f == modf) return EOF;
    return e;
}
/* sim65 has no lseek: rewinding the module is a close and a reopen, which
 * cc65 gives the same FILE slot (the lowest free one); anything else fails. */
static int my_fseek(FILE* f, long o, int w) {
    FILE* g;
    if (cfg[2] == 4) return -1;
    if (f != modf || o || w != SEEK_SET) return 99;
    fclose(f);
    g = fopen("mod.pt3", "rb");
    return g == f ? 0 : 98;
}
/* The core's confirm_aux calls ram_empty, which reads /RAM's directory
 * block into copy_buf: the driver must not keep anything there. */
static unsigned char my_consent(void) { ++consents; if (!intact()) pre_ok = 0; memset(copy, 0xEE, 512); return cfg[1]; }
/* The /RAM driver's FORMAT writes a block into the buffer ram_format gives
 * it, MAIN $2000-$21FF (where PT3.PLG's code lies); in this flat bank that
 * is also the engine image, which pg_end must find intact afterwards. */
static unsigned char saved2000[512], restored = 1;
static unsigned char my_format(void) {
    memcpy(saved2000, (void*)0x2000, 512); memset((void*)0x2000, 0x00, 512);
    ++formats; return 1;
}
static void my_gotoxy(unsigned char x, unsigned char y) { col = x; row = y; }
static void my_cputs(const char* s) { if (row == 3 && col == 0) strcpy(credit, s); }
int main(void) {
    FILE* f; unsigned i, frames; unsigned char res, k;
    f = fopen("run.cfg", "rb"); if (!f || fread(cfg, 1, 8, f) != 8) return 10; fclose(f);
    api.version = cfg[0]; api.copy_buf = copy; api.cfg_path = cfgpath; api.note = note;
    api.fopen = my_fopen; api.fread = my_fread; api.fclose = my_fclose; api.fseek = my_fseek;
    api.aux_consent = my_consent; api.ram_format = my_format; api.gotoxy = my_gotoxy; api.cputs = my_cputs;
    A = &api;
    fill();
    modf = source = my_fopen("mod.pt3", "rb"); if (!source) return 11;
    n = fread(SONG, 1, 512, source); if (n == 0) return 12;
    while ((i = fread(copy, 1, 512, source)) != 0) n += i;    /* the scan: n is the real length */
    if (cfg[3] | cfg[4]) n = cfg[3] | cfg[4] << 8;
    if (cfg[6]) SONG[cfg[6]] ^= 0xFF;
    zp_set(); res = pg_setup(); zp_check();
    printf("setup=%u aux=%u io_bad=%u r=%u consents=%u pre=%u closed_source=%u opened=%s\n",
           res, aux, io_bad, r, consents, pre_ok, source == 0, opened);
    printf("untouched=%u low=%u credit=%s\n", intact(), intact_from(0x0800, 0x2000), credit);
    frames = cfg[5];
    if (res == 1) for (i = 0; i < frames; ++i) {
        zp_set(); k = pg_call(1); zp_check();
        printf("frame %u %u", i, k);
        for (k = 0; k < 14; ++k) printf(" %02x", pt_regs[k]);
        printf("\n");
    }
    if (source && my_fclose(source)) io_bad = 1;     /* pt3.c's done: */
    if (aux) { pg_end(); if (formats && memcmp(saved2000, (void*)0x2000, 512)) restored = 0; }
    printf("formats=%u note=[%s] zp=%u opens=%u closes=%u restored=%u\n", formats, note, zp_ok, opens, closes, restored);
    return 0;
}
'''


def cfg_for(tmp, cpu):
    target = Path(subprocess.check_output([shutil.which('cl65'), '--print-target-path'], text=True).strip())
    base = 'sim65c02' if cpu == '65c02' else 'sim6502'
    text = (target.parent / f'cfg/{base}.cfg').read_text()
    old = 'start = $0200, size = $FDF0 - __STACKSIZE__'
    assert text.count(old) == 1
    text = text.replace(old, 'start = $C100, size = $FDF0 - $C100 - __STACKSIZE__')
    old = '    BSS:      load = MAIN,   type = bss, define   = yes;'
    assert text.count(old) == 1
    # the driver's code and strings before BSS: ld65 does not write a gap
    text = text.replace(old, '    PGCODE:   load = MAIN,   type = ro;\n    PGRODATA: load = MAIN,   type = ro;\n'
                        + old + '\n    PGBSS:    load = MAIN,   type = bss;')
    path = tmp / f'{base}.cfg'
    path.write_text(text)
    return base, path


@unittest.skipUnless(ppt3_sim.available(), 'needs cc65 and sim65')
class Driver(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.TemporaryDirectory(prefix='ppt3-driver-')
        cls.tmp = Path(cls.tmpdir.name)
        cls.image, _ = ppt3_sim.build_engine(cls.tmp)
        cls.progs = {}
        for cpu in ('6502', '65c02'):
            d = cls.tmp / cpu
            d.mkdir()
            (d / 'main.c').write_text(HARNESS)
            base, cfg = cfg_for(d, cpu)
            subprocess.run(['ca65', '--cpu', cpu, '-D', 'PPT3_SIM_LAYOUT=1', '-o', str(d / 'hook.o'), str(PPT3 / 'hook.s')],
                           check=True, capture_output=True, text=True)
            subprocess.run(['cl65', '-t', base, '-C', str(cfg), '-O', '-I', str(ROOT / 'src'), '-o', str(d / 'prog'),
                            str(d / 'main.c'), str(d / 'hook.o')], check=True, capture_output=True, text=True)
            (d / 'eng.bin').write_bytes(cls.image)
            cls.progs[cpu] = d
        cls.grouik = ppt3_sim.Grouik(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir.cleanup()

    def run_case(self, data, version=6, consent=1, fault=0, n=0, frames=0, song=0, engine=None, cpus=('6502', '65c02')):
        outs = []
        for cpu in cpus:
            d = self.progs[cpu]
            (d / 'mod.pt3').write_bytes(data)
            (d / 'eng.bin').write_bytes(self.image if engine is None else engine)
            (d / 'run.cfg').write_bytes(bytes([version, consent, fault, n & 255, n >> 8, frames, song, 0]))
            r = subprocess.run(['sim65', str(d / 'prog')], cwd=d, capture_output=True, text=True, timeout=300)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            out = r.stdout
            self.assertIn('zp=1', out, 'host zero page $60-$7F changed')
            self.assertIn('pre=1', out, 'AUX written before the consent')
            self.assertIn('low=1', out, 'AUX $0800-$1FFF (/RAM\'s bitmap and directory) written')
            self.assertIn('restored=1', out, 'main $2000-$21FF not restored around ram_format')
            opens = int(re.search(r'opens=(\d+)', out)[1])
            closes = int(re.search(r'closes=(\d+)', out)[1])
            self.assertEqual(opens, closes, out)           # every file closed exactly once
            outs.append(out)
        self.assertEqual(len(set(outs)), 1, outs)           # both CPUs agree
        return outs[0]

    def field(self, out, name):
        return re.search(name + r'=(\S*)', out)[1]

    def test_plays_the_same_registers_as_the_engine_alone(self):
        data = module(2048)
        out = self.run_case(data, frames=40)
        self.assertIn('setup=1 aux=1 io_bad=0 r=0 consents=1', out)
        self.assertIn('closed_source=1 opened=/VOL/A2FILE/PPT3.BIN', out)
        self.assertIn('credit=Player: GROUiK/French Touch', out)
        self.assertIn('formats=1 note=[/RAM rebuilt.]', out)
        alone = self.grouik.run(data, frames=40)
        got = re.findall(r'frame (\d+) (\d+)((?: [0-9a-f]{2}){14})', out)
        self.assertEqual(len(got), 40)
        for (i, res, regs), (gres, out14, _) in zip(got, alone[1:]):
            self.assertEqual((int(res), bytes.fromhex(regs.replace(' ', ''))), (gres, out14), f'frame {i}')

    def test_declined_or_not_eligible_writes_nothing_to_aux(self):
        data = module(2048)
        for kw, consents in ((dict(consent=0), 1), (dict(version=5), 0), (dict(n=0x8001), 0),
                             (dict(fault=1), 0), (dict(fault=7), 0)):
            with self.subTest(**kw):
                out = self.run_case(data, **kw)
                self.assertIn(f'setup=0 aux=0 io_bad=0 r=0 consents={consents}', out)
                self.assertIn('untouched=1', out)
                self.assertIn('closed_source=0', out)           # pt3_lib still needs it
                self.assertIn('formats=0 note=[]', out)

    def test_foreign_or_stale_engine_file_is_never_used(self):
        data = module(2048)
        bad_abi = bytearray(self.image); bad_abi[4] ^= 0xFF
        for engine in (b'', self.image[:20], b'XPT3' + self.image[4:], bytes(bad_abi)):
            out = self.run_case(data, engine=engine, cpus=('6502',))
            self.assertIn('setup=0 aux=0 io_bad=0 r=0 consents=0', out)
            self.assertIn('untouched=1', out)

    def test_errors_after_the_consent_stop_and_rebuild_ram(self):
        data = module(2048)
        cases = [dict(fault=2), dict(fault=3), dict(fault=4), dict(fault=5), dict(fault=6),
                 dict(n=len(data) + 1), dict(n=len(data) - 1), dict(song=250),
                 dict(engine=self.image[:-1]), dict(engine=self.image + b'\0')]
        for kw in cases:
            with self.subTest(**{k: (len(v) if isinstance(v, bytes) else v) for k, v in kw.items()}):
                out = self.run_case(data, **kw)
                self.assertRegex(out, r'setup=2 aux=1 io_bad=[1-9] r=0 consents=1')
                self.assertIn('closed_source=1', out)
                self.assertIn('formats=1 note=[/RAM rebuilt.]', out)

    def test_init_refuses_a_module_bound_it_cannot_trust(self):
        # n below a PT3 header: the engine's INIT wrapper trips (r = 1)
        out = self.run_case(module(2048)[:150])
        self.assertIn('setup=2 aux=1 io_bad=0 r=1 consents=1', out)
        self.assertIn('formats=1 note=[/RAM rebuilt.]', out)

    def test_replay_staging_in_copy_buf_is_caught(self):
        """The 2026-10-03 POM2 failure, replayed: a driver staging in copy_buf
        across the question loads /RAM's directory as the engine's first
        block. With the harness's clobbering consent it must not play."""
        d = self.tmp / 'replay'
        shutil.copytree(PPT3, d / 'src', ignore=shutil.ignore_patterns('original'))
        drv = (d / 'src/driver.s').read_text()
        old = 'PG_STAGE        = $3900         ; pt3.c SECOND: the staging buffer'
        self.assertEqual(drv.count(old), 1)
        (d / 'src/driver.s').write_text(drv.replace(old, '.import _copy\nPG_STAGE = _copy'))
        (d / 'main.c').write_text(HARNESS.replace('static unsigned char cfg[8], copy[512]', 'unsigned char copy[512]; static unsigned char cfg[8]'))
        base, cfg = cfg_for(d, '6502')
        subprocess.run(['ca65', '-D', 'PPT3_SIM_LAYOUT=1', '-o', str(d / 'hook.o'), str(d / 'src/hook.s')],
                       check=True, capture_output=True, text=True)
        subprocess.run(['cl65', '-t', base, '-C', str(cfg), '-O', '-I', str(ROOT / 'src'), '-o', str(d / 'prog'),
                        str(d / 'main.c'), str(d / 'hook.o')], check=True, capture_output=True, text=True)
        (d / 'eng.bin').write_bytes(self.image)
        (d / 'mod.pt3').write_bytes(module(2048))
        (d / 'run.cfg').write_bytes(bytes([6, 1, 0, 0, 0, 3, 0, 0]))
        # garbage may run away: a cycle limit, and bytes, not text
        r = subprocess.run(['sim65', '-x', '400000000', str(d / 'prog')], cwd=d, capture_output=True, timeout=300)
        out = r.stdout.decode('latin-1')
        self.assertFalse(r.returncode == 0 and 'setup=1 ' in out and
                         len(re.findall(r'frame \d+ 0', out)) == 3, out)

    def test_api_offsets_match_the_header(self):
        sys.path.insert(0, str(ROOT / 'tools'))
        import test_abi_freeze as t
        offsets, off = {}, 0
        for f in t.fields('A2fcApi'):
            name = f[3:] if f.startswith('fn ') else re.split(r'[ *]', f)[-1]
            offsets[name] = off
            off += 2 if f.startswith('fn ') else t.size(f)
        text = (PPT3 / 'driver.s').read_text()
        for name, value in re.findall(r'^API_(\w+)\s*=\s*(\d+)', text, re.M):
            self.assertEqual(offsets[name.lower()], int(value), name)
        # the driver's constants come from abi.inc itself (hook.s includes it)
        self.assertIn('.include "abi.inc"', (PPT3 / 'hook.s').read_text())


if __name__ == '__main__':
    unittest.main()
