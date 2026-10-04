"""GROUiK's PT3 engine (src/plugins/ppt3/engine.s + ppt3.s): what it may touch.

Every call of the real engine image runs in tools/mos6502.py, which records
each address read and written. Allowed:
  reads   the image, its variables (PPT3BSS), zero page $60-$7F, the stack
          page, and the module [$4000, modhi) -- nothing else: never
          $C000-$CFFF, never past the module;
  writes  zero page $60-$7F, the stack page, PPT3BSS, PPT3_OUT, and the
          self-modified operands the original player patches (listed here
          from its source).
Real modules (generated, plus a sample of a local corpus when present),
crafted malformed ones (pointers past the end or into $C0xx, a runaway
command stream, too many deferred commands, a sample offset on the built-in
empty sample) and random mutations. After every call: host zero page and
stack pointer restored. The malformed ones must end in a guard trip
(result 1). The register streams are cross-checked with sim65 on both CPUs.
"""
import os
import random
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ppt3_sim
from mos6502 import CPU, Halt
from pt3_fixture import module

ROOT = Path(__file__).resolve().parents[1]
CORPUS = Path(os.environ.get('A2FC_PT3_CORPUS', ROOT / 'media/pt3'))
MODULE = 0x4000
BASE = 0x2000                       # PPT3_BASE (abi.inc)
OPERANDS = [('MODADDR', 1), ('MODADDR_H', 1), ('MDADDR2', 1), ('MDADDR2_H', 1), ('LPosPtr', 1), ('LPosPtr', 5),
            ('PatsPtr', 1), ('PatsPtr', 8), ('OrnPtrs', 1), ('OrnPtrs', 8), ('SamPtrs', 1), ('SamPtrs', 8),
            ('Delay', 1), ('CrPsPtr', 0), ('CrPsPtr', 1), ('AdInPtA', 1), ('AdInPtA', 5), ('AdInPtB', 1),
            ('AdInPtB', 5), ('AdInPtC', 1), ('AdInPtC', 5), ('Version', 1), ('M2', 0),
            ('PrNote', 1), ('PrSlide', 1), ('PrSlide', 8), ('Env_Del', 1), ('ESldAdd', 1), ('ESldAdd', 9),
            ('AddToEn', 1)]   # (L3, the note-table generator's patched opcode, is not in A2FC's INIT)


def word(b, at, v):
    b[at:at + 2] = (v & 0xFFFF).to_bytes(2, 'little')


def rd16(b, at):
    return b[at] | b[at + 1] << 8


class Engine:
    def __init__(self, image, labels):
        self.image, self.labels = image, labels
        self.bss = range(labels['__PPT3BSS_RUN__'], labels['__PPT3BSS_RUN__'] + labels['__PPT3BSS_SIZE__'])
        self.code = range(BASE, BASE + len(image))
        self.operands = {labels[n] + k for n, k in OPERANDS} | set(range(BASE + 8, BASE + 22))

    def run(self, data, frames, modhi=None):
        cpu = CPU()
        cpu.m[BASE:BASE + len(self.image)] = self.image
        cpu.m[MODULE:MODULE + len(data)] = data
        for a in range(0xC000, 0xD000):
            cpu.m[a] = 0xEE              # "I/O": must never be read
        hi = MODULE + len(data) if modhi is None else modhi
        cpu.m[BASE + 22], cpu.m[BASE + 23] = hi & 255, hi >> 8
        out = []
        for i in range(frames + 1):
            zp = bytes((i * 5 + k * 17 + 3) & 255 for k in range(32))
            cpu.m[0x60:0x80] = zp
            cpu.reads.clear()
            cpu.writes.clear()
            s = cpu.s
            r = cpu.call(BASE + 5, 1 if i else 0)
            self.check(cpu, hi, zp, s)
            out.append((r, bytes(cpu.m[BASE + 8:BASE + 22])))
            if r:
                break
        return out

    def check(self, cpu, hi, zp, s):
        if bytes(cpu.m[0x60:0x80]) != zp:
            raise AssertionError('host zero page $60-$7F changed')
        if cpu.s != s:
            raise AssertionError('stack pointer not restored')
        deep = min((a for a in cpu.writes if 0x100 <= a < 0x200), default=0x1FF)
        if deep < 0x100 + s - 48:
            raise AssertionError('engine stack deeper than 48 bytes: $%04X' % deep)
        for a in cpu.reads:
            if not (a in self.code or a in self.bss or 0x60 <= a < 0x80 or 0x100 <= a < 0x200
                    or MODULE <= a < hi):
                raise AssertionError('read outside the allowed areas: $%04X' % a)
        for a in cpu.writes:
            if not (a in self.bss or a in self.operands or 0x60 <= a < 0x80 or 0x100 <= a < 0x200):
                raise AssertionError('write outside the engine variables: $%04X' % a)


@unittest.skipUnless(ppt3_sim.available(), 'needs cc65 and sim65')
class EngineAccesses(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.TemporaryDirectory(prefix='ppt3-engine-')
        image, labels = ppt3_sim.build_engine(cls.tmpdir.name)
        cls.engine = Engine(image, labels)
        cls.labels = labels

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir.cleanup()

    def plays(self, data, frames=150, **kw):
        out = self.engine.run(data, frames, **kw)
        self.assertNotEqual(out[-1][0], 1, 'unexpected guard trip')
        return out

    def trips(self, data, frames=400, **kw):
        out = self.engine.run(data, frames, **kw)
        self.assertEqual(out[-1][0], 1, 'malformed module was not refused')
        return out

    def test_generated_modules_stay_in_bounds(self):
        for size in (2048, 16384):
            self.plays(module(size), 200)

    def test_corpus_sample_stays_in_bounds(self):
        files = sorted(p for p in CORPUS.rglob('*') if p.suffix.upper() == '.PT3') if CORPUS.is_dir() else []
        if not files:
            self.skipTest('no local PT3 corpus')
        rng = random.Random(1)
        for path in rng.sample(files, min(12, len(files))):
            data = path.read_bytes()
            if len(data) > 0x8000:
                continue
            with self.subTest(path=path.name):
                out = self.engine.run(data, 150)
                self.assertNotEqual(out[-1][0], 1)

    def test_crafted_malformed_modules_trip(self):
        good = bytearray(module(2048))
        table = rd16(good, 103)
        cases = {}
        start = rd16(good, table)
        # the fixture's patterns play notes only: the sample and ornament
        # cases first select sample 1 ($D1) or ornament 0 ($40)
        for name, at, value, lead in (('pattern A past the end', table, len(good), b''),
                                      ('pattern A into $C0xx', table, 0xC010 - MODULE, b''),
                                      ('pattern B past the end', table + 2, len(good) + 300, b''),
                                      ('pattern table past the end', 103, len(good) - 3, b''),
                                      ('sample 1 past the end', 107, len(good) + 1, b'\xD1\x50'),
                                      ('sample 1 into $C0xx', 107, 0xC000 - MODULE, b'\xD1\x50'),
                                      ('sample 1 runs off the end', 107, len(good) - 4, b'\xD1\x50'),
                                      ('ornament 0 past the end', 169, len(good) - 1, b'\x40\x50')):
            b = bytearray(good)
            word(b, at, value)
            b[start:start + len(lead)] = lead
            cases[name] = b
        big = bytearray(module(16384))
        at = rd16(big, rd16(big, 103))
        big[at:at + 400] = bytes([0x20]) * 400                 # noise commands, no row end
        cases['runaway command stream'] = big
        b = bytearray(good)
        b[start:start + 11] = bytes([9] * 5 + [0x50] + [1] * 5)  # five deferred commands in a row
        cases['five deferred commands'] = b
        b = bytearray(good)
        b[start:start + 3] = bytes([3, 0x50, 40])               # sample offset 40 on the empty sample
        cases['sample offset on the built-in empty sample'] = b
        for name, data in cases.items():
            with self.subTest(name):
                self.trips(data)

    def test_bounds_the_host_cannot_trust(self):
        data = module(2048)
        for hi in (MODULE + 201, MODULE + 0x8001, 0xFFFF):
            with self.subTest(modhi=hex(hi)):
                out = self.engine.run(data, 1, modhi=hi)
                self.assertEqual(out[0][0], 1)      # INIT refuses before reading anything

    def test_do_nothing_commands_are_not_stacked(self):
        """RA21.PT3 (corpus) reads on past a channel's $00 end marker into
        more $00 bytes: each is command 0, C_NOP. The original pushes them
        all; A2FC skips the push (C_NOP does nothing) and plays on, with a
        bounded stack. Measured: the first push limit refused RA21 at frame
        3833 while pt3_lib played it."""
        b = bytearray(module(2048))
        start = rd16(b, rd16(b, 103))
        b[start:start + 41] = bytes([0x0A] * 20 + [0, 0, 6, 7] * 5 + [0x50])
        out = self.plays(bytes(b), 50)
        self.assertGreater(len(out), 40)

    def test_four_deferred_commands_still_play(self):
        b = bytearray(module(2048))
        start = rd16(b, rd16(b, 103))
        b[start:start + 9] = bytes([9] * 4 + [0x50] + [3] * 4)
        self.plays(bytes(b), 50)

    def test_random_mutations_never_escape(self):
        rng = random.Random(3)
        base = module(2048)
        for k in range(40):
            b = bytearray(base)
            for _ in range(rng.randint(1, 12)):
                at = rng.choice([rng.randrange(99, 202), rng.randrange(202, len(b))])
                b[at] = rng.randrange(256)
            with self.subTest(case=k):
                self.engine.run(bytes(b), 120)      # trip or play, never out of bounds

    def test_the_audit_sees_a_disabled_guard(self):
        """Replay: without the pattern guard the read lands in $C0xx and the
        audit says so; without the push limit five commands play on."""
        src = (ppt3_sim.PPT3 / 'ppt3.s').read_text()
        guard = '.macro MOD_LDA_C\n        JSR g_rd_c\n.endmacro'
        assert src.count(guard) == 1
        good = bytearray(module(2048))
        table = rd16(good, 103)
        b = bytearray(good)
        word(b, table, 0xC010 - MODULE)
        with tempfile.TemporaryDirectory() as t:
            image, labels = ppt3_sim.build_engine(t, src.replace(guard, '.macro MOD_LDA_C\n        LDA (z80_C),Y\n.endmacro'))
            with self.assertRaisesRegex(AssertionError, r'read outside the allowed areas: \$C0'):
                Engine(image, labels).run(bytes(b), 5)
        push = '        JSR g_push_check    ; A2FC: at most PUSH_MAX deferred commands\n'
        assert src.count(push) == 1
        b = bytearray(good)
        start = rd16(b, table)
        b[start:start + 11] = bytes([9] * 5 + [0x50] + [1] * 5)
        with tempfile.TemporaryDirectory() as t:
            image, labels = ppt3_sim.build_engine(t, src.replace(push, ''))
            self.assertEqual(Engine(image, labels).run(bytes(b), 5)[-1][0], 0)

    def test_same_registers_as_the_original_player(self):
        """The A2FC engine's AYREGS, frame by frame, equal those of GROUiK's
        original player (ppt3.s without PPT3_A2FC = the ACME build), run
        the way the demo runs it, once both have the same ZX note table
        (A2FC copies it; the original's own is scaled for a 1 MHz AY and
        is written over after its INIT): the guards, the relocated zero
        page, the wrapper and the skipped C_NOP pushes change nothing a
        valid module can hear. Generated modules, and a corpus sample."""
        from pt3_compare import zx_table
        mods = [module(2048), module(16384)]
        files = sorted(p for p in CORPUS.rglob('*') if p.suffix.upper() == '.PT3') if CORPUS.is_dir() else []
        rng = random.Random(7)
        mods += [p.read_bytes() for p in rng.sample(files, min(10, len(files)))]
        with tempfile.TemporaryDirectory() as t:
            mine, original = ppt3_sim.Grouik(t), ppt3_sim.Faithful(t)
            for k, data in enumerate(mods):
                if len(data) > 0x5000:      # the original needs player + module below $C000
                    continue
                g, f = mine.run(data, 1500), original.run(data, 1500, note_table=zx_table(data))
                n = min(len(g) - 1, len(f))
                with self.subTest(module=k):
                    self.assertGreater(n, 10)
                    for i in range(n):
                        self.assertEqual(g[i + 1][2], f[i][1], 'frame %d' % (i + 1))
                        self.assertEqual(g[i + 1][0] == 2, f[i][0] == 1, 'end, frame %d' % (i + 1))

    def init_tables(self, version, table):
        m = bytearray(module(2048))
        m[13], m[99] = ord(version), table
        cpu = CPU()
        cpu.m[BASE:BASE + len(self.engine.image)] = self.engine.image
        cpu.m[MODULE:MODULE + len(m)] = m
        hi = MODULE + len(m)
        cpu.m[BASE + 22], cpu.m[BASE + 23] = hi & 255, hi >> 8
        cpu.call(BASE + 5, 0)
        nt, vt = self.labels['NT_'], self.labels['VT_']
        return [cpu.m[nt + 2 * i] | cpu.m[nt + 2 * i + 1] << 8 for i in range(96)], bytes(cpu.m[vt:vt + 256])

    def test_tables_against_the_references(self):
        """INIT's volume tables equal pt3_lib's archived ones (3.0-3.4 and
        3.5+); its note table is the ZX one pt3_frequency_reference.json
        archives, exactly -- ST's note 23 included ($03FD; Grouik's scaled
        generator patched it to $02FD) -- and notes.inc is that file."""
        import json
        text = (ROOT / 'src/plugins/pt3lib/init.inc').read_text()
        refs = []
        for name in ('33_34', '35'):
            block = text.split(';PT3VolumeTable_' + name + ':', 1)[1].splitlines()[1:17]
            refs.append(bytes(int(v, 16) for row in block for v in re.findall(r'\$([0-9A-F]+)', row)))
        zx = json.loads((ROOT / 'tools/pt3_frequency_reference.json').read_text())
        names = {(0, True): 'PT_33_34r', (0, False): 'PT_34_35', (1, True): 'ST', (1, False): 'ST',
                 (2, True): 'ASM_34r', (2, False): 'ASM_34_35', (3, True): 'REAL_34r', (3, False): 'REAL_34_35'}
        for version in '0123456789':
            for table in range(4):
                with self.subTest(version=version, table=table):
                    nt, vt = self.init_tables(version, table)
                    self.assertEqual(vt[16:], refs[0 if version < '5' else 1][16:])
                    self.assertEqual(nt, zx[names[(table, version < '4')]])
        inc = (ROOT / 'src/plugins/ppt3/notes.inc').read_text()
        for name in ('PT_34_35', 'PT_33_34r', 'ST', 'ASM_34_35', 'ASM_34r', 'REAL_34_35', 'REAL_34r'):
            block = inc.split('nt_%s:' % name.lower(), 1)[1].split(':', 1)[0]
            self.assertEqual([int(v, 16) for v in re.findall(r'\$([0-9A-F]{4})', block)][:96], zx[name])

    def test_output_is_converted_to_the_mockingboard_clock(self):
        """PPT3_OUT is the player's AYREGS converted like pt3_lib's: tones
        (12 bits), noise (5 bits) and envelope x 1181/2048, rounded --
        1.0227/1.7734 within 0.09 cent; R13 $FF unless a shape is set."""
        def mb(p):
            return (p * 1181 + 1024) >> 11
        data = module(2048)
        with tempfile.TemporaryDirectory() as t:
            frames = ppt3_sim.Grouik(t).run(data, 200)
        for r, out, raw in frames[1:]:
            for c in range(3):
                p = raw[2 * c] | (raw[2 * c + 1] & 15) << 8
                self.assertEqual(out[2 * c] | out[2 * c + 1] << 8, mb(p))
            self.assertEqual(out[6], mb(raw[6] & 31))
            self.assertEqual(out[7:11], raw[7:11])
            self.assertEqual(out[11] | out[12] << 8, mb(raw[11] | raw[12] << 8))
            self.assertEqual(out[13], raw[13] if raw[13] < 0x80 else 0xFF)

    def test_matches_sim65_on_both_cpus(self):
        data = module(2048)
        mine = self.engine.run(data, 120)
        with tempfile.TemporaryDirectory() as t:
            for cpu in ('6502', '65c02'):
                sim = ppt3_sim.Grouik(t, cpu).run(data, 120)
                self.assertEqual([(r, o) for r, o, _ in sim], mine, cpu)


if __name__ == '__main__':
    unittest.main()
