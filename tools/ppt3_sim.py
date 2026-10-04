"""Run the real PT3 engines of PT3.PLG under sim65 and return AY register streams.

grouik(): the GROUiK/French Touch engine image, assembled from
    src/plugins/ppt3/engine.s exactly as the build does, loaded at $2000
    with the module at $4000 (its AUX addresses; sim65 has one flat bank).
    The engine image lives at $2000 (PPT3_BASE).
    Every call goes through PPT3_ENTRY; the harness fills the host zero page
    $60-$7F with a pattern before each call and fails if one byte differs
    after it. Per frame: result (0 play, 1 guard trip, 2 end), the 14
    registers the A2FC host writes (PPT3_OUT), and the player's raw AYREGS.

pt3lib(): Vince Weaver's pt3_lib with the A2FC adapter (src/plugins/pt3.s),
    the module whole in memory at $8000 (16 KB at most: bit 6 of a
    page number is the adapter's cache mark), with or without the 1.77 -> 1 MHz conversion.
    Per frame: result (0, 1 error, 2 end) and the 14 registers pt_output
    would write.

Both build in a temporary directory; nothing outside it is written.
"""
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PPT3 = ROOT / 'src/plugins/ppt3'
PLUGINS = ROOT / 'src/plugins'

GROUIK_C = r'''
#include <stdio.h>
#include <stdlib.h>
#define ENTRY ((unsigned char (__fastcall__*)(unsigned char))0x2005)
static unsigned char hdr[8], rec[29];
int main(void) {
    FILE* f; unsigned n, frames, i, ayregs; unsigned char k, r, *zp = (unsigned char*)0x60;
    f = fopen("run.cfg", "rb"); if (!f || fread(hdr, 1, 8, f) != 8) return 10; fclose(f);
    frames = hdr[0] | hdr[1] << 8; ayregs = hdr[2] | hdr[3] << 8;
    f = fopen("eng.bin", "rb"); if (!f) return 11;
    n = fread((void*)0x2000, 1, 0x1B00, f); fclose(f); if (n < 64) return 12;
    f = fopen("mod.pt3", "rb"); if (!f) return 13;
    n = fread((void*)0x4000, 1, 0x8000, f); fclose(f);
    *(unsigned*)0x2016 = hdr[4] ? (hdr[4] | hdr[5] << 8) : 0x4000 + n;
    for (i = 0; i <= frames; ++i) {
        for (k = 0; k < 32; ++k) zp[k] = (unsigned char)(i * 7 + k * 13 + 1);
        r = ENTRY(i ? 1 : 0);
        for (k = 0; k < 32; ++k) if (zp[k] != (unsigned char)(i * 7 + k * 13 + 1)) return 20;
        if (!i && (hdr[6] | hdr[7])) {      /* analysis only: replace the note table */
            f = fopen("nt.bin", "rb"); if (!f || fread((void*)(hdr[6] | hdr[7] << 8), 1, 192, f) != 192) return 14; fclose(f);
        }
        rec[0] = r;
        for (k = 0; k < 14; ++k) { rec[1 + k] = ((unsigned char*)0x2008)[k]; rec[15 + k] = ((unsigned char*)ayregs)[k]; }
        fwrite(rec, 1, 29, stdout);
        if (r) break;
    }
    return 0;
}
'''

PT3LIB_C = r'''
#include <stdio.h>
#include <string.h>
extern unsigned char pt_regs[];
extern unsigned pt_end;
void __fastcall__ pt_tables(unsigned char*);
void __fastcall__ pt_hw_start(unsigned char);
unsigned char pt_init(void), pt_frame(void);
unsigned char tables[512], pt_pages[256];
unsigned char __fastcall__ pt_page(unsigned char page) {(void)page; return 0;}
static unsigned char hdr[2], rec[15];
int main(void) {
    FILE* f; unsigned n, frames, i, p; unsigned char r;
    f = fopen("run.cfg", "rb"); if (!f || fread(hdr, 1, 2, f) != 2) return 10; fclose(f);
    frames = hdr[0] | hdr[1] << 8;
    f = fopen("mod.pt3", "rb"); if (!f) return 13;
    n = fread((void*)0x8000, 1, 0x4000, f); fclose(f);
    pt_end = n;
    for (p = 0; p < 256; ++p) pt_pages[p] = p * 256u < n ? 0x80 + p : 0; /* bit 6 is the cache mark: stay in $8000-$BFFF */
    pt_tables(tables);
    r = pt_init();
    rec[0] = r; memset(rec + 1, 0, 14); fwrite(rec, 1, 15, stdout);
    if (r) return 0;
    for (i = 1; i <= frames; ++i) {
        r = pt_frame();
        rec[0] = r; memcpy(rec + 1, pt_regs, 14); fwrite(rec, 1, 15, stdout);
        if (r) break;
    }
    return 0;
}
'''

SIM_CFG_START = '$C100'


def _cfg(tmp, cpu, start):
    target = Path(subprocess.check_output([shutil.which('cl65'), '--print-target-path'], text=True).strip())
    base = 'sim65c02' if cpu == '65c02' else 'sim6502'
    cfg = (target.parent / f'cfg/{base}.cfg').read_text()
    old = 'start = $0200, size = $FDF0 - __STACKSIZE__'
    assert cfg.count(old) == 1
    cfg = cfg.replace(old, f'start = {start}, size = $FDF0 - {start} - __STACKSIZE__')
    path = tmp / f'{base}-{start[1:]}.cfg'
    path.write_text(cfg)
    return base, path


def available():
    return all(shutil.which(t) for t in ('ca65', 'ld65', 'cl65', 'sim65'))


def build_engine(tmp, source=None):
    """Assemble engine.s (optionally a patched copy of ppt3.s) -> (image bytes, labels)."""
    tmp = Path(tmp)
    src = tmp / 'ppt3src'
    if src.exists():
        shutil.rmtree(src)
    shutil.copytree(PPT3, src, ignore=shutil.ignore_patterns('original'))
    if source is not None:
        (src / 'ppt3.s').write_text(source)
    obj = tmp / 'engine.o'
    subprocess.run(['ca65', '-g', '-o', str(obj), '-I', str(src), str(src / 'engine.s')],
                   check=True, capture_output=True, text=True)
    out = tmp / 'eng.bin'
    lbl = tmp / 'eng.lbl'
    subprocess.run(['ld65', '-C', str(src / 'engine.cfg'), '-Ln', str(lbl), '-o', str(out), str(obj)],
                   check=True, capture_output=True, text=True)
    labels = {}
    for line in lbl.read_text().splitlines():
        m = re.match(r'al ([0-9A-F]+) \.(\S+)', line)
        if m:
            labels.setdefault(m[2], int(m[1], 16))
    return out.read_bytes(), labels


class Grouik:
    """A built sim65 harness for the engine; run() many modules on it."""
    def __init__(self, tmp, cpu='6502', source=None):
        self.tmp = Path(tmp) / f'grouik-{cpu}'
        self.tmp.mkdir(parents=True, exist_ok=True)
        self.image, self.labels = build_engine(self.tmp, source)
        (self.tmp / 'eng.bin').write_bytes(self.image)
        (self.tmp / 'main.c').write_text(GROUIK_C)
        base, cfg = _cfg(self.tmp, cpu, SIM_CFG_START)
        self.prog = self.tmp / 'prog'
        subprocess.run(['cl65', '-t', base, '-C', str(cfg), '-O', '-o', str(self.prog), str(self.tmp / 'main.c')],
                       check=True, capture_output=True, text=True)

    def run(self, module, frames=3000, modhi=0, note_table=None):
        """note_table: 96 periods written over the engine's NT_ after INIT
        (analysis: GROUiK's logic with a ZX table, comparable to pt3_lib's)."""
        (self.tmp / 'mod.pt3').write_bytes(module)
        ay = self.labels['AYREGS']
        nt = 0
        if note_table is not None:
            nt = self.labels['NT_']
            (self.tmp / 'nt.bin').write_bytes(b''.join(v.to_bytes(2, 'little') for v in note_table))
        (self.tmp / 'run.cfg').write_bytes(bytes([frames & 255, frames >> 8, ay & 255, ay >> 8,
                                                  modhi & 255, modhi >> 8, nt & 255, nt >> 8]))
        r = subprocess.run(['sim65', str(self.prog)], cwd=self.tmp, capture_output=True, timeout=600)
        if r.returncode:
            raise RuntimeError(f'grouik harness exit {r.returncode}')
        data = r.stdout
        assert len(data) % 29 == 0
        return [(data[i], data[i + 1:i + 15], data[i + 15:i + 29]) for i in range(0, len(data), 29)]


FAITHFUL_C = r'''
#include <stdio.h>
static unsigned char hdr[6], rec[15];
int main(void) {
    FILE* f; unsigned frames, i, ayregs; unsigned char k;
    unsigned char* zp = 0;
    f = fopen("run.cfg", "rb"); if (!f || fread(hdr, 1, 6, f) != 6) return 10; fclose(f);
    frames = hdr[0] | hdr[1] << 8; ayregs = hdr[2] | hdr[3] << 8;
    f = fopen("ppt3.bin", "rb"); if (!f) return 11;
    if (fread((void*)0x6000, 1, 0x6000, f) < 64) return 12; fclose(f);
    for (k = 0; k < 8; k += 2) { zp[0x20 + k] = k * 2; zp[0x21 + k] = 0xC0; }  /* OUT1..OUT4: plain RAM */
    zp[0x30] = 1;                                                            /* SETUP: play once */
    ((void (*)(void))0x6000)();                                              /* START: INIT */
    if (hdr[4] | hdr[5]) {                       /* analysis: a ZX note table over NT_ */
        f = fopen("nt.bin", "rb"); if (!f || fread((void*)(hdr[4] | hdr[5] << 8), 1, 192, f) != 192) return 14; fclose(f);
    }
    for (i = 1; i <= frames; ++i) {
        ((void (*)(void))0x600A)();                                          /* START+10: PLAY */
        rec[0] = zp[0x30] >> 7;
        for (k = 0; k < 14; ++k) rec[1 + k] = ((unsigned char*)ayregs)[k];
        fwrite(rec, 1, 15, stdout);
        if (rec[0]) break;
    }
    return 0;
}
'''


class Faithful:
    """The ORIGINAL player (ppt3.s without PPT3_A2FC, byte-identical to the
    ACME build of ppt3.a), assembled at $6000 with the module included the
    way the demo does it (MDLADDR), its ROUT writing into plain RAM at $C000 (modules up to 24 KB).
    Per frame: SETUP bit 7 (loop point passed) and AYREGS. The oracle for
    the A2FC engine's raw AYREGS."""
    def __init__(self, tmp, cpu='6502'):
        self.tmp = Path(tmp) / f'faithful-{cpu}'
        self.tmp.mkdir(parents=True, exist_ok=True)
        (self.tmp / 'main.c').write_text(FAITHFUL_C)
        base, cfg = _cfg(self.tmp, cpu, SIM_CFG_START)
        self.prog = self.tmp / 'prog'
        subprocess.run(['cl65', '-t', base, '-C', str(cfg), '-O', '-o', str(self.prog), str(self.tmp / 'main.c')],
                       check=True, capture_output=True, text=True)
        (self.tmp / 'faithful.cfg').write_text('MEMORY { RAM: file = %O, start = $6000, size = $6000; }\n'
                                               'SEGMENTS { CODE: load = RAM, type = rw; }\n')

    def run(self, module, frames=3000, note_table=None):
        """note_table: 96 periods written over NT_ after INIT."""
        (self.tmp / 'rt-frag.pt3').write_bytes(module)
        subprocess.run(['ca65', '-g', '-o', 'ppt3.o', '-I', str(self.tmp), str(PPT3 / 'ppt3.s')],
                       cwd=self.tmp, check=True, capture_output=True, text=True)
        subprocess.run(['ld65', '-C', 'faithful.cfg', '-Ln', 'ppt3.lbl', '-o', 'ppt3.bin', 'ppt3.o'],
                       cwd=self.tmp, check=True, capture_output=True, text=True)
        lbl = (self.tmp / 'ppt3.lbl').read_text()
        ay = int(re.search(r'al ([0-9A-F]+) \.AYREGS\b', lbl)[1], 16)
        nt = 0
        if note_table is not None:
            nt = int(re.search(r'al ([0-9A-F]+) \.NT_\b', lbl)[1], 16)
            (self.tmp / 'nt.bin').write_bytes(b''.join(v.to_bytes(2, 'little') for v in note_table))
        (self.tmp / 'run.cfg').write_bytes(bytes([frames & 255, frames >> 8, ay & 255, ay >> 8, nt & 255, nt >> 8]))
        r = subprocess.run(['sim65', str(self.prog)], cwd=self.tmp, capture_output=True, timeout=600)
        if r.returncode:
            raise RuntimeError(f'faithful harness exit {r.returncode}')
        data = r.stdout
        return [(data[i], data[i + 1:i + 15]) for i in range(0, len(data), 15)]


class Pt3lib:
    def __init__(self, tmp, cpu='6502', converted=True):
        self.tmp = Path(tmp) / f'pt3lib-{cpu}-{int(converted)}'
        self.tmp.mkdir(parents=True, exist_ok=True)
        source = (PLUGINS / 'pt3.s').read_text().replace('PT3_LOC=$3700', 'PT3_LOC=$8000')
        source = source.replace('.include "pt3lib/init.inc"', '.align 256\n.include "pt3lib/init.inc"')
        if not converted:
            source = 'PT3_DISABLE_FREQ_CONVERSION=1\nPT3_DISABLE_ENABLE_FREQ_CONVERSION=1\n' + source
        (self.tmp / 'pt3.s').write_text(source)
        (self.tmp / 'main.c').write_text(PT3LIB_C)
        base = 'sim65c02' if cpu == '65c02' else 'sim6502'
        self.prog = self.tmp / 'prog'
        subprocess.run(['cl65', '-C', str(ROOT / 'sdk/pt3-sim.cfg'), '-t', base, '-O', '--asm-include-dir', str(PLUGINS),
                        '-o', str(self.prog), str(self.tmp / 'main.c'), str(self.tmp / 'pt3.s')],
                       check=True, capture_output=True, text=True)

    def run(self, module, frames=3000):
        (self.tmp / 'mod.pt3').write_bytes(module)
        (self.tmp / 'run.cfg').write_bytes(bytes([frames & 255, frames >> 8]))
        r = subprocess.run(['sim65', str(self.prog)], cwd=self.tmp, capture_output=True, timeout=600)
        if r.returncode:
            raise RuntimeError(f'pt3lib harness exit {r.returncode}')
        data = r.stdout
        assert len(data) % 15 == 0
        return [(data[i], data[i + 1:i + 15]) for i in range(0, len(data), 15)]


if __name__ == '__main__':
    import sys
    with tempfile.TemporaryDirectory() as t:
        g = Grouik(t)
        for name in sys.argv[1:]:
            frames = g.run(Path(name).read_bytes())
            print(name, len(frames), frames[-1][0])
