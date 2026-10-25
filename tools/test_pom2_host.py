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
from pom2 import Pom2


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
            with patch('pom2.subprocess.Popen'), patch('pom2.time.time', side_effect=[0, 31]), \
                    patch.object(host, 'stop') as stop:
                with self.assertRaisesRegex(RuntimeError, 'ne repond pas'):
                    host.start()
            stop.assert_called_once()

    def test_shutdown_failure_preserves_an_existing_assertion(self):
        host = self.host(1)
        host.__exit__(AssertionError, AssertionError('bytes differ'), None)


POM = Path(os.environ.get('POM2_ROOT', Path.home() / 'src/pom2'))


@unittest.skipUnless(sys.platform == 'darwin' and (POM / 'build/libpom2_core.a').exists(),
                     'needs the native macOS POM2 library')
class NativeHost(unittest.TestCase):
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
