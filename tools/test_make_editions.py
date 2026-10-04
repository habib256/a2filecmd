"""`make disk` builds both editions when ARCH is not given, and
`make BOTH_EDITIONS=1 disk` must do the same once: given on the command line
the variable reached the sub-makes through MAKEFLAGS, and each one called
itself again without end. make -n shows the recursion without building."""
import os
import signal
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def plan(*args):
    # make -n still runs the recursive $(MAKE) lines: a regression would
    # recurse without end, so the whole process group goes on a timeout.
    proc = subprocess.Popen(['make', '-n', *args], cwd=ROOT, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True, start_new_session=True)
    try:
        out, _ = proc.communicate(timeout=60)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
        raise AssertionError('make -n %s did not end: the sub-makes recurse' % ' '.join(args))
    return proc.returncode, [l for l in out.splitlines() if ' disk' in l and 'ARCH=' in l]


class Editions(unittest.TestCase):
    def test_both_editions_once(self):
        for args in ((), ('BOTH_EDITIONS=1', 'disk'), ('disk',)):
            with self.subTest(args=args):
                rc, calls = plan(*args) if args else plan('disk')
                self.assertEqual(rc, 0)
                self.assertEqual([c.split()[1:] for c in calls],
                                 [['ARCH=6502', 'BOTH_EDITIONS=', 'disk'], ['ARCH=enh', 'BOTH_EDITIONS=', 'disk']])

    def test_one_edition_does_not_recurse(self):
        for arch in ('6502', 'enh'):
            with self.subTest(arch=arch):
                rc, calls = plan('ARCH=' + arch, 'BOTH_EDITIONS=', 'disk')
                self.assertEqual(rc, 0)
                self.assertEqual(calls, [])


if __name__ == '__main__':
    unittest.main()
