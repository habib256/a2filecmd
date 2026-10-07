"""Execute BOOTBLK's entrypoint with faults before/after physical I/O."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_six_plugins import PREFIX, ROOT

# Four three-block disks (boot blocks 0-1, the volume directory's block 2)
# in a file: 0 BOOT, the volume booted from; 1 TARGET; 2 OTHER, another
# volume; 3 a TARGET twin, the same volume header byte for byte but other
# entries and other boot blocks. Unit $60 holds disk `src`, unit $D0 disk
# `tgt`; argv[7] "XY" puts disk X in $D0 and Y in $60 while the question
# is on the screen ("--": no swap).
HARNESS = PREFIX + r'''
static unsigned char original[1024], replacement[1024];
#define ORIGINAL original
#define REPLACEMENT replacement
#include "src/plugins/bootblk.c"
static unsigned char disks[4][1536];
static unsigned int calls, writes, fail1, fail2;
static int mode, consent, same, tgt = 1, src = 0;
static const char* swap;
static char twins = '-';             /* 'T': a second TARGET on line, 'B': a second BOOT */
static unsigned char mock(unsigned char cmd, void* p) {
    struct Blk* io = p;
    unsigned char *disk;
    int fault;
    if (cmd == 0xC5) {
        struct Onl* o = p;
        memset(o->buf, 0, 256);
        o->buf[0] = 0x64; memcpy(o->buf + 1, "BOOT", 4);
        o->buf[16] = 0xD6; memcpy(o->buf + 17, "TARGET", 6);
        if (twins == 'T') { o->buf[32] = 0xE6; memcpy(o->buf + 33, "TARGET", 6); }
        if (twins == 'B') { o->buf[32] = 0xE4; memcpy(o->buf + 33, "BOOT", 4); }
        return 0;
    }
    ++calls;
    if ((cmd != 0x80 && cmd != 0x81) || io->block > 2) abort();
    if (io->unit != 0x60 && io->unit != 0xD0) abort();
    disk = disks[io->unit == 0xD0 ? tgt : src] + io->block * 512;
    fault = calls == fail1 || calls == fail2;
    if (cmd == 0x81) {
        if (io->unit != 0xD0) abort(); /* never write the source */
        if (io->block > 1) abort();    /* nor the volume directory */
        ++writes;
    }
    if (fault && mode == 0) return 0x27;
    if (cmd == 0x80) memcpy(io->buf, disk, 512);
    else memcpy(disk, io->buf, 512);
    if (fault) {
        if (mode == 1) return 0x27; /* completed I/O, then error */
        if (cmd == 0x80) io->buf[511] ^= 0x80;
        else disk[511] ^= 0x80; /* silent corruption caught by readback */
    }
    return 0;
}
static unsigned char confirm(const char* s) {
    (void)s;
    if (swap[0] != '-') tgt = swap[0] - '0';
    if (swap[1] != '-') src = swap[1] - '0';
    return consent;
}
int main(int argc, char** argv) {
    static struct A2fcApi api;
    static struct Panel panels[2];
    static struct Entry selected;
    static unsigned char active, copy[512];
    static char note[80];
    FILE* f;
    fail1 = atoi(argv[1]); fail2 = atoi(argv[2]); mode = atoi(argv[3]);
    consent = atoi(argv[4]); same = atoi(argv[5]);
    f = fopen(argv[6], "rb");
    if (!f || fread(disks, 1, sizeof disks, f) != sizeof disks) abort();
    fclose(f);
    swap = argv[7]; tgt = atoi(argv[8]);
    /* argv[9]: the twins; argv[10]: a panel path instead of the volume list */
    if (argc > 9) twins = argv[9][0];
    if (argc > 10 && strcmp(argv[10], "-")) strcpy(panels[0].path, argv[10]);
    strcpy(selected.name, same ? "/BOOT" : "/TARGET");
    selected.mdate = same ? 6 : 13;
    api.panels = panels; api.active = &active; api.selected = &selected;
    api.copy_buf = copy; api.note = note; api.cfg_path = "/BOOT/A2FILE/A2FILE.CFG";
    api.strcpy = strcpy; api.mli = mock; api.confirm = confirm;
    plugin_entry(&api);
    f = fopen(argv[6], "wb"); fwrite(disks, 1, sizeof disks, f); fclose(f);
    printf("%u %u\n%s\n", calls, writes, note);
    return 0;
}
'''


def disk(seed, name, header_from=None):
    """Three blocks; block 2 a ProDOS volume header named `name`."""
    data = bytearray((i * (2 * seed + 7) + 93 * seed + i // 512) & 255 for i in range(1536))
    h = data[1024:]
    h[0:4] = bytes([0, 0, 3, 0])
    h[4] = 0xF0 | len(name)
    h[5:20] = name.encode().ljust(15, b'\0')
    h[35], h[36] = 39, 13
    h[39:41] = (6).to_bytes(2, 'little')
    h[41:43] = (280).to_bytes(2, 'little')
    data[1024:] = h
    if header_from is not None:
        data[1024:1024 + 43] = header_from[1024:1024 + 43]
    return bytes(data)


class BootBlocks(unittest.TestCase):
    # The four reads of block 2 (target, source before the question; target,
    # source after) come first: block I/O call 5 is the first boot block read.
    ID = 4

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='bootblk-faults-')
        cls.root = Path(cls.tmp.name)
        source = cls.root / 'test.c'
        source.write_text(HARNESS)
        cls.exe = cls.root / 'test'
        subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-I', str(ROOT),
                        str(source), '-o', str(cls.exe)], check=True, capture_output=True)
        cls.source = disk(1, 'BOOT')
        cls.target = disk(2, 'TARGET')
        cls.other = disk(3, 'OTHER')
        cls.twin = disk(4, 'TARGET', header_from=cls.target)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_all(self, fail=0, second=0, mode=0, consent=1, same=0, swap='--', tgt=1,
                twins='-', panel='-'):
        path = self.root / 'result.bin'
        path.write_bytes(self.source + self.target + self.other + self.twin)
        result = subprocess.check_output([str(self.exe), str(fail), str(second),
                  str(mode), str(consent), str(same), str(path), swap, str(tgt),
                  twins, panel], text=True)
        counts, note = result.split('\n', 1)
        calls, writes = map(int, counts.split())
        data = path.read_bytes()
        disks = [data[i * 1536:(i + 1) * 1536] for i in range(4)]
        self.assertEqual(disks[0], self.source, 'source must remain untouched')
        return calls, writes, note, disks

    def run_case(self, fail=0, second=0, mode=0, consent=1, same=0):
        calls, writes, note, disks = self.run_all(fail, second, mode, consent, same)
        self.assertEqual(disks[1][1024:], self.target[1024:], 'no filesystem block writes')
        self.assertEqual(disks[2:], [self.other, self.twin])
        return calls, writes, note, disks[1]

    def test_success_verifies_both_blocks(self):
        calls, writes, note, target = self.run_case()
        self.assertEqual((calls, writes), (self.ID + 8, 2))
        self.assertEqual(target, self.source[:1024] + self.target[1024:])
        self.assertIn('rewritten from', note)

    def test_all_preflight_read_failures_write_nothing(self):
        for mode in (0, 1):
            for fail in range(1, self.ID + 5):
                with self.subTest(mode=mode, fail=fail):
                    calls, writes, note, target = self.run_case(fail, mode=mode)
                    self.assertEqual(writes, 0)
                    self.assertEqual(target, self.target)
                    self.assertIn('othing written', note)

    def test_install_errors_before_and_after_io_restore_both_originals(self):
        for mode in (0, 1, 2):
            for fail in range(self.ID + 5, self.ID + 9):
                with self.subTest(mode=mode, fail=fail):
                    calls, writes, note, target = self.run_case(fail, mode=mode)
                    self.assertEqual(target, self.target)
                    self.assertIn('both original blocks restored and verified', note)
                    self.assertGreaterEqual(writes, 3)

    def test_failed_restore_reports_incomplete_and_still_attempts_other_block(self):
        # Failure on second installation write, then each rollback I/O.
        for mode in (0, 1, 2):
            for offset in range(4):
                start = self.ID + (9 if mode == 2 else 8)
                second = start + offset
                with self.subTest(mode=mode, second=second):
                    calls, writes, note, target = self.run_case(
                        self.ID + (8 if mode == 2 else 7), second, mode)
                    self.assertIn('BOOT RESTORE FAILED', note)
                    self.assertEqual(writes, 4, 'both restoration writes must be attempted')
                    if offset < 2:
                        self.assertEqual(target[512:], self.target[512:])
                    else:
                        self.assertEqual(target[:512], self.target[:512])

    def test_declining_does_not_write_blocks(self):
        """Only the two block-2 reads that identify the volumes happen."""
        calls, writes, note, target = self.run_case(consent=0)
        self.assertEqual((calls, writes), (2, 0))
        self.assertEqual(target, self.target)

    def test_source_volume_is_refused(self):
        calls, writes, note, target = self.run_case(same=1)
        self.assertEqual((calls, writes), (0, 0))
        self.assertIn('volume booted from', note)
        self.assertEqual(target, self.target)


class SwappedDisk(unittest.TestCase):
    """The boot blocks go to the disk the question named, or nowhere.

    Before the fix (measured 2026-10-06 on 535682e with this harness, the
    disk in unit $D0 changed while the question was on the screen): with
    OTHER swapped in, OTHER's blocks 0 and 1 became BOOT's, 8 calls, 2
    writes, note 'Boot blocks of /TARGET rewritten from /BOOT'; the same
    with the TARGET twin (same volume header, other entries), and with a
    volume-list entry whose unit held OTHER from the start (the name was
    never checked against the unit). A source swapped during the question
    gave TARGET the boot blocks of OTHER.

    The identity is block 2 whole, all 512 bytes compared exactly: read
    before the question (where its volume name must also be the one the
    question gives) and again after it, before the first boot block read."""

    run_all = BootBlocks.run_all

    @classmethod
    def setUpClass(cls):
        BootBlocks.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def assert_untouched(self, disks, note):
        self.assertEqual(disks, [self.source, self.target, self.other, self.twin])
        self.assertIn('Nothing written', note)

    def test_another_volume_swapped_in_during_the_question(self):
        calls, writes, note, disks = self.run_all(swap='2-')
        self.assertEqual(writes, 0)
        self.assert_untouched(disks, note)
        self.assertIn('/TARGET', note)

    def test_the_same_name_with_other_contents(self):
        calls, writes, note, disks = self.run_all(swap='3-')
        self.assertEqual(writes, 0)
        self.assert_untouched(disks, note)

    def test_the_source_swapped_during_the_question(self):
        calls, writes, note, disks = self.run_all(swap='-2')
        self.assertEqual(writes, 0)
        self.assert_untouched(disks, note)
        self.assertIn('/BOOT', note)

    def test_a_stale_volume_list_entry_is_refused_before_the_question(self):
        """The selected /TARGET's unit holds OTHER: never asked, never written."""
        calls, writes, note, disks = self.run_all(tgt=2)
        self.assertEqual((calls, writes), (2, 0))
        self.assertEqual(disks, [self.source, self.target, self.other, self.twin])
        self.assertIn('not on line', note)


class TwoVolumesOfOneName(unittest.TestCase):
    """A path names a volume, not a drive. Before: find_unit took the first
    ON_LINE record with the name while ProDOS resolved the panel's path to
    either drive -- the WIPE data loss of the bug hunt, through the same
    lookup. Now refused before any block is read; a volume-list row, opened
    by its unit, is not concerned."""

    run_all = BootBlocks.run_all

    @classmethod
    def setUpClass(cls):
        BootBlocks.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_a_panel_path_on_one_target_is_written(self):
        calls, writes, note, disks = self.run_all(panel='/TARGET/SUB')
        self.assertEqual(writes, 2)
        self.assertEqual(disks[1][:1024], self.source[:1024])

    def test_two_targets_of_one_name_refuse_a_panel_path(self):
        calls, writes, note, disks = self.run_all(twins='T', panel='/TARGET/SUB')
        self.assertEqual((calls, writes), (0, 0))
        self.assertEqual(note.strip(), 'Two volumes named /TARGET: pick it in the volume list.')
        self.assertEqual(disks, [self.source, self.target, self.other, self.twin])

    def test_two_targets_of_one_name_a_volume_list_row_still_works(self):
        calls, writes, note, disks = self.run_all(twins='T')
        self.assertEqual(writes, 2)
        self.assertEqual(disks[1][:1024], self.source[:1024])

    def test_two_volumes_named_like_the_boot_volume_refuse(self):
        """The source is only known by its name (cfg_path): two drives with
        it, and the boot blocks could come from either."""
        for panel in ('-', '/TARGET'):
            with self.subTest(panel=panel):
                calls, writes, note, disks = self.run_all(twins='B', panel=panel)
                self.assertEqual((calls, writes), (0, 0))
                self.assertEqual(note.strip(), 'Two volumes named /BOOT. Nothing written.')
                self.assertEqual(disks, [self.source, self.target, self.other, self.twin])


# find_unit as each edition's cc65 compiles it -- assembly in the overlay,
# a C twin under PLUGIN_HOST -- under sim65. argv: the ON_LINE table (256
# bytes as hex), the name. Output: the unit, in hex.
SIM_HARNESS = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "p/bootblk_c.c"
static unsigned char table[256];
int main(int argc, char** argv)
{
    unsigned int i, x;
    (void)argc;
    for (i = 0; i < 256; ++i) { sscanf(argv[1] + 2 * i, "%2x", &x); table[i] = x; }
    BUF = table;
    printf("%02X\n", find_unit(argv[2]));
    return 0;
}
'''


class FindUnitCc65(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os, re, shutil
        from test_wipe import toolchains
        chains = toolchains()
        if not chains:
            raise unittest.SkipTest('no cc65 toolchain')
        cls.tmp = tempfile.TemporaryDirectory(prefix='bootblk-cc65-')
        d = cls.dir = Path(cls.tmp.name)
        (d / 'harness.c').write_text(SIM_HARNESS)
        (d / 'p').mkdir()
        shutil.copyfile(ROOT / 'src/plugins/bootblk.c', d / 'p/bootblk_c.c')
        shutil.copyfile(ROOT / 'src/a2fc_plugin.h', d / 'a2fc_plugin.h')
        cls.exe = {}
        for cpu, cl65, sim65, env, cfgdir in chains:
            cfg = (cfgdir / f'{cpu}.cfg').read_text()
            cfg = cfg.replace('    RODATA:', '    OVLHDR:   load = MAIN, type = ro;\n    RODATA:', 1)
            (d / f'{cpu}.cfg').write_text(cfg)
            exe = d / f'find-{cpu}'
            env = {**os.environ, **env}
            subprocess.run([cl65, '-t', cpu, '-C', str(d / f'{cpu}.cfg'), '-O', '-Oirs', '-Cl',
                            '-o', str(exe), str(d / 'harness.c')], check=True, cwd=d, env=env,
                           capture_output=True)
            cls.exe[cpu] = (sim65, exe, env)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def find(self, records, name, stale=()):
        t = bytearray(256)
        for i, (b, n) in enumerate(records):
            t[16 * i] = b; t[16 * i + 1:16 * i + 1 + len(n)] = n
        for i, (b, n) in enumerate(stale, len(records) + 1):
            t[16 * i] = b; t[16 * i + 1:16 * i + 1 + len(n)] = n
        got = set()
        for cpu, (sim65, exe, env) in self.exe.items():
            p = subprocess.run([sim65, str(exe), t.hex(), name], cwd=self.dir, env=env,
                               capture_output=True, text=True, timeout=60)
            self.assertEqual(p.returncode, 0, (cpu, p.stderr))
            got.add(int(p.stdout.strip(), 16))
        self.assertEqual(len(got), 1, 'the two compilers disagree')
        return got.pop()

    def test_one_volume(self):
        recs = [(0x64, b'BOOT'), (0xD6, b'TARGET'), (0x52, b'TA')]
        self.assertEqual(self.find(recs, '/TARGET'), 0xD0)
        self.assertEqual(self.find(recs, '/BOOT'), 0x60)
        self.assertEqual(self.find(recs, '/TA'), 0x50)
        self.assertEqual(self.find(recs, '/TARGE'), 0)
        self.assertEqual(self.find(recs, '/TARGETS'), 0)

    def test_two_volumes_of_one_name(self):
        recs = [(0x64, b'BOOT'), (0xD6, b'TARGET'), (0x80, b''), (0xE6, b'TARGET')]
        self.assertEqual(self.find(recs, '/TARGET'), 1)
        self.assertEqual(self.find(recs, '/BOOT'), 0x60)

    def test_a_record_past_the_terminator_is_not_a_volume(self):
        self.assertEqual(self.find([(0x64, b'BOOT')], '/TARGET', stale=[(0xD6, b'TARGET')]), 0)
        self.assertEqual(self.find([(0x64, b'BOOT')], '/BOOT', stale=[(0xE4, b'BOOT')]), 0x60)


if __name__ == '__main__':
    unittest.main()
