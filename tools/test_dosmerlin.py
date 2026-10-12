"""Existing Merlin decoder on immutable DOS drives, DSK and 2IMG inputs."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
import test_dos_stream as D
from test_dosint import HARNESS as BASE
from mini33_fixture import make_disk, offset

H = BASE.replace('#include "src/plugins/dosint.c"', '#include "src/plugins/merlin.c"')

def high(b):
    return bytes(c | 128 for c in b)

def disk(b):
    return make_disk([('TEXT', 0, b)])

class Merlin(unittest.TestCase):
    run_disk = D.Streams.run_disk

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='dosmerlin-', dir='/tmp')
        cls.p = Path(cls.tmp.name)
        cls.h = cls.p / 'h.c'
        cls.h.write_text(H)
        cls.exe = cls.p / 'host'
        subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-I', str(D.ROOT),
                        str(cls.h), '-o', str(cls.exe)], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_columns_quotes_comments_and_stale_sizes(self):
        b = high(b'LABEL LDA #$20 ;note\r ASC "A B" ;quoted space\r*Comment\r')
        expected = '\nLABEL    LDA   #$20       ;note\n         ASC   "A B"      ;quoted space\n*Comment'
        for image in (0, 1, 2):
            for size in (0, 1, 0xffffff):
                out, _, _ = self.run_disk(disk(b), image=image, size=size)
                self.assertTrue(out.decode().startswith(expected), out)

    def test_terminator_sector_boundary_and_full_allocation_errors(self):
        # First NUL terminates DOS text, including stale trailing sector bytes.
        b = high(b'*' + b'X'*254 + b'\r') + b'\0' + bytes(range(256))*2
        for image in (0, 1, 2):
            out, counts, _ = self.run_disk(disk(b), image=image)
            self.assertNotIn(b'?', out)
            for fault in list(range(1, counts[1]+1)) + ([1001,1002,1003,1004] if image else []):
                out, _, _ = self.run_disk(disk(b), image=image, fault=fault, good=False)
                # Validation errors precede all text; display-pass faults are reported.
                if fault <= counts[1]//2 or fault in (1001,1002,1003,1004):
                    self.assertEqual(out, b'')
        # A completely filled final sector has no NUL and remains valid.
        self.run_disk(disk(high(b'*'+b'X'*254+b'\r')))

    def test_malformed_data_catalog_and_sector_aliases(self):
        for b in (b'ordinary text\r', high(b' LDA #0\r')+b'\x01', b'\xff'):
            self.run_disk(disk(b), good=False)
        raw = disk(high(b'*OK\r')*100)
        bad = bytearray(raw);bad[offset(17,15)+14] ^= 1
        self.run_disk(bad, key=783, good=False)
        bad = bytearray(raw);p=offset(3,15);bad[p+14:p+16]=bad[p+12:p+14]
        self.run_disk(bad, good=False)
        self.run_disk(raw, typ=6, good=False)

    def test_paging_cancellation_closes_source(self):
        out, counts, _ = self.run_disk(disk(high(b'*LINE\r')*80), image=1, keys='E')
        self.assertEqual(out.count(b'*LINE'), 21)
        self.assertEqual(counts[2:4], [2,2])

    def test_real_merlin_sources_when_available(self):
        from legacy_corpus import dos_files
        p=Path.home()/'.cache/a2fc/asimov_corpus/raw/images/programming/assembler/merlin/MERLIN-8_DOS33.dsk'
        if not p.exists():self.skipTest('local Merlin corpus unavailable')
        count=0
        for name, typ, aux, b in dos_files(p.read_bytes()):
            if typ!=4:continue
            with self.subTest(name=name):
                out, _, _=self.run_disk(disk(b), image=1, keys='N'*1000)
                self.assertTrue(out);count+=1
        self.assertGreater(count,0)

    def test_cc65_both_cpus(self):
        if not shutil.which('cl65') or not shutil.which('sim65'):self.skipTest('cc65 unavailable')
        root=Path(subprocess.check_output(['cl65','--print-target-path'],text=True).strip()).parent
        for cpu,target in (('6502','sim6502'),('65c02','sim65c02')):
            cfg=self.p/(target+'.cfg')
            cfg.write_text((root/'cfg'/(target+'.cfg')).read_text().replace('\n    CODE:', '\n    OVLHDR: load = MAIN, type = ro;\n    CODE:',1))
            exe=self.p/target
            subprocess.run(['cl65','-t',target,'--cpu',cpu,'-Oirs','-Cl','-C',str(cfg),'-I',str(D.ROOT),'-o',str(exe),str(self.h)],check=True,capture_output=True)
            for image in (0,1,2):
                raw=disk(high(b'LABEL LDA #$20 ;note\r')+b'\0'+b'old'*100)
                expected, counts, _=self.run_disk(raw,image=image)
                actual, _, _=self.run_disk(raw,image=image,exe=exe)
                self.assertEqual(actual,expected)
                for fault in (1, counts[1], *([1002,1003,1004] if image else [])):
                    self.run_disk(raw,image=image,exe=exe,fault=fault,good=False)

if __name__=='__main__':unittest.main()
