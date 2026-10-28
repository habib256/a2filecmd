"""POM2 hardware setup and persistence failures must reach the bench caller."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'bench'))
from pom2 import Pom2, Session, Timeout


class Lifecycle(unittest.TestCase):
    def host(self, code=None):
        host = Pom2('/tmp/disposable.hdv')
        host.proc = Mock(pid=12345)
        host.proc.poll.return_value = code
        host.proc.wait.return_value = 0 if code is None else code
        return host

    @patch('pom2.os.killpg')
    def test_clean_shutdown_signals_only_the_owned_process(self, kill):
        host = self.host()
        with patch('pom2.subprocess.call') as external:
            host.stop()
        kill.assert_called_once_with(12345, signal.SIGTERM)
        external.assert_not_called()
        self.assertIsNone(host.proc)

    @patch('pom2.os.killpg')
    def test_flush_failure_is_not_a_successful_bench(self, kill):
        host = self.host(1)
        with self.assertRaisesRegex(RuntimeError, 'sauvegarde'):
            host.stop()
        kill.assert_not_called()
        self.assertIsNone(host.proc)

    @patch('pom2.os.killpg')
    def test_forced_exit_is_a_failure_even_if_wait_returns_zero(self, kill):
        host = self.host()
        host.proc.wait.side_effect = [subprocess.TimeoutExpired('host', 5), 0]
        with self.assertRaisesRegex(RuntimeError, 'sauvegarde'):
            host.stop()
        self.assertEqual(kill.call_args_list[1].args, (12345, signal.SIGKILL))

    @patch('pom2.os.killpg', side_effect=ProcessLookupError)
    def test_exit_between_poll_and_signal_is_reaped(self, kill):
        host = self.host()
        proc = host.proc
        host.stop()
        proc.wait.assert_called_once_with(timeout=5)

    def test_startup_failure_is_immediate_and_closes_the_log(self):
        with tempfile.TemporaryDirectory() as directory:
            host = Pom2(Path(directory) / 'disk.hdv')
            proc = Mock(returncode=3)
            proc.poll.return_value = 3
            with patch('pom2.subprocess.Popen', return_value=proc) as spawn, \
                    patch.object(host, 'rq') as request:
                with self.assertRaisesRegex(RuntimeError, 'code 3'):
                    host.start()
            self.assertTrue(spawn.call_args.kwargs['stdout'].closed)
            request.assert_not_called()
            self.assertIsNone(host.proc)

    def test_startup_timeout_cleans_up_without_entering_context(self):
        with tempfile.TemporaryDirectory() as directory:
            host = Pom2(Path(directory) / 'disk.hdv')
            with patch('pom2.subprocess.Popen'), patch('pom2.time.monotonic', side_effect=[0, 31]), \
                    patch.object(host, 'stop') as stop:
                with self.assertRaisesRegex(RuntimeError, 'ne repond pas'):
                    host.start()
            stop.assert_called_once()

    def test_shutdown_failure_preserves_an_existing_assertion(self):
        host = self.host(1)
        host.__exit__(AssertionError, AssertionError('bytes differ'), None)


class ActiveDeadlines(unittest.TestCase):
    def test_wall_clock_jump_during_suspend_does_not_expire_ui_wait(self):
        wall, active, calls = [0], [0], [0]
        session = Session(Mock(), sym={})
        def ready():
            calls[0] += 1
            if calls[0] == 1:
                wall[0] += 3600  # The host slept; the emulator did too.
                return False
            active[0] += 0.1
            return True
        with patch('pom2.time.time', side_effect=lambda: wall[0]), \
                patch('pom2.time.monotonic', side_effect=lambda: active[0]), \
                patch('pom2.time.sleep'):
            session.wait(ready, 'resumed emulator', 1)
        self.assertEqual(calls[0], 2)

    def test_active_deadline_still_rejects_a_stalled_emulator(self):
        clock = [0]
        session = Session(Mock(), sym={})
        session.p.screen.return_value = ['stalled']
        def stalled():
            clock[0] += 0.5
            return False
        with patch('pom2.time.monotonic', side_effect=lambda: clock[0]), \
                patch('pom2.time.sleep'), patch('builtins.print'):
            with self.assertRaisesRegex(Timeout, 'stalled emulator'):
                session.wait(stalled, 'stalled emulator', 1)
        self.assertEqual(clock[0], 1)


POM = Path(os.environ.get('POM2_ROOT', Path.home() / 'src/pom2'))


@unittest.skipUnless(sys.platform == 'darwin' and (POM / 'build/libpom2_core.a').exists(),
                     'needs the native macOS POM2 library')
class NativeHost(unittest.TestCase):
    def test_production_ident_fixed_sample_after_suffix_calls(self):
        # Export private labels without changing a byte of the shipped stage.
        # A sim65 rebuild uses a different sample address and missed this bug.
        import re
        import ctypes
        import struct
        from corpus_census import C_SOURCE
        from test_merlin_ident import MerlinIdentification
        with tempfile.TemporaryDirectory(prefix='native-ident-') as directory:
            tmp = Path(directory)
            exe = tmp / 'probe'
            command = ['c++', '-std=c++17', '-O2']
            command += ['-I' + str(POM / sub) for sub in ('src', 'include', 'build/generated', 'imgui')]
            command += [str(ROOT / 'tools/fixtures/ident_formats_probe.cpp'), str(POM / 'build/libpom2_core.a'), '-framework', 'CoreAudio', '-framework', 'AudioToolbox', '-framework', 'AudioUnit', '-framework', 'CoreFoundation', '-o', str(exe)]
            subprocess.run(command, check=True, capture_output=True)
            # Use all identification fixtures, then compare this stage alone
            # against the real C classifier at the host's ordinary address.
            fixture_class = MerlinIdentification
            fixture_class.setUpClass()
            fixture = fixture_class()
            records = []
            def collect(data, expected=None, typ=4, size=1, arg=13, bad=0, exe=None, name='SOURCE', aux=0):
                if not bad:
                    records.append((bytes(data), typ, name, aux))
            fixture.check = collect
            try:
                for method in ('cases', 'visicalc_cases', 'originals', 'printshop_cases', 'movie_cases', 'pcs_cases', 'dpc_cases', 'multiscr_cases', 'mouse_bin_cases', 'multiplan_bin_cases', 'lisa_bin_cases', 'sc_bin_cases', 'arlequin_bin_cases', 'macpaint_cases', 'open_metadata_cases', 'basint_cases', 'lisa4_cases'):
                    getattr(fixture, method)()
            finally:
                fixture_class.tearDownClass()
            # Probe every type as well: F8 Arlequin skips the BIN path that
            # happened to initialize ptr1 in the old optimized stage.
            for prefix in (b'\x09\x51gs', b'\x09\x51xs', b'>L40:1140\r', b'>BJ90:1\r'):
                for typ in range(256):
                    for filename in ('WINDOW', 'SHEET.TXT'):
                        records.append((prefix, typ, filename, 0))
            records.append((b'U' * (65536 + 8192), 6, 'LARGE', 0))
            # The host's unsigned int is 32 bits; match the target's 16-bit
            # words when the classifier decomposes a 32-bit physical EOF.
            detector = (ROOT / 'src/plugins/ident.c').read_text()
            declaration = 'static union { unsigned long l; unsigned int w[2]; } sz;'
            self.assertEqual(detector.count(declaration), 1)
            detector = detector.replace(declaration, 'static union { uint32_t l; uint16_t w[2]; } sz;')
            reference = '#include <stdint.h>\n' + C_SOURCE.replace('#include "src/plugins/ident.c"', detector)
            wrapper = reference + r'''
const char* extra_for_probe(const char* name,int typ,int aux,const unsigned char* bytes,unsigned long len,int dos){
 memset(&ce,0,sizeof ce);strncpy(ce.name,name,NAME_LEN-1);ce.type=typ;ce.aux=aux;ce.size=len;
 actual=ce;e=&actual;b=sample;sz.l=len;n=len<512?len:512;id_dos=dos;reader=NULL;
 memset(sample,0,sizeof sample);memcpy(sample,bytes,n);extra();return reader?reader:"";
}
'''
            src = tmp / 'reference.c'
            src.write_text(wrapper)
            lib = tmp / 'reference.so'
            subprocess.run(['cc', '-std=c99', '-shared', '-fPIC', '-I', str(ROOT), '-I', str(ROOT / 'src/plugins'), str(src), '-o', str(lib)], check=True, capture_output=True)
            classify = ctypes.CDLL(str(lib)).extra_for_probe
            classify.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int]
            classify.restype = ctypes.c_char_p
            cases = tmp / 'cases.bin'
            packed = bytearray()
            seen = set()
            for data, typ, filename, aux in records:
                name = filename.encode()[:16]
                for dos in (0, 1):
                    identity = (data, typ, name, aux, dos)
                    if identity in seen:
                        continue
                    seen.add(identity)
                    expected = classify(name, typ, aux, data, len(data), dos)
                    self.assertLess(len(expected), 16)
                    if filename == 'LARGE':
                        self.assertNotEqual(expected, b'IMAGE')
                    packed += struct.pack('<17sBHIHB16s512s', name, typ, aux, len(data), min(len(data), 512), dos, expected, data[:512])
            cases.write_bytes(packed)
            self.assertGreater(len(seen), 500)
            names = ('_actual', '_n', '_sz', '_id_dos', '_reader', '_extra')
            for arch, build, target in (('enh', 'build', 'apple2enh'), ('6502', 'build-6502', 'apple2')):
                subprocess.run(['make', 'ARCH=' + arch, build + '/idformats.PLG'], cwd=ROOT, check=True, capture_output=True)
                source = tmp / (arch + '.s')
                source.write_text((ROOT / build / 'idformats.s').read_text() + '\n.export ' + ','.join(names) + '\n')
                obj = tmp / (arch + '.o')
                subprocess.run(['ca65', '-t', target, str(source), '-o', str(obj)], check=True, capture_output=True)
                library = subprocess.run(['make', '-s', '-f', 'Makefile', '-f', '-', 'ARCH=' + arch, 'qualification-lib'], input='qualification-lib:\n\t@echo $(CC65LIB)\n', cwd=ROOT, text=True, capture_output=True, check=True).stdout.strip()
                binary, labels = tmp / (arch + '.bin'), tmp / (arch + '.lbl')
                subprocess.run(['ld65', '-C', str(ROOT / 'sdk/ident.cfg'), '-D', '__OVLSIZE__=0x2500', '-Ln', str(labels), '-o', str(binary), str(obj), str(ROOT / build / 'idformats_svc.o'), library], check=True, capture_output=True)
                subprocess.run([sys.executable, str(ROOT / 'tools/seal_mcs_stage.py'), str(binary), str(labels), '0x4000', '1'], check=True, capture_output=True)
                self.assertEqual(binary.read_bytes(), (ROOT / build / 'idformats.PLG').read_bytes())
                symbols = {m[2]: m[1] for m in re.finditer(r'al ([0-9A-Fa-f]{6}) \.([^\s]+)', labels.read_text())}
                result = subprocess.run([str(exe), str(binary), *[symbols[n] for n in names], '1' if arch == 'enh' else '0', str(cases)], capture_output=True, text=True, timeout=120)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn(str(len(seen)) + ' classification cases, 0 errors', result.stdout)
                print(arch + ': ' + result.stdout.strip())

    def test_disk_protection_sensor_with_stopped_and_running_motor(self):
        # Run the actual assembly against the sequencer, never flat I/O RAM.
        with tempfile.TemporaryDirectory(prefix='dos-sense-') as directory:
            tmp = Path(directory)
            disk = tmp / 'disposable.dsk'
            original = bytes((i * 37 + 11) & 255 for i in range(143360))
            disk.write_bytes(original)
            (tmp / 'entry.s').write_text('.segment "CODE"\n lda #$E0\n jsr _dw_protected\n sta $0200\n jmp $FFF0\n.include "dos33_sense.inc"\n')
            (tmp / 'zp.s').write_text('.exportzp ptr1\nptr1=$06\n')
            (tmp / 'probe.cfg').write_text('MEMORY { RAM: start=$0800, size=$1000, file=%O; }\nSEGMENTS { CODE: load=RAM,type=ro; }\n')
            for name in ('entry', 'zp'):
                subprocess.run(['ca65', '-I', str(ROOT / 'src/plugins'), str(tmp / (name + '.s')), '-o', str(tmp / (name + '.o'))], check=True, capture_output=True)
            binary = tmp / 'probe.bin'
            subprocess.run(['ld65', '-C', str(tmp / 'probe.cfg'), str(tmp / 'entry.o'), str(tmp / 'zp.o'), '-o', str(binary)], check=True, capture_output=True)
            exe = tmp / 'probe'
            command = ['c++', '-std=c++17', '-O2']
            command += ['-I' + str(POM / sub) for sub in ('src', 'include', 'build/generated', 'imgui')]
            source = ROOT / 'tools/fixtures/dos33_sense_probe.cpp'
            command += ['-DPOM2_ROOT="' + str(POM) + '"']
            command += [str(source), str(POM / 'build/libpom2_core.a'), '-framework', 'CoreAudio', '-framework', 'AudioToolbox', '-framework', 'AudioUnit', '-framework', 'CoreFoundation', '-o', str(exe)]
            subprocess.run(command, check=True, capture_output=True)
            result = subprocess.run([str(exe), str(binary), str(disk)], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(len([line for line in result.stdout.splitlines() if line.startswith('slot=')]), 48)
            self.assertEqual(disk.read_bytes(), original)

    def test_actual_host_hardware_and_failed_flushes(self):
        # Instrument the real host at its boot and shutdown boundaries. No
        # listener, worker or guest runs; every medium is a disposable file.
        source = (ROOT / 'bench/pom2_playtest/pom2_playtest.cpp').read_text()
        source = '#include <cstdlib>\n' + source
        boot = 'if (!ctrl.bootFromSlot(bootSlot))'
        self.assertEqual(source.count(boot), 1)
        source = source.replace(boot, '''
        if (!floppyCard || floppyCard->iwmHost() != iic ||
            floppyCard->getSlot() != bootSlot) return 80;
        if (false)''')
        # Drop only the run loop and server startup, leaving the actual
        # persistence/return-code code intact; inject failed device saves.
        start = source.index('        ctrl.setCyclesPerFrame(speed);')
        end = source.index('        bool saved = true;', start)
        source = source[:start] + source[end:]
        for call, flag in [('floppyCard->flushPendingWrites()', 'F'),
                           ('diskCard->flushBay(0, err)', 'H'),
                           ('diskCard->flushBay(1, err)', 'D'),
                           ('spUnit->saveDirty()', 'S')]:
            source = source.replace(call, '(std::getenv("A2FC_FAIL_%s") ? false : %s)' % (flag, call))
        with tempfile.TemporaryDirectory(prefix='pom2-host-test-') as directory:
            tmp = Path(directory)
            src = tmp / 'host.cpp'
            src.write_text(source)
            disk = tmp / 'disk.po'
            original = bytes(143360)
            disk.write_bytes(original)
            for slot in (6, 5):
                exe = tmp / ('host%d' % slot)
                built = subprocess.run([sys.executable, str(ROOT / 'bench/build_dos_host.py'),
                    '--pom2', str(POM), '--source', str(src), '--slot', str(slot),
                    '--output', str(exe)], capture_output=True, text=True)
                self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
                for preset in (('iie', 'iic', 'iie_unenh') if slot == 6 else ('iie',)):
                    args = [str(exe), '--preset', preset, '--disk', str(disk),
                            '--boot', str(slot), str(disk)]
                    for failure in ('', 'F', 'S') if preset == 'iic' else ('', 'F', 'H', 'D'):
                        with self.subTest(slot=slot, preset=preset, failure=failure):
                            env = dict(os.environ, POM2_MEDIA_WRITE_DEFAULT='protected')
                            for key in list(env):
                                if key.startswith('A2FC_FAIL_'):
                                    del env[key]
                            if failure:
                                env['A2FC_FAIL_' + failure] = '1'
                            command = args + (['--hd2', str(disk)] if failure == 'D' else [])
                            result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=15)
                            self.assertEqual(result.returncode, 1 if failure else 0, result.stdout + result.stderr)
                            self.assertEqual(disk.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
