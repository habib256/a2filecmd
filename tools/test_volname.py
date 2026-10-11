"""Run the complete VOLNAME C/inline assembly with both native compilers.

MLI faults use a disposable volume-header byte array. Check its bytes and
prefix mutations, rather than trusting only the displayed error.
"""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS = r'''
#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include "volname.c"
static unsigned char disk[512], before[512], prefix[65];
static unsigned char get_error, probe_error, rename_error, cancelled, scenario;
static unsigned int sets, renames, reports, reads, draws;
static char shown[80], input[17], cfg[64], paths_before[2][64], cfg_before[64];
static unsigned char __fastcall__ mock_mli(unsigned char cmd, void* block) {
    struct Pfx* p = block;
    if (cmd == 0xC7) {
        if (get_error) return get_error; /* leave the scratch buffer stale */
        memcpy(p->path, prefix, prefix[0] + 1); return 0;
    }
    if (cmd == 0xC6) {
        ++sets;
        if (scenario == 9 && !p->path[0]) return 0x27;
        if (scenario == 10 && renames && p->path[0] == 4) return 0x27;
        if (scenario == 11 && p->path[0] == 9) return 0x27;
        if ((p->path[0] == 4 && !memcmp(p->path + 1, "/NEW", 4)) ||
            (p->path[0] == 7 && !memcmp(p->path + 1, "/LONGER", 7))) {
            if (probe_error) return probe_error;
        }
        memcpy(prefix, p->path, p->path[0] + 1); return 0;
    }
    if (cmd == 0xC2) {
        struct Rn* r = block;
        ++renames;
        if (rename_error && !((scenario == 9 || scenario == 12) && renames > 1)) return rename_error;
        disk[4] = 0xF0 | (r->new[0] - 1);
        memcpy(disk + 5, r->new + 2, r->new[0] - 1);
        probe_error = 0; return 0;
    }
    return 0x27;
}
static void __fastcall__ show(const char* s) { strcpy(shown, s); }
static void __fastcall__ report(const char* s) { ++reports; show(s); }
static unsigned char __fastcall__ answer(const char* s, const char* initial, unsigned char hex)
{ (void)s; (void)initial; (void)hex; strcpy(input, scenario >= 13 ? "LONGER" : "NEW"); return !cancelled; }
static unsigned char __fastcall__ reread(unsigned char i) { (void)i; ++reads; return 1; }
static void redraw(void) { ++draws; }
int main(int argc, char** argv) {
    static struct A2fcApi api;
    static struct Panel panels[2];
    static struct Entry selected;
    static unsigned char active, copy[512];
    unsigned int i;
    scenario = atoi(argv[1]);
    (void)argc;
    for (i = 0; i < 512; ++i) disk[i] = (unsigned char)(i * 13 + 7);
    disk[4] = 0xF3; memcpy(disk + 5, "OLD", 3);
    memcpy(before, disk, 512);
    prefix[0] = 9; memcpy(prefix + 1, "/OLD/WORK", 9);
    memset(copy, 0xA5, 512);
    /* A valid but unrelated stale prefix: previously this could be restored. */
    copy[0] = 6; memcpy(copy + 1, "/OTHER", 6);
    strcpy(panels[0].path, "/OLD/WORK");
    strcpy(panels[1].path, "/OLD/DATA");
    strcpy(cfg, "/OLD/A2FILE/A2FILE.CFG");
    if (scenario >= 13) {
        char* path = scenario == 13 ? panels[0].path : scenario == 14 ? panels[1].path : cfg;
        strcpy(path, "/OLD/"); memset(path + 5, 'A', 57); path[62] = 0;
        path[20] = path[36] = path[52] = '/'; /* legal ProDOS components, each <= 15 */
        if (scenario == 16) cfg[60] = 0; /* exactly 63 bytes after rename */
        if (scenario == 17) {
            strcpy(cfg, "/OLDISH/"); memset(cfg + 8, 'A', 55); cfg[63] = 0;
            cfg[23] = cfg[39] = cfg[55] = '/';
        }
        strcpy(paths_before[0], panels[0].path); strcpy(paths_before[1], panels[1].path); strcpy(cfg_before, cfg);
        panels[0].first = panels[1].first = 37;
    }
    get_error = scenario == 1 || scenario == 7 || scenario == 8 ? 0x27 : scenario == 2 ? 0x40 : 0;
    probe_error = scenario == 3 || scenario == 8 ? 0 : scenario == 4 ? 0x27 : 0x45;
    rename_error = scenario == 5 || scenario == 7 || scenario == 9 || scenario == 11 || scenario == 12 ? 0x27 : 0;
    cancelled = scenario == 6;
    api.panels = panels; api.active = &active; api.selected = &selected;
    api.input = input; api.copy_buf = copy; api.cfg_path = cfg;
    api.message = show; api.prompt = answer; api.report_error = report;
    api.mli = mock_mli; api.strcpy = strcpy; api.strlen = strlen;
    api.read_panel = reread; api.draw_all = redraw;
    plugin_entry(&api);
    if (scenario >= 13) {
        if (scenario <= 15) {
            if (memcmp(disk, before, 512) || sets || renames || reads || draws) return 31;
            if (prefix[0] != 9 || memcmp(prefix + 1, "/OLD/WORK", 9)) return 32;
            if (strcmp(panels[0].path, paths_before[0]) || strcmp(panels[1].path, paths_before[1]) || strcmp(cfg, cfg_before)) return 33;
            if (panels[0].first != 37 || panels[1].first != 37) return 40;
            if (!strstr(shown, "Path too long")) return 34;
        } else {
            before[4] = 0xF6; memcpy(before + 5, "LONGER", 6);
            if (memcmp(disk, before, 512) || renames != 1 || reads != 2 || draws != 1 || reports) return 35;
            if (strcmp(panels[0].path, "/LONGER/WORK") || strcmp(panels[1].path, "/LONGER/DATA")) return 36;
            if (scenario == 16 && (strlen(cfg) != 63 || memcmp(cfg, "/LONGER/", 8))) return 37;
            if (scenario == 17 && (strlen(cfg) != 63 || memcmp(cfg, "/OLDISH/", 8))) return 38;
            if (prefix[0] != 7 || memcmp(prefix + 1, "/LONGER", 7)) return 39;
        }
        return 0;
    }
    if (scenario == 0 || scenario == 10 || scenario == 12) {
        before[4] = 0xF3; memcpy(before + 5, "NEW", 3);
        if (memcmp(disk, before, 512)) return 10;
        if (renames != (scenario == 12 ? 2 : 1) || reads != 2 || draws != 1 || reports != (scenario == 10)) return 11;
        if (strcmp(panels[0].path, "/NEW/WORK") || strcmp(panels[1].path, "/NEW/DATA")) return 12;
        if (strcmp(cfg, "/NEW/A2FILE/A2FILE.CFG")) return 13;
        if (scenario != 10 && (prefix[0] != 4 || memcmp(prefix + 1, "/NEW", 4))) return 14;
        if (scenario == 10 && (prefix[0] != 9 || memcmp(prefix + 1, "/OLD/WORK", 9))) return 15;
        if (scenario == 10 && strstr(shown, "Volume renamed")) return 16;
    } else {
        if (memcmp(disk, before, 512)) return 20;
        if (scenario != 11 && (prefix[0] != 9 || memcmp(prefix + 1, "/OLD/WORK", 9))) return 21;
        if (scenario == 11 && prefix[0]) return 28; /* restoration failed: report it */
        if (strcmp(panels[0].path, "/OLD/WORK") || strcmp(cfg, "/OLD/A2FILE/A2FILE.CFG")) return 22;
        if (reads || draws) return 23;
        if (get_error && (sets || renames || reports != 1)) return 24;
        if ((scenario == 3 || scenario == 4 || scenario == 6) && renames) return 25;
        if (scenario == 5 && (renames != 2 || reports != 1)) return 26;
        if (scenario == 6 && sets) return 27;
        if (scenario == 9 && (renames != 1 || reports != 1)) return 29;
        if (scenario == 11 && (renames != 2 || reports != 2)) return 30;
    }
    return 0;
}
'''


class VolnameNative(unittest.TestCase):
    def test_mli_faults_preserve_volume_and_prefix(self):
        head = Path(os.environ.get('CC65_HEAD', str(Path.home() / 'opt/cc65-head')))
        compilers = [(shutil.which('cl65'), {}, 'sim65c02'),
                     (str(head / 'bin/cl65'), {'CC65_HOME': str(head / 'share/cc65')}, 'sim6502')]
        with tempfile.TemporaryDirectory(prefix='volname-sim-') as directory:
            tmp = Path(directory)
            # Only relocate the header for sim65; all service stubs and inline
            # assembly remain intact, including the actual path rewrite.
            source = (ROOT / 'src/plugins/volname.c').read_text().replace('"../a2fc_plugin.h"', '"a2fc_plugin.h"').replace('"OVLHDR"', '"RODATA"')
            (tmp / 'volname.c').write_text(source)
            (tmp / 'test.c').write_text(HARNESS)
            for compiler, extra, target in compilers:
                executable = tmp / target
                result = subprocess.run([compiler, '-t', target, '-O', '-Oirs', '-Cl', '--codesize', '100', '-I', str(ROOT / 'src'), '-o', str(executable), str(tmp / 'test.c')], env={**os.environ, **extra}, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                for scenario in range(18):
                    with self.subTest(target=target, scenario=scenario):
                        run = subprocess.run([shutil.which('sim65'), str(executable), str(scenario)], capture_output=True, text=True, timeout=10)
                        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)


if __name__ == '__main__':
    unittest.main()
